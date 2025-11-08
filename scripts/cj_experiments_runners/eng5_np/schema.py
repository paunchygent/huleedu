"""Schema helpers for ENG5 NP runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_schema_available(schema_path: Path) -> dict[str, Any]:
    """Load and return the ENG5 schema JSON, raising if missing."""

    if not schema_path.exists():
        raise FileNotFoundError(
            f"ENG5 schema missing at {schema_path}. Did you move Documentation/schemas?"
        )
    return json.loads(schema_path.read_text(encoding="utf-8"))
