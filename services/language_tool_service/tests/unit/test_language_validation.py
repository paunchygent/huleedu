"""Language code validation tests for grammar routes.

Tests focus on language field validation and format requirements.
"""

from __future__ import annotations

import pytest


class TestLanguageValidation:
    """Tests for language code validation."""

    @pytest.mark.parametrize(
        "language, expected_status",
        [
            # Valid language codes
            ("en-US", 200),
            ("en-GB", 200),
            ("sv-SE", 200),
            ("de-DE", 200),
            ("fr-FR", 200),
            ("es-ES", 200),
            ("it-IT", 200),
            ("pt-PT", 200),
            ("pt-BR", 200),
            ("nl-NL", 200),
            ("pl-PL", 200),
            ("ru-RU", 200),
            ("auto", 200),
            # Invalid language codes
            ("invalid", 400),
            ("english", 400),
            ("en", 400),  # Missing country code
            ("US", 400),  # Missing language code
            ("en-usa", 400),  # Wrong format
            ("en_US", 400),  # Underscore instead of hyphen
            ("EN-US", 400),  # Wrong case for language part
            ("en-us", 400),  # Wrong case for country part
        ],
    )
    async def test_language_code_validation(
        self, test_client, language: str, expected_status: int
    ) -> None:
        """Test grammar check endpoint validates language codes properly."""
        # Arrange
        request_body = {"text": "Test text for language validation.", "language": language}

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == expected_status

        if expected_status == 400:
            response_data = await response.get_json()
            assert "error" in response_data
            assert response_data["error"]["code"] == "VALIDATION_ERROR"
            assert "String should match pattern" in response_data["error"]["message"]

    async def test_missing_language_defaults_to_en_us(self, test_client) -> None:
        """Test that missing language field defaults to en-US."""
        # Arrange
        request_body = {"text": "Test text without language field."}

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        assert response_data["language"] == "en-US"

    @pytest.mark.parametrize(
        "language",
        [
            "en-US",
            "sv-SE",
            "de-DE",
            "fr-FR",
            "es-ES",
        ],
    )
    async def test_language_preserved_in_response(
        self, test_client, language: str
    ) -> None:
        """Test that the language from request is preserved in response."""
        # Arrange
        request_body = {
            "text": "Test text to verify language preservation.",
            "language": language,
        }

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        assert response_data["language"] == language

    async def test_auto_language_detection(self, test_client) -> None:
        """Test that 'auto' language code is accepted for automatic detection."""
        # Arrange
        request_body = {
            "text": "This text should have its language automatically detected.",
            "language": "auto",
        }

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        assert response_data["language"] == "auto"

    @pytest.mark.parametrize(
        "text, language",
        [
            ("Hello, how are you today?", "en-US"),
            ("Hej, hur mår du idag?", "sv-SE"),
            ("Guten Tag, wie geht es Ihnen?", "de-DE"),
            ("Bonjour, comment allez-vous?", "fr-FR"),
            ("Hola, ¿cómo estás?", "es-ES"),
        ],
    )
    async def test_language_specific_text_processing(
        self, test_client, text: str, language: str
    ) -> None:
        """Test that different languages are processed correctly."""
        # Arrange
        request_body = {"text": text, "language": language}

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        assert response_data["language"] == language
        assert "errors" in response_data
        assert isinstance(response_data["errors"], list)