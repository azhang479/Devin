from pathlib import Path

from appeals.evidence import match_criteria
from appeals.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]
POLICY = load_rules(ROOT / "rules" / "payers")["acme"].policies[0]


def test_missing_criteria_include_descriptions():
    result = match_criteria("The patient reports low back pain.", POLICY)

    assert result.missing == ["conservative_therapy", "neuro_deficit"]
    assert [(item.criterion_id, item.description) for item in result.missing_details] == [
        ("conservative_therapy", "At least 6 weeks of failed conservative therapy"),
        ("neuro_deficit", "Progressive neurological deficit"),
    ]
    assert all(item.snippet is None for item in result.missing_details)


def test_snippet_expands_to_word_boundaries_and_stays_bounded():
    note = (
        "Today's clinical "
        + "case " * 7
        + "visit 6 weeks and more text around symptoms and treatment plan documented "
        "carefully by the clinician."
    )
    result = match_criteria(note, POLICY)
    snippet = result.matched[0].snippet
    assert snippet is not None
    start = note.index(snippet)
    end = start + len(snippet)

    assert snippet.startswith("case")
    assert len(snippet) <= 120
    assert start == 0 or note[start - 1].isspace()
    assert end == len(note) or note[end].isspace()
