from appeals.models import CriterionEvidence, EvidenceResult
from appeals.rules import Policy


def match_criteria(note_text: str, policy: Policy) -> EvidenceResult:
    text = note_text or ""
    lowered = text.casefold()
    matched = []
    missing = []
    for criterion in policy.criteria:
        hit = next((term for term in criterion.any_of if term.casefold() in lowered), None)
        if hit is None:
            missing.append(criterion.id)
            continue
        start = lowered.find(hit.casefold())
        snippet_start = max(0, start - 40)
        snippet_end = min(len(text), start + len(hit) + 40)
        matched.append(
            CriterionEvidence(
                criterion_id=criterion.id,
                description=criterion.description,
                snippet=text[snippet_start:snippet_end].strip(),
            )
        )
    return EvidenceResult(
        matched=matched,
        missing=missing,
        meets_min=len(matched) >= policy.min_criteria,
    )
