"""Compare triage output with the hand-authored synthetic scenario labels."""

import json
from datetime import date
from pathlib import Path

from appeals.carc import load_carc_table
from appeals.parser import parse_835
from appeals.rules import load_rules
from appeals.triage import triage

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 10, 24)


def main() -> int:
    payers = load_rules(ROOT / "rules" / "payers")
    carc_table = load_carc_table(ROOT / "data" / "carc_codes.yaml")
    by_scenario: dict[str, dict[str, int]] = {}
    total = category_correct = action_correct = 0
    total_at_stake = expected_recovery = 0.0

    for case_path in sorted((ROOT / "data" / "synthetic" / "cases").glob("*.json")):
        case = json.loads(case_path.read_text(encoding="utf-8"))
        remit_path = case_path.parent / case["remit_file"]
        denials = parse_835(remit_path.read_text(encoding="utf-8"))
        if len(denials) != 1:
            raise ValueError(f"{case['id']} should contain exactly one claim")
        result = triage(
            denials[0],
            payers[case["payer_id"]],
            carc_table,
            note_text=case["note"],
            auth_number=case.get("auth_number"),
            proof_of_timely_filing=case.get("proof_of_timely_filing", False),
            today=TODAY,
        )
        expected = case["expected"]
        category_ok = result.category == expected["category"]
        action_ok = result.action == expected["action"]
        total += 1
        category_correct += category_ok
        action_correct += action_ok
        scenario = by_scenario.setdefault(
            case["scenario"], {"cases": 0, "passed": 0, "failed": 0}
        )
        scenario["cases"] += 1
        if category_ok and action_ok:
            scenario["passed"] += 1
        else:
            scenario["failed"] += 1
        total_at_stake += result.amount_at_stake
        expected_recovery += result.amount_at_stake * result.win_probability

    category_accuracy = category_correct / total if total else 0.0
    action_accuracy = action_correct / total if total else 0.0
    lines = [
        "| Metric | Result |",
        "|---|---:|",
        f"| Cases | {total} |",
        f"| Category accuracy | {category_correct}/{total} ({category_accuracy:.1%}) |",
        f"| Action accuracy | {action_correct}/{total} ({action_accuracy:.1%}) |",
        f"| Total amount at stake | ${total_at_stake:,.2f} |",
        f"| Expected recovery | ${expected_recovery:,.2f} |",
        "",
        "| Scenario | Passed | Total | Result |",
        "|---|---:|---:|---|",
    ]
    for scenario_name, metrics in sorted(by_scenario.items()):
        outcome = "PASS" if metrics["failed"] == 0 else "FAIL"
        lines.append(
            f"| {scenario_name} | {metrics['passed']} | {metrics['cases']} | {outcome} |"
        )
    report_md = "\n".join(lines) + "\n"
    report_json = {
        "today": TODAY.isoformat(),
        "cases": total,
        "category_accuracy": category_accuracy,
        "action_accuracy": action_accuracy,
        "category_correct": category_correct,
        "action_correct": action_correct,
        "total_amount_at_stake": round(total_at_stake, 2),
        "expected_recovery": round(expected_recovery, 2),
        "scenarios": by_scenario,
    }
    (ROOT / "eval" / "report.json").write_text(
        json.dumps(report_json, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "eval" / "report.md").write_text(report_md, encoding="utf-8")
    print(report_md, end="")
    return 1 if action_accuracy < 0.9 else 0


if __name__ == "__main__":
    raise SystemExit(main())
