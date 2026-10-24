from datetime import date
from pathlib import Path

import pytest

from appeals.carc import load_carc_table
from appeals.models import Adjustment, Denial, ServiceLine
from appeals.rules import load_rules
from appeals.triage import triage

ROOT = Path(__file__).resolve().parents[1]
PAYERS = load_rules(ROOT / "rules" / "payers")
CARC = load_carc_table(ROOT / "data" / "carc_codes.yaml")
TODAY = date(2026, 10, 24)


def make_denial(
    carc: str,
    group: str = "CO",
    cpt: str = "72148",
    modifiers: list[str] | None = None,
    remit_date: date = date(2026, 9, 20),
) -> Denial:
    return Denial(
        claim_id="TEST-1",
        billed=1000,
        paid=200,
        payer_id="acme",
        patient_name="Mira Alder",
        service_date=date(2026, 9, 1),
        remit_date=remit_date,
        lines=[ServiceLine(cpt=cpt, modifiers=modifiers or [], charge=1000)],
        adjustments=[Adjustment(group=group, carc=carc, amount=800)],
    )


@pytest.mark.parametrize(
    ("carc", "group", "kwargs", "expected"),
    [
        ("4", "CO", {}, "resubmit"),
        ("22", "CO", {}, "resubmit"),
        ("18", "CO", {}, "write_off"),
        ("45", "CO", {}, "write_off"),
        ("27", "CO", {}, "bill_patient"),
        ("1", "PR", {}, "bill_patient"),
        ("29", "CO", {"proof_of_timely_filing": True}, "appeal"),
        ("29", "CO", {}, "write_off"),
        (
            "50",
            "CO",
            {"note_text": "The patient completed six weeks of physical therapy."},
            "appeal",
        ),
        ("50", "CO", {"note_text": "Routine review; stable symptoms."}, "gather_documentation"),
        ("197", "CO", {"auth_number": "AUTH-1"}, "resubmit"),
        ("197", "CO", {"note_text": "Urgent emergency evaluation was required."}, "appeal"),
        ("197", "CO", {}, "write_off"),
        ("97", "CO", {}, "appeal"),
        ("97", "CO", {"cpt": "72148"}, "write_off"),
        ("999", "CO", {}, "gather_documentation"),
    ],
)
def test_action_branches(carc, group, kwargs, expected):
    kwargs = dict(kwargs)
    cpt = kwargs.pop("cpt", "72148")
    modifiers = ["59"] if carc == "97" and expected == "appeal" else []
    note = kwargs.pop("note_text", "")
    result = triage(
        make_denial(carc, group=group, cpt=cpt, modifiers=modifiers),
        PAYERS["acme"],
        CARC,
        note_text=note,
        today=TODAY,
        **kwargs,
    )
    assert result.action == expected


def test_largest_non_patient_adjustment_is_primary():
    denial = make_denial("50")
    denial.adjustments = [
        Adjustment(group="CO", carc="16", amount=200),
        Adjustment(group="CO", carc="50", amount=500),
        Adjustment(group="PR", carc="1", amount=900),
    ]
    result = triage(
        denial,
        PAYERS["acme"],
        CARC,
        note_text="six weeks of physical therapy",
        today=TODAY,
    )
    assert result.carc == "50"
    assert result.category == "medical_necessity"


def test_all_patient_adjustments_select_largest_patient_adjustment():
    denial = make_denial("1", group="PR")
    denial.adjustments = [
        Adjustment(group="PR", carc="1", amount=50),
        Adjustment(group="PR", carc="2", amount=80),
    ]
    assert triage(denial, PAYERS["acme"], CARC, today=TODAY).carc == "2"


def test_prior_auth_number_precedes_emergency_exception():
    result = triage(
        make_denial("197"),
        PAYERS["acme"],
        CARC,
        note_text="Emergency evaluation.",
        auth_number="AUTH-1",
        today=TODAY,
    )
    assert result.action == "resubmit"


def test_deadline_override_and_priority_urgency_math():
    result = triage(
        make_denial(
            "50",
            remit_date=date(2026, 1, 1),
        ),
        PAYERS["acme"],
        CARC,
        note_text="six weeks of physical therapy",
        today=TODAY,
    )
    assert result.action == "write_off"
    assert result.reason == "appeal deadline passed"

    imminent = triage(
        make_denial("4", remit_date=date(2026, 5, 14)),
        PAYERS["acme"],
        CARC,
        today=TODAY,
    )
    assert imminent.days_left == 17
    assert imminent.win_probability == 0.85
    assert imminent.amount_at_stake == 800
    assert imminent.priority == pytest.approx(800 * 0.85 * (1 + 13 / 30))


def test_medical_necessity_policy_and_evidence_scoring():
    denial = make_denial("50")
    result = triage(
        denial,
        PAYERS["acme"],
        CARC,
        note_text="After six weeks of physical therapy the patient has weakness.",
        today=TODAY,
    )
    assert result.action == "appeal"
    assert result.policy_id == "ACME-RAD-014"
    assert result.win_probability == pytest.approx(0.65)
    assert result.evidence.meets_min
    assert result.evidence.matched[0].snippet

    no_policy = triage(
        make_denial("50", cpt="99213"),
        PAYERS["acme"],
        CARC,
        note_text="six weeks of physical therapy",
        today=TODAY,
    )
    assert no_policy.action == "gather_documentation"
    assert no_policy.policy_id is None


def test_deadline_dates_and_resubmit_win_probability():
    result = triage(make_denial("4"), PAYERS["acme"], CARC, today=TODAY)
    assert result.deadline == date(2027, 3, 19)
    assert result.win_probability == 0.85
