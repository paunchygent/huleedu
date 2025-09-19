"""
Comprehensive behavioral tests for LanguageTool service API models following Rule 075 methodology.

Tests focus on Pydantic model behavior, not implementation details:
- Model creation and field validation
- Serialization and deserialization behavior
- Default value handling and required field validation
- Swedish character handling (åäöÅÄÖ) for text processing models
- Edge cases and boundary conditions for LanguageTool-specific data

All tests use direct model instantiation without @patch usage.
"""

from __future__ import annotations

from typing import Any

import pytest
from common_core.api_models.language_tool import (
    GrammarCheckRequest,
    GrammarCheckResponse,
)
from pydantic import ValidationError

from services.language_tool_service.api_models import (
    LanguageToolMatch,
    LanguageToolRawResponse,
)


class TestLanguageToolRawResponseModel:
    """Tests for LanguageToolRawResponse model creation and field validation."""

    @pytest.mark.parametrize(
        "language, software, warnings",
        [
            (
                {"name": "English", "code": "en-US", "detectedLanguage": "en"},
                {
                    "name": "LanguageTool",
                    "version": "6.3",
                    "buildDate": "2023-12-15",
                    "apiVersion": "1",
                },
                {"incompleteResults": "false"},
            ),
            (
                {"name": "Swedish", "code": "sv-SE", "detectedLanguage": "sv"},
                {
                    "name": "LanguageTool",
                    "version": "6.3",
                    "buildDate": "2023-12-15",
                    "apiVersion": "1",
                },
                {},
            ),
            (
                {"name": "German", "code": "de-DE", "detectedLanguage": "de"},
                {
                    "name": "LanguageTool",
                    "version": "6.2",
                    "buildDate": "2023-11-01",
                    "apiVersion": "1",
                },
                {"incompleteResults": "true", "languageDetectionWarning": "true"},
            ),
        ],
    )
    def test_languagetool_raw_response_creation_valid_fields(
        self, language: dict[str, Any], software: dict[str, Any], warnings: dict[str, Any]
    ) -> None:
        """Test LanguageToolRawResponse model creation with valid language detection data."""
        # Act
        response = LanguageToolRawResponse(
            matches=[],
            language=language,
            software=software,
            warnings=warnings,
        )

        # Assert
        assert response.matches == []
        assert response.language == language
        assert response.software == software
        assert response.warnings == warnings

    def test_languagetool_raw_response_default_values_and_empty_fields(self) -> None:
        """Test LanguageToolRawResponse handles default values for optional fields."""
        # Test with minimal required fields only
        minimal_response = LanguageToolRawResponse(language={"name": "English", "code": "en-US"})

        assert minimal_response.matches == []
        assert minimal_response.software == {}
        assert minimal_response.warnings == {}
        assert minimal_response.language == {"name": "English", "code": "en-US"}

    @pytest.mark.parametrize(
        "matches, expected_count",
        [
            ([], 0),
            ([{"message": "Test error", "offset": 0, "length": 5}], 1),
            (
                [
                    {"message": "First error", "offset": 0, "length": 5},
                    {"message": "Grammatikfel", "offset": 10, "length": 8},
                    {"message": "Stavfel med åäö", "offset": 20, "length": 3},
                ],
                3,
            ),
            (
                [
                    {
                        "message": "Error with Swedish: användare behöver åäö",
                        "offset": 0,
                        "length": 15,
                    },
                    {"message": "Multiple errors", "offset": 30, "length": 10},
                    {"message": "Final check", "offset": 45, "length": 5},
                    {"message": "One more", "offset": 55, "length": 4},
                    {"message": "Last one", "offset": 65, "length": 3},
                ],
                5,
            ),
        ],
    )
    def test_languagetool_raw_response_matches_handling(
        self, matches: list[dict[str, Any]], expected_count: int
    ) -> None:
        """Test LanguageToolRawResponse handles various match counts including Swedish content."""
        response = LanguageToolRawResponse(
            matches=matches, language={"name": "English", "code": "en-US"}
        )

        assert len(response.matches) == expected_count
        assert response.matches == matches

    def test_languagetool_raw_response_required_language_field(self) -> None:
        """Test LanguageToolRawResponse requires language field."""
        with pytest.raises(ValidationError) as exc_info:
            LanguageToolRawResponse(**{})  # Intentionally empty to test validation

        assert "language" in str(exc_info.value)
        assert "Field required" in str(exc_info.value)


class TestLanguageToolMatchModel:
    """Tests for LanguageToolMatch model creation and field validation."""

    @pytest.mark.parametrize(
        "message, short_message, offset, length, sentence",
        [
            ("This is a test error", "Test error", 0, 5, "This is a test sentence."),
            ("Grammar error detected", "", 10, 7, "A sentence with grammar error."),
            ("Stavfel hittades", "Stavfel", 5, 8, "Ett mening med stavfel här."),
            ("Grammatikfel med åäö", "Åäö-fel", 15, 3, "Texten innehåller åäö-tecken för test."),
            (
                "Längre meddelande om språkfel i svenska",
                "Språkfel",
                0,
                20,
                "Användaren behöver åtgärda åäö-problematik.",
            ),
            ("Punctuation error found", "Punct", 25, 1, "This sentence has punctuation, error."),
            ("Word order issue", "Order", 5, 10, "Swedish word order can be different."),
        ],
    )
    def test_languagetool_match_creation_valid_fields(
        self, message: str, short_message: str, offset: int, length: int, sentence: str
    ) -> None:
        """Test LanguageToolMatch model creation with valid fields including Swedish characters."""
        # Arrange
        context = {"text": "Sample context text", "offset": 0, "length": 50}
        error_type = {"typeName": "grammar"}
        rule = {"id": "TEST_RULE", "category": {"id": "GRAMMAR", "name": "Grammar"}}

        # Act
        match = LanguageToolMatch(
            message=message,
            shortMessage=short_message,
            offset=offset,
            length=length,
            replacements=[],
            context=context,
            sentence=sentence,
            type=error_type,
            rule=rule,
        )

        # Assert
        assert match.message == message
        assert match.shortMessage == short_message
        assert match.offset == offset
        assert match.length == length
        assert match.sentence == sentence
        assert match.context == context
        assert match.type == error_type
        assert match.rule == rule

    def test_languagetool_match_default_values_and_optional_fields(self) -> None:
        """Test LanguageToolMatch handles default values for optional fields."""
        # Test with minimal required fields
        minimal_match = LanguageToolMatch(
            message="Test error",
            offset=0,
            length=5,
            replacements=[],
            context={"text": "context"},
            sentence="Test sentence.",
            type={"typeName": "grammar"},
            rule={"id": "TEST_RULE"},
        )

        assert minimal_match.shortMessage == ""
        assert minimal_match.replacements == []
        assert minimal_match.ignoreForIncompleteSentence is False
        assert minimal_match.contextForSureMatch == 0

    @pytest.mark.parametrize(
        "replacements, ignore_incomplete, context_confidence",
        [
            ([], False, 0),
            ([{"value": "correction"}], True, 5),
            ([{"value": "första"}, {"value": "andra"}], False, 10),
            ([{"value": "åäö-korrigering"}], True, 8),
            (
                [{"value": "användare"}, {"value": "behöver"}, {"value": "svenska tecken åäö"}],
                False,
                15,
            ),
            ([{"value": "simple fix"}], True, 100),
        ],
    )
    def test_languagetool_match_field_combinations_with_swedish_content(
        self, replacements: list[dict[str, str]], ignore_incomplete: bool, context_confidence: int
    ) -> None:
        """Test LanguageToolMatch handles various field combinations inc. Swedish corrections."""
        match = LanguageToolMatch(
            message="Test grammar error",
            offset=5,
            length=10,
            replacements=replacements,
            context={"text": "Sample context with åäö", "offset": 0, "length": 25},
            sentence="Test sentence with potential åäö characters.",
            type={"typeName": "grammar"},
            rule={
                "id": "SWEDISH_GRAMMAR",
                "category": {"id": "GRAMMAR", "name": "Svenska grammatik"},
            },
            ignoreForIncompleteSentence=ignore_incomplete,
            contextForSureMatch=context_confidence,
        )

        assert match.replacements == replacements
        assert match.ignoreForIncompleteSentence == ignore_incomplete
        assert match.contextForSureMatch == context_confidence

    def test_languagetool_match_required_fields_validation(self) -> None:
        """Test LanguageToolMatch validates required fields."""
        with pytest.raises(ValidationError) as exc_info:
            LanguageToolMatch(**{})  # Intentionally empty to test validation

        error_fields = str(exc_info.value)
        required_fields = ["message", "offset", "length", "context", "sentence", "type", "rule"]

        for field in required_fields:
            assert field in error_fields

    @pytest.mark.parametrize(
        "offset, length",
        [
            (0, 1),  # Start of text
            (100, 50),  # Middle position
            (0, 0),  # Zero length (should be valid for insertion points)
            (1000, 1),  # Large offset
            (5, 100),  # Long error span
        ],
    )
    def test_languagetool_match_position_boundary_conditions(
        self, offset: int, length: int
    ) -> None:
        """Test LanguageToolMatch handles various position and length combinations."""
        match = LanguageToolMatch(
            message="Position test error",
            offset=offset,
            length=length,
            replacements=[],
            context={"text": "Context text for position testing", "offset": 0, "length": 50},
            sentence="Position test sentence.",
            type={"typeName": "position"},
            rule={"id": "POSITION_RULE"},
        )

        assert match.offset == offset
        assert match.length == length


class TestGrammarCheckRequestModel:
    """Tests for GrammarCheckRequest model validation and field constraints."""

    @pytest.mark.parametrize(
        "text, language",
        [
            ("Simple test text.", "en-US"),
            ("Enkel testtext på svenska.", "sv-SE"),
            ("Texto de prueba en español.", "es-ES"),
            ("Text mit deutschen Wörtern.", "de-DE"),
            ("Text with åäö Swedish characters included.", "sv-SE"),
            ("Användare behöver korrekt språkhantering.", "sv-SE"),
            ("Längre text som innehåller flera meningar. Detta är andra meningen.", "sv-SE"),
            ("A" * 1000, "en-US"),  # Long text boundary test
            ("Single word", "en-US"),
        ],
    )
    def test_grammar_check_request_valid_fields(self, text: str, language: str) -> None:
        """Test GrammarCheckRequest model creation with valid text and language codes."""
        # Act
        request = GrammarCheckRequest(text=text, language=language)

        # Assert
        assert request.text == text
        assert request.language == language

    def test_grammar_check_request_default_language(self) -> None:
        """Test GrammarCheckRequest uses default language when not specified."""
        request = GrammarCheckRequest(text="Test text without language specified.")

        assert request.text == "Test text without language specified."
        assert request.language == "en-US"

    def test_grammar_check_request_accepts_alias_input(self) -> None:
        """Ensure camelCase API fields populate model attributes."""
        request = GrammarCheckRequest.model_validate(
            {
                "text": "Alias field input",
                "language": "en-US",
                "enabledCategories": ["GRAMMAR"],
                "enabledRules": ["RULE_1"],
            }
        )

        assert request.enabled_categories == ["GRAMMAR"]
        assert request.enabled_rules == ["RULE_1"]

    def test_grammar_check_request_alias_and_payload_conversion(self) -> None:
        """Ensure optional request settings are accepted and serialized for LanguageTool."""
        request = GrammarCheckRequest(
            text="Intro clause should trigger comma rule.",
            language="en-US",
            level="picky",
            enabledCategories=["GRAMMAR", "PUNCTUATION"],
            disabledRules=["SOME_RULE"],
            enabledOnly=True,
        )

        payload = request.to_languagetool_payload()

        assert request.level == "picky"
        assert request.enabled_categories == ["GRAMMAR", "PUNCTUATION"]
        assert request.disabled_rules == ["SOME_RULE"]
        assert payload["level"] == "picky"
        assert payload["enabledCategories"] == "GRAMMAR,PUNCTUATION"
        assert payload["disabledRules"] == "SOME_RULE"
        assert payload["enabledOnly"] == "true"

    @pytest.mark.parametrize(
        "invalid_text, error_type",
        [
            ("", "too_short"),  # Empty text
            ("A" * 50001, "too_long"),  # Text exceeding maximum length
        ],
    )
    def test_grammar_check_request_text_validation_errors(
        self, invalid_text: str, error_type: str
    ) -> None:
        """Test GrammarCheckRequest validates text length constraints."""
        with pytest.raises(ValidationError) as exc_info:
            GrammarCheckRequest(text=invalid_text)

        error_msg = str(exc_info.value)
        if error_type == "too_short":
            assert (
                "at least 1 character" in error_msg
                or "String should have at least 1 character" in error_msg
            )
        elif error_type == "too_long":
            assert (
                "at most 50000 character" in error_msg
                or "String should have at most 50000 characters" in error_msg
            )

    @pytest.mark.parametrize(
        "invalid_language",
        [
            "invalid",  # No hyphen format
            "english",  # Full language name
            "en-usa",  # Lowercase country
            "ENG-US",  # Wrong language format
            "sv_SE",  # Underscore instead of hyphen
            "123-45",  # Numbers instead of letters
            "",  # Empty string
            "en-",  # Missing country
            "-US",  # Missing language
            "en-USA",  # Three-letter country code
        ],
    )
    def test_grammar_check_request_language_validation_errors(self, invalid_language: str) -> None:
        """Test GrammarCheckRequest validates language code format."""
        with pytest.raises(ValidationError) as exc_info:
            GrammarCheckRequest(text="Valid text.", language=invalid_language)

        error_msg = str(exc_info.value)
        assert "String should match pattern" in error_msg or "does not match" in error_msg


class TestGrammarCheckResponseModel:
    """Tests for GrammarCheckResponse model validation and field behavior."""

    @pytest.mark.parametrize(
        "total_errors, category_counts, rule_counts, language, processing_time",
        [
            (0, {}, {}, "en-US", 100),
            (3, {"GRAMMAR": 2, "PUNCTUATION": 1}, {"RULE_1": 2, "RULE_2": 1}, "sv-SE", 250),
            (
                5,
                {"GRAMMAR": 3, "SPELLING": 2},
                {"SPELL_ERROR": 2, "GRAMMAR_ERROR": 3},
                "de-DE",
                500,
            ),
            (1, {"PUNCTUATION": 1}, {"COMMA_SPLICE": 1}, "es-ES", 75),
            (
                10,
                {"GRAMMAR": 4, "PUNCTUATION": 3, "SPELLING": 2, "STYLE": 1},
                {"GRAMMAR_RULE": 4, "PUNCT_RULE": 3, "SPELL_RULE": 2, "STYLE_RULE": 1},
                "sv-SE",
                1000,
            ),
        ],
    )
    def test_grammar_check_response_creation_valid_fields(
        self,
        total_errors: int,
        category_counts: dict[str, int],
        rule_counts: dict[str, int],
        language: str,
        processing_time: int,
    ) -> None:
        """Test GrammarCheckResponse model creation with valid statistical data."""
        # Act
        response = GrammarCheckResponse(
            errors=[],
            total_grammar_errors=total_errors,
            grammar_category_counts=category_counts,
            grammar_rule_counts=rule_counts,
            language=language,
            processing_time_ms=processing_time,
        )

        # Assert
        assert response.errors == []
        assert response.total_grammar_errors == total_errors
        assert response.grammar_category_counts == category_counts
        assert response.grammar_rule_counts == rule_counts
        assert response.language == language
        assert response.processing_time_ms == processing_time

    def test_grammar_check_response_default_values_and_required_fields(self) -> None:
        """Test GrammarCheckResponse handles default values and validates required fields."""
        # Test with minimal required fields
        minimal_response = GrammarCheckResponse(
            total_grammar_errors=2,
            language="en-US",
            processing_time_ms=150,
        )

        assert minimal_response.errors == []
        assert minimal_response.grammar_category_counts == {}
        assert minimal_response.grammar_rule_counts == {}
        assert minimal_response.total_grammar_errors == 2
        assert minimal_response.language == "en-US"
        assert minimal_response.processing_time_ms == 150

    @pytest.mark.parametrize(
        "errors",
        [
            [],
            [{"message": "Simple error", "offset": 0, "length": 5, "category": "GRAMMAR"}],
            [
                {"message": "First error", "offset": 0, "length": 3, "category": "GRAMMAR"},
                {
                    "message": "Second error with åäö",
                    "offset": 10,
                    "length": 8,
                    "category": "SPELLING",
                },
            ],
            [
                {
                    "message": "Complex Swedish error: användare behöver åäö",
                    "offset": 15,
                    "length": 12,
                    "category": "GRAMMAR",
                    "rule_id": "SWEDISH_GRAMMAR",
                    "suggestions": ["användaren", "användarna"],
                }
            ],
            [
                {"message": f"Error {i}", "offset": i * 10, "length": 5, "category": "TEST"}
                for i in range(5)
            ],
        ],
    )
    def test_grammar_check_response_errors_handling_with_swedish_content(
        self, errors: list[dict[str, Any]]
    ) -> None:
        """Test GrammarCheckResponse handles various error structures including Swedish content."""
        response = GrammarCheckResponse(
            errors=errors,
            total_grammar_errors=len(errors),
            language="sv-SE",
            processing_time_ms=200,
        )

        assert response.errors == errors
        assert len(response.errors) == len(errors)

    @pytest.mark.parametrize(
        "invalid_total_errors, invalid_processing_time",
        [
            (-1, 100),  # Negative error count
            (0, -1),  # Negative processing time
            (-5, -10),  # Both negative
        ],
    )
    def test_grammar_check_response_validation_errors(
        self, invalid_total_errors: int, invalid_processing_time: int
    ) -> None:
        """Test GrammarCheckResponse validates non-negative integer constraints."""
        with pytest.raises(ValidationError) as exc_info:
            GrammarCheckResponse(
                total_grammar_errors=invalid_total_errors,
                language="en-US",
                processing_time_ms=invalid_processing_time,
            )

        error_msg = str(exc_info.value)
        assert (
            "greater than or equal to 0" in error_msg
            or "Input should be greater than or equal to 0" in error_msg
        )

    def test_grammar_check_response_required_fields_validation(self) -> None:
        """Test GrammarCheckResponse validates all required fields."""
        with pytest.raises(ValidationError) as exc_info:
            GrammarCheckResponse(**{})  # Intentionally empty to test validation

        error_msg = str(exc_info.value)
        required_fields = ["total_grammar_errors", "language", "processing_time_ms"]

        for field in required_fields:
            assert field in error_msg


class TestModelSerializationBehavior:
    """Tests for Pydantic model serialization and deserialization behavior."""

    def test_languagetool_raw_response_serialization_roundtrip(self) -> None:
        """Test LanguageToolRawResponse serialization and deserialization preserves data."""
        # Arrange
        original_data = {
            "matches": [{"message": "Test error with åäö", "offset": 5, "length": 3}],
            "language": {"name": "Swedish", "code": "sv-SE", "detectedLanguage": "sv"},
            "software": {"name": "LanguageTool", "version": "6.3", "buildDate": "2023-12-15"},
            "warnings": {"incompleteResults": "false"},
        }

        # Act - Create model, serialize, then deserialize
        response = LanguageToolRawResponse(**original_data)
        serialized = response.model_dump()
        deserialized = LanguageToolRawResponse(**serialized)

        # Assert
        assert deserialized.matches == original_data["matches"]
        assert deserialized.language == original_data["language"]
        assert deserialized.software == original_data["software"]
        assert deserialized.warnings == original_data["warnings"]

    def test_languagetool_match_serialization_roundtrip(self) -> None:
        """Test LanguageToolMatch serialization and deserialization preserves Swedish characters."""
        # Arrange
        original_data = {
            "message": "Grammatikfel med svenska tecken åäöÅÄÖ",
            "shortMessage": "Åäö-fel",
            "offset": 10,
            "length": 15,
            "replacements": [{"value": "användare"}, {"value": "åäö-korrigering"}],
            "context": {"text": "Kontext med åäö-tecken", "offset": 0, "length": 25},
            "sentence": "Användaren behöver åtgärda åäö-problematik.",
            "type": {"typeName": "grammar"},
            "rule": {"id": "SWEDISH_RULE", "category": {"name": "Svenska"}},
            "ignoreForIncompleteSentence": True,
            "contextForSureMatch": 95,
        }

        # Act - Create model, serialize, then deserialize
        match = LanguageToolMatch(**original_data)
        serialized = match.model_dump()
        deserialized = LanguageToolMatch(**serialized)

        # Assert
        assert deserialized.message == original_data["message"]
        assert deserialized.shortMessage == original_data["shortMessage"]
        assert deserialized.replacements == original_data["replacements"]
        assert deserialized.context == original_data["context"]
        assert deserialized.sentence == original_data["sentence"]
        assert (
            deserialized.ignoreForIncompleteSentence == original_data["ignoreForIncompleteSentence"]
        )

    def test_grammar_check_models_serialization_roundtrip(self) -> None:
        """Test GrammarCheck request/response models preserve data through serialization."""
        # Test request serialization
        request_data = {
            "text": "Testtext med svenska tecken åäöÅÄÖ för validering.",
            "language": "sv-SE",
        }
        request = GrammarCheckRequest(**request_data)
        request_serialized = request.model_dump()
        request_deserialized = GrammarCheckRequest(**request_serialized)

        assert request_deserialized.text == request_data["text"]
        assert request_deserialized.language == request_data["language"]

        # Test response serialization
        response_data = {
            "errors": [{"message": "Fel med åäö", "category": "GRAMMAR"}],
            "total_grammar_errors": 1,
            "grammar_category_counts": {"GRAMMAR": 1},
            "grammar_rule_counts": {"SWEDISH_RULE": 1},
            "language": "sv-SE",
            "processing_time_ms": 125,
        }
        response = GrammarCheckResponse(**response_data)
        response_serialized = response.model_dump()
        response_deserialized = GrammarCheckResponse(**response_serialized)

        assert response_deserialized.errors == response_data["errors"]
        assert response_deserialized.total_grammar_errors == response_data["total_grammar_errors"]
        assert response_deserialized.language == response_data["language"]
