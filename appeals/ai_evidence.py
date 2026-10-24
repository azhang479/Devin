from appeals.llm.client import LLMClient
from appeals.llm.prompts import EVIDENCE_SCHEMA, EVIDENCE_SYSTEM, EVIDENCE_USER
from appeals.llm.verify import find_in_note
from appeals.models import CriterionEvidence, EvidenceResult
from appeals.rules import Policy


def match_criteria_ai(
    note_text: str,
    policy: Policy,
    client: LLMClient,
) -> EvidenceResult:
    criteria_lines = "\n".join(f"- {item.id}: {item.description}" for item in policy.criteria)
    response = client.generate_json(
        EVIDENCE_SYSTEM,
        EVIDENCE_USER.format(
            policy_id=policy.policy_id,
            title=policy.title,
            criteria_lines=criteria_lines,
            note=note_text,
        ),
        EVIDENCE_SCHEMA,
    )
    allowed = {item.id: item for item in policy.criteria}
    model_entries = {}
    for entry in response.get("criteria", []):
        criterion_id = entry.get("criterion_id")
        if criterion_id in allowed and criterion_id not in model_entries:
            model_entries[criterion_id] = entry

    matched = []
    missing = []
    missing_details = []
    rejected_quotes = []
    for criterion in policy.criteria:
        entry = model_entries.get(criterion.id)
        quote = entry.get("quote", "") if entry is not None else ""
        verified = find_in_note(note_text, quote) if isinstance(quote, str) else None
        if entry is not None and entry.get("met") is True and verified is not None:
            matched.append(
                CriterionEvidence(
                    criterion_id=criterion.id,
                    description=criterion.description,
                    snippet=verified,
                )
            )
            continue
        missing.append(criterion.id)
        missing_details.append(
            CriterionEvidence(
                criterion_id=criterion.id,
                description=criterion.description,
            )
        )
        if entry is not None and entry.get("met") is True and isinstance(quote, str):
            rejected_quotes.append(quote)

    return EvidenceResult(
        matched=matched,
        missing=missing,
        missing_details=missing_details,
        meets_min=len(matched) >= policy.min_criteria,
        method="ai",
        rejected_quotes=rejected_quotes,
    )
