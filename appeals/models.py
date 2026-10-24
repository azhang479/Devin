from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Adjustment(BaseModel):
    group: str
    carc: str
    amount: float


class ServiceLine(BaseModel):
    cpt: str
    modifiers: list[str] = Field(default_factory=list)
    charge: float = 0.0


class Claim(BaseModel):
    claim_id: str
    billed: float
    paid: float
    payer_id: str = "unknown"
    patient_name: str = "Unknown patient"
    service_date: date | None = None
    remit_date: date | None = None
    lines: list[ServiceLine] = Field(default_factory=list)


class Denial(Claim):
    adjustments: list[Adjustment] = Field(default_factory=list)
    rarc: list[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="allow")


class CriterionEvidence(BaseModel):
    criterion_id: str
    description: str
    snippet: str | None = None


class EvidenceResult(BaseModel):
    matched: list[CriterionEvidence] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    missing_details: list[CriterionEvidence] = Field(default_factory=list)
    meets_min: bool = False


class TriageResult(BaseModel):
    category: str
    carc: str
    action: str
    reason: str
    deadline: date
    days_left: int
    win_probability: float
    amount_at_stake: float
    priority: float
    evidence: EvidenceResult = Field(default_factory=EvidenceResult)
    policy_id: str | None = None


def denial_from_dict(value: dict[str, Any]) -> Denial:
    """Accept the compact JSON denial format and common aliases."""
    data = dict(value)
    if "lines" not in data:
        data["lines"] = data.pop("service_lines", [])
    if "service_date" not in data:
        data["service_date"] = data.pop("dos", None)
    if "remit_date" not in data:
        data["remit_date"] = data.pop("denial_date", None)
    if "adjustments" not in data and "cas" in data:
        data["adjustments"] = data.pop("cas")
    if "rarc" not in data and "rarcs" in data:
        data["rarc"] = data.pop("rarcs")
    return Denial.model_validate(data)
