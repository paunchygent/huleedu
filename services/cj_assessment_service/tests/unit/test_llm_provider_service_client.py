"""Unit tests for LLM Provider Service client."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import aiohttp
import pytest
from common_core.error_enums import ErrorCode
from huleedu_service_libs.error_handling import HuleEduError, assert_raises_huleedu_error

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.llm_provider_service_client import (
    LLMProviderServiceClient,
    _build_llm_config_override_payload,
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

    async def test_generate_comparison_async_success(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test successful async comparison generation forwards payload verbatim."""
        # Mock async response - LLM Provider Service queues request and returns 202
        mock_response = AsyncMock()
        mock_response.status = 202
        mock_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "queue_id": str(uuid4()),
                    "status": "queued",
                    "message": (
                        "Request queued for processing. Result will be delivered via "
                        "callback to topic: huleedu.llm_provider.comparison_result.v1"
                    ),
                    "estimated_wait_minutes": 2,
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
        metadata = {"essay_a_id": "123", "essay_b_id": "456"}

        # Call generate_comparison
        correlation_id = uuid4()
        result = await client.generate_comparison(
            user_prompt=prompt,
            model_override="claude-3-5-haiku",
            temperature_override=0.1,
            correlation_id=correlation_id,
            request_metadata=metadata,
        )

        # Async-only architecture: result should always be None
        # Results delivered via Kafka callbacks
        assert result is None

        # Verify API call and request body
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        assert call_args[0][0] == "http://test-llm-service:8090/api/v1/comparison"

        # Verify request body
        request_body = call_args[1]["json"]
        assert request_body["user_prompt"] == prompt
        # Verify no separate essay fields exist
        assert "essay_a" not in request_body
        assert "essay_b" not in request_body
        overrides = request_body["llm_config_overrides"]
        assert overrides["provider_override"] == "anthropic"
        assert overrides["model_override"] == "claude-3-5-haiku"
        assert overrides["temperature_override"] == 0.1
        assert "system_prompt_override" not in overrides
        assert "callback_topic" in request_body
        assert request_body["callback_topic"] == client.settings.LLM_PROVIDER_CALLBACK_TOPIC
        assert request_body["metadata"] == metadata

    async def test_generate_comparison_passes_system_prompt_override(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Ensure system prompt overrides flow into llm_config_overrides."""
        mock_response = AsyncMock()
        mock_response.status = 202
        mock_response.text = AsyncMock(
            return_value=json.dumps({"queue_id": str(uuid4()), "status": "queued"})
        )
        mock_session.post.return_value.__aenter__.return_value = mock_response

        prompt = "Compare essays"
        correlation_id = uuid4()
        override_prompt = "CJ canonical prompt"

        await client.generate_comparison(
            user_prompt=prompt,
            correlation_id=correlation_id,
            system_prompt_override=override_prompt,
        )

        request_body = mock_session.post.call_args[1]["json"]
        assert request_body["llm_config_overrides"]["system_prompt_override"] == override_prompt
        assert request_body["user_prompt"] == prompt
        assert request_body["metadata"] == {}

    async def test_generate_comparison_passes_request_metadata(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Ensure request metadata is forwarded to the provider."""
        mock_response = AsyncMock()
        mock_response.status = 202
        mock_response.text = AsyncMock(return_value=json.dumps({"queue_id": str(uuid4())}))
        mock_session.post.return_value.__aenter__.return_value = mock_response

        prompt = """Compare essays\nEssay A (ID: 1):\nA\n\nEssay B (ID: 2):\nB"""
        metadata = {"essay_a_id": "1", "essay_b_id": "2"}

        await client.generate_comparison(
            user_prompt=prompt,
            correlation_id=uuid4(),
            request_metadata=metadata,
        )

        request_body = mock_session.post.call_args[1]["json"]
        assert request_body["metadata"] == metadata


class TestOverrideAdapter:
    """Unit tests for the override payload adapter."""

    def test_returns_none_when_all_fields_none(self) -> None:
        payload = _build_llm_config_override_payload()
        assert payload is None

    def test_converts_string_provider_to_enum_value(self) -> None:
        payload = _build_llm_config_override_payload(
            provider_override="ANTHROPIC",
            model_override="claude",
        )
        assert payload is not None
        assert payload["provider_override"] == "anthropic"
        assert payload["model_override"] == "claude"

    def test_unknown_provider_omits_provider_override_but_preserves_other_fields(self) -> None:
        payload = _build_llm_config_override_payload(
            provider_override="unknown-provider",
            model_override="claude",
            temperature_override=0.7,
        )
        assert payload == {
            "model_override": "claude",
            "temperature_override": 0.7,
        }

    def test_preserves_none_fields_without_defaults(self) -> None:
        payload = _build_llm_config_override_payload(
            provider_override=None,
            model_override=None,
            temperature_override=None,
            system_prompt_override="prompt",
        )
        assert payload == {"system_prompt_override": "prompt"}

    async def test_generate_comparison_rejects_sync_response(
        self, client: LLMProviderServiceClient, mock_session: AsyncMock
    ) -> None:
        """Test that 200 responses are rejected as architectural violations."""
        # Mock synchronous response - this should be rejected
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(
            return_value=json.dumps(
                {
                    "winner": "Essay A",
                    "justification": "Essay A has better structure",
                    "confidence": 4.5,
                    "provider": "anthropic",
                    "model": "claude-3-5-haiku",
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

        # Call generate_comparison - should raise error
        correlation_id = uuid4()
        with assert_raises_huleedu_error(
            error_code=ErrorCode.INVALID_RESPONSE, message_contains="synchronous response (200)"
        ):
            await client.generate_comparison(
                user_prompt=prompt,
                model_override="claude-3-5-haiku",
                temperature_override=0.1,
                correlation_id=correlation_id,
            )

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

    # Queue-based response tests

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
