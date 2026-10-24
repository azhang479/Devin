import json
from pathlib import Path

from appeals.parser import parse_835, parse_denials

ROOT = Path(__file__).resolve().parents[1]


def test_parse_multiple_claims_adjustments_modifiers_and_rarc():
    text = (ROOT / "tests" / "fixtures" / "sample.835").read_text(encoding="utf-8")
    denials = parse_835(text)

    assert len(denials) == 2
    first, second = denials
    assert first.claim_id == "CLM-1001"
    assert first.payer_id == "acme"
    assert first.patient_name == "MIRA ALDER"
    assert first.service_date.isoformat() == "2026-09-12"
    assert first.remit_date.isoformat() == "2026-10-10"
    assert first.lines[0].cpt == "72148"
    assert first.lines[0].modifiers == ["59"]
    assert first.lines[0].charge == 800
    assert [(item.carc, item.amount) for item in first.adjustments] == [
        ("50", 400),
        ("16", 300),
    ]
    assert first.rarc == ["N290"]
    assert second.adjustments[0].group == "PR"
    assert [item.carc for item in second.adjustments] == ["1", "2"]


def test_json_denial_input_accepts_aliases():
    result = parse_denials(
        json.dumps(
            {
                "claim_id": "JSON-1",
                "billed": 120,
                "paid": 0,
                "payer_id": "acme",
                "patient_name": "Mira Alder",
                "dos": "2026-09-01",
                "denial_date": "2026-10-01",
                "service_lines": [{"cpt": "72148", "modifiers": ["25"], "charge": 120}],
                "cas": [{"group": "CO", "carc": "50", "amount": 120}],
                "rarcs": ["N290"],
            }
        )
    )
    assert result[0].lines[0].modifiers == ["25"]
    assert result[0].adjustments[0].carc == "50"


def test_parse_six_cas_triplets_and_header_remit_date():
    text = (ROOT / "tests" / "fixtures" / "sample.835").read_text(encoding="utf-8")
    text = text.replace(
        "BPR*I*0*C*ACH*CTX*01*999999999*DA*123456789*999999999*999999999*"
        "01*999999999*DA*123456789*20261010~",
        "BPR*I*0*C*ACH*CTX*01*999999999*DA*123456789*999999999*999999999*"
        "01*999999999*DA*123456789*20261010~\nDTM*405*20261011~",
    )
    text = text.replace(
        "CAS*CO*50*400.00*1*16*300.00~",
        "CAS*CO*50*400.00*1*16*300.00*1*11*100.00*1*4*50.00*1*"
        "45*25.00*1*29*75.00*1~",
    )
    first = parse_835(text)[0]
    assert first.remit_date.isoformat() == "2026-10-11"
    assert [item.carc for item in first.adjustments] == ["50", "16", "11", "4", "45", "29"]
