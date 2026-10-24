from appeals.llm.client import LLMClient, LLMError
from appeals.llm.prompts import (
    DOC_REQUEST_FALLBACK,
    DOC_REQUEST_SYSTEM,
    DOC_REQUEST_USER,
)
from appeals.models import Denial, TriageResult
from appeals.rules import Policy


def draft_doc_request(
    denial: Denial,
    triage_result: TriageResult,
    policy: Policy | None,
    client: LLMClient | None,
) -> tuple[str | None, str]:
    if (
        triage_result.action != "gather_documentation"
        or triage_result.category != "medical_necessity"
        or policy is None
    ):
        return None, "none"

    missing_lines = "\n".join(
        f"- {item.description}" for item in triage_result.evidence.missing_details
    )
    if not missing_lines:
        missing_lines = "- none"
    service_date = denial.service_date.isoformat() if denial.service_date else "not provided"
    fallback = DOC_REQUEST_FALLBACK.format(
        claim_id=denial.claim_id,
        patient=denial.patient_name,
        service_date=service_date,
        policy_id=policy.policy_id,
        title=policy.title,
        min_criteria=policy.min_criteria,
        missing_lines=missing_lines,
    ).strip()
    if client is None:
        return fallback, "template"

    matched_lines = "\n".join(
        f"- {item.description}" for item in triage_result.evidence.matched
    )
    if not matched_lines:
        matched_lines = "- none"
    cpts = ", ".join(dict.fromkeys(line.cpt for line in denial.lines))
    try:
        text = client.generate_text(
            DOC_REQUEST_SYSTEM,
            DOC_REQUEST_USER.format(
                claim_id=denial.claim_id,
                patient=denial.patient_name,
                service_date=service_date,
                cpts=cpts,
                policy_id=policy.policy_id,
                title=policy.title,
                min_criteria=policy.min_criteria,
                matched_lines=matched_lines,
                missing_lines=missing_lines,
            ),
        ).strip()
    except LLMError:
        return fallback, "template"
    if not text or len(text) > 1000:
        return fallback, "template"
    return text, "ai"
