"""Unit tests for core logic in the Class Management Service."""

import pytest

from services.class_management_service.core_logic import parse_student_name


@pytest.mark.parametrize(
    "full_name, expected_first, expected_last, expected_confidence",
    [
        ("Anna Andersson", "Anna", "Andersson", 0.9),
        ("Erik Johan Svensson", "Erik Johan", "Svensson", 0.9),
        ("Svensson", "", "Svensson", 0.5),
        ("", "", "", 0.0),
        ("  Björn  ", "", "Björn", 0.5),
    ],
)
def test_parse_student_name(
    full_name: str, expected_first: str, expected_last: str, expected_confidence: float
) -> None:
    """Test student name parsing for various formats."""
    result = parse_student_name(full_name)

    assert result.parsed_name.parsed_name.first_name == expected_first
    assert result.parsed_name.parsed_name.last_name == expected_last
    assert result.confidence == expected_confidence
