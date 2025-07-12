"""Simplified unit tests for LLM API routes logic."""

from uuid import uuid4

import pytest

from common_core import EssayComparisonWinner, LLMProviderType
from services.llm_provider_service.api_models import (
    LLMComparisonRequest,
    LLMComparisonResponse,
    LLMConfigOverrides,
    LLMProviderStatus,
)
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.internal_models import LLMOrchestratorResponse


@pytest.mark.asyncio
async def test_comparison_response_model_validation() -> None:
    """Test LLMComparisonResponse model validation."""
    # Arrange
    correlation_id = uuid4()

    # Act - Valid response
    response = LLMComparisonResponse(
        winner=EssayComparisonWinner.ESSAY_A,
        justification="Essay A is better",
        confidence=4.4,  # 1-5 scale
        provider=LLMProviderType.OPENAI,
        model="gpt-4",
        response_time_ms=150,
        token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        cost_estimate=0.005,
        correlation_id=correlation_id,
        trace_id="trace-123",
    )

    # Assert
    assert response.winner == EssayComparisonWinner.ESSAY_A
    assert response.confidence == 4.4
    assert response.token_usage is not None
    assert response.token_usage["total_tokens"] == 150


@pytest.mark.asyncio
async def test_comparison_request_model_validation() -> None:
    """Test LLMComparisonRequest model validation."""
    # Act - Valid request
    request = LLMComparisonRequest(
        user_prompt="Compare these essays",
        essay_a="Essay A content",
        essay_b="Essay B content",
    )

    # Assert
    assert request.user_prompt == "Compare these essays"
    assert request.llm_config_overrides is None
    assert request.correlation_id is None


@pytest.mark.asyncio
async def test_comparison_request_with_overrides() -> None:
    """Test LLMComparisonRequest with config overrides."""
    # Act
    request = LLMComparisonRequest(
        user_prompt="Compare",
        essay_a="A",
        essay_b="B",
        llm_config_overrides=LLMConfigOverrides(
            provider_override=LLMProviderType.ANTHROPIC,
            model_override="claude-3",
            temperature_override=0.3,
            system_prompt_override=None,
            max_tokens_override=None,
        ),
    )

    # Assert
    assert request.llm_config_overrides is not None
    assert request.llm_config_overrides.provider_override == LLMProviderType.ANTHROPIC
    assert request.llm_config_overrides.temperature_override == 0.3


def test_provider_status_model() -> None:
    """Test LLMProviderStatus model."""
    # Act
    status = LLMProviderStatus(
        name=LLMProviderType.OPENAI,
        enabled=True,
        available=True,
        circuit_breaker_state="closed",
        default_model="gpt-4",
        last_success="2024-01-01T12:00:00",
        failure_count=0,
        average_response_time_ms=250.5,
    )

    # Assert
    assert status.name == "openai"
    assert status.available is True
    assert status.circuit_breaker_state == "closed"
    assert status.average_response_time_ms == 250.5


def test_orchestrator_response_to_api_response_mapping() -> None:
    """Test mapping from internal orchestrator response to API response."""
    # Arrange
    correlation_id = uuid4()
    orchestrator_response = LLMOrchestratorResponse(
        winner=EssayComparisonWinner.ESSAY_B,
        justification="Better argumentation",
        confidence=0.9,
        provider=LLMProviderType.ANTHROPIC,
        model="claude-3",
        response_time_ms=200,
        token_usage={"prompt_tokens": 150, "completion_tokens": 75, "total_tokens": 225},
        cost_estimate=0.008,
        correlation_id=correlation_id,
        trace_id="trace-456",
    )

    # Act - Map to API response (simulating the transformation logic)
    winner = orchestrator_response.winner
    confidence_scaled = 1.0 + (orchestrator_response.confidence * 4.0)
    confidence_scaled = max(1.0, min(5.0, confidence_scaled))

    api_response = LLMComparisonResponse(
        winner=winner,
        justification=orchestrator_response.justification,
        confidence=confidence_scaled,
        provider=orchestrator_response.provider,
        model=orchestrator_response.model,
        response_time_ms=orchestrator_response.response_time_ms,
        token_usage=orchestrator_response.token_usage,
        cost_estimate=orchestrator_response.cost_estimate,
        correlation_id=orchestrator_response.correlation_id,
        trace_id=orchestrator_response.trace_id,
    )

    # Assert
    assert api_response.winner == EssayComparisonWinner.ESSAY_B
    assert api_response.justification == "Better argumentation"
    assert api_response.confidence == 4.6  # 1.0 + (0.9 * 4.0) = 4.6
    assert api_response.cost_estimate == 0.008


def test_provider_error_response_format() -> None:
    """Test provider error response formatting."""
    # Arrange
    correlation_id = uuid4()
    from services.llm_provider_service.exceptions import raise_rate_limit_error

    # Simulate catching a HuleEduError
    try:
        raise_rate_limit_error(
            service="llm_provider_service",
            operation="generate_comparison",
            external_service="openai_api",
            message="Rate limit exceeded. Please retry after 60 seconds.",
            correlation_id=correlation_id,
            limit=1000,
            window_seconds=60,
            retry_after=60,
            provider="openai"
        )
    except HuleEduError as error:
        # Act - Format for API response
        error_response = {
            "error": str(error),
            "error_code": error.error_detail.error_code.value,
            "correlation_id": str(correlation_id),
            "details": error.error_detail.details,
        }

        # Assert
        assert "Rate limit exceeded" in error_response["error"]
        assert error_response["error_code"] == "RATE_LIMIT"
        assert error_response["correlation_id"] == str(correlation_id)
        assert isinstance(error_response["details"], dict)
        assert error_response["details"]["retry_after"] == 60
