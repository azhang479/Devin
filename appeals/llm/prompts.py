"""Prompt text and JSON schemas for the optional local-LLM features."""

EVIDENCE_SYSTEM = """You review clinical documentation for an insurance appeal.
You are given a payer policy's criteria and a clinical note. For each criterion, decide whether
the note affirmatively documents it.

Rules:
- A criterion is met only if the note states it as present or completed.
- Negated, planned, pending, or hypothetical findings do NOT meet a criterion
  (for example "denies numbness", "plans to start PT", "MRI pending").
- Synonyms and abbreviations count (for example "PT" means physical therapy, and
  "8 weeks" satisfies "at least 6 weeks").
- For each met criterion, copy the shortest exact phrase from the note that proves it,
  character for character. Do not paraphrase, correct, or combine separate phrases.
- If a criterion is not met, set "met" to false and "quote" to an empty string.
- Return exactly one entry per criterion id, using only the ids given."""

EVIDENCE_USER = """Policy: {policy_id} - {title}
Criteria:
{criteria_lines}

Clinical note:
<<<
{note}
>>>"""

EVIDENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion_id": {"type": "string"},
                    "met": {"type": "boolean"},
                    "quote": {"type": "string"},
                },
                "required": ["criterion_id", "met", "quote"],
            },
        }
    },
    "required": ["criteria"],
}

ARGUMENT_SYSTEM = """You draft the argument paragraph of a medical-necessity appeal letter from a
healthcare practice to an insurer. Write one paragraph of 3 to 5 sentences in a plain,
professional tone.

Rules:
- Use only the facts provided: the policy, its criteria, and the verified quotes from the
  clinical note.
- Do not add diagnoses, test results, dates, durations, or any other clinical facts that are
  not in the quotes.
- When you cite the note, put the exact quote in double quotes.
- Do not include a greeting, signature, claim number, or address."""

ARGUMENT_USER = """Payer: {payer_name}
Policy: {policy_id} - {title} (version {version})
Service: CPT {cpts}
Denial reason: {carc} - {carc_description}
Criteria met, with verified quotes from the clinical note:
{evidence_lines}"""

DOC_REQUEST_SYSTEM = """You write a short, polite message from a billing specialist to the treating
clinician, asking for the documentation needed to appeal a denied insurance claim.
Write 2 to 4 sentences. Name each missing item and say what kind of finding would document it.
Never suggest documenting anything that did not happen: ask the clinician to add each item only
if it is clinically accurate. Do not include a greeting line or a signature."""

DOC_REQUEST_USER = """Claim {claim_id}, patient {patient}, date of service {service_date}, CPT {cpts}
Payer policy: {policy_id} - {title} (requires at least {min_criteria} criteria)
Already documented:
{matched_lines}
Missing:
{missing_lines}"""

DOC_REQUEST_FALLBACK = """Claim {claim_id} ({patient}, date of service {service_date}) was denied as \
not medically necessary. To appeal under {policy_id} ({title}), the record must document at least \
{min_criteria} of the policy criteria. Please add documentation for the following, only if \
clinically accurate:
{missing_lines}"""

EOB_SYSTEM = """You extract structured data from the text of an insurance Explanation of Benefits
(EOB) for a single claim. Copy values exactly as printed.

Rules:
- Amounts are plain numbers without "$" or commas (for example 1416.91).
- Dates use the format YYYY-MM-DD.
- Adjustment group codes are two letters (CO, PR, OA, PI, CR). The reason code (CARC) is the
  code that follows the group code; for example "CO-50" is group "CO" with carc "50".
- "cpt" is the 5-character procedure code; "modifiers" are the 2-character modifiers printed
  with it, if any.
- payer_id must be one of the allowed values.
- If a value is not printed, use an empty string or an empty list."""

EOB_USER = """Allowed payer_id values:
{payer_options}

EOB text:
<<<
{text}
>>>"""

EOB_SCHEMA = {
    "type": "object",
    "properties": {
        "claim_id": {"type": "string"},
        "payer_id": {"type": "string"},
        "patient_name": {"type": "string"},
        "service_date": {"type": "string"},
        "remit_date": {"type": "string"},
        "billed": {"type": "number"},
        "paid": {"type": "number"},
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cpt": {"type": "string"},
                    "modifiers": {"type": "array", "items": {"type": "string"}},
                    "charge": {"type": "number"},
                },
                "required": ["cpt", "modifiers", "charge"],
            },
        },
        "adjustments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "group": {"type": "string"},
                    "carc": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["group", "carc", "amount"],
            },
        },
    },
    "required": [
        "claim_id",
        "payer_id",
        "patient_name",
        "service_date",
        "remit_date",
        "billed",
        "paid",
        "lines",
        "adjustments",
    ],
}
