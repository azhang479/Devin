from datetime import date, timedelta

from appeals.carc import lookup_carc
from appeals.models import Denial, EvidenceResult, TriageResult
from appeals.rules import PayerRules, Policy

APPEAL_BASE = {
    "medical_necessity": 0.55,
    "prior_auth": 0.45,
    "bundling": 0.40,
    "timely_filing": 0.30,
}


def _policy_for(denial: Denial, payer: PayerRules) -> Policy | None:
    codes = {line.cpt for line in denial.lines}
    return next((policy for policy in payer.policies if codes.intersection(policy.cpt_codes)), None)


def _primary_adjustment(denial: Denial):
    non_patient = [adjustment for adjustment in denial.adjustments if adjustment.group != "PR"]
    candidates = non_patient or denial.adjustments
    if not candidates:
        return None
    return max(candidates, key=lambda adjustment: adjustment.amount)


def triage(
    denial: Denial,
    payer: PayerRules,
    carc_table: dict[str, dict[str, str]],
    note_text: str = "",
    auth_number: str | None = None,
    proof_of_timely_filing: bool = False,
    today: date | None = None,
) -> TriageResult:
    today = today or date.today()
    adjustment = _primary_adjustment(denial)
    carc = adjustment.carc if adjustment else "unknown"
    category = lookup_carc(carc, carc_table)["category"]
    policy = _policy_for(denial, payer)
    evidence = EvidenceResult()
    if category == "medical_necessity" and policy is not None:
        from appeals.evidence import match_criteria

        evidence = match_criteria(note_text, policy)

    remit_date = denial.remit_date or today
    deadline = remit_date + timedelta(days=payer.appeal.deadline_days)
    days_left = (deadline - today).days
    action: str
    reason: str
    if category == "coding_error":
        action, reason = "resubmit", "Correct the coding or billing information and resubmit the claim."
    elif category == "cob":
        action, reason = "resubmit", "Submit the claim to the primary payer first."
    elif category in {"duplicate", "contractual"}:
        action, reason = "write_off", "This adjustment is not a recoverable appeal opportunity."
    elif category in {"eligibility", "patient_responsibility"}:
        action, reason = "bill_patient", "The remaining balance is the patient's responsibility."
    elif category == "timely_filing":
        if proof_of_timely_filing:
            action, reason = "appeal", "Submit proof that the claim was filed within the payer's limit."
        else:
            action, reason = "write_off", "No proof of timely filing is available."
    elif category == "medical_necessity":
        if policy is None:
            action, reason = "gather_documentation", "No matching CPT policy is available; gather documentation."
        elif evidence.meets_min:
            action, reason = "appeal", "The clinical note supports the policy's minimum criteria."
        else:
            action, reason = "gather_documentation", "The note does not yet support the policy's minimum criteria."
    elif category == "prior_auth":
        if auth_number:
            action, reason = "resubmit", "Add the available authorization number and resubmit."
        elif any(keyword.casefold() in note_text.casefold() for keyword in payer.emergency_keywords):
            action, reason = "appeal", "The note documents an emergency exception to prior authorization."
        else:
            action, reason = "write_off", "No authorization or documented emergency exception is available."
    elif category == "bundling":
        modifiers = {modifier for line in denial.lines for modifier in line.modifiers}
        has_modifier = bool(modifiers.intersection(payer.bundling.modifiers))
        has_keyword = any(
            keyword.casefold() in note_text.casefold() for keyword in payer.bundling.keywords
        )
        if has_modifier or has_keyword:
            action, reason = "appeal", "Provide documentation that the service was distinct from the bundled service."
        else:
            action, reason = "write_off", "No distinct-service modifier or supporting note language is present."
    else:
        action, reason = "gather_documentation", "The adjustment code is unknown; gather supporting documentation."

    if action == "appeal" and days_left < 0:
        action, reason = "write_off", "appeal deadline passed"

    win_probability = 0.0
    if action == "appeal":
        win_probability = APPEAL_BASE.get(category, 0.0)
        if category == "medical_necessity" and policy is not None:
            win_probability += 0.10 * (len(evidence.matched) - policy.min_criteria)
        win_probability = min(0.90, max(0.05, win_probability))
    elif action == "resubmit":
        win_probability = 0.85

    amount_at_stake = denial.billed - denial.paid
    urgency = 1 + max(0, 30 - days_left) / 30 if days_left >= 0 else 0
    return TriageResult(
        category=category,
        carc=carc,
        action=action,
        reason=reason,
        deadline=deadline,
        days_left=days_left,
        win_probability=win_probability,
        amount_at_stake=amount_at_stake,
        priority=amount_at_stake * win_probability * urgency,
        evidence=evidence,
        policy_id=policy.policy_id if policy else None,
    )
