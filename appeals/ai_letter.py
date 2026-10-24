import re

from appeals.carc import load_carc_table, lookup_carc
from appeals.llm.client import LLMClient, LLMError
from appeals.llm.prompts import ARGUMENT_SYSTEM, ARGUMENT_USER
from appeals.llm.verify import find_in_note
from appeals.models import Denial, TriageResult
from appeals.rules import PayerRules, Policy

QUOTED_SPAN = re.compile(r'[“"]([^”"]{3,})[”"]')


def draft_argument(
    denial: Denial,
    triage_result: TriageResult,
    payer: PayerRules,
    policy: Policy | None,
    note_text: str,
    client: LLMClient,
) -> str | None:
    if (
        triage_result.action != "appeal"
        or triage_result.category != "medical_necessity"
        or policy is None
        or not triage_result.evidence.matched
    ):
        return None

    cpts = ", ".join(dict.fromkeys(line.cpt for line in denial.lines))
    evidence_lines = "\n".join(
        f'- {item.description}: "{item.snippet or ""}"'
        for item in triage_result.evidence.matched
    )
    carc_description = lookup_carc(
        triage_result.carc, load_carc_table()
    )["description"]
    try:
        argument = client.generate_text(
            ARGUMENT_SYSTEM,
            ARGUMENT_USER.format(
                payer_name=payer.name,
                policy_id=policy.policy_id,
                title=policy.title,
                version=policy.version,
                cpts=cpts,
                carc=triage_result.carc,
                carc_description=carc_description,
                evidence_lines=evidence_lines,
            ),
        )
    except LLMError:
        return None

    argument = argument.strip()
    if not argument or len(argument) > 1500:
        return None
    if any(find_in_note(note_text, quote) is None for quote in QUOTED_SPAN.findall(argument)):
        return None
    return argument
