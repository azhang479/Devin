from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError


class AppealDestination(BaseModel):
    fax: str
    address: str


class AppealRules(BaseModel):
    deadline_days: int = Field(gt=0)
    levels: list[str] = Field(min_length=1)
    submit_to: AppealDestination


class Criterion(BaseModel):
    id: str
    description: str
    any_of: list[str] = Field(min_length=1)


class Policy(BaseModel):
    policy_id: str
    title: str
    version: str
    effective_date: date
    cpt_codes: list[str] = Field(min_length=1)
    min_criteria: int = Field(ge=0)
    criteria: list[Criterion]


class BundlingRules(BaseModel):
    modifiers: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class PayerRules(BaseModel):
    payer_id: str
    name: str
    appeal: AppealRules
    policies: list[Policy]
    bundling: BundlingRules
    emergency_keywords: list[str] = Field(default_factory=list)


def load_rules(directory: str | Path) -> dict[str, PayerRules]:
    rules: dict[str, PayerRules] = {}
    for path in sorted(Path(directory).glob("*.yaml")):
        try:
            with path.open(encoding="utf-8") as source:
                payer = PayerRules.model_validate(yaml.safe_load(source))
        except (ValidationError, yaml.YAMLError, TypeError) as exc:
            raise ValueError(f"Invalid payer rules in {path}: {exc}") from exc
        if payer.payer_id in rules:
            raise ValueError(f"Duplicate payer_id {payer.payer_id!r} in {path}")
        rules[payer.payer_id] = payer
    return rules
