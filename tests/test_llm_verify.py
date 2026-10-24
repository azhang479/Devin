from appeals.llm.verify import find_in_note


def test_find_in_note_normalizes_case_and_whitespace_but_returns_original_text():
    note = "Completed SIX   WEEKS of Physical Therapy."

    assert find_in_note(note, "six weeks of physical therapy") == (
        "SIX   WEEKS of Physical Therapy"
    )


def test_find_in_note_strips_outer_punctuation_and_quotes():
    note = "Symptoms include weakness and numbness."

    assert find_in_note(note, " “WEAKNESS and numbness.” ") == "weakness and numbness"


def test_find_in_note_rejects_quotes_shorter_than_three_characters():
    assert find_in_note("No.", "ab") is None
    assert find_in_note("An exact phrase.", "exact") == "exact"
