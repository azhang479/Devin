from datetime import date
from pathlib import Path

from appeals.carc import load_carc_table
from appeals.letter import render_letter
from appeals.models import Adjustment, Denial, ServiceLine
from appeals.rules import load_rules
from appeals.triage import triage

ROOT = Path(__file__).resolve().parents[1]


def test_appeal_letter_renders_policy_and_evidence_and_nonappeal_is_none():
    payer = load_rules(ROOT / "rules" / "payers")["acme"]
    carc = load_carc_table(ROOT / "data" / "carc_codes.yaml")
    denial = Denial(
        claim_id="LETTER-1",
        billed=800,
        paid=100,
        payer_id="acme",
        patient_name="Mira Alder",
        service_date=date(2026, 9, 1),
        remit_date=date(2026, 9, 1),
        lines=[ServiceLine(cpt="72148", modifiers=[], charge=800)],
        adjustments=[Adjustment(group="CO", carc="50", amount=700)],
    )
    result = triage(
        denial,
        payer,
        carc,
        note_text="After six weeks of physical therapy the patient reports weakness.",
        today=date(2026, 10, 24),
    )
    letter = render_letter(denial, result, payer, payer.policies[0])
    assert letter is not None
    assert "ACME-RAD-014" in letter
    assert "6 weeks of failed conservative therapy" in letter
    assert "DRAFT — requires clinician/biller review before submission" in letter
    assert render_letter(
        denial,
        result.model_copy(update={"action": "write_off"}),
        payer,
        payer.policies[0],
    ) is None
