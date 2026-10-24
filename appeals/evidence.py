from appeals.models import CriterionEvidence, EvidenceResult
from appeals.rules import Policy


def _snippet(text: str, start: int, end: int) -> str:
    left = max(0, start - 40)
    right = min(len(text), end + 40)
    while left > 0 and not text[left - 1].isspace():
        left -= 1
    while right < len(text) and not text[right].isspace():
        right += 1

    while right - left > 120:
        left_context = start - left
        right_context = right - end
        if left_context >= right_context and left < start:
            while left < start and not text[left].isspace():
                left += 1
            while left < start and text[left].isspace():
                left += 1
        elif right > end:
            while right > end and not text[right - 1].isspace():
                right -= 1
            while right > end and text[right - 1].isspace():
                right -= 1
        else:
            break

    if right - left > 120:
        left = max(left, start - max(0, (120 - (end - start)) // 2))
        right = min(len(text), left + 120)
    return text[left:right].strip()


def match_criteria(note_text: str, policy: Policy) -> EvidenceResult:
    text = note_text or ""
    lowered = text.casefold()
    matched = []
    missing = []
    missing_details = []
    for criterion in policy.criteria:
        hit = next((term for term in criterion.any_of if term.casefold() in lowered), None)
        if hit is None:
            missing.append(criterion.id)
            missing_details.append(
                CriterionEvidence(
                    criterion_id=criterion.id,
                    description=criterion.description,
                )
            )
            continue
        start = lowered.find(hit.casefold())
        matched.append(
            CriterionEvidence(
                criterion_id=criterion.id,
                description=criterion.description,
                snippet=_snippet(text, start, start + len(hit)),
            )
        )
    return EvidenceResult(
        matched=matched,
        missing=missing,
        missing_details=missing_details,
        meets_min=len(matched) >= policy.min_criteria,
    )
