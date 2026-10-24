from datetime import date
from pathlib import Path

from appeals.ai_letter import draft_argument
from appeals.carc import load_carc_table
from appeals.letter import TEMPLATE_DIR, _environment, render_letter
from appeals.llm.client import LLMError
from appeals.models import Adjustment, Denial, ServiceLine
from appeals.rules import load_rules
from appeals.triage import triage

ROOT = Path(__file__).resolve().parents[1]
PAYERS = load_rules(ROOT / "rules" / "payers")
CARC = load_carc_table(ROOT / "data" / "carc_codes.yaml")
PAYER = PAYERS["acme"]
POLICY = PAYER.policies[0]
NOTE = "The patient completed six weeks of physical therapy and reports weakness."


class FakeClient:
    model = "fake"

    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error
        self.calls = 0

    def generate_json(self, system, user, schema):
        raise AssertionError("Unexpected JSON request")

    def generate_text(self, system, user):
        self.calls += 1
        if self.error:
            raise self.error
        return self.text


def _appeal_context():
    denial = Denial(
        claim_id="LETTER-AI",
        billed=1500,
        paid=0,
        payer_id="acme",
        patient_name="Synthetic Patient",
        service_date=date(2026, 9, 15),
        remit_date=date(2026, 10, 1),
        lines=[ServiceLine(cpt="72148", charge=1500)],
        adjustments=[Adjustment(group="CO", carc="50", amount=1500)],
    )
    result = triage(
        denial,
        PAYER,
        CARC,
        note_text=NOTE,
        today=date(2026, 10, 24),
    )
    return denial, result


def test_argument_is_inserted_as_its_own_paragraph_and_no_argument_is_legacy_identical():
    denial, result = _appeal_context()
    argument = 'The record documents "six weeks of physical therapy" and "weakness".'
    letter = render_letter(denial, result, PAYER, POLICY, argument=argument)
    assert letter is not None
    letter_lines = letter.splitlines()
    argument_line = letter_lines.index(argument)
    assert letter_lines[argument_line - 1] == ""
    assert letter_lines[argument_line + 1] == ""
    assert letter.index("Please review the enclosed documentation") > letter.index(argument)

    source = (TEMPLATE_DIR / "appeal_letter.txt.j2").read_text(encoding="utf-8")
    conditional = "{% if argument %}\n\n{{ argument }}\n\n{% endif %}\n"
    assert conditional in source
    legacy_template = _environment.from_string(source.replace(conditional, "", 1))
    legacy_output = legacy_template.render(
        practice="Springfield Family Medicine",
        destination=PAYER.appeal.submit_to,
        denial=denial,
        triage=result,
        payer=PAYER,
        policy=POLICY,
        carc_description=CARC["50"]["description"],
    )
    assert render_letter(denial, result, PAYER, POLICY) == legacy_output


def test_draft_argument_accepts_only_verified_quotes_and_bounded_text():
    denial, result = _appeal_context()

    assert draft_argument(
        denial,
        result,
        PAYER,
        POLICY,
        NOTE,
        FakeClient('The note documents "six weeks of physical therapy" and "weakness".'),
    ) == 'The note documents "six weeks of physical therapy" and "weakness".'
    assert (
        draft_argument(
            denial,
            result,
            PAYER,
            POLICY,
            NOTE,
            FakeClient('The note documents "fabricated symptoms".'),
        )
        is None
    )
    assert draft_argument(
        denial,
        result,
        PAYER,
        POLICY,
        NOTE,
        FakeClient("A" * 1501),
    ) is None


def test_draft_argument_handles_llm_errors_and_skips_nonappeals():
    denial, result = _appeal_context()
    assert (
        draft_argument(
            denial,
            result,
            PAYER,
            POLICY,
            NOTE,
            FakeClient(error=LLMError("offline")),
        )
        is None
    )

    client = FakeClient("should not be requested")
    assert (
        draft_argument(
            denial,
            result.model_copy(update={"action": "write_off"}),
            PAYER,
            POLICY,
            NOTE,
            client,
        )
        is None
    )
    assert client.calls == 0
