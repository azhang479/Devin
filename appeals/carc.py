from pathlib import Path
from typing import Any

import yaml

DEFAULT_CARC_PATH = Path(__file__).resolve().parent.parent / "data" / "carc_codes.yaml"


def load_carc_table(path: str | Path = DEFAULT_CARC_PATH) -> dict[str, dict[str, str]]:
    with Path(path).open(encoding="utf-8") as source:
        data: dict[str, Any] = yaml.safe_load(source) or {}
    return {str(code): row for code, row in data.items()}


def lookup_carc(code: str, table: dict[str, dict[str, str]]) -> dict[str, str]:
    return table.get(str(code), {"description": f"Unknown CARC {code}", "category": "unknown"})
