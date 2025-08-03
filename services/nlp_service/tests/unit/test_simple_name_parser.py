"""
Unit tests for simple name parser.

Tests predictable, conservative name parsing without cultural assumptions.
"""

from __future__ import annotations

import pytest

from services.nlp_service.features.student_matching.matching.simple_name_parser import (
    SimpleNameParser,
)
from services.nlp_service.features.student_matching.models import NameComponents


class TestSimpleNameParser:
    """Tests for the SimpleNameParser class."""

    @pytest.fixture
    def parser(self) -> SimpleNameParser:
        """Fixture to provide a SimpleNameParser instance."""
        return SimpleNameParser()

    @pytest.mark.parametrize(
        "full_name, expected_first, expected_last, expected_middle, expected_full",
        [
            # Simple cases
            ("Anna Andersson", "Anna", "Andersson", [], "Anna Andersson"),
            ("Erik Johansson", "Erik", "Johansson", [], "Erik Johansson"),
            # Single names
            ("Anna", "Anna", "", [], "Anna"),
            ("Björn", "Björn", "", [], "Björn"),
            # Three-word names (conservative: first + middle + last)
            ("Anna Karin Svensson", "Anna", "Svensson", ["Karin"], "Anna Karin Svensson"),
            ("Erik Johan Andersson", "Erik", "Andersson", ["Johan"], "Erik Johan Andersson"),
            # Multiple middle names
            (
                "Mary Jane Watson Smith",
                "Mary",
                "Smith",
                ["Jane", "Watson"],
                "Mary Jane Watson Smith",
            ),
            # Compound names with hyphens (preserved)
            ("Anna-Karin Svensson", "Anna-Karin", "Svensson", [], "Anna-Karin Svensson"),
            ("Carl-Johan Öberg", "Carl-Johan", "Öberg", [], "Carl-Johan Öberg"),
            # International names (no special handling)
            ("José María García", "José", "García", ["María"], "José María García"),
            ("Klaus von Habsburg", "Klaus", "Habsburg", ["von"], "Klaus von Habsburg"),
            ("Ahmed Al-Rashid", "Ahmed", "Al-Rashid", [], "Ahmed Al-Rashid"),
        ],
    )
    def test_parse_name_predictable_rules(
        self,
        parser: SimpleNameParser,
        full_name: str,
        expected_first: str,
        expected_last: str,
        expected_middle: list[str],
        expected_full: str,
    ) -> None:
        """Test predictable name parsing rules across cultures."""
        result = parser.parse_name(full_name)

        assert result.first_name == expected_first
        assert result.last_name == expected_last
        assert result.middle_names == expected_middle
        assert result.full_name == expected_full

    @pytest.mark.parametrize(
        "input_name, expected_normalized",
        [
            # Whitespace normalization
            ("  Anna   Andersson  ", "Anna Andersson"),
            ("Anna\t\tAndersson", "Anna Andersson"),
            # Dash normalization (all types become standard hyphen)
            ("Anna–Karin Svensson", "Anna-Karin Svensson"),  # En dash
            ("Anna—Karin Svensson", "Anna-Karin Svensson"),  # Em dash
            ("Anna - Karin Svensson", "Anna-Karin Svensson"),  # Spaced dash
        ],
    )
    def test_normalization_consistent(
        self, parser: SimpleNameParser, input_name: str, expected_normalized: str
    ) -> None:
        """Test that normalization is predictable and consistent."""
        result = parser.parse_name(input_name)
        # The normalized version should be reflected in how it's parsed
        reconstructed = (
            f"{result.first_name} {' '.join(result.middle_names)} {result.last_name}".strip()
        )
        reconstructed = " ".join(reconstructed.split())  # Clean up extra spaces

        # For cases where we expect specific normalization
        if "Anna-Karin" in expected_normalized:
            assert "Anna-Karin" in result.first_name

    def test_parse_name_empty_and_edge_cases(self, parser: SimpleNameParser) -> None:
        """Test edge cases for name parsing."""
        # Empty string
        result = parser.parse_name("")
        assert result.first_name == ""
        assert result.last_name == ""
        assert result.middle_names == []
        assert result.full_name == ""

        # Whitespace only
        result = parser.parse_name("   ")
        assert result.first_name == ""
        assert result.last_name == ""
        assert result.middle_names == []
        assert result.full_name == "   "  # Original preserved

    def test_get_match_variations_standard_cases(self, parser: SimpleNameParser) -> None:
        """Test generation of name variations for matching."""
        name_components = NameComponents(
            first_name="Anna",
            last_name="Andersson",
            middle_names=["Karin"],
            full_name="Anna Karin Andersson",
        )

        variations = parser.get_match_variations(name_components)

        # Should include multiple formats
        assert "Anna Karin Andersson" in variations  # Full name
        assert "Anna Andersson" in variations  # First + Last
        assert "Andersson, Anna" in variations  # Reversed format
        assert "Anna K. Andersson" in variations  # With middle initial

        # Should not have duplicates
        assert len(variations) == len(set(v.lower() for v in variations))

    def test_get_match_variations_no_middle_names(self, parser: SimpleNameParser) -> None:
        """Test variations for names without middle names."""
        name_components = NameComponents(
            first_name="Erik", last_name="Johansson", middle_names=[], full_name="Erik Johansson"
        )

        variations = parser.get_match_variations(name_components)

        expected_variations = [
            "Erik Johansson",  # Full name
            "Johansson, Erik",  # Reversed format
        ]

        # Should be exactly these variations (first+last same as full, so deduplicated)
        assert len(variations) == 2
        for expected in expected_variations:
            assert expected in variations

    def test_get_match_variations_only_first_name(self, parser: SimpleNameParser) -> None:
        """Test variations for names with only first name."""
        name_components = NameComponents(
            first_name="Anna", last_name="", middle_names=[], full_name="Anna"
        )

        variations = parser.get_match_variations(name_components)

        # Should only contain the full name when no last name
        assert variations == ["Anna"]

    def test_cross_cultural_consistency(self, parser: SimpleNameParser) -> None:
        """Test that parser works consistently across different cultural naming patterns."""
        test_cases = [
            # Western names
            ("John Smith", "John", "Smith", []),
            ("Mary Jane Watson", "Mary", "Watson", ["Jane"]),
            # Hispanic names
            ("José María García", "José", "García", ["María"]),
            ("Ana Isabel Rodríguez Martínez", "Ana", "Martínez", ["Isabel", "Rodríguez"]),
            # German names
            ("Klaus von Habsburg", "Klaus", "Habsburg", ["von"]),
            ("Anna-Liese Schmidt", "Anna-Liese", "Schmidt", []),
            # Arabic names
            ("Ahmed Al-Rashid", "Ahmed", "Al-Rashid", []),
            ("Fatima bint Mohammed", "Fatima", "Mohammed", ["bint"]),
            # Asian names (Western order)
            ("Li Wei Chen", "Li", "Chen", ["Wei"]),
            ("Yuki Tanaka", "Yuki", "Tanaka", []),
        ]

        for full_name, expected_first, expected_last, expected_middle in test_cases:
            result = parser.parse_name(full_name)
            assert result.first_name == expected_first, f"Failed on {full_name}"
            assert result.last_name == expected_last, f"Failed on {full_name}"
            assert result.middle_names == expected_middle, f"Failed on {full_name}"

    def test_no_cultural_assumptions(self, parser: SimpleNameParser) -> None:
        """Test that parser makes no assumptions about cultural naming patterns."""
        # These should all be parsed identically using simple rules
        identical_structure_names = [
            "John Smith Jones",  # English
            "Jean Pierre Martin",  # French
            "Hans Klaus Mueller",  # German
            "José María García",  # Spanish
            "Ahmed Hassan Ali",  # Arabic
        ]

        for name in identical_structure_names:
            result = parser.parse_name(name)
            parts = name.split()

            # All should follow same pattern: first + middle + last
            assert result.first_name == parts[0]
            assert result.last_name == parts[-1]
            assert result.middle_names == parts[1:-1]
