from datetime import date, datetime
from typing import Any

from pydantic import ValidationError

from appeals.models import Adjustment, Denial, ServiceLine, denial_from_dict


def _date(value: str) -> date | None:
    if len(value) != 8 or not value.isdigit():
        return None
    return datetime.strptime(value, "%Y%m%d").date()


def _number(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _parse_cas(parts: list[str]) -> list[Adjustment]:
    if len(parts) < 4:
        return []
    group = parts[1]
    adjustments = []
    for index in range(2, len(parts), 3):
        if index + 1 >= len(parts) or not parts[index]:
            continue
        adjustments.append(
            Adjustment(group=group, carc=parts[index], amount=_number(parts[index + 1]))
        )
    return adjustments


def parse_835(text: str) -> list[Denial]:
    """Parse the simplified claim/remittance segments used by the project."""
    segments = [
        [element.strip() for element in segment.strip().split("*")]
        for segment in text.replace("\r", "").replace("\n", "").split("~")
        if segment.strip()
    ]
    payer_id = "unknown"
    bpr_date: date | None = None
    header_remit_date: date | None = None
    denials: list[Denial] = []
    current: dict[str, Any] | None = None

    for parts in segments:
        tag = parts[0]
        if tag == "N1" and len(parts) > 1 and parts[1] == "PR" and len(parts) > 4:
            payer_id = parts[4]
        elif tag == "BPR" and len(parts) > 16:
            bpr_date = _date(parts[16])
        elif tag == "DTM" and len(parts) > 2 and parts[1] == "405" and current is None:
            header_remit_date = _date(parts[2])
        elif tag == "CLP":
            if current is not None:
                denials.append(Denial.model_validate(current))
            current = {
                "claim_id": parts[1] if len(parts) > 1 else "",
                "billed": _number(parts[3] if len(parts) > 3 else None),
                "paid": _number(parts[4] if len(parts) > 4 else None),
                "payer_id": payer_id,
                "patient_name": "Unknown patient",
                "service_date": None,
                "remit_date": header_remit_date or bpr_date,
                "lines": [],
                "adjustments": [],
                "rarc": [],
            }
        elif current is not None:
            if tag == "N1" and len(parts) > 1 and parts[1] == "PR" and len(parts) > 4:
                current["payer_id"] = parts[4]
            elif tag == "NM1" and len(parts) > 3 and parts[1] == "QC":
                last = parts[3] or ""
                first = parts[4] if len(parts) > 4 else ""
                current["patient_name"] = " ".join(part for part in (first, last) if part)
            elif tag == "DTM" and len(parts) > 2:
                parsed_date = _date(parts[2])
                if parts[1] == "472":
                    current["service_date"] = parsed_date
                elif parts[1] == "405" and current["remit_date"] is None:
                    current["remit_date"] = parsed_date
            elif tag == "SVC" and len(parts) > 2:
                composite = parts[1].split(":")
                code = composite[1] if len(composite) > 1 else ""
                current["lines"].append(
                    ServiceLine(
                        cpt=code,
                        modifiers=[modifier for modifier in composite[2:] if modifier],
                        charge=_number(parts[2]),
                    )
                )
            elif tag == "CAS":
                current["adjustments"].extend(_parse_cas(parts))
            elif tag == "LQ" and len(parts) > 2 and parts[1] == "HE":
                current["rarc"].append(parts[2])

    if current is not None:
        denials.append(Denial.model_validate(current))
    return denials


def parse_denials(value: str) -> list[Denial]:
    """Parse either a simplified 835 document or JSON denial input."""
    import json

    stripped = value.lstrip()
    if not stripped.startswith(("{", "[")):
        return parse_835(value)
    try:
        payload = json.loads(value)
        records = payload if isinstance(payload, list) else payload.get("denials", [payload])
        return [denial_from_dict(record) for record in records]
    except (json.JSONDecodeError, ValidationError, AttributeError, TypeError) as exc:
        raise ValueError(f"Invalid JSON denial input: {exc}") from exc
