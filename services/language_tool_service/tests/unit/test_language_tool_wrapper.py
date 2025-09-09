"""Unit tests for Language Tool wrapper implementation."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import aiohttp
import pytest
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.error_handling.correlation import CorrelationContext

from services.language_tool_service.config import Settings
from services.language_tool_service.implementations.language_tool_manager import (
    LanguageToolManager,
)
from services.language_tool_service.implementations.language_tool_wrapper import (
    LanguageToolWrapper,
)


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.LANGUAGE_TOOL_PORT = 8081
    settings.LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS = 10
    settings.LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS = 30
    settings.GRAMMAR_CATEGORIES_BLOCKED = ["TYPOS", "MISSPELLING", "SPELLING", "TYPOGRAPHY"]
    settings.GRAMMAR_CATEGORIES_ALLOWED = ["GRAMMAR", "CONFUSED_WORDS", "AGREEMENT"]
    return settings


@pytest.fixture
def mock_manager() -> AsyncMock:
    """Create mock Language Tool manager."""
    manager = AsyncMock(spec=LanguageToolManager)
    manager.health_check.return_value = True
    manager.restart_if_needed.return_value = None
    manager.get_status.return_value = {
        "running": True,
        "pid": 12345,
        "restart_count": 0,
        "port": 8081,
        "heap_size": "512m",
    }
    return manager


class _TestableLanguageToolWrapper(LanguageToolWrapper):
    """Testable version of LanguageToolWrapper with injectable HTTP client."""

    def __init__(
        self, settings: Settings, manager: LanguageToolManager, http_client_factory: Any = None
    ) -> None:
        super().__init__(settings, manager)
        self._http_client_factory = http_client_factory
        self._mock_call_response: list[dict[str, Any]] | None = None
        self._mock_call_exception: Exception | None = None

    async def _ensure_session(self) -> Any:
        """Override to use injectable HTTP client."""
        if self._http_client_factory:
            return self._http_client_factory()
        return await super()._ensure_session()

    async def _call_language_tool(
        self, text: str, language: str, correlation_context: Any
    ) -> list[dict[str, Any]]:
        """Override for testing - allows mocking without patching."""
        if self._mock_call_exception:
            raise self._mock_call_exception
        if self._mock_call_response is not None:
            return self._mock_call_response
        return await super()._call_language_tool(text, language, correlation_context)

    def set_mock_call_response(self, response: list[dict[str, Any]]) -> None:
        """Set mock response for _call_language_tool."""
        self._mock_call_response = response
        self._mock_call_exception = None

    def set_mock_call_exception(self, exception: Exception) -> None:
        """Set mock exception for _call_language_tool."""
        self._mock_call_exception = exception
        self._mock_call_response = None


@pytest.fixture
def wrapper(mock_settings: Settings, mock_manager: AsyncMock) -> _TestableLanguageToolWrapper:
    """Create testable Language Tool wrapper instance for testing."""
    return _TestableLanguageToolWrapper(mock_settings, mock_manager)


class TestLanguageToolWrapper:
    """Test suite for LanguageToolWrapper."""

    @pytest.mark.asyncio
    async def test_check_text_success(self, wrapper: _TestableLanguageToolWrapper) -> None:
        """Test successful text checking with grammar errors."""
        # Arrange
        correlation_context = CorrelationContext(
            original="test-id",
            uuid=UUID("12345678-1234-1234-1234-123456789012"),
            source="generated",
        )
        test_text = "This are a test sentence with grammer issues."

        mock_response_matches = [
            {
                "message": "Subject-verb disagreement",
                "shortMessage": "Grammar error",
                "offset": 5,
                "length": 3,
                "replacements": [{"value": "is"}],
                "rule": {
                    "id": "SUBJECT_VERB_AGREEMENT",
                    "category": {
                        "id": "GRAMMAR",
                        "name": "Grammar",
                    },
                    "issueType": "grammar",
                },
                "context": {
                    "text": "This are a test sentence",
                    "offset": 5,
                },
            },
            {
                "message": "Spelling mistake",
                "shortMessage": "Typo",
                "offset": 30,
                "length": 7,
                "replacements": [{"value": "grammar"}],
                "rule": {
                    "id": "MORFOLOGIK_RULE_EN_US",
                    "category": {
                        "id": "TYPOS",
                        "name": "Typographical Errors",
                    },
                    "issueType": "misspelling",
                },
                "context": {
                    "text": "sentence with grammer issues",
                    "offset": 14,
                },
            },
        ]

        wrapper.set_mock_call_response(mock_response_matches)

        # Act
        result = await wrapper.check_text(test_text, correlation_context)

        # Assert
        assert len(result) == 1  # Only grammar error, typo filtered out
        assert result[0]["rule_id"] == "SUBJECT_VERB_AGREEMENT"
        assert result[0]["category_id"] == "GRAMMAR"
        assert result[0]["offset"] == 5
        assert result[0]["replacements"] == ["is"]

    @pytest.mark.asyncio
    async def test_check_text_timeout(self, wrapper: _TestableLanguageToolWrapper) -> None:
        """Test timeout handling during text checking."""
        # Arrange
        correlation_context = CorrelationContext(
            original="test-id",
            uuid=UUID("12345678-1234-1234-1234-123456789012"),
            source="generated",
        )
        test_text = "Test text"

        wrapper.set_mock_call_exception(asyncio.TimeoutError())

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await wrapper.check_text(test_text, correlation_context)

        assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_check_text_client_error(self, wrapper: _TestableLanguageToolWrapper) -> None:
        """Test client error handling during text checking."""
        # Arrange
        correlation_context = CorrelationContext(
            original="test-id",
            uuid=UUID("12345678-1234-1234-1234-123456789012"),
            source="generated",
        )
        test_text = "Test text"

        wrapper.set_mock_call_exception(aiohttp.ClientError("Connection failed"))

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await wrapper.check_text(test_text, correlation_context)

        assert "external_service" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_check_text_server_unhealthy_triggers_restart(
        self, wrapper: _TestableLanguageToolWrapper, mock_manager: AsyncMock
    ) -> None:
        """Test that server restart is attempted when health check fails."""
        # Arrange
        correlation_context = CorrelationContext(
            original="test-id",
            uuid=UUID("12345678-1234-1234-1234-123456789012"),
            source="generated",
        )
        test_text = "Test text"

        # Set up mock manager to return False for health check
        mock_manager.health_check.return_value = False  # Server unhealthy

        wrapper.set_mock_call_exception(Exception("Server error"))

        # Act & Assert
        with pytest.raises(HuleEduError):
            await wrapper.check_text(test_text, correlation_context)

        # Verify restart was attempted
        mock_manager.health_check.assert_called_once()
        mock_manager.restart_if_needed.assert_called_once()

    def test_filter_categories(self, wrapper: _TestableLanguageToolWrapper) -> None:
        """Test category filtering logic."""
        # Arrange
        matches = [
            {
                "rule": {
                    "category": {"id": "GRAMMAR", "name": "Grammar"},
                    "issueType": "grammar",
                }
            },
            {
                "rule": {
                    "category": {"id": "TYPOS", "name": "Typographical Errors"},
                    "issueType": "misspelling",
                }
            },
            {
                "rule": {
                    "category": {"id": "SPELLING", "name": "Spelling"},
                    "issueType": "misspelling",
                }
            },
            {
                "rule": {
                    "category": {"id": "CONFUSED_WORDS", "name": "Confused Words"},
                    "issueType": "grammar",
                }
            },
            {
                "rule": {
                    "category": {"id": "TYPOGRAPHY", "name": "Typography"},
                    "issueType": "typographical",
                }
            },
        ]

        # Act
        filtered = wrapper._filter_categories(matches)

        # Assert
        assert len(filtered) == 2
        assert filtered[0]["rule"]["category"]["id"] == "GRAMMAR"
        assert filtered[1]["rule"]["category"]["id"] == "CONFUSED_WORDS"

    def test_map_to_grammar_errors(self, wrapper: _TestableLanguageToolWrapper) -> None:
        """Test mapping LanguageTool matches to GrammarError format."""
        # Arrange
        matches = [
            {
                "message": "Use 'an' instead of 'a'",
                "shortMessage": "Article error",
                "offset": 10,
                "length": 1,
                "replacements": [{"value": "an"}],
                "rule": {
                    "id": "EN_A_VS_AN",
                    "category": {
                        "id": "GRAMMAR",
                        "name": "Grammar",
                    },
                    "issueType": "grammar",
                },
                "context": {
                    "text": "This is a apple",
                    "offset": 8,
                },
            }
        ]
        original_text = "This is a apple in the basket."

        # Act
        errors = wrapper._map_to_grammar_errors(matches, original_text)

        # Assert
        assert len(errors) == 1
        error = errors[0]
        assert error["rule_id"] == "EN_A_VS_AN"
        assert error["message"] == "Use 'an' instead of 'a'"
        assert error["offset"] == 10
        assert error["length"] == 1
        assert error["replacements"] == ["an"]
        assert error["category"] == "Grammar"
        assert error["category_id"] == "GRAMMAR"
        assert error["category_name"] == "Grammar"
        assert error["context"] == "This is a apple"
        assert error["context_offset"] == 8
        assert error["severity"] == "warning"

    def test_map_to_grammar_errors_without_context(
        self, wrapper: _TestableLanguageToolWrapper
    ) -> None:
        """Test mapping when LanguageTool doesn't provide context."""
        # Arrange
        matches = [
            {
                "message": "Error message",
                "offset": 50,
                "length": 5,
                "replacements": [],
                "rule": {
                    "id": "TEST_RULE",
                    "category": {
                        "id": "GRAMMAR",
                        "name": "Grammar",
                    },
                },
                "context": {},  # Empty context
            }
        ]
        original_text = "a" * 45 + "test error here" + "b" * 50

        # Act
        errors = wrapper._map_to_grammar_errors(matches, original_text)

        # Assert
        assert len(errors) == 1
        error = errors[0]
        # Should extract context from original text
        assert error["context"]
        assert error["context_offset"] == 40  # offset (50) - context_start (10)
        assert "error" in error["context"]

    @pytest.mark.asyncio
    async def test_get_health_status_healthy(
        self, wrapper: _TestableLanguageToolWrapper, mock_manager: AsyncMock
    ) -> None:
        """Test health status check when server is healthy."""
        # Arrange
        correlation_context = CorrelationContext(
            original="test-id",
            uuid=UUID("12345678-1234-1234-1234-123456789012"),
            source="generated",
        )
        mock_manager.health_check.return_value = True

        # Mock the HTTP session
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_session.get.return_value.__aenter__.return_value = mock_response

        # Set mock HTTP client factory
        wrapper._http_client_factory = lambda: mock_session

        # Act
        status = await wrapper.get_health_status(correlation_context)

        # Assert
        assert status["status"] == "healthy"
        assert status["implementation"] == "production"
        assert "server" in status
        assert status["server"]["running"] is True

    @pytest.mark.asyncio
    async def test_get_health_status_unhealthy(
        self, wrapper: _TestableLanguageToolWrapper, mock_manager: AsyncMock
    ) -> None:
        """Test health status check when server is unhealthy."""
        # Arrange
        correlation_context = CorrelationContext(
            original="test-id",
            uuid=UUID("12345678-1234-1234-1234-123456789012"),
            source="generated",
        )
        mock_manager.health_check.return_value = False

        # Act
        status = await wrapper.get_health_status(correlation_context)

        # Assert
        assert status["status"] == "unhealthy"
        assert status["response_time_ms"] == 0

    @pytest.mark.asyncio
    async def test_concurrent_requests_limited(
        self, wrapper: _TestableLanguageToolWrapper, mock_settings: Settings
    ) -> None:
        """Test that concurrent requests are limited by semaphore."""
        # Arrange
        mock_settings.LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS = 2
        wrapper.semaphore = asyncio.Semaphore(2)

        correlation_context = CorrelationContext(
            original="test-id",
            uuid=UUID("12345678-1234-1234-1234-123456789012"),
            source="generated",
        )
        call_count = 0
        max_concurrent = 0
        current_concurrent = 0

        async def slow_call(*_args: Any) -> list[dict[str, Any]]:
            nonlocal call_count, max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            call_count += 1
            await asyncio.sleep(0.1)  # Simulate slow response
            current_concurrent -= 1
            return []

        # Override the _call_language_tool method directly
        wrapper._call_language_tool = slow_call  # type: ignore[assignment]

        # Act - Start 5 concurrent requests
        tasks = [wrapper.check_text(f"Text {i}", correlation_context) for i in range(5)]
        await asyncio.gather(*tasks)

        # Assert
        assert call_count == 5
        assert max_concurrent <= 2  # Should never exceed semaphore limit

    @pytest.mark.asyncio
    async def test_cleanup(self, wrapper: _TestableLanguageToolWrapper) -> None:
        """Test cleanup of resources."""
        # Arrange
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        wrapper.http_session = mock_session

        # Act
        await wrapper.cleanup()

        # Assert
        mock_session.close.assert_called_once()
        assert wrapper.http_session is None
