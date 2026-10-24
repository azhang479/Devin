import re


def find_in_note(note: str, quote: str) -> str | None:
    cleaned = quote.strip().strip("\"'“”‘’.,;:")
    if len(cleaned) < 3:
        return None
    pattern = r"\s+".join(re.escape(word) for word in cleaned.split())
    match = re.search(pattern, note, flags=re.IGNORECASE)
    return match.group(0) if match is not None else None
