"""Evaluate structured EOB extraction against the paired synthetic 835 files."""

import argparse
import json
import os
import time
from datetime import date
from pathlib import Path

from appeals.carc import load_carc_table
from appeals.eob import EOBValidationError, extract_eob, extract_pdf_text
from appeals.llm.client import LLMError, OllamaClient
from appeals.parser import parse_835
from appeals.rules import load_rules
from appeals.triage import triage

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 24)
REPORT_JSON = ROOT / "eval" / "eob_report.json"
REPORT_MD = ROOT / "eval" / "eob_report.md"
FIELD_NAMES = (
    "claim_id",
    "payer_id",
    "patient_name",
    "service_date",
    "remit_date",
    "billed",
    "paid",
    "lines",
    "adjustments",
)


def _equivalent_fields(expected, actual) -> dict[str, bool]:
    return {
        "claim_id": expected.claim_id == actual.claim_id,
        "payer_id": expected.payer_id == actual.payer_id,
        "patient_name": expected.patient_name == actual.patient_name,
        "service_date": expected.service_date == actual.service_date,
        "remit_date": expected.remit_date == actual.remit_date,
        "billed": abs(expected.billed - actual.billed) <= 0.005,
        "paid": abs(expected.paid - actual.paid) <= 0.005,
        "lines": {
            (line.cpt, tuple(line.modifiers)) for line in expected.lines
        }
        == {(line.cpt, tuple(line.modifiers)) for line in actual.lines},
        "adjustments": sorted(
            (item.group, item.carc, round(item.amount, 2))
            for item in expected.adjustments
        )
        == sorted(
            (item.group, item.carc, round(item.amount, 2))
            for item in actual.adjustments
        ),
    }


def _load_report() -> dict:
    if REPORT_JSON.exists():
        return json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    return {"models": {}}


def run(model: str) -> dict:
    payers = load_rules(ROOT / "rules" / "payers")
    carc_table = load_carc_table(ROOT / "data" / "carc_codes.yaml")
    client = OllamaClient(
        model=model,
        host=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        cache_dir=None,
    )
    cases_dir = ROOT / "data" / "synthetic" / "cases"
    eobs_dir = ROOT / "data" / "synthetic" / "eobs"
    case_rows = []
    fields_correct = 0
    action_matches = 0
    elapsed_seconds = []

    for pdf_path in sorted(eobs_dir.glob("*.pdf")):
        case_id = pdf_path.stem
        case = json.loads((cases_dir / f"{case_id}.json").read_text(encoding="utf-8"))
        expected_denials = parse_835(
            (cases_dir / case["remit_file"]).read_text(encoding="utf-8")
        )
        if len(expected_denials) != 1:
            raise ValueError(f"{case_id} should contain exactly one claim")
        expected = expected_denials[0]
        payer = payers[case["payer_id"]]
        error = None
        started = time.perf_counter()
        try:
            text = extract_pdf_text(pdf_path.read_bytes())
            actual = extract_eob(text, payers, client)
            field_results = _equivalent_fields(expected, actual)
            expected_action = triage(
                expected,
                payer,
                carc_table,
                note_text=case["note"],
                auth_number=case.get("auth_number"),
                proof_of_timely_filing=case.get("proof_of_timely_filing", False),
                today=TODAY,
            ).action
            actual_action = triage(
                actual,
                payer,
                carc_table,
                note_text=case["note"],
                auth_number=case.get("auth_number"),
                proof_of_timely_filing=case.get("proof_of_timely_filing", False),
                today=TODAY,
            ).action
            action_matches += actual_action == expected_action
        except (EOBValidationError, LLMError, ValueError) as exc:
            field_results = dict.fromkeys(FIELD_NAMES, False)
            expected_action = triage(
                expected,
                payer,
                carc_table,
                note_text=case["note"],
                auth_number=case.get("auth_number"),
                proof_of_timely_filing=case.get("proof_of_timely_filing", False),
                today=TODAY,
            ).action
            actual_action = None
            error = str(exc)
        elapsed_seconds.append(time.perf_counter() - started)
        fields_correct += sum(field_results.values())
        case_rows.append(
            {
                "id": case_id,
                "fields_correct": sum(field_results.values()),
                "fields_total": len(FIELD_NAMES),
                "fully_correct": all(field_results.values()),
                "expected_action": expected_action,
                "actual_action": actual_action,
                "action_match": actual_action == expected_action,
                "error": error,
            }
        )

    total_fields = len(case_rows) * len(FIELD_NAMES)
    metrics = {
        "cases": len(case_rows),
        "fields_correct": fields_correct,
        "fields_total": total_fields,
        "cases_fully_correct": sum(row["fully_correct"] for row in case_rows),
        "action_matches": action_matches,
        "mean_seconds_per_case": (
            sum(elapsed_seconds) / len(elapsed_seconds) if elapsed_seconds else 0.0
        ),
        "per_case": case_rows,
    }
    report = _load_report()
    report.setdefault("models", {})[model] = metrics
    lines = [
        "## EOB PDF extraction evaluation",
        "",
        "| Model | Cases | Fields correct | Fully correct cases | Action matches | Mean seconds/case |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for model_name, result in report["models"].items():
        lines.append(
            f"| {model_name} | {result['cases']} | "
            f"{result['fields_correct']}/{result['fields_total']} | "
            f"{result['cases_fully_correct']}/{result['cases']} | "
            f"{result['action_matches']}/{result['cases']} | "
            f"{result['mean_seconds_per_case']:.2f} |"
        )
    lines.extend(
        [
            "",
            "| Model | Case | Fields correct | Expected action | Extracted action | Action match | Error |",
            "|---|---|---:|---|---|---|---|",
        ]
    )
    for model_name, result in report["models"].items():
        for row in result["per_case"]:
            lines.append(
                f"| {model_name} | {row['id']} | {row['fields_correct']}/"
                f"{row['fields_total']} | {row['expected_action']} | "
                f"{row['actual_action'] or '—'} | "
                f"{'yes' if row['action_match'] else 'no'} | "
                f"{row['error'] or '—'} |"
            )
    markdown = "\n".join(lines) + "\n"
    REPORT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    REPORT_MD.write_text(markdown, encoding="utf-8")
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
