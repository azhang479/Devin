"""Generate deterministic, fictional claim-denial fixtures."""

import json
import random
from datetime import date, timedelta
from pathlib import Path

from appeals.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "data" / "synthetic" / "cases"
TODAY = date(2026, 10, 24)
PAYER_IDS = ["acme", "blueriver", "summit"]
NAMES = [
    ("Mira", "Alder"),
    ("Jonah", "Bexley"),
    ("Tessa", "Caldwell"),
    ("Ronan", "Dale"),
    ("Elise", "Easton"),
    ("Caleb", "Farrow"),
    ("Nina", "Gardner"),
    ("Owen", "Hartwell"),
    ("Lena", "Iverson"),
    ("Miles", "Jensen"),
    ("Ada", "Kendall"),
    ("Theo", "Larkin"),
    ("Mara", "Merritt"),
    ("Evan", "North"),
    ("Cora", "Oakley"),
    ("Levi", "Parker"),
    ("Iris", "Quincy"),
    ("Silas", "Rowan"),
    ("Vera", "Sutton"),
    ("Noah", "Thatcher"),
    ("Esme", "Underwood"),
    ("Felix", "Vale"),
    ("Willa", "West"),
    ("Arlo", "York"),
    ("Della", "Zimmer"),
    ("Remy", "Ashford"),
    ("Lila", "Briar"),
    ("Gavin", "Crosby"),
    ("Faye", "Drake"),
    ("Hugo", "Ellery"),
]
SCENARIOS = [
    ("mednec_supported", "50", ["72148", "29881", "95810"], "medical_necessity", "appeal", 6),
    (
        "mednec_unsupported",
        "50",
        ["72148", "29881", "95810"],
        "medical_necessity",
        "gather_documentation",
        3,
    ),
    (
        "mednec_deadline_passed",
        "50",
        ["72148", "29881", "95810"],
        "medical_necessity",
        "write_off",
        2,
    ),
    ("frequency_supported", "151", ["97110"], "medical_necessity", "appeal", 2),
    ("prior_auth_has_number", "197", ["72148", "97110", "29881", "95810"], "prior_auth", "resubmit", 2),
    ("prior_auth_emergency", "197", ["72148", "97110", "29881", "95810"], "prior_auth", "appeal", 2),
    ("prior_auth_none", "197", ["72148", "97110", "29881", "95810"], "prior_auth", "write_off", 1),
    ("modifier_error", "4", ["99213"], "coding_error", "resubmit", 2),
    ("missing_info", "16", ["72148", "97110", "29881", "95810"], "coding_error", "resubmit", 2),
    ("bundling_mod59", "97", ["97110"], "bundling", "appeal", 2),
    ("duplicate", "18", ["72148", "97110", "29881", "95810"], "duplicate", "write_off", 1),
    ("timely_with_proof", "29", ["72148", "97110", "29881", "95810"], "timely_filing", "appeal", 1),
    ("timely_no_proof", "29", ["72148", "97110", "29881", "95810"], "timely_filing", "write_off", 1),
    ("cob", "22", ["72148", "97110", "29881", "95810"], "cob", "resubmit", 1),
    ("eligibility", "27", ["72148", "97110", "29881", "95810"], "eligibility", "bill_patient", 1),
    ("deductible", "1", ["72148", "97110", "29881", "95810"], "patient_responsibility", "bill_patient", 1),
]


def note_for(scenario: str, cpt: str, payer_id: str, payers) -> str:
    if scenario == "prior_auth_emergency":
        return (
            "The patient presented for an urgent evaluation after a sudden change in symptoms. "
            "Care was provided during an emergent episode in the emergency department. "
            "The clinician stabilized the patient and documented the need for immediate treatment."
        )
    if scenario in {"mednec_supported", "mednec_deadline_passed", "frequency_supported"}:
        policy = next(policy for policy in payers[payer_id].policies if cpt in policy.cpt_codes)
        terms = [
            criterion.any_of[0] for criterion in policy.criteria[: policy.min_criteria]
        ]
        complaint = {
            "72148": "low back pain radiating into the leg",
            "97110": "reduced strength and difficulty completing daily movement",
            "29881": "persistent pain and catching in the left knee",
            "95810": "snoring with daytime sleepiness",
        }.get(cpt, "ongoing symptoms")
        documentation = " and ".join(terms)
        return (
            f"The patient reports {complaint} affecting usual activities. "
            f"Today's clinical note documents {documentation} and persistent symptoms despite care. "
            "The clinician recommends the requested service to guide the next stage of treatment."
        )
    if scenario == "bundling_mod59":
        return (
            "The patient received a separate therapeutic exercise service during this visit. "
            "The interventions addressed distinct functional goals from the other billed service. "
            "The clinician documented the separate work and response."
        )
    if scenario == "prior_auth_has_number":
        return (
            "The patient attended a planned visit for ongoing symptoms. "
            "The clinician provided the service and reviewed the treatment plan. "
            "Authorization documentation is available for this episode."
        )
    if scenario == "mednec_unsupported":
        return (
            "The patient reports intermittent discomfort during daily activity. "
            "Examination findings are stable without new concerns. "
            "Routine follow-up and home care were discussed."
        )
    if scenario == "prior_auth_none":
        return (
            "The patient attended a scheduled outpatient visit for chronic symptoms. "
            "The clinician reviewed the existing plan and discussed routine follow-up. "
            "The record contains no authorization reference or exception documentation."
        )
    return (
        "The patient attended a routine visit for ongoing care. "
        "The clinician reviewed the treatment plan and current symptoms. "
        "Follow-up was arranged according to the care plan."
    )


def render_835(
    claim_id: str,
    payer_id: str,
    patient: tuple[str, str],
    cpt: str,
    modifier: str | None,
    billed: float,
    paid: float,
    carc: str,
    remit_date: date,
    service_date: date,
) -> str:
    group = "PR" if carc in {"1", "2", "3"} else "CO"
    adjustment = round(billed - paid, 2)
    service_code = ":".join(["HC", cpt] + ([modifier] if modifier else []))
    segments = [
        "ISA*00*          *00*          *ZZ*SYNTHETIC      *ZZ*APPEALS        *261024*1200*^*00501*000000001*0*P*:~",
        "GS*HP*SYNTHETIC*APPEALS*20261024*1200*1*X*005010X221A1~",
        "ST*835*0001~",
        f"BPR*I*0*C*ACH*CTX*01*999999999*DA*123456789*999999999*999999999*01*999999999*DA*123456789*{remit_date:%Y%m%d}~",
        "TRN*1*TRACE0001*1234567890~",
        f"N1*PR*{payer_id.title()} Plan*XV*{payer_id}~",
        "N1*PE*Springfield Family Medicine*XX*1234567890~",
        (
            f"CLP*{claim_id}*1*{billed:.2f}*{paid:.2f}*0*CI*REF{claim_id[-3:]}*11*1~"
        ),
        f"NM1*QC*1*{patient[1].upper()}*{patient[0].upper()}****MI*MEMBER{claim_id[-3:]}~",
        f"DTM*472*{service_date:%Y%m%d}~",
        f"SVC*{service_code}*{billed:.2f}*{paid:.2f}*UN*1~",
        f"CAS*{group}*{carc}*{adjustment:.2f}~",
        "LQ*HE*N290~",
        "SE*12*0001~",
        "GE*1*1~",
        "IEA*1*000000001~",
    ]
    return "\n".join(segments) + "\n"


def main() -> None:
    rng = random.Random(42)
    payers = load_rules(ROOT / "rules" / "payers")
    expanded = [
        (scenario, carc, cpts, category, action)
        for scenario, carc, cpts, category, action, count in SCENARIOS
        for _ in range(count)
    ]
    rng.shuffle(expanded)
    CASES_DIR.mkdir(parents=True, exist_ok=True)

    for index, (scenario, carc, cpts, category, action) in enumerate(expanded, start=1):
        case_id = f"CASE-{index:03d}"
        payer_id = rng.choice(PAYER_IDS)
        cpt = rng.choice(cpts)
        patient = NAMES[index - 1]
        billed = round(rng.uniform(90, 4500), 2)
        paid = round(rng.uniform(0, billed * 0.55), 2) if action != "bill_patient" else 0.0
        modifier = "59" if scenario == "bundling_mod59" else "25" if scenario == "modifier_error" else None
        if scenario == "mednec_deadline_passed":
            remit_date = date(2026, 1, 5) + timedelta(days=rng.randrange(0, 20))
        else:
            remit_date = date(2026, 9, 20) + timedelta(days=rng.randrange(0, 31))
        service_date = remit_date - timedelta(days=rng.randrange(7, 75))
        auth_number = f"SYN-AUTH-{index:03d}" if scenario == "prior_auth_has_number" else None
        proof = scenario == "timely_with_proof"
        remit_name = f"{case_id}.835"
        remit_text = render_835(
            case_id,
            payer_id,
            patient,
            cpt,
            modifier,
            billed,
            paid,
            carc,
            remit_date,
            service_date,
        )
        case_data = {
            "id": case_id,
            "scenario": scenario,
            "payer_id": payer_id,
            "note": note_for(scenario, cpt, payer_id, payers),
            "auth_number": auth_number,
            "proof_of_timely_filing": proof,
            "remit_file": remit_name,
            "expected": {"category": category, "action": action},
        }
        (CASES_DIR / f"{case_id}.json").write_text(
            json.dumps(case_data, indent=2) + "\n", encoding="utf-8"
        )
        (CASES_DIR / remit_name).write_text(remit_text, encoding="utf-8")


if __name__ == "__main__":
    main()
