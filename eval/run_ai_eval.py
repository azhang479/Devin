"""Compare local-LLM evidence matching with deterministic keyword matching."""

import argparse
import json
import os
import time
from datetime import date
from pathlib import Path

from appeals.ai_evidence import match_criteria_ai
from appeals.carc import load_carc_table
from appeals.llm.client import LLMError, OllamaClient
from appeals.models import Adjustment, Denial, ServiceLine
from appeals.rules import load_rules
from appeals.triage import triage

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 24)
AI_CASES = ROOT / "eval" / "ai_cases.json"
AI_REPORT_JSON = ROOT / "eval" / "ai_report.json"
AI_REPORT_MD = ROOT / "eval" / "ai_report.md"
NOTE = (
    "Cases were hand-authored to include paraphrases and negations; they are not a "
    "sample of real clinical notes."
)


def _criterion_metrics(results: list[tuple[set[str], set[str]]]) -> dict[str, float | int]:
    true_positive = sum(len(actual & expected) for actual, expected in results)
    false_positive = sum(len(actual - expected) for actual, expected in results)
    false_negative = sum(len(expected - actual) for actual, expected in results)
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
    }


def _accuracy(actions: list[tuple[str, str]]) -> dict[str, int | float]:
    correct = sum(actual == expected for actual, expected in actions)
    total = len(actions)
    return {
        "correct": correct,
        "total": total,
        "accuracy": correct / total if total else 0.0,
    }


def _load_report() -> dict:
    if AI_REPORT_JSON.exists():
        return json.loads(AI_REPORT_JSON.read_text(encoding="utf-8"))
    return {"note": NOTE, "keyword": {}, "models": {}}


def _write_markdown(report: dict) -> str:
    methods = [("Keyword", report["keyword"])] + [
        (model, values) for model, values in report["models"].items()
    ]
    lines = [
        "## AI evidence-matching evaluation",
        "",
        NOTE,
        "",
        "| Method | Action accuracy | TP | FP | FN | Precision | Recall | Rejected quotes | Mean seconds/case | Max seconds/case |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, values in methods:
        action = values["action"]
        criteria = values["criteria"]
        lines.append(
            f"| {method} | {action['correct']}/{action['total']} "
            f"({action['accuracy']:.1%}) | {criteria['true_positive']} | "
            f"{criteria['false_positive']} | {criteria['false_negative']} | "
            f"{criteria['precision']:.1%} | {criteria['recall']:.1%} | "
            f"{values.get('rejected_quotes', 0)} | "
            f"{values.get('mean_seconds_per_case', 0.0):.2f} | "
            f"{values.get('max_seconds_per_case', 0.0):.2f} |"
        )

    models = list(report["models"])
    lines.extend(
        [
            "",
            "| Case | Expected action | Keyword action | "
            + " | ".join(f"{model} AI action" for model in models)
            + " |",
            "|---|---|---|"
            + "---|"
            * len(models),
        ]
    )
    per_model = {
        model: {item["id"]: item for item in values["cases"]}
        for model, values in report["models"].items()
    }
    keyword_cases = {item["id"]: item for item in report["keyword"]["cases"]}
    for case_id, keyword_case in keyword_cases.items():
        actions = [
            per_model[model].get(case_id, {}).get("ai_action", "—") for model in models
        ]
        lines.append(
            f"| {case_id} | {keyword_case['expected_action']} | "
            f"{keyword_case['keyword_action']} | "
            + " | ".join(actions)
            + " |"
        )
    return "\n".join(lines) + "\n"


def run(model: str) -> dict:
    payers = load_rules(ROOT / "rules" / "payers")
    carc_table = load_carc_table(ROOT / "data" / "carc_codes.yaml")
    cases = json.loads(AI_CASES.read_text(encoding="utf-8"))["cases"]
    client = OllamaClient(
        model=model,
        host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        cache_dir=None,
    )

    keyword_cases = []
    ai_cases = []
    keyword_actions = []
    ai_actions = []
    keyword_criteria = []
    ai_criteria = []
    rejected_quotes = 0
    elapsed_seconds = []

    for case in cases:
        denial = Denial(
            claim_id=case["id"],
            billed=1500.00,
            paid=0.0,
            payer_id=case["payer_id"],
            patient_name="Synthetic Patient",
            service_date=date(2026, 9, 15),
            remit_date=date(2026, 10, 1),
            lines=[ServiceLine(cpt=case["cpt"], charge=1500.00)],
            adjustments=[Adjustment(group="CO", carc="50", amount=1500.00)],
        )
        payer = payers[case["payer_id"]]
        expected_action = case["expected_action"]
        expected_criteria = set(case["expected_met"])
        keyword_result = triage(
            denial,
            payer,
            carc_table,
            note_text=case["note"],
            today=TODAY,
        )
        keyword_action = keyword_result.action
        keyword_actions.append((keyword_action, expected_action))
        keyword_criteria.append(
            (
                {item.criterion_id for item in keyword_result.evidence.matched},
                expected_criteria,
            )
        )
        keyword_cases.append(
            {
                "id": case["id"],
                "expected_action": expected_action,
                "keyword_action": keyword_action,
            }
        )

        started = time.perf_counter()
        try:
            ai_result = triage(
                denial,
                payer,
                carc_table,
                note_text=case["note"],
                today=TODAY,
                evidence_matcher=lambda note, policy: match_criteria_ai(
                    note, policy, client
                ),
            )
            ai_action = ai_result.action
            actual_criteria = {item.criterion_id for item in ai_result.evidence.matched}
            rejected_quotes += len(ai_result.evidence.rejected_quotes)
            error = None
        except LLMError as exc:
            ai_action = "LLMError"
            actual_criteria = set()
            error = str(exc)
        elapsed_seconds.append(time.perf_counter() - started)
        ai_actions.append((ai_action, expected_action))
        ai_criteria.append((actual_criteria, expected_criteria))
        ai_cases.append(
            {
                "id": case["id"],
                "expected_action": expected_action,
                "ai_action": ai_action,
                "error": error,
            }
        )

    keyword_metrics = {
        "action": _accuracy(keyword_actions),
        "criteria": _criterion_metrics(keyword_criteria),
        "cases": keyword_cases,
    }
    ai_metrics = {
        "action": _accuracy(ai_actions),
        "criteria": _criterion_metrics(ai_criteria),
        "rejected_quotes": rejected_quotes,
        "mean_seconds_per_case": sum(elapsed_seconds) / len(elapsed_seconds),
        "max_seconds_per_case": max(elapsed_seconds, default=0.0),
        "cases": ai_cases,
    }
    report = _load_report()
    report["note"] = NOTE
    report["keyword"] = keyword_metrics
    report.setdefault("models", {})[model] = ai_metrics
    markdown = _write_markdown(report)
    AI_REPORT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    AI_REPORT_MD.write_text(markdown, encoding="utf-8")
    print(markdown, end="")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default=os.environ.get("APPEALS_LLM_MODEL", "qwen2.5:3b"),
    )
    args = parser.parse_args()
    run(args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
