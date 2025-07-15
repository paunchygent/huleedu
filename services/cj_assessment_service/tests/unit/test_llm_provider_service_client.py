"""Unit tests for LLM Provider Service client."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import aiohttp
import pytest
from huleedu_service_libs.error_handling import HuleEduError, assert_raises_huleedu_error

from common_core.error_enums import ErrorCode
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.llm_provider_service_client import (
    LLMProviderServiceClient,
)


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    from common_core import LLMProviderType

    settings = MagicMock(spec=Settings)
    settings.LLM_PROVIDER_SERVICE_URL = "http://test-llm-service:8090/api/v1"
    settings.DEFAULT_LLM_PROVIDER = LLMProviderType.ANTHROPIC
    settings.DEFAULT_LLM_MODEL = "claude-3-haiku"
    settings.DEFAULT_LLM_TEMPERATURE = 0.1
    settings.LLM_PROVIDER_CALLBACK_TOPIC = "llm-provider-callbacks"
    return settings


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock HTTP session."""
    return AsyncMock(spec=aiohttp.ClientSession)


@pytest.fixture
def mock_retry_manager() -> AsyncMock:
    """Create mock retry manager that preserves HuleEduError semantics like real implementation."""
    retry_manager = AsyncMock()

    # Make retry manager behave like the real implementation - preserve HuleEduError instances
    async def passthrough(func: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return await func()
        except HuleEduError:
            # ✅ CORRECT: Pass through HuleEduError unchanged (preserves error code semantics)
            raise
        except aiohttp.ClientResponseError as e:
            # Convert raw HTTP errors to HuleEduError
            from uuid import uuid4

            from huleedu_service_libs.error_handling import raise_external_service_error

            raise_external_service_error(
                service="cj_assessment_service",
                operation="llm_provider_service_client_request",
                external_service="llm_provider_service",
                message=f"{e.message}: {e.status}",
                correlation_id=uuid4(),
                status_code=e.status,
            )
        except Exception as e:
            # Convert other raw exceptions to HuleEduError
            from uuid import uuid4

            from huleedu_service_libs.error_handling import raise_external_service_error

            raise_external_service_error(
                service="cj_assessment_service",
                operation="llm_provider_service_client_request",
                external_service="llm_provider_service",
                message=f"HTTP request failed: {str(e)}",
                correlation_id=uuid4(),
                exception_type=type(e).__name__,
            )

    retry_manager.with_retry.side_effect = passthrough
    return retry_manager


@pytest.fixture
def client(
    mock_session: AsyncMock, mock_settings: Settings, mock_retry_manager: AsyncMock
) -> LLMProviderServiceClient:
    """Create LLM Provider Service client for testing."""
    return LLMProviderServiceClient(mock_session, mock_settings, mock_retry_manager)


class TestLLMProviderServiceClient:
    """Test cases for LLM Provider Service client."""

    async def test_extract_essays_from_prompt_success(
        self, client: LLMProviderServiceClient
    ) -> None:
        """Test successful extraction of essays from formatted prompt."""
        prompt = """Compare these two essays and determine which is better written.
Essay A (ID: 123):
This is the content of essay A.
It has multiple lines.

Essay B (ID: 456):
This is the content of essay B.
It also has multiple lines.

Please respond with a JSON object containing:
- 'winner': 'Essay A' or 'Essay B'
- 'justification': Brief explanation of your decision
- 'confidence': Rating from 1-5 (5 = very confident)"""

        result = client._extract_essays_from_prompt(prompt)

        assert result is not None
        base_prompt, essay_a, essay_b = result

        assert "Compare these two essays" in base_prompt
        assert "This is the content of essay A" in essay_a
        assert "multiple lines" in essay_a
        assert "This is the content of essay B" in essay_b
        assert "multiple lines" in essay_b

    async def test_extract_essays_from_prompt_failure(
        self, client: LLMProviderServiceClient
    ) -> None:
        """Test extraction failure with malformed prompt."""
        prompt = "This prompt doesn't contain the expected essay format"

        result = client._extract_essays_from_prompt(prompt)
        assert result is None

    async def test_generate_comparison_success(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test successful comparison generation."""
        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "winner": "Essay A",
                    "justification": "Essay A has better structure",
                    "confidence": 4.5,
                    "provider": "anthropic",
                    "model": "claude-3-haiku",
                    "cached": False,
                    "response_time_ms": 1500,
                    "correlation_id": str(uuid4()),
                }
            )
        )

        mock_session.post.return_value.__aenter__.return_value = mock_response

        # Create test prompt
        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content.

Please respond with a JSON object."""

        # Call generate_comparison
        correlation_id = uuid4()
        try:
            result = await client.generate_comparison(
                user_prompt=prompt,
                model_override="claude-3-haiku",
                temperature_override=0.1,
                correlation_id=correlation_id,
            )
        except HuleEduError as e:
            pytest.fail(f"Unexpected error: {e}")

        # Verify result
        assert result is not None
        assert result["winner"] == "Essay A"
        assert result["justification"] == "Essay A has better structure"
        assert result["confidence"] == 4.5

        # Verify API call
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "http://test-llm-service:8090/api/v1/comparison"

        # Verify request body
        request_body = call_args[1]["json"]
        # The extraction includes header lines up to essay content
        assert "Compare these two essays." in request_body["user_prompt"]
        assert request_body["essay_a"] == "Essay A content."
        assert request_body["essay_b"] == "Essay B content."
        assert request_body["llm_config_overrides"]["provider_override"] == "anthropic"
        assert request_body["llm_config_overrides"]["model_override"] == "claude-3-haiku"
        assert request_body["llm_config_overrides"]["temperature_override"] == 0.1

    async def test_generate_comparison_http_error(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test handling of HTTP error responses."""
        # Mock error response
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(
            return_value=json.dumps(
                {"error": "Internal server error", "details": "Provider unavailable"}
            )
        )

        mock_session.post.return_value.__aenter__.return_value = mock_response

        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        correlation_id = uuid4()
        with assert_raises_huleedu_error(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR, message_contains="Internal server error"
        ) as _:
            await client.generate_comparison(
                user_prompt=prompt,
                correlation_id=correlation_id,
            )

    async def test_generate_comparison_network_error(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test handling of network errors."""
        # Mock network error
        mock_session.post.side_effect = aiohttp.ClientError("Connection failed")

        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        correlation_id = uuid4()
        with assert_raises_huleedu_error(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR, message_contains="Connection failed"
        ) as _:
            await client.generate_comparison(
                user_prompt=prompt,
                correlation_id=correlation_id,
            )

    async def test_generate_comparison_invalid_prompt(
        self, client: LLMProviderServiceClient
    ) -> None:
        """Test handling of invalid prompt format."""
        prompt = "This is not a valid comparison prompt"

        correlation_id = uuid4()
        with assert_raises_huleedu_error(
            error_code=ErrorCode.VALIDATION_ERROR, message_contains="Invalid prompt format"
        ) as _:
            await client.generate_comparison(
                user_prompt=prompt,
                correlation_id=correlation_id,
            )

    async def test_generate_comparison_json_parse_error(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test handling of invalid JSON response."""
        # Mock response with invalid JSON
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="Invalid JSON response")

        mock_session.post.return_value.__aenter__.return_value = mock_response

        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        correlation_id = uuid4()
        with assert_raises_huleedu_error(
            error_code=ErrorCode.PARSING_ERROR,
            message_contains="Failed to parse immediate response JSON",
        ) as _:
            await client.generate_comparison(
                user_prompt=prompt,
                correlation_id=correlation_id,
            )

    # Queue-based response tests
    async def test_generate_comparison_queued_returns_none(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test that queued response (202) returns None for callback-based processing."""
        queue_id = str(uuid4())

        # Mock initial 202 response
        mock_initial_response = AsyncMock()
        mock_initial_response.status = 202
        mock_initial_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "queue_id": queue_id,
                    "status": "queued",
                    "estimated_wait_minutes": 5,
                    "status_url": f"/api/v1/status/{queue_id}",
                }
            )
        )

        mock_session.post.return_value.__aenter__.return_value = mock_initial_response

        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        correlation_id = uuid4()
        try:
            result = await client.generate_comparison(
                user_prompt=prompt,
                correlation_id=correlation_id,
            )
        except HuleEduError as e:
            pytest.fail(f"Unexpected error: {e}")

        # Verify result is None for async processing
        assert result is None

        # Verify API call was made with callback topic
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        request_body = call_args[1]["json"]
        assert "callback_topic" in request_body
        assert request_body["callback_topic"] == client.settings.LLM_PROVIDER_CALLBACK_TOPIC

    async def test_generate_comparison_queued_no_queue_id(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test handling of 202 response without queue_id."""
        # Mock initial 202 response without queue_id
        mock_initial_response = AsyncMock()
        mock_initial_response.status = 202
        mock_initial_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "status": "queued",
                    "message": "Request queued",
                }
            )
        )

        mock_session.post.return_value.__aenter__.return_value = mock_initial_response

        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        correlation_id = uuid4()
        with assert_raises_huleedu_error(
            error_code=ErrorCode.INVALID_RESPONSE,
            message_contains="Queue response missing queue_id",
        ) as _:
            await client.generate_comparison(
                user_prompt=prompt,
                correlation_id=correlation_id,
            )

    async def test_generate_comparison_callback_topic_required(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test that callback topic is included in request for async processing."""
        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "winner": "Essay A",
                    "justification": "Essay A has better structure",
                    "confidence": 4.5,
                    "provider": "anthropic",
                    "model": "claude-3-haiku",
                    "cached": False,
                    "response_time_ms": 1500,
                    "correlation_id": str(uuid4()),
                }
            )
        )

        mock_session.post.return_value.__aenter__.return_value = mock_response

        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        correlation_id = uuid4()
        await client.generate_comparison(
            user_prompt=prompt,
            correlation_id=correlation_id,
        )

        # Verify callback topic is included in request
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        request_body = call_args[1]["json"]
        assert "callback_topic" in request_body
        assert request_body["callback_topic"] == client.settings.LLM_PROVIDER_CALLBACK_TOPIC
