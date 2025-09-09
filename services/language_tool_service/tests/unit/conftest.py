"""Shared fixtures and test configuration for Language Tool Service unit tests.

This module provides common test fixtures, dependency injection setup, and
mock providers used across all unit test files for the grammar routes.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling.correlation import CorrelationContext
from prometheus_client import CollectorRegistry, Counter, Histogram
from quart import Quart
from quart_dishka import QuartDishka

from services.language_tool_service.api.grammar_routes import grammar_bp
from services.language_tool_service.config import Settings
from services.language_tool_service.protocols import LanguageToolWrapperProtocol


class TestProvider(Provider):
    """Test provider for dependency injection with mocked dependencies."""

    scope = Scope.APP

    @provide
    def provide_settings(self) -> Settings:
        """Provide mock settings for testing."""
        mock_settings = MagicMock(spec=Settings)
        mock_settings.SERVICE_NAME = "language-tool-service"
        mock_settings.ENVIRONMENT.value = "test"
        return mock_settings

    @provide
    def provide_language_tool_wrapper(self) -> LanguageToolWrapperProtocol:
        """Provide mock Language Tool wrapper for testing."""
        mock = AsyncMock(spec=LanguageToolWrapperProtocol)
        mock.check_text.return_value = []
        return mock

    @provide
    def provide_metrics(self) -> dict[str, Any]:
        """Provide test metrics registry for isolation."""
        test_registry = CollectorRegistry()

        # Create metrics with test registry
        request_count = Counter(
            "request_count",
            "Total requests",
            ["method", "endpoint", "status"],
            registry=test_registry,
        )

        grammar_analysis_total = Counter(
            "grammar_analysis_total",
            "Total grammar analyses",
            ["status", "text_length_range"],
            registry=test_registry,
        )

        grammar_analysis_duration_seconds = Histogram(
            "grammar_analysis_duration_seconds", "Grammar analysis duration", registry=test_registry
        )

        request_duration = Histogram(
            "request_duration", "Request duration", ["method", "endpoint"], registry=test_registry
        )

        return {
            "request_count": request_count,
            "grammar_analysis_total": grammar_analysis_total,
            "grammar_analysis_duration_seconds": grammar_analysis_duration_seconds,
            "request_duration": request_duration,
        }

    @provide(scope=Scope.REQUEST)
    def provide_correlation_context(self) -> CorrelationContext:
        """Provide mock correlation context for testing."""
        return CorrelationContext(
            original="test-correlation-id",
            uuid=UUID("12345678-1234-1234-1234-123456789012"),
            source="generated",
        )


@pytest.fixture
async def test_app() -> AsyncGenerator[Quart, None]:
    """Create test Quart application with DI setup."""
    app = Quart(__name__)
    app.config.update({"TESTING": True})
    app.register_blueprint(grammar_bp)

    # Set up error handling middleware
    from huleedu_service_libs.error_handling.quart import register_error_handlers

    register_error_handlers(app)

    # Set up Dishka DI with test provider
    container = make_async_container(TestProvider())
    QuartDishka(app=app, container=container)

    try:
        yield app
    finally:
        await container.close()


@pytest.fixture
async def test_client(test_app: Quart) -> AsyncGenerator[Any, None]:
    """Create test client for making requests."""
    async with test_app.test_client() as client:
        yield client


def create_mock_grammar_error(
    category: str = "GRAMMAR",
    rule_id: str = "TEST_RULE",
    message: str = "Test error",
    offset: int = 0,
    length: int = 5,
) -> dict[str, Any]:
    """Create a mock grammar error with standard structure.

    Args:
        category: Error category/type name
        rule_id: Rule identifier
        message: Error message
        offset: Character offset in text
        length: Length of the error span

    Returns:
        Dictionary representing a grammar error
    """
    return {
        "type": {"typeName": category},
        "rule": {"id": rule_id},
        "message": message,
        "offset": offset,
        "length": length,
        "replacements": [],
        "category_id": category.upper(),
        "category_name": category.title(),
        "context": "Test context",
        "context_offset": 0,
    }


def generate_text_with_words(word_count: int) -> str:
    """Generate text with exact word count for testing.

    Args:
        word_count: Number of words to generate

    Returns:
        Text string with exact word count
    """
    # Use varied words to make it more realistic
    words = ["The", "quick", "brown", "fox", "jumps", "over", "lazy", "dog"]
    result = []
    for i in range(word_count):
        result.append(words[i % len(words)])
    return " ".join(result)
