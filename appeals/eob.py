from copy import deepcopy
from io import BytesIO

from pypdf import PdfReader

from appeals.llm.client import LLMClient
from appeals.llm.prompts import EOB_SCHEMA, EOB_SYSTEM, EOB_USER
from appeals.models import Denial, denial_from_dict
from appeals.rules import PayerRules

ALLOWED_GROUPS = {"CO", "PR", "OA", "PI", "CR"}


class EOBValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise ValueError(f"Unable to read PDF: {exc}") from exc


def extract_eob(
    text: str,
    payers: dict[str, PayerRules],
    client: LLMClient,
) -> Denial:
    schema = deepcopy(EOB_SCHEMA)
    schema["properties"]["payer_id"]["enum"] = list(payers)
    payer_options = "\n".join(
        f"- {payer_id}: {payer.name}" for payer_id, payer in payers.items()
    )
    extracted = client.generate_json(
        EOB_SYSTEM,
        EOB_USER.format(payer_options=payer_options, text=text),
        schema,
    )
    data = dict(extracted)
    for field in ("service_date", "remit_date"):
        if data.get(field) == "":
            data[field] = None
    try:
        denial = denial_from_dict(data)
    except (TypeError, ValueError) as exc:
        errors = (
            [f"{item['loc']}: {item['msg']}" for item in exc.errors()]
            if hasattr(exc, "errors")
            else [str(exc)]
        )
        raise EOBValidationError(errors) from exc

    errors = []
    lowered_text = text.casefold()
    if denial.payer_id not in payers:
        errors.append(f"Unknown payer_id: {denial.payer_id}")
    if not denial.claim_id.strip():
        errors.append("Claim number is empty")
    elif denial.claim_id.casefold() not in lowered_text:
        errors.append(f"Claim number not found in EOB text: {denial.claim_id}")
    if not denial.adjustments:
        errors.append("EOB contains no adjustments")
    for adjustment in denial.adjustments:
        if adjustment.carc.casefold() not in lowered_text:
            errors.append(f"CARC not found in EOB text: {adjustment.carc}")
        if adjustment.group not in ALLOWED_GROUPS:
            errors.append(f"Invalid adjustment group: {adjustment.group}")
    billed_values = (f"{denial.billed:,.2f}", f"{denial.billed:.2f}")
    if not any(value.casefold() in lowered_text for value in billed_values):
        errors.append(f"Billed amount not found in EOB text: {denial.billed:.2f}")
    if errors:
        raise EOBValidationError(errors)
    return denial
