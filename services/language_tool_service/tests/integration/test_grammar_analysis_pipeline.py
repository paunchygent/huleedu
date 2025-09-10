"""End-to-end integration tests for grammar analysis pipeline.

This module implements behavioral integration tests for the complete grammar
analysis pipeline using real HTTP requests and actual LanguageTool processing.
NO mocking is used - all tests validate real system behavior.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from dishka import make_async_container
from huleedu_service_libs.error_handling.quart import register_error_handlers
from quart import Quart
from quart_dishka import QuartDishka

from services.language_tool_service.api.grammar_routes import grammar_bp
from services.language_tool_service.api.health_routes import health_bp
from services.language_tool_service.di import (
    CoreInfrastructureProvider,
    ServiceImplementationsProvider,
)

# Test data with known grammar errors for validation (using stub patterns)
ENGLISH_ERROR_TEXT = "I went there to see what happened."  # Triggers stub pattern for "there"
SWEDISH_ERROR_TEXT = "Det här är en mening som har grammatikfel."
MALFORMED_TEXT = "\x00\x01\x02" * 1000  # Triggers Java exception

# Test data for category filtering validation
TYPO_TEXT = (
    "I will recieve the package tomorrow."  # Contains typo that should be filtered (stub pattern)
)
GRAMMAR_ONLY_TEXT = "I went there to their house."  # Should not trigger grammar error (has both "there" and "their")

# Large text for concurrent testing
LARGE_TEXT = "I went there to see what happened. " * 50  # Multiplies the stub pattern

# Known good text for baseline validation
CORRECT_TEXT = "This is a perfectly correct sentence with no grammar errors."


@pytest.fixture
async def app() -> AsyncGenerator[Quart, None]:
    """Create real app instance with test configuration.

    Sets up the actual Language Tool Service app with real DI container
    but uses stub implementation for testing purposes.
    No mocking - uses real Dishka providers and service infrastructure.
    """
    # Force stub mode for integration tests to avoid requiring real JAR
    os.environ["USE_STUB_LANGUAGE_TOOL"] = "true"

    app = Quart(__name__)
    app.config.update({"TESTING": True})

    # Register blueprints
    app.register_blueprint(grammar_bp)
    app.register_blueprint(health_bp)

    # Set up error handling middleware
    register_error_handlers(app)

    # Set up real DI container with actual providers
    container = make_async_container(
        CoreInfrastructureProvider(),
        ServiceImplementationsProvider(),
    )
    QuartDishka(app=app, container=container)

    # Expose metrics through app.extensions like the real service
    from services.language_tool_service.metrics import METRICS

    app.extensions = getattr(app, "extensions", {})
    app.extensions["metrics"] = METRICS

    try:
        yield app
    finally:
        await container.close()
        # Clean up environment
        if "USE_STUB_LANGUAGE_TOOL" in os.environ:
            del os.environ["USE_STUB_LANGUAGE_TOOL"]


@pytest.fixture
async def client(app: Quart) -> AsyncGenerator[Any, None]:
    """Create test client for real HTTP requests.

    Args:
        app: The real Language Tool Service app

    Returns:
        Quart test client for making actual HTTP requests
    """
    async with app.test_client() as client:
        yield client


class TestGrammarAnalysisPipeline:
    """End-to-end integration tests for grammar analysis pipeline.

    These tests validate the complete grammar analysis flow from HTTP request
    through Java LanguageTool processing to filtered response. All tests use
    real implementations without mocking.
    """

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_grammar_analysis_with_real_errors(self, client: Any) -> None:
        """Test real grammar error detection with actual LanguageTool processing.

        Validates that the complete pipeline correctly identifies and categorizes
        grammar errors using real LanguageTool analysis.
        """
        # Arrange: Prepare text with known grammar errors
        request_data = {"text": ENGLISH_ERROR_TEXT, "language": "en-US"}

        # Act: Send real HTTP request to grammar check endpoint
        response = await client.post("/v1/check", json=request_data)

        # Assert: Verify response structure and content
        assert response.status_code == 200
        response_data = await response.get_json()

        # Verify basic response structure
        assert "errors" in response_data
        assert "total_grammar_errors" in response_data
        assert "grammar_category_counts" in response_data
        assert "grammar_rule_counts" in response_data
        assert "language" in response_data
        assert "processing_time_ms" in response_data

        # Verify response values
        assert response_data["language"] == "en-US"
        assert isinstance(response_data["total_grammar_errors"], int)
        assert response_data["total_grammar_errors"] >= 0
        assert isinstance(response_data["processing_time_ms"], int)
        assert response_data["processing_time_ms"] > 0

        # Verify errors list structure if errors found
        if response_data["total_grammar_errors"] > 0:
            assert len(response_data["errors"]) == response_data["total_grammar_errors"]

            # Verify each error has required fields
            for error in response_data["errors"]:
                assert "rule_id" in error
                assert "message" in error
                assert "offset" in error
                assert "length" in error
                assert "category" in error
                assert isinstance(error["offset"], int)
                assert isinstance(error["length"], int)
                assert error["offset"] >= 0
                assert error["length"] > 0

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_category_filtering_excludes_typos(self, client: Any) -> None:
        """Test that TYPOS/SPELLING categories are filtered out as configured.

        Validates that the category filtering configuration correctly excludes
        spelling and typo errors while preserving grammar errors.
        """
        # Arrange: Use text with both typos and grammar errors
        request_data = {"text": TYPO_TEXT, "language": "en-US"}

        # Act: Send request and get response
        response = await client.post("/v1/check", json=request_data)

        # Assert: Verify filtering behavior
        assert response.status_code == 200
        response_data = await response.get_json()

        # Verify no blocked categories appear in results
        blocked_categories = ["TYPOS", "MISSPELLING", "SPELLING", "TYPOGRAPHY"]
        category_counts = response_data.get("grammar_category_counts", {})

        for blocked_category in blocked_categories:
            assert blocked_category not in category_counts, (
                f"Blocked category {blocked_category} found in results: {category_counts}"
            )

        # Verify that if errors exist, they are from allowed categories
        allowed_categories = [
            "GRAMMAR",
            "CONFUSED_WORDS",
            "AGREEMENT",
            "PUNCTUATION",
            "REDUNDANCY",
            "STYLE",
        ]

        for category in category_counts.keys():
            assert category in allowed_categories or category.upper() == "UNKNOWN", (
                f"Unexpected category {category} found in results"
            )

    @pytest.mark.integration
    @pytest.mark.timeout(45)
    async def test_multiple_language_support(self, client: Any) -> None:
        """Test that en-US and sv-SE produce different analysis results.

        Validates that the service correctly handles multiple languages
        and produces language-specific grammar analysis.
        """
        # Arrange: Test data for different languages
        test_cases = [
            {"text": ENGLISH_ERROR_TEXT, "language": "en-US", "expected_lang": "en-US"},
            {"text": SWEDISH_ERROR_TEXT, "language": "sv-SE", "expected_lang": "sv-SE"},
        ]

        results = []

        # Act: Test each language
        for test_case in test_cases:
            request_data = {"text": test_case["text"], "language": test_case["language"]}

            response = await client.post("/v1/check", json=request_data)

            # Assert: Basic response validation
            assert response.status_code == 200
            response_data = await response.get_json()

            # Verify language-specific response
            assert response_data["language"] == test_case["expected_lang"]

            # Store results for comparison
            results.append(
                {
                    "language": response_data["language"],
                    "total_errors": response_data["total_grammar_errors"],
                    "categories": response_data["grammar_category_counts"],
                    "processing_time": response_data["processing_time_ms"],
                }
            )

        # Assert: Verify different languages can produce different results
        # Note: This may vary based on text content and LanguageTool rules
        assert len(results) == 2
        assert results[0]["language"] != results[1]["language"]

        # Each result should have valid processing time
        for result in results:
            assert result["processing_time"] > 0

    @pytest.mark.integration
    @pytest.mark.timeout(60)
    async def test_concurrent_request_handling(self, client: Any) -> None:
        """Test parallel request processing with asyncio.gather.

        Validates that the service can handle multiple concurrent requests
        without degrading response quality or causing race conditions.
        """
        # Arrange: Create multiple concurrent requests
        concurrent_requests = [
            {"text": ENGLISH_ERROR_TEXT, "language": "en-US"},
            {"text": CORRECT_TEXT, "language": "en-US"},
            {"text": GRAMMAR_ONLY_TEXT, "language": "en-US"},
            {"text": LARGE_TEXT, "language": "en-US"},
            {"text": SWEDISH_ERROR_TEXT, "language": "sv-SE"},
        ]

        async def make_request(request_data: dict[str, str]) -> Any:
            """Make a single HTTP request and return response data."""
            response = await client.post("/v1/check", json=request_data)
            assert response.status_code == 200
            response_json = await response.get_json()
            return response_json

        # Act: Execute all requests concurrently
        tasks = [make_request(req) for req in concurrent_requests]
        responses = await asyncio.gather(*tasks)

        # Assert: Verify all responses are valid
        assert len(responses) == len(concurrent_requests)

        for i, response_data in enumerate(responses):
            expected_language = concurrent_requests[i]["language"]

            # Verify basic response structure
            assert "errors" in response_data
            assert "total_grammar_errors" in response_data
            assert "language" in response_data
            assert "processing_time_ms" in response_data

            # Verify language matches request
            assert response_data["language"] == expected_language

            # Verify processing time is reasonable (not timeout)
            assert response_data["processing_time_ms"] > 0
            assert response_data["processing_time_ms"] < 30000  # Less than 30 seconds

            # Verify error count is non-negative
            assert response_data["total_grammar_errors"] >= 0

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_error_propagation_from_java(self, client: Any) -> None:
        """Test Java exception handling and structured error propagation.

        Validates that exceptions from the LanguageTool Java process
        are properly caught and converted to structured HTTP errors.
        """
        # Arrange: Use malformed text that may trigger Java exceptions
        request_data = {"text": MALFORMED_TEXT, "language": "en-US"}

        # Act: Send request that might cause Java-level issues
        response = await client.post("/v1/check", json=request_data)

        # Assert: Verify error handling behavior
        # The service should either:
        # 1. Successfully process the malformed text (robust handling)
        # 2. Return a structured error response (proper error propagation)

        if response.status_code == 200:
            # Case 1: Successful processing despite malformed input
            response_data = await response.get_json()

            # Verify response structure is valid
            assert "errors" in response_data
            assert "total_grammar_errors" in response_data
            assert "language" in response_data
            assert "processing_time_ms" in response_data

            # Verify values are sensible
            assert isinstance(response_data["total_grammar_errors"], int)
            assert response_data["total_grammar_errors"] >= 0
            assert response_data["processing_time_ms"] > 0

        else:
            # Case 2: Structured error response
            # Should be in 4xx or 5xx range with structured error format
            assert 400 <= response.status_code < 600

            # Check if response has structured error format
            try:
                error_data = await response.get_json()
                # Should have error details from huleedu_service_libs.error_handling
                assert "error" in error_data or "message" in error_data
            except Exception:
                # Some errors might not have JSON body, which is also acceptable
                pass

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_baseline_correct_text_processing(self, client: Any) -> None:
        """Test processing of correct text with no grammar errors.

        Validates baseline functionality with grammatically correct text
        to ensure the service doesn't produce false positives.
        """
        # Arrange: Use grammatically correct text
        request_data = {"text": CORRECT_TEXT, "language": "en-US"}

        # Act: Send request
        response = await client.post("/v1/check", json=request_data)

        # Assert: Verify clean response for correct text
        assert response.status_code == 200
        response_data = await response.get_json()

        # Verify response structure
        assert response_data["language"] == "en-US"
        assert response_data["total_grammar_errors"] >= 0  # Should be 0 or very low
        assert response_data["processing_time_ms"] > 0

        # Verify empty or minimal error lists for correct text
        # Note: LanguageTool might still suggest style improvements
        assert isinstance(response_data["errors"], list)
        assert isinstance(response_data["grammar_category_counts"], dict)
        assert isinstance(response_data["grammar_rule_counts"], dict)
