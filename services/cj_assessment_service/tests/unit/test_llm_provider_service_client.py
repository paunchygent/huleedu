"""Unit tests for LLM Provider Service client."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import aiohttp
import pytest

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
    # Queue polling settings
    settings.LLM_QUEUE_POLLING_ENABLED = True
    settings.LLM_QUEUE_POLLING_INITIAL_DELAY_SECONDS = 0.1  # Short for tests
    settings.LLM_QUEUE_POLLING_MAX_DELAY_SECONDS = 1.0
    settings.LLM_QUEUE_POLLING_EXPONENTIAL_BASE = 1.5
    settings.LLM_QUEUE_POLLING_MAX_ATTEMPTS = 5  # Fewer for tests
    settings.LLM_QUEUE_TOTAL_TIMEOUT_SECONDS = 10  # Shorter for tests
    return settings


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock HTTP session."""
    return AsyncMock(spec=aiohttp.ClientSession)


@pytest.fixture
def mock_retry_manager() -> AsyncMock:
    """Create mock retry manager."""
    retry_manager = AsyncMock()

    # Make retry manager pass through the function call
    async def passthrough(func: Any, *args: Any, **kwargs: Any) -> Any:
        return await func()

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
        result, error = await client.generate_comparison(
            user_prompt=prompt,
            model_override="claude-3-haiku",
            temperature_override=0.1,
        )

        # Verify result
        assert error is None
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

        result, error = await client.generate_comparison(user_prompt=prompt)

        assert result is None
        assert error == "Internal server error: Provider unavailable"

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

        result, error = await client.generate_comparison(user_prompt=prompt)

        assert result is None
        assert error and "HTTP request failed: Connection failed" in error

    async def test_generate_comparison_invalid_prompt(
        self, client: LLMProviderServiceClient
    ) -> None:
        """Test handling of invalid prompt format."""
        prompt = "This is not a valid comparison prompt"

        result, error = await client.generate_comparison(user_prompt=prompt)

        assert result is None
        assert error == "Invalid prompt format: Could not extract essays"

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

        result, error = await client.generate_comparison(user_prompt=prompt)

        assert result is None
        assert error and "Failed to parse immediate response JSON" in error

    # Queue-based response tests
    async def test_generate_comparison_queued_success(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test successful handling of queued response with polling."""
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

        # Mock status check responses (queued -> processing -> completed)
        mock_status_responses = [
            # First status check: queued
            AsyncMock(
                status=200,
                text=AsyncMock(
                    return_value=json.dumps(
                        {
                            "queue_id": queue_id,
                            "status": "queued",
                            "position_in_queue": 2,
                        }
                    )
                ),
            ),
            # Second status check: processing
            AsyncMock(
                status=200,
                text=AsyncMock(
                    return_value=json.dumps(
                        {
                            "queue_id": queue_id,
                            "status": "processing",
                        }
                    )
                ),
            ),
            # Third status check: completed
            AsyncMock(
                status=200,
                text=AsyncMock(
                    return_value=json.dumps(
                        {
                            "queue_id": queue_id,
                            "status": "completed",
                            "result_available": True,
                        }
                    )
                ),
            ),
        ]

        # Mock result retrieval response
        mock_result_response = AsyncMock()
        mock_result_response.status = 200
        mock_result_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "winner": "Essay B",
                    "justification": "Essay B has superior argumentation",
                    "confidence": 4.2,
                    "provider": "anthropic",
                    "model": "claude-3-haiku",
                    "response_time_ms": 2500,
                }
            )
        )

        # Set up mock responses in order
        mock_session.post.return_value.__aenter__.return_value = mock_initial_response
        mock_session.get.return_value.__aenter__.side_effect = mock_status_responses + [
            mock_result_response
        ]

        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        result, error = await client.generate_comparison(user_prompt=prompt)

        # Verify successful result
        assert error is None
        assert result is not None
        assert result["winner"] == "Essay B"
        assert result["justification"] == "Essay B has superior argumentation"
        assert result["confidence"] == 4.2

        # Verify API calls were made
        mock_session.post.assert_called_once()  # Initial comparison request
        assert mock_session.get.call_count == 4  # 3 status checks + 1 result retrieval

    async def test_generate_comparison_queued_failed(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test handling of failed queue processing."""
        queue_id = str(uuid4())

        # Mock initial 202 response
        mock_initial_response = AsyncMock()
        mock_initial_response.status = 202
        mock_initial_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "queue_id": queue_id,
                    "status": "queued",
                }
            )
        )

        # Mock status check response showing failure
        mock_status_response = AsyncMock()
        mock_status_response.status = 200
        mock_status_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "queue_id": queue_id,
                    "status": "failed",
                    "error_message": "Provider timeout",
                }
            )
        )

        mock_session.post.return_value.__aenter__.return_value = mock_initial_response
        mock_session.get.return_value.__aenter__.return_value = mock_status_response

        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        result, error = await client.generate_comparison(user_prompt=prompt)

        assert result is None
        assert error == "Queue processing failed: Provider timeout"

    async def test_generate_comparison_queued_expired(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test handling of expired queue requests."""
        queue_id = str(uuid4())

        # Mock initial 202 response
        mock_initial_response = AsyncMock()
        mock_initial_response.status = 202
        mock_initial_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "queue_id": queue_id,
                    "status": "queued",
                }
            )
        )

        # Mock status check response showing expiration
        mock_status_response = AsyncMock()
        mock_status_response.status = 200
        mock_status_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "queue_id": queue_id,
                    "status": "expired",
                }
            )
        )

        mock_session.post.return_value.__aenter__.return_value = mock_initial_response
        mock_session.get.return_value.__aenter__.return_value = mock_status_response

        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        result, error = await client.generate_comparison(user_prompt=prompt)

        assert result is None
        assert error == "Queue request expired"

    async def test_generate_comparison_queued_timeout(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test handling of queue polling timeout."""
        queue_id = str(uuid4())

        # Mock initial 202 response
        mock_initial_response = AsyncMock()
        mock_initial_response.status = 202
        mock_initial_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "queue_id": queue_id,
                    "status": "queued",
                }
            )
        )

        # Mock status check response always returning "processing"
        mock_status_response = AsyncMock()
        mock_status_response.status = 200
        mock_status_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "queue_id": queue_id,
                    "status": "processing",
                }
            )
        )

        mock_session.post.return_value.__aenter__.return_value = mock_initial_response
        mock_session.get.return_value.__aenter__.return_value = mock_status_response

        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        result, error = await client.generate_comparison(user_prompt=prompt)

        assert result is None
        assert error == "Maximum polling attempts reached"

    async def test_generate_comparison_queued_polling_disabled(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock, mock_settings: Settings
    ) -> None:
        """Test handling when queue polling is disabled."""
        # Disable queue polling
        mock_settings.LLM_QUEUE_POLLING_ENABLED = False

        queue_id = str(uuid4())

        # Mock initial 202 response
        mock_initial_response = AsyncMock()
        mock_initial_response.status = 202
        mock_initial_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "queue_id": queue_id,
                    "status": "queued",
                }
            )
        )

        mock_session.post.return_value.__aenter__.return_value = mock_initial_response

        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        result, error = await client.generate_comparison(user_prompt=prompt)

        assert result is None
        assert error == "Request queued but polling is disabled"

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

        result, error = await client.generate_comparison(user_prompt=prompt)

        assert result is None
        assert error == "Queue response missing queue_id"

    async def test_queue_status_check_not_found(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test handling of queue status check returning 404."""
        queue_id = str(uuid4())

        # Mock initial 202 response
        mock_initial_response = AsyncMock()
        mock_initial_response.status = 202
        mock_initial_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "queue_id": queue_id,
                    "status": "queued",
                }
            )
        )

        # Mock status check response with 404
        mock_status_response = AsyncMock()
        mock_status_response.status = 404
        mock_status_response.text = AsyncMock(return_value="Not found")

        mock_session.post.return_value.__aenter__.return_value = mock_initial_response
        mock_session.get.return_value.__aenter__.return_value = mock_status_response

        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        result, error = await client.generate_comparison(user_prompt=prompt)

        assert result is None
        assert (
            error == "Maximum polling attempts reached"
        )  # Will exhaust attempts due to 404 errors

    async def test_result_retrieval_expired(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test handling of result retrieval returning 410 (expired)."""
        queue_id = str(uuid4())

        # Mock initial 202 response
        mock_initial_response = AsyncMock()
        mock_initial_response.status = 202
        mock_initial_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "queue_id": queue_id,
                    "status": "queued",
                }
            )
        )

        # Mock status check response showing completion
        mock_status_response = AsyncMock()
        mock_status_response.status = 200
        mock_status_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "queue_id": queue_id,
                    "status": "completed",
                }
            )
        )

        # Mock result retrieval response with 410
        mock_result_response = AsyncMock()
        mock_result_response.status = 410
        mock_result_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "error": "Result expired",
                }
            )
        )

        mock_session.post.return_value.__aenter__.return_value = mock_initial_response
        mock_session.get.return_value.__aenter__.side_effect = [
            mock_status_response,
            mock_result_response,
        ]

        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        result, error = await client.generate_comparison(user_prompt=prompt)

        assert result is None
        assert error == "Queue result expired"

    @patch("asyncio.sleep")  # Mock sleep to speed up tests
    async def test_exponential_backoff_timing(
        self, mock_sleep: AsyncMock, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test that exponential backoff timing works correctly."""
        queue_id = str(uuid4())

        # Mock initial 202 response
        mock_initial_response = AsyncMock()
        mock_initial_response.status = 202
        mock_initial_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "queue_id": queue_id,
                    "status": "queued",
                }
            )
        )

        # Mock status check responses (processing -> completed)
        mock_status_responses = [
            AsyncMock(
                status=200,
                text=AsyncMock(
                    return_value=json.dumps(
                        {
                            "queue_id": queue_id,
                            "status": "processing",
                        }
                    )
                ),
            ),
            AsyncMock(
                status=200,
                text=AsyncMock(
                    return_value=json.dumps(
                        {
                            "queue_id": queue_id,
                            "status": "completed",
                        }
                    )
                ),
            ),
        ]

        # Mock result response
        mock_result_response = AsyncMock()
        mock_result_response.status = 200
        mock_result_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "winner": "Essay A",
                    "justification": "Test result",
                    "confidence": 4.0,
                    "provider": "anthropic",
                    "model": "claude-3-haiku",
                }
            )
        )

        mock_session.post.return_value.__aenter__.return_value = mock_initial_response
        mock_session.get.return_value.__aenter__.side_effect = mock_status_responses + [
            mock_result_response
        ]

        prompt = """Compare these two essays.
Essay A (ID: 123):
Essay A content.

Essay B (ID: 456):
Essay B content."""

        result, error = await client.generate_comparison(user_prompt=prompt)

        assert error is None
        assert result is not None

        # Verify sleep was called with exponential backoff
        assert mock_sleep.call_count == 1  # One sleep before second status check
        # First delay should be initial_delay * exponential_base = 0.1 * 1.5 = 0.15
        # Use approximate equality due to floating point precision
        call_args = mock_sleep.call_args[0][0]
        assert abs(call_args - 0.15) < 0.01  # Close enough to 0.15
