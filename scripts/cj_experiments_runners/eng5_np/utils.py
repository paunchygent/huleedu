"""Shared helpers for ENG5 NP runner modules."""

from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path


def sha256_of_file(path: Path, chunk_size: int = 65_536) -> str:
    """Return a lowercase SHA256 checksum for *path*."""

    digest = sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")


def sanitize_identifier(value: str) -> str:
    """Convert filenames into deterministic uppercase identifiers."""

    token = _NON_ALNUM.sub("_", value).strip("_")
    return token.upper() or "ESSAY"
