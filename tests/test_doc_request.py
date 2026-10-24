from datetime import date
from pathlib import Path

from appeals.carc import load_carc_table
from appeals.doc_request import draft_doc_request
from appeals.llm.client import LLMError
from appeals.models import Adjustment, Denial, ServiceLine
from appeals.rules import load_rules
from appeals.triage import triage

ROOT = Path(__file__).resolve().parents[1]
PAYER = load_rules(ROOT / "rules" / "payers")["acme"]
CARC = load_carc_table(ROOT / "data" / "carc_codes.yaml")
POLICY = PAYER.policies[0]


class FakeClient:
    model = "fake"

    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error
        self.user = None

    def generate_json(self, system, user, schema):
        raise AssertionError("Unexpected JSON request")

    def generate_text(self, system, user):
        self.user = user
        if self.error:
            raise self.error
        return self.text


def _unsupported_case():
    denial = Denial(
        claim_id="DOC-REQUEST",
        billed=1000,
        paid=0,
        payer_id="acme",
        patient_name="Synthetic Patient",
        service_date=date(2026, 9, 15),
        remit_date=date(2026, 10, 1),
        lines=[ServiceLine(cpt="72148", charge=1000)],
        adjustments=[Adjustment(group="CO", carc="50", amount=1000)],
    )
    result = triage(
        denial,
        PAYER,
        CARC,
        note_text="Low back pain; no treatment is documented.",
        today=date(2026, 10, 24),
    )
    return denial, result


def test_template_request_lists_missing_criterion_descriptions():
    denial, result = _unsupported_case()

    text, method = draft_doc_request(denial, result, POLICY, None)

    assert method == "template"
    assert text is not None
    assert "- At least 6 weeks of failed conservative therapy" in text
    assert "- Progressive neurological deficit" in text


def test_ai_request_is_used_when_valid_and_falls_back_on_error():
    denial, result = _unsupported_case()
    client = FakeClient("Please document any clinically accurate conservative care.")
    assert draft_doc_request(denial, result, POLICY, client) == (
        "Please document any clinically accurate conservative care.",
        "ai",
    )
    assert "Already documented:\n- none" in client.user
    assert "At least 6 weeks of failed conservative therapy" in client.user

    fallback, method = draft_doc_request(
        denial,
        result,
        POLICY,
        FakeClient(error=LLMError("offline")),
    )
    assert method == "template"
    assert fallback is not None
    assert "Progressive neurological deficit" in fallback


def test_invalid_ai_request_uses_template_fallback():
    denial, result = _unsupported_case()

    text, method = draft_doc_request(
        denial,
        result,
        POLICY,
        FakeClient("x" * 1001),
    )

    assert method == "template"
    assert text is not None
    assert "At least 6 weeks of failed conservative therapy" in text


def test_not_applicable_returns_none():
    denial, result = _unsupported_case()
    appeal = result.model_copy(update={"action": "appeal"})

    assert draft_doc_request(denial, appeal, POLICY, None) == (None, "none")
