"""Text validation edge case tests for grammar routes.

Tests focus on text content validation including length constraints,
special characters, and encoding scenarios.
"""

from __future__ import annotations

import pytest


class TestTextLengthValidation:
    """Tests for text length validation."""

    @pytest.mark.parametrize(
        "text, expected_status",
        [
            # Valid lengths
            ("a", 200),  # 1 character minimum
            ("a" * 50000, 200),  # 50000 character maximum
            ("Valid text with normal length.", 200),
            # Invalid lengths
            ("", 400),  # Empty string
            ("a" * 50001, 400),  # Exceeds maximum
        ],
    )
    async def test_text_length_constraints(
        self, test_client, text: str, expected_status: int
    ) -> None:
        """Test grammar check endpoint enforces text length constraints."""
        # Arrange
        request_body = {"text": text, "language": "en-US"}

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == expected_status

        if expected_status == 400:
            response_data = await response.get_json()
            assert "error" in response_data
            assert response_data["error"]["code"] == "VALIDATION_ERROR"
            assert (
                "at least 1 character" in response_data["error"]["message"]
                or "at most 50000 characters" in response_data["error"]["message"]
            )

    async def test_empty_text_rejected(self, test_client) -> None:
        """Test that empty text string is properly rejected."""
        # Arrange
        request_body = {"text": "", "language": "en-US"}

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 400
        response_data = await response.get_json()
        assert "error" in response_data
        assert "at least 1 character" in response_data["error"]["message"]

    async def test_whitespace_only_text_accepted(self, test_client) -> None:
        """Test that whitespace-only text is accepted (valid edge case)."""
        # Arrange
        request_body = {"text": "   \n\t  ", "language": "en-US"}

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        assert response_data["total_grammar_errors"] == 0


class TestSpecialCharacterHandling:
    """Tests for special character and encoding scenarios."""

    @pytest.mark.parametrize(
        "text",
        [
            # Swedish characters
            "Jag älskar att äta köttbullar med lingonsylt.",
            "Åsa bor i Örebro och har många vänner där.",
            "ÅÄÖ åäö - svenska bokstäver",
            # Emojis and special unicode
            "This is a test with emojis 😀 🎉 🚀",
            "Mixed content: Hello 世界 مرحبا мир",
            # Special punctuation
            "Test with special punctuation: « » — – … ¿¡",
            # Mixed encodings
            "Café, naïve, résumé - diacritical marks",
        ],
    )
    async def test_special_characters_accepted(self, test_client, text: str) -> None:
        """Test that special characters and encodings are properly handled."""
        # Arrange
        request_body = {"text": text, "language": "en-US"}

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        assert "errors" in response_data
        assert "total_grammar_errors" in response_data
        assert response_data["language"] == "en-US"

    async def test_swedish_text_with_swedish_language(self, test_client) -> None:
        """Test Swedish text with Swedish language code."""
        # Arrange
        request_body = {"text": "Detta är en svensk text med åäö tecken.", "language": "sv-SE"}

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        assert response_data["language"] == "sv-SE"

    @pytest.mark.parametrize(
        "text",
        [
            "Line 1\nLine 2\nLine 3",  # Unix line endings
            "Line 1\r\nLine 2\r\nLine 3",  # Windows line endings
            "Line 1\rLine 2\rLine 3",  # Old Mac line endings
            "Paragraph 1\n\nParagraph 2\n\nParagraph 3",  # Multiple line breaks
            "\n\nText with leading newlines",
            "Text with trailing newlines\n\n",
        ],
    )
    async def test_multiline_text_handling(self, test_client, text: str) -> None:
        """Test that multiline text is properly handled."""
        # Arrange
        request_body = {"text": text, "language": "en-US"}

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        assert "errors" in response_data

    async def test_html_entities_in_text(self, test_client) -> None:
        """Test that HTML entities in text are handled."""
        # Arrange
        request_body = {
            "text": "Text with &lt;html&gt; entities &amp; special &quot;quotes&quot;",
            "language": "en-US",
        }

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        assert "errors" in response_data

    async def test_very_long_single_word(self, test_client) -> None:
        """Test handling of very long single words."""
        # Arrange
        long_word = "a" * 1000  # 1000 character word
        request_body = {
            "text": f"This text contains a very long word: {long_word}",
            "language": "en-US",
        }

        # Act
        response = await test_client.post("/v1/check", json=request_body)

        # Assert
        assert response.status_code == 200
        response_data = await response.get_json()
        assert "errors" in response_data
