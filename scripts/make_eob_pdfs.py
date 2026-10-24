import json
from pathlib import Path

from fpdf import FPDF

from appeals.carc import load_carc_table, lookup_carc
from appeals.models import Denial
from appeals.parser import parse_835
from appeals.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]
CASE_IDS = ("CASE-001", "CASE-005", "CASE-007", "CASE-010", "CASE-013", "CASE-020")


def _safe(text: str) -> str:
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _money(amount: float) -> str:
    return f"${amount:,.2f}"


def _add_line(pdf: FPDF, text: str) -> None:
    pdf.cell(0, 8, _safe(text))
    pdf.ln(8)


def _write_eob(
    path: Path,
    denial: Denial,
    payer_name: str,
    carc_table: dict[str, dict[str, str]],
) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    _add_line(pdf, payer_name)
    pdf.set_font("Helvetica", style="B", size=16)
    _add_line(pdf, "Explanation of Benefits")
    pdf.set_font("Helvetica", size=11)
    _add_line(pdf, f"Claim number: {denial.claim_id}")
    _add_line(pdf, f"Patient: {denial.patient_name}")
    service_date = (
        denial.service_date.strftime("%m/%d/%Y") if denial.service_date else "Not provided"
    )
    remit_date = denial.remit_date.strftime("%m/%d/%Y") if denial.remit_date else "Not provided"
    _add_line(pdf, f"Date of service: {service_date}")
    _add_line(pdf, f"Date processed: {remit_date}")
    pdf.ln(4)

    widths = (35, 45, 50, 50)
    for label, width in zip(("CPT", "Modifiers", "Billed charge", "Paid"), widths):
        pdf.cell(width, 8, _safe(label), border=1)
    pdf.ln(8)
    for line in denial.lines:
        values = (
            line.cpt,
            ", ".join(line.modifiers) or "-",
            _money(line.charge),
            _money(denial.paid),
        )
        for value, width in zip(values, widths):
            pdf.cell(width, 8, _safe(value), border=1)
        pdf.ln(8)

    pdf.ln(4)
    pdf.set_font("Helvetica", style="B", size=12)
    _add_line(pdf, "Adjustments")
    pdf.set_font("Helvetica", size=11)
    for adjustment in denial.adjustments:
        description = lookup_carc(adjustment.carc, carc_table)["description"]
        _add_line(
            pdf,
            f"{adjustment.group}-{adjustment.carc}  {description}  {_money(adjustment.amount)}",
        )
    patient_responsibility = sum(
        adjustment.amount for adjustment in denial.adjustments if adjustment.group == "PR"
    )
    pdf.ln(4)
    _add_line(pdf, f"Billed: {_money(denial.billed)}")
    _add_line(pdf, f"Paid: {_money(denial.paid)}")
    _add_line(pdf, f"Patient responsibility: {_money(patient_responsibility)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


def main() -> None:
    payers = load_rules(ROOT / "rules" / "payers")
    carc_table = load_carc_table(ROOT / "data" / "carc_codes.yaml")
    cases_dir = ROOT / "data" / "synthetic" / "cases"
    output_dir = ROOT / "data" / "synthetic" / "eobs"
    for case_id in CASE_IDS:
        case_path = cases_dir / f"{case_id}.json"
        remit_path = cases_dir / f"{case_id}.835"
        case = json.loads(case_path.read_text(encoding="utf-8"))
        denials = parse_835(remit_path.read_text(encoding="utf-8"))
        if len(denials) != 1:
            raise ValueError(f"{case_id} should contain exactly one claim")
        payer = payers[case["payer_id"]]
        _write_eob(
            output_dir / f"{case_id}.pdf",
            denials[0],
            payer.name,
            carc_table,
        )


if __name__ == "__main__":
    main()
