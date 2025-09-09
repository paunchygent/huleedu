"""Unit tests for Grammar models."""

from __future__ import annotations

import json

import pytest
from common_core.events.nlp_events import GrammarAnalysis, GrammarError


class TestGrammarError:
    """Test GrammarError model."""

    def test_grammar_error_creation_with_all_fields(self) -> None:
        """Test creating a GrammarError with all required fields."""
        error = GrammarError(
            rule_id="CONFUSION_RULE_ID",
            message="Possible confusion between 'their' and 'there'",
            short_message="Word confusion",
            offset=15,
            length=5,
            replacements=["there"],
            category="grammar",
            severity="warning",
            category_id="GRAMMAR",
            category_name="Grammar",
            context="I think their essay is over there.",
            context_offset=2,
        )

        # Verify all fields are properly set
        assert error.rule_id == "CONFUSION_RULE_ID"
        assert error.message == "Possible confusion between 'their' and 'there'"
        assert error.short_message == "Word confusion"
        assert error.offset == 15
        assert error.length == 5
        assert error.replacements == ["there"]
        assert error.category == "grammar"
        assert error.severity == "warning"
        assert error.category_id == "GRAMMAR"
        assert error.category_name == "Grammar"
        assert error.context == "I think their essay is over there."
        assert error.context_offset == 2

    def test_grammar_error_serialization_round_trip(self) -> None:
        """Test serialization and deserialization of GrammarError."""
        original_error = GrammarError(
            rule_id="DOUBLE_SPACE",
            message="Double space detected",
            short_message="Extra space",
            offset=10,
            length=2,
            replacements=[" "],
            category="typography",
            severity="info",
            category_id="PUNCTUATION",
            category_name="Punctuation",
            context="Some text  with double space.",
            context_offset=3,
        )

        # Serialize to JSON
        json_data = original_error.model_dump(mode="json")
        json_str = json.dumps(json_data)

        # Deserialize back
        loaded_data = json.loads(json_str)
        restored_error = GrammarError(**loaded_data)

        # Verify all fields match
        assert restored_error.rule_id == original_error.rule_id
        assert restored_error.message == original_error.message
        assert restored_error.short_message == original_error.short_message
        assert restored_error.offset == original_error.offset
        assert restored_error.length == original_error.length
        assert restored_error.replacements == original_error.replacements
        assert restored_error.category == original_error.category
        assert restored_error.severity == original_error.severity
        assert restored_error.category_id == original_error.category_id
        assert restored_error.category_name == original_error.category_name
        assert restored_error.context == original_error.context
        assert restored_error.context_offset == original_error.context_offset

    def test_grammar_error_field_validation(self) -> None:
        """Test field validation for GrammarError."""
        # Test that all required fields must be provided
        with pytest.raises(ValueError, match="Field required"):
            GrammarError()

        # Test that offset must be non-negative (if we add validation)
        error = GrammarError(
            rule_id="TEST_RULE",
            message="Test message",
            short_message="Test",
            offset=-1,  # Negative offset should work for now, as no validation added
            length=1,
            category="test",
            category_id="TEST",
            category_name="Test",
            context="test context",
            context_offset=0,
        )
        assert error.offset == -1  # Current behavior, no validation

    def test_grammar_error_default_values(self) -> None:
        """Test default values for optional fields."""
        error = GrammarError(
            rule_id="TEST_RULE",
            message="Test message",
            short_message="Test",
            offset=0,
            length=1,
            category="test",
            category_id="TEST",
            category_name="Test",
            context="test context",
            context_offset=0,
        )

        # Test default values
        assert error.replacements == []  # default_factory=list
        assert error.severity == "info"  # default="info"

    def test_grammar_error_json_schema_generation(self) -> None:
        """Test JSON schema generation includes new fields."""
        schema = GrammarError.model_json_schema()
        # Verify all fields are in the schema
        properties = schema["properties"]
        assert "rule_id" in properties
        assert "message" in properties
        assert "short_message" in properties
        assert "offset" in properties
        assert "length" in properties
        assert "replacements" in properties
        assert "category" in properties
        assert "severity" in properties
        assert "category_id" in properties
        assert "category_name" in properties
        assert "context" in properties
        assert "context_offset" in properties

        # Verify required fields
        required_fields = schema["required"]
        expected_required = [
            "rule_id",
            "message",
            "short_message",
            "offset",
            "length",
            "category",
            "category_id",
            "category_name",
            "context",
            "context_offset",
        ]
        for field in expected_required:
            assert field in required_fields


class TestGrammarAnalysis:
    """Test GrammarAnalysis model."""

    def test_grammar_analysis_with_enhanced_errors(self) -> None:
        """Test GrammarAnalysis integration with enhanced GrammarError."""
        errors = [
            GrammarError(
                rule_id="GRAMMAR_RULE",
                message="Subject-verb disagreement",
                short_message="Grammar error",
                offset=10,
                length=3,
                replacements=["are"],
                category="grammar",
                severity="error",
                category_id="GRAMMAR",
                category_name="Grammar",
                context="The students is working hard.",
                context_offset=4,
            ),
            GrammarError(
                rule_id="PUNCT_RULE",
                message="Missing comma before conjunction",
                short_message="Punctuation",
                offset=25,
                length=1,
                replacements=[", and"],
                category="punctuation",
                severity="warning",
                category_id="PUNCTUATION",
                category_name="Punctuation",
                context="We studied hard and we passed.",
                context_offset=15,
            ),
        ]

        analysis = GrammarAnalysis(
            error_count=2,
            errors=errors,
            language="en",
            processing_time_ms=150,
        )

        assert analysis.error_count == 2
        assert len(analysis.errors) == 2
        assert analysis.language == "en"
        assert analysis.processing_time_ms == 150

        # Verify first error
        first_error = analysis.errors[0]
        assert first_error.category_id == "GRAMMAR"
        assert first_error.category_name == "Grammar"
        assert first_error.context == "The students is working hard."
        assert first_error.context_offset == 4

        # Verify second error
        second_error = analysis.errors[1]
        assert second_error.category_id == "PUNCTUATION"
        assert second_error.category_name == "Punctuation"
        assert second_error.context == "We studied hard and we passed."
        assert second_error.context_offset == 15

    def test_grammar_analysis_serialization_with_enhanced_errors(self) -> None:
        """Test GrammarAnalysis serialization includes new error fields."""
        error = GrammarError(
            rule_id="TEST_RULE",
            message="Test error",
            short_message="Test",
            offset=0,
            length=1,
            category="test",
            category_id="TEST_CAT",
            category_name="Test Category",
            context="Test context text",
            context_offset=5,
        )

        analysis = GrammarAnalysis(
            error_count=1,
            errors=[error],
            language="en",
        )

        # Serialize to dict
        analysis_dict = analysis.model_dump(mode="json")

        # Verify structure
        assert "error_count" in analysis_dict
        assert "errors" in analysis_dict
        assert len(analysis_dict["errors"]) == 1
        error_dict = analysis_dict["errors"][0]
        assert "category_id" in error_dict
        assert "category_name" in error_dict
        assert "context" in error_dict
        assert "context_offset" in error_dict
        assert error_dict["category_id"] == "TEST_CAT"
        assert error_dict["category_name"] == "Test Category"
        assert error_dict["context"] == "Test context text"
        assert error_dict["context_offset"] == 5
