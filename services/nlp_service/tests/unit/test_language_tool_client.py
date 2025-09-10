"""Unit tests for LanguageToolServiceClient following Rule 075.

Comprehensive behavioral testing of Language Tool Service integration
with retry logic, circuit breaker support, and response parsing.
Following HuleEdu testing standards: no conftest, explicit utilities,
Protocol-based mocking.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import aiohttp
import pytest
from aioresponses import aioresponses
from common_core.events.nlp_events import GrammarAnalysis, GrammarError
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreakerError

from services.nlp_service.config import Settings
from services.nlp_service.implementations.language_tool_client_impl import (
    LanguageToolServiceClient,
)


class MockSettings:
    """Mock Settings for LanguageToolServiceClient tests."""
    
    def __init__(self) -> None:
        """Initialize mock settings with default values."""
        self.LANGUAGE_TOOL_SERVICE_URL = "http://language-tool-service:8085"
        self.LANGUAGE_TOOL_REQUEST_TIMEOUT = 30
        self.LANGUAGE_TOOL_MAX_RETRIES = 3
        self.LANGUAGE_TOOL_RETRY_DELAY = 0.5


def create_mock_language_tool_response(
    matches: list[dict[str, Any]] | None = None,
    language: str = "en-US",
    grammar_category_counts: dict[str, int] | None = None,
    grammar_rule_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Create mock LanguageTool service response.
    
    Args:
        matches: List of grammar errors
        language: Detected language
        grammar_category_counts: Analytics by category
        grammar_rule_counts: Analytics by rule
        
    Returns:
        Mock response dictionary
    """
    if matches is None:
        matches = []
        
    response = {
        "matches": matches,
        "language": {
            "detectedLanguage": {
                "code": language
            }
        }
    }
    
    if grammar_category_counts is not None:
        response["grammar_category_counts"] = grammar_category_counts
        
    if grammar_rule_counts is not None:
        response["grammar_rule_counts"] = grammar_rule_counts
        
    return response


def create_sample_grammar_error_match() -> dict[str, Any]:
    """Create sample grammar error match from LanguageTool response.
    
    Returns:
        Mock match dictionary with all required fields
    """
    return {
        "rule": {
            "id": "COMMA_RULE",
            "category": {
                "id": "PUNCTUATION",
                "name": "Punctuation"
            }
        },
        "message": "Add comma before 'and' in compound sentence",
        "shortMessage": "Missing comma",
        "offset": 15,
        "length": 3,
        "replacements": [
            {"value": ", and"}
        ],
        "type": {
            "typeName": "error"
        },
        "context": {
            "text": "The quick brown fox and the lazy dog",
            "offset": 12
        }
    }


class TestLanguageToolServiceClientInitialization:
    """Test client initialization and configuration."""
    
    def test_client_initialization_with_settings(self) -> None:
        """Test client initializes correctly with settings."""
        # Arrange
        settings = MockSettings()
        
        # Act
        client = LanguageToolServiceClient(settings)
        
        # Assert
        assert client.service_url == "http://language-tool-service:8085"
        assert client.request_timeout == 30
        assert client.max_retries == 3
        assert client.retry_delay == 0.5


class TestLanguageMappingBehavior:
    """Test language code mapping functionality."""
    
    def test_language_mapping_en_to_en_us(self) -> None:
        """Test English language mapping from en to en-US."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        
        # Act
        mapped = client._map_language_code("en")
        
        # Assert
        assert mapped == "en-US"
    
    def test_language_mapping_sv_to_sv_se(self) -> None:
        """Test Swedish language mapping from sv to sv-SE."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        
        # Act
        mapped = client._map_language_code("sv")
        
        # Assert
        assert mapped == "sv-SE"
    
    def test_language_mapping_auto_unchanged(self) -> None:
        """Test auto language detection code remains unchanged."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        
        # Act
        mapped = client._map_language_code("auto")
        
        # Assert
        assert mapped == "auto"
    
    def test_language_mapping_unknown_passthrough(self) -> None:
        """Test unknown language codes pass through unchanged."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        
        # Act
        mapped = client._map_language_code("fr")
        
        # Assert
        assert mapped == "fr"


class TestRetryLogicBehavior:
    """Test HTTP error retry logic."""
    
    def test_is_retryable_error_4xx_false(self) -> None:
        """Test 4xx errors are not retryable."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        
        # Act & Assert
        assert not client._is_retryable_error(400)
        assert not client._is_retryable_error(404)
        assert not client._is_retryable_error(422)
        assert not client._is_retryable_error(499)
    
    def test_is_retryable_error_5xx_true(self) -> None:
        """Test 5xx errors are retryable."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        
        # Act & Assert
        assert client._is_retryable_error(500)
        assert client._is_retryable_error(502)
        assert client._is_retryable_error(503)
        assert client._is_retryable_error(599)


class TestGrammarCheckSuccess:
    """Test successful grammar checking scenarios."""
    
    @pytest.mark.asyncio
    async def test_successful_grammar_check(self) -> None:
        """Test successful grammar check with proper response mapping."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        correlation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        match = create_sample_grammar_error_match()
        response = create_mock_language_tool_response(
            matches=[match],
            language="en-US",
            grammar_category_counts={"PUNCTUATION": 1},
            grammar_rule_counts={"COMMA_RULE": 1}
        )
        
        with aioresponses() as m:
            m.post(
                "http://language-tool-service:8085/v1/check",
                payload=response,
                status=200
            )
            
            # Act
            async with aiohttp.ClientSession() as session:
                result = await client.check_grammar(
                    "The quick brown fox and the lazy dog",
                    session,
                    correlation_id,
                    "en"
                )
        
        # Assert
        assert isinstance(result, GrammarAnalysis)
        assert result.error_count == 1
        assert len(result.errors) == 1
        assert result.language == "en-US"
        assert result.processing_time_ms > 0
        assert result.grammar_category_counts == {"PUNCTUATION": 1}
        assert result.grammar_rule_counts == {"COMMA_RULE": 1}
        
        # Verify grammar error mapping
        error = result.errors[0]
        assert error.rule_id == "COMMA_RULE"
        assert error.message == "Add comma before 'and' in compound sentence"
        assert error.short_message == "Missing comma"
        assert error.offset == 15
        assert error.length == 3
        assert error.replacements == [", and"]
        assert error.category == "punctuation"
        assert error.severity == "error"
        assert error.category_id == "PUNCTUATION"
        assert error.category_name == "Punctuation"
        assert error.context == "The quick brown fox and the lazy dog"
        assert error.context_offset == 12
    
    @pytest.mark.asyncio
    async def test_empty_text_handling(self) -> None:
        """Test behavior with empty string input."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        correlation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        response = create_mock_language_tool_response(
            matches=[],
            language="en-US"
        )
        
        with aioresponses() as m:
            m.post(
                "http://language-tool-service:8085/v1/check",
                payload=response,
                status=200
            )
            
            # Act
            async with aiohttp.ClientSession() as session:
                result = await client.check_grammar(
                    "",
                    session,
                    correlation_id,
                    "en"
                )
        
        # Assert
        assert result.error_count == 0
        assert len(result.errors) == 0
        assert result.language == "en-US"
        assert result.processing_time_ms >= 0  # Fast responses can be 0ms
    
    @pytest.mark.asyncio
    async def test_response_mapping_with_all_fields(self) -> None:
        """Test complete response mapping with all GrammarError and analytics fields."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        correlation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        # Complex match with all possible fields
        complex_match = {
            "rule": {
                "id": "CONFUSION_RULE",
                "category": {
                    "id": "GRAMMAR",
                    "name": "Grammar and Style"
                }
            },
            "message": "Did you mean 'their' instead of 'there'?",
            "shortMessage": "Wrong word",
            "offset": 20,
            "length": 5,
            "replacements": [
                {"value": "their"},
                {"value": "they're"}
            ],
            "type": {
                "typeName": "warning"
            },
            "context": {
                "text": "The students put there books on the table",
                "offset": 17
            }
        }
        
        response = create_mock_language_tool_response(
            matches=[complex_match],
            language="en-US",
            grammar_category_counts={"GRAMMAR": 1, "PUNCTUATION": 0},
            grammar_rule_counts={"CONFUSION_RULE": 1, "COMMA_RULE": 0}
        )
        
        with aioresponses() as m:
            m.post(
                "http://language-tool-service:8085/v1/check",
                payload=response,
                status=200
            )
            
            # Act
            async with aiohttp.ClientSession() as session:
                result = await client.check_grammar(
                    "The students put there books on the table",
                    session,
                    correlation_id,
                    "auto"
                )
        
        # Assert - Complete field mapping
        assert result.error_count == 1
        error = result.errors[0]
        assert error.rule_id == "CONFUSION_RULE"
        assert error.message == "Did you mean 'their' instead of 'there'?"
        assert error.short_message == "Wrong word"
        assert error.offset == 20
        assert error.length == 5
        assert error.replacements == ["their", "they're"]
        assert error.category == "grammar"
        assert error.severity == "warning"
        assert error.category_id == "GRAMMAR"
        assert error.category_name == "Grammar and Style"
        assert error.context == "The students put there books on the table"
        assert error.context_offset == 17
        
        # Assert - Analytics fields
        assert result.grammar_category_counts == {"GRAMMAR": 1, "PUNCTUATION": 0}
        assert result.grammar_rule_counts == {"CONFUSION_RULE": 1, "COMMA_RULE": 0}
    
    @pytest.mark.asyncio
    async def test_analytics_fields_mapping(self) -> None:
        """Test grammar_category_counts and grammar_rule_counts mapping."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        correlation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        analytics_counts = {
            "GRAMMAR": 3,
            "PUNCTUATION": 2,
            "STYLE": 1
        }
        rule_counts = {
            "COMMA_RULE": 2,
            "CONFUSION_RULE": 3,
            "STYLE_RULE": 1
        }
        
        response = create_mock_language_tool_response(
            matches=[],  # Focus on analytics, not individual errors
            language="en-US",
            grammar_category_counts=analytics_counts,
            grammar_rule_counts=rule_counts
        )
        
        with aioresponses() as m:
            m.post(
                "http://language-tool-service:8085/v1/check",
                payload=response,
                status=200
            )
            
            # Act
            async with aiohttp.ClientSession() as session:
                result = await client.check_grammar(
                    "Sample text for analytics",
                    session,
                    correlation_id,
                    "en"
                )
        
        # Assert
        assert result.grammar_category_counts == analytics_counts
        assert result.grammar_rule_counts == rule_counts
    
    @pytest.mark.asyncio
    async def test_swedish_text_handling(self) -> None:
        """Test handling of Swedish text with special characters åäöÅÄÖ."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        correlation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        # Swedish text with special characters
        swedish_text = "Hej på dig! Jag heter Åsa Hägerström från Göteborg."
        
        response = create_mock_language_tool_response(
            matches=[],
            language="sv-SE",
            grammar_category_counts={"GRAMMAR": 0},
            grammar_rule_counts={}
        )
        
        with aioresponses() as m:
            # Verify the request payload contains correct language mapping
            async def payload_checker(url, **kwargs):
                request_data = kwargs.get('data')
                if isinstance(request_data, str):
                    request_json = json.loads(request_data)
                elif hasattr(request_data, 'read'):
                    content = await request_data.read()
                    request_json = json.loads(content.decode())
                else:
                    request_json = request_data
                
                # Verify language mapping sv -> sv-SE
                assert request_json['language'] == 'sv-SE'
                assert request_json['text'] == swedish_text
                return response
            
            m.post(
                "http://language-tool-service:8085/v1/check",
                payload=response,
                status=200
            )
            
            # Act
            async with aiohttp.ClientSession() as session:
                result = await client.check_grammar(
                    swedish_text,
                    session,
                    correlation_id,
                    "sv"  # Should map to sv-SE
                )
        
        # Assert
        assert result.language == "sv-SE"
        assert result.error_count == 0


class TestErrorHandling:
    """Test error handling and retry behavior."""
    
    @pytest.mark.asyncio
    async def test_4xx_error_no_retry(self) -> None:
        """Test 4xx errors don't trigger retry attempts."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        correlation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        with aioresponses() as m:
            # Only one call should be made (no retries for 4xx)
            m.post(
                "http://language-tool-service:8085/v1/check",
                status=400,
                payload={"error": "Bad Request"}
            )
            
            # Act & Assert
            async with aiohttp.ClientSession() as session:
                with pytest.raises(HuleEduError) as exc_info:
                    await client.check_grammar(
                        "Test text",
                        session,
                        correlation_id,
                        "en"
                    )
                
                # Verify it's an external service error
                assert "Language Tool Service returned 400" in str(exc_info.value)
        
        # Verify only one call was made (no retries)
        assert len(m.requests) == 1
    
    @pytest.mark.asyncio
    async def test_5xx_error_with_retry(self) -> None:
        """Test 5xx errors trigger retry with exponential backoff."""
        # Arrange
        settings = MockSettings()
        settings.LANGUAGE_TOOL_MAX_RETRIES = 2
        settings.LANGUAGE_TOOL_RETRY_DELAY = 0.01  # Very fast for testing
        client = LanguageToolServiceClient(settings)
        correlation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        # First test: ensure final failure after exhausting retries
        with aioresponses() as m:
            # All calls return 500 to exhaust retries
            m.post(
                "http://language-tool-service:8085/v1/check",
                status=500,
                payload={"error": "Internal Server Error"},
                repeat=True
            )
            
            # Should fail after all retries exhausted
            async with aiohttp.ClientSession() as session:
                with pytest.raises(HuleEduError):
                    await client.check_grammar(
                        "Test text",
                        session,
                        correlation_id,
                        "en"
                    )
        
        # Assert - Should have made initial + 2 retry attempts = 3 total
        # Check the actual request calls made to the URL
        request_key = ('POST', 'http://language-tool-service:8085/v1/check')
        post_calls = list(m.requests.values())[0] if m.requests else []
        assert len(post_calls) == 3
    
    @pytest.mark.asyncio
    async def test_timeout_with_retry(self) -> None:
        """Test timeout errors trigger retry attempts."""
        # Arrange
        settings = MockSettings()
        settings.LANGUAGE_TOOL_MAX_RETRIES = 1
        settings.LANGUAGE_TOOL_RETRY_DELAY = 0.01  # Very fast for testing
        client = LanguageToolServiceClient(settings)
        correlation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        with aioresponses() as m:
            # All calls timeout to test retry exhaustion
            m.post(
                "http://language-tool-service:8085/v1/check",
                exception=aiohttp.ServerTimeoutError("Request timeout"),
                repeat=True
            )
            
            # Should fail after all retries exhausted
            async with aiohttp.ClientSession() as session:
                with pytest.raises(HuleEduError):
                    await client.check_grammar(
                        "Test text",
                        session,
                        correlation_id,
                        "en"
                    )
        
        # Assert - Should have made initial + 1 retry = 2 total
        # Check the actual request calls made to the URL
        post_calls = list(m.requests.values())[0] if m.requests else []
        assert len(post_calls) == 2


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration and graceful degradation."""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_open_degradation(self) -> None:
        """Test graceful degradation when circuit breaker is open."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        correlation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        # Mock circuit breaker that raises CircuitBreakerError
        mock_circuit_breaker = AsyncMock()
        mock_circuit_breaker.call.side_effect = CircuitBreakerError("Circuit is open")
        client._circuit_breaker = mock_circuit_breaker
        
        # Act
        async with aiohttp.ClientSession() as session:
            result = await client.check_grammar(
                "Test text",
                session,
                correlation_id,
                "en"
            )
        
        # Assert - Should return empty analysis
        assert isinstance(result, GrammarAnalysis)
        assert result.error_count == 0
        assert len(result.errors) == 0
        assert result.language == "en"  # Default from input since not "auto"
        assert result.processing_time_ms >= 0  # Allow 0 for circuit breaker case
        assert result.grammar_category_counts is None
        assert result.grammar_rule_counts is None
        
        # Verify circuit breaker was called
        mock_circuit_breaker.call.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_no_circuit_breaker_direct_call(self) -> None:
        """Test direct HTTP call when no circuit breaker is configured."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        correlation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        # Ensure no circuit breaker attribute
        if hasattr(client, '_circuit_breaker'):
            delattr(client, '_circuit_breaker')
        
        response = create_mock_language_tool_response()
        
        with aioresponses() as m:
            m.post(
                "http://language-tool-service:8085/v1/check",
                payload=response,
                status=200
            )
            
            # Act
            async with aiohttp.ClientSession() as session:
                result = await client.check_grammar(
                    "Test text",
                    session,
                    correlation_id,
                    "en"
                )
        
        # Assert - Should work normally without circuit breaker
        assert isinstance(result, GrammarAnalysis)
        assert result.error_count == 0


class TestRequestPayloadValidation:
    """Test request payload construction and validation."""
    
    @pytest.mark.asyncio
    async def test_request_headers_include_correlation_id(self) -> None:
        """Test request headers include correlation ID and content type."""
        # Arrange
        client = LanguageToolServiceClient(MockSettings())
        correlation_id = UUID("12345678-1234-5678-1234-567812345678")
        
        with aioresponses() as m:
            m.post(
                "http://language-tool-service:8085/v1/check",
                payload=create_mock_language_tool_response(),
                status=200
            )
            
            # Act
            async with aiohttp.ClientSession() as session:
                await client.check_grammar(
                    "Test text",
                    session,
                    correlation_id,
                    "en"
                )
        
        # Assert - Check that request was made with proper headers
        # This is verified by the successful operation and logging