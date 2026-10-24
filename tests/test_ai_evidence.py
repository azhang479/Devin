from datetime import date
from pathlib import Path

from appeals.ai_evidence import match_criteria_ai
from appeals.carc import load_carc_table
from appeals.models import Adjustment, Denial, ServiceLine
from appeals.rules import load_rules
from appeals.triage import triage

ROOT = Path(__file__).resolve().parents[1]
PAYERS = load_rules(ROOT / "rules" / "payers")
CARC = load_carc_table(ROOT / "data" / "carc_codes.yaml")
POLICY = PAYERS["acme"].policies[0]
TODAY = date(2026, 10, 24)


class FakeClient:
    model = "fake"

    def __init__(self, response):
        self.response = response

    def generate_json(self, system, user, schema):
        return self.response

    def generate_text(self, system, user):
        raise AssertionError("Unexpected text request")


def test_verified_quotes_are_taken_from_the_original_note():
    note = "Completed eight weeks of supervised PT without relief."
    result = match_criteria_ai(
        note,
        POLICY,
        FakeClient(
            {
                "criteria": [
                    {
                        "criterion_id": "conservative_therapy",
                        "met": True,
                        "quote": "EIGHT weeks of supervised PT",
                    }
                ]
            }
        ),
    )

    assert [item.criterion_id for item in result.matched] == ["conservative_therapy"]
    assert result.matched[0].snippet == "eight weeks of supervised PT"
    assert result.missing == ["neuro_deficit"]
    assert result.missing_details[0].description == "Progressive neurological deficit"
    assert result.meets_min
    assert result.method == "ai"


def test_fabricated_unknown_duplicate_omitted_and_unmet_criteria_are_handled():
    result = match_criteria_ai(
        "Completed six weeks of therapy.",
        POLICY,
        FakeClient(
            {
                "criteria": [
                    {"criterion_id": "unknown", "met": True, "quote": "made up text"},
                    {
                        "criterion_id": "conservative_therapy",
                        "met": True,
                        "quote": "six weeks of therapy",
                    },
                    {
                        "criterion_id": "conservative_therapy",
                        "met": True,
                        "quote": "fabricated quote",
                    },
                    {
                        "criterion_id": "neuro_deficit",
                        "met": False,
                        "quote": "",
                    },
                ]
            }
        ),
    )

    assert [item.criterion_id for item in result.matched] == ["conservative_therapy"]
    assert result.missing == ["neuro_deficit"]
    assert result.rejected_quotes == []
    assert result.meets_min


def test_fabricated_quote_is_missing_and_added_to_rejected_quotes():
    result = match_criteria_ai(
        "The patient is improving.",
        POLICY,
        FakeClient(
            {
                "criteria": [
                    {
                        "criterion_id": "conservative_therapy",
                        "met": True,
                        "quote": "completed ten weeks of PT",
                    }
                ]
            }
        ),
    )

    assert result.matched == []
    assert result.missing == ["conservative_therapy", "neuro_deficit"]
    assert result.rejected_quotes == ["completed ten weeks of PT"]
    assert not result.meets_min


def test_injected_ai_evidence_matcher_makes_ai_01_an_appeal():
    note = (
        "Lumbar radicular pain down the left leg. Completed a 2-month course of PT "
        "plus NSAIDs without relief. Exam shows a diminished left ankle reflex and "
        "decreased sensation over the L5 dermatome."
    )
    denial = Denial(
        claim_id="AI-01",
        billed=1500,
        paid=0,
        payer_id="acme",
        patient_name="Synthetic Patient",
        service_date=date(2026, 9, 15),
        remit_date=date(2026, 10, 1),
        lines=[ServiceLine(cpt="72148", charge=1500)],
        adjustments=[Adjustment(group="CO", carc="50", amount=1500)],
    )
    client = FakeClient(
        {
            "criteria": [
                {
                    "criterion_id": "conservative_therapy",
                    "met": True,
                    "quote": "2-month course of PT",
                },
                {
                    "criterion_id": "neuro_deficit",
                    "met": True,
                    "quote": "diminished left ankle reflex",
                },
            ]
        }
    )

    result = triage(
        denial,
        PAYERS["acme"],
        CARC,
        note_text=note,
        today=TODAY,
        evidence_matcher=lambda text, policy: match_criteria_ai(text, policy, client),
    )

    assert result.action == "appeal"
    assert result.evidence.method == "ai"
    assert len(result.evidence.matched) == 2
