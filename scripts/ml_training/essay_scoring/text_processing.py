"""Text normalization utilities for dataset preparation and leakage guards."""

from __future__ import annotations

import hashlib
import re
import unicodedata

_ZERO_WIDTH_CHARS = {
    "\u200b",  # zero width space
    "\u200c",  # zero width non-joiner
    "\u200d",  # zero width joiner
    "\ufeff",  # zero width no-break space / BOM
}

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text_for_hashing(text: str) -> str:
    """Normalize text for stable hashing and duplication checks."""

    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "".join(ch for ch in normalized if ch not in _ZERO_WIDTH_CHARS)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def sha256_text(text: str) -> str:
    """Return SHA256 hex digest for the given text."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def count_words(text: str) -> int:
    """Count words as contiguous sequences of alphanumeric characters."""

    in_word = False
    count = 0
    for ch in text:
        if ch.isalnum():
            if not in_word:
                count += 1
                in_word = True
        else:
            in_word = False
    return count
