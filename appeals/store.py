from dataclasses import dataclass

from appeals.models import Denial, TriageResult
from appeals.rules import PayerRules


@dataclass
class DenialRecord:
    id: str
    denial: Denial
    payer: PayerRules
    note: str
    auth_number: str | None
    proof_of_timely_filing: bool
    triage: TriageResult
    letter: str | None
    status: str = "pending"


class InMemoryStore:
    def __init__(self) -> None:
        self.records: dict[str, DenialRecord] = {}

    def add(self, record: DenialRecord) -> None:
        self.records[record.id] = record

    def get(self, record_id: str) -> DenialRecord | None:
        return self.records.get(record_id)
