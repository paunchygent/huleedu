"""Simple, predictable name parsing without pattern-based assumptions."""

from __future__ import annotations

import re

from ..models import NameComponents


class SimpleNameParser:
    """Simple name parser with predictable, conservative rules.

    This parser makes no assumptions about cultural naming conventions.
    It uses basic heuristics that work across cultures and gracefully
    degrade when assumptions don't hold.
    """

    def parse_name(self, full_name: str) -> NameComponents:
        """Parse a full name into components using simple, predictable rules.

        Rules:
        1. One word: treat as first name
        2. Two words: first + last name
        3. Three+ words: first + middle(s) + last name
        4. Preserve original full name for reference

        No cultural assumptions, no pattern matching.
        """
        # Store original for full_name field
        original_name = full_name

        # Basic normalization: collapse whitespace and normalize dashes
        normalized = self._normalize_whitespace(full_name)
        normalized = self._normalize_dashes(normalized)

        if not normalized:
            return NameComponents(
                first_name="", last_name="", middle_names=[], full_name=original_name
            )

        # Split into words, preserving compound names with hyphens
        words = self._split_preserving_compounds(normalized)

        if not words:
            return NameComponents(
                first_name="", last_name="", middle_names=[], full_name=original_name
            )

        # Apply simple rules
        if len(words) == 1:
            return NameComponents(
                first_name=words[0], last_name="", middle_names=[], full_name=original_name
            )
        elif len(words) == 2:
            return NameComponents(
                first_name=words[0], last_name=words[1], middle_names=[], full_name=original_name
            )
        else:
            # Conservative approach: first + middle(s) + last
            return NameComponents(
                first_name=words[0],
                last_name=words[-1],
                middle_names=words[1:-1],
                full_name=original_name,
            )

    def get_match_variations(self, name_components: NameComponents) -> list[str]:
        """Get name variations for matching.

        Returns standard variations without cultural assumptions:
        - Full name as provided
        - First + Last (if both exist)
        - Last, First (reversed format)
        - With middle initials (if present)
        """
        variations = [name_components.full_name]

        if name_components.first_name and name_components.last_name:
            # Standard first + last format
            first_last = f"{name_components.first_name} {name_components.last_name}"
            variations.append(first_last)

            # Reversed format
            reversed_format = f"{name_components.last_name}, {name_components.first_name}"
            variations.append(reversed_format)

            # With middle initials if present
            if name_components.middle_names:
                initials = " ".join(name[0] + "." for name in name_components.middle_names if name)
                with_initials = (
                    f"{name_components.first_name} {initials} {name_components.last_name}"
                )
                variations.append(with_initials)

        # Remove duplicates while preserving order
        seen = set()
        unique_variations = []
        for variation in variations:
            normalized_variation = variation.lower().strip()
            if normalized_variation not in seen:
                seen.add(normalized_variation)
                unique_variations.append(variation)

        return unique_variations

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace consistently."""
        if not text:
            return ""
        return " ".join(text.split())

    def _normalize_dashes(self, text: str) -> str:
        """Normalize various dash types to standard hyphen."""
        if not text:
            return ""
        # Handle common dash variations including spaced dashes
        return re.sub(r"\s*[-–—]\s*", "-", text)

    def _split_preserving_compounds(self, text: str) -> list[str]:
        """Split on spaces while preserving hyphenated compound names."""
        if not text:
            return []

        # Split on whitespace; hyphens within words are preserved
        words = text.split()

        # Filter out empty strings
        return [word for word in words if word.strip()]
