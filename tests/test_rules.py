from pathlib import Path

import pytest

from appeals.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]


def test_all_fictional_payer_rules_load():
    rules = load_rules(ROOT / "rules" / "payers")
    assert set(rules) == {"acme", "blueriver", "summit"}
    assert {rules[payer].appeal.deadline_days for payer in rules} == {60, 90, 180}
    for payer in rules.values():
        assert {code for policy in payer.policies for code in policy.cpt_codes} >= {
            "72148",
            "97110",
            "29881",
            "95810",
        }


def test_invalid_rule_schema_raises_clear_error(tmp_path: Path):
    (tmp_path / "bad.yaml").write_text("payer_id: missing-fields\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid payer rules in"):
        load_rules(tmp_path)
