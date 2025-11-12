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


def generate_essay_id(filename_stem: str, max_length: int = 36) -> str:
    """Generate essay ID with length constraint using truncation and hash suffix.

    Args:
        filename_stem: The file stem (name without extension) to convert to an essay ID
        max_length: Maximum allowed length for the essay ID (default: 36 for VARCHAR(36))

    Returns:
        A unique, deterministic essay ID that respects the length constraint

    Examples:
        >>> generate_essay_id("Short Name", max_length=36)
        'SHORT_NAME'
        >>> generate_essay_id("EDITH_STRANDLER_SA24_ENG5_NP_WRITING_ROLE_MODELS", max_length=36)
        'EDITH_STRANDLER_SA24_ENG5_NP_W_A3F4B2C1'  # 36 chars with hash
    """
    sanitized = sanitize_identifier(filename_stem)

    if len(sanitized) <= max_length:
        return sanitized

    # Need to truncate: reserve space for underscore and 8-char hash suffix
    hash_suffix_length = 8
    separator_length = 1  # for the underscore
    base_max_length = max_length - hash_suffix_length - separator_length

    # Generate deterministic hash from full sanitized name
    name_hash = sha256(sanitized.encode()).hexdigest()[:hash_suffix_length]

    # Truncate base and append hash
    base = sanitized[:base_max_length]
    return f"{base}_{name_hash.upper()}"
