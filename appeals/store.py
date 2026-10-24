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
    doc_request: str | None = None
    doc_request_method: str = "none"
    analysis_method: str = "keyword"
    ai_error: str | None = None
    ai_argument: bool = False
    source: str = "835"


class InMemoryStore:
    def __init__(self) -> None:
        self.records: dict[str, DenialRecord] = {}

    def add(self, record: DenialRecord) -> None:
        self.records[record.id] = record

    def get(self, record_id: str) -> DenialRecord | None:
        return self.records.get(record_id)
