from pathlib import Path

import pytest

from appeals.eob import EOBValidationError, extract_eob, extract_pdf_text
from appeals.parser import parse_835
from appeals.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]
PAYERS = load_rules(ROOT / "rules" / "payers")
PDF_PATH = ROOT / "data" / "synthetic" / "eobs" / "CASE-001.pdf"
REMIT_PATH = ROOT / "data" / "synthetic" / "cases" / "CASE-001.835"


class FakeClient:
    model = "fake"

    def __init__(self, response):
        self.response = response
        self.system = None
        self.user = None
        self.schema = None

    def generate_json(self, system, user, schema):
        self.system = system
        self.user = user
        self.schema = schema
        return self.response

    def generate_text(self, system, user):
        raise AssertionError("Unexpected text request")


def _ground_truth():
    return parse_835(REMIT_PATH.read_text(encoding="utf-8"))[0]


def test_generated_pdf_extracts_and_validates_against_fake_client():
    text = extract_pdf_text(PDF_PATH.read_bytes())
    denial = _ground_truth()
    client = FakeClient(denial.model_dump(mode="json"))

    extracted = extract_eob(text, PAYERS, client)

    assert extracted == denial
    assert client.schema["properties"]["payer_id"]["enum"] == list(PAYERS)
    assert "- acme: Acme Health Plan (synthetic)" in client.user
    assert "Explanation of Benefits" in text
    assert denial.claim_id in text


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("claim_id", "NOT-IN-EOB", "Claim number not found"),
        ("payer_id", "unknown", "Unknown payer_id"),
        ("adjustments", [{"group": "CO", "carc": "999", "amount": 100}], "CARC not found"),
    ],
)
def test_eob_semantic_validation_collects_errors(field, value, expected_error):
    payload = _ground_truth().model_dump(mode="json")
    payload[field] = value

    with pytest.raises(EOBValidationError) as exc_info:
        extract_eob(extract_pdf_text(PDF_PATH.read_bytes()), PAYERS, FakeClient(payload))

    assert any(expected_error in error for error in exc_info.value.errors)


def test_empty_dates_become_none_and_adjustment_groups_are_validated():
    payload = _ground_truth().model_dump(mode="json")
    payload["service_date"] = ""
    payload["remit_date"] = ""
    extracted = extract_eob(
        extract_pdf_text(PDF_PATH.read_bytes()),
        PAYERS,
        FakeClient(payload),
    )
    assert extracted.service_date is None
    assert extracted.remit_date is None

    payload["adjustments"][0]["group"] = "ZZ"
    with pytest.raises(EOBValidationError, match="Invalid adjustment group"):
        extract_eob(
            extract_pdf_text(PDF_PATH.read_bytes()),
            PAYERS,
            FakeClient(payload),
        )
