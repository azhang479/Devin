from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from appeals.carc import load_carc_table, lookup_carc
from appeals.models import Denial, TriageResult
from appeals.rules import PayerRules, Policy

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_environment = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(enabled_extensions=()),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_letter(
    denial: Denial,
    triage_result: TriageResult,
    payer: PayerRules,
    policy: Policy | None = None,
    argument: str | None = None,
) -> str | None:
    if triage_result.action != "appeal":
        return None
    return _environment.get_template("appeal_letter.txt.j2").render(
        practice="Springfield Family Medicine",
        destination=payer.appeal.submit_to,
        denial=denial,
        triage=triage_result,
        payer=payer,
        policy=policy,
        argument=argument,
        carc_description=lookup_carc(triage_result.carc, load_carc_table())["description"],
    )
