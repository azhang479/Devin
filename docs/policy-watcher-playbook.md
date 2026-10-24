# Playbook: Payer policy watcher

Use this as a Devin playbook (or a scheduled Devin automation) to keep `rules/payers/*.yaml` in sync with payer policy changes.

## Inputs
- One or more payer bulletins (Markdown/PDF/URL). In the demo: `policy_bulletins/acme-2026-11-bulletin.md`.

## Procedure
1. Read each bulletin. Identify every change that affects appeal handling: appeal deadlines, appeal levels, submission address/fax, and for each policy: CPT codes, criteria, keywords, `min_criteria`, version, effective date.
2. Locate the matching payer file in `rules/payers/` and the policy by `policy_id`. If the bulletin references a policy that doesn't exist, add it rather than guessing an existing one.
3. Edit the YAML:
   - Bump `version` and set `effective_date` to the bulletin's effective date.
   - Change criteria exactly as described in the bulletin; do not invent criteria or keywords that the bulletin does not support (synonyms of the bulletin's own terms are fine).
4. Add tests in `tests/` that prove the change:
   - a clinical note that meets the new criteria triages to `appeal`;
   - a note that only met the old criteria (if the change is stricter) or newly qualifies (if looser) behaves as the bulletin implies.
5. Run `ruff check .`, `pytest -q`, and `python eval/run_eval.py`. If eval accuracy drops, explain which cases changed and why in the PR (a policy change can legitimately change the expected action — update those cases' `expected` blocks only when the bulletin justifies it).
6. Open a PR titled `rules(<payer>): apply <bulletin name>` whose description contains: a quote of each bulletin change, the corresponding YAML diff summary, the new tests, and eval before/after.

## Guardrails
- Only touch `rules/`, `tests/`, and (if justified) `data/synthetic/cases/*.json` expected labels.
- Never merge; a human biller/clinician reviews every rules PR.
- If a bulletin is ambiguous (e.g. effective date unclear), leave the rule unchanged and ask in the PR description.
