"""Text normalization utilities for consistent processing."""

from __future__ import annotations

import re
import unicodedata


def normalize_text(text: str) -> str:
    """Normalize text for consistent processing.

    Handles:
    - Unicode normalization
    - Whitespace cleanup
    - Line ending normalization
    """
    if not text:
        return ""

    # Unicode normalization (NFC - composed form)
    # This ensures å is stored as single character, not a + ring
    text = unicodedata.normalize("NFC", text)

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Replace tabs with spaces
    text = text.replace("\t", " ")

    # Remove zero-width characters
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)

    # Normalize quotes
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(""", "'").replace(""", "'")

    # Remove excessive whitespace while preserving paragraph breaks
    lines = text.split("\n")
    normalized_lines = []

    for line in lines:
        # Clean up line but preserve if it was originally empty
        cleaned = " ".join(line.split()) if line.strip() else ""
        normalized_lines.append(cleaned)

    # Join lines back
    return "\n".join(normalized_lines)


def clean_name(name: str) -> str:
    """Clean a name for matching purposes.

    Preserves Swedish characters but removes unnecessary punctuation.
    """
    if not name:
        return ""

    # Normalize unicode
    name = unicodedata.normalize("NFC", name)

    # Remove leading/trailing whitespace
    name = name.strip()

    # Normalize internal whitespace
    name = " ".join(name.split())

    # Remove common punctuation that might interfere
    # but preserve hyphens for compound names
    name = re.sub(r'[.,;:!?"\'()]', "", name)

    return name


def clean_email(email: str) -> str:
    """Clean an email address for matching.

    Lowercases and removes common variations.
    """
    if not email:
        return ""

    # Lowercase
    email = email.lower().strip()

    # Remove mailto: prefix if present
    if email.startswith("mailto:"):
        email = email[7:]

    # Remove angle brackets if present
    email = email.strip("<>")

    return email


def extract_words(text: str, min_length: int = 2) -> list[str]:
    """Extract words from text, filtering by minimum length."""
    # Unicode word boundaries to handle Swedish characters
    words = re.findall(r"\b\w+\b", text, re.UNICODE)

    # Filter by length
    return [w for w in words if len(w) >= min_length]


def remove_common_words(text: str, language: str = "sv") -> str:
    """Remove common stop words from text.

    Args:
        text: Text to process
        language: Language code (sv for Swedish, en for English)
    """
    # Common Swedish stop words
    swedish_stops = {
        "och",
        "i",
        "att",
        "det",
        "som",
        "en",
        "på",
        "är",
        "av",
        "för",
        "med",
        "till",
        "den",
        "har",
        "de",
        "inte",
        "om",
        "ett",
        "han",
        "men",
        "var",
        "jag",
        "sig",
        "från",
        "vi",
        "kan",
        "hans",
        "där",
        "alla",
        "när",
        "denna",
        "hon",
        "över",
        "än",
        "två",
        "ha",
        "mot",
        "denna",
        "nu",
        "blir",
        "ju",
        "efter",
        "bara",
        "år",
        "få",
        "mycket",
    }

    # Common English stop words
    english_stops = {
        "the",
        "be",
        "to",
        "of",
        "and",
        "a",
        "in",
        "that",
        "have",
        "i",
        "it",
        "for",
        "not",
        "on",
        "with",
        "he",
        "as",
        "you",
        "do",
        "at",
        "this",
        "but",
        "his",
        "by",
        "from",
        "they",
        "we",
        "say",
        "her",
        "she",
        "or",
        "an",
        "will",
        "my",
        "one",
        "all",
        "would",
        "there",
        "their",
        "what",
        "so",
        "up",
        "out",
        "if",
        "about",
        "who",
        "get",
    }

    stops = swedish_stops if language == "sv" else english_stops

    words = text.split()
    filtered = [w for w in words if w.lower() not in stops]

    return " ".join(filtered)


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to maximum length, preserving word boundaries."""
    if len(text) <= max_length:
        return text

    # Find last space before limit
    truncate_at = text.rfind(" ", 0, max_length - len(suffix))

    if truncate_at == -1:
        # No space found, hard truncate
        return text[: max_length - len(suffix)] + suffix

    return text[:truncate_at] + suffix
