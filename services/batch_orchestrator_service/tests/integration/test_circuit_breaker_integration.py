"""
Integration tests for circuit breaker functionality in Batch Orchestrator Service.

This tests the real-world behavior of circuit breakers protecting HTTP calls.
"""

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientError, ClientSession
from common_core.pipeline_models import PhaseName
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerError

from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.implementations.batch_conductor_client_impl import (
    BatchConductorClientImpl,
)
from services.batch_orchestrator_service.implementations.circuit_breaker_batch_conductor_client import (  # noqa: E501
    CircuitBreakerBatchConductorClient,
)


@pytest.fixture
def mock_settings() -> Settings:
    """Provide test settings."""
    return Settings(
        BCS_BASE_URL="http://test-bcs:4002",
        BCS_PIPELINE_ENDPOINT="/internal/v1/pipelines/define",
        BCS_REQUEST_TIMEOUT=5,
    )


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    """Provide a circuit breaker with low thresholds for testing."""
    return CircuitBreaker(
        name="test_batch_conductor",
        failure_threshold=2,  # Open after 2 failures
        recovery_timeout=timedelta(seconds=1),  # Short recovery for tests
        success_threshold=1,  # Only need 1 success to close
        expected_exception=Exception,  # Catch all exceptions including ValueError
    )


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_failures(
    mock_settings: Settings, circuit_breaker: CircuitBreaker
) -> None:
    """Test that circuit breaker opens after reaching failure threshold."""
    # Create a mock HTTP session that always fails
    mock_session = AsyncMock(spec=ClientSession)
    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.text.return_value = "Internal Server Error"

    # Make the session.post always fail
    mock_session.post.return_value.__aenter__.return_value = mock_response

    # Create client and wrap with circuit breaker
    base_client = BatchConductorClientImpl(mock_session, mock_settings)
    resilient_client = CircuitBreakerBatchConductorClient(base_client, circuit_breaker)

    # First two calls should fail with ValueError (from the client)
    for i in range(2):
        with pytest.raises(ValueError) as exc_info:
            await resilient_client.resolve_pipeline(
                "batch-123", PhaseName.SPELLCHECK, "550e8400-e29b-41d4-a716-446655440001"
            )
        assert "BCS returned error status 500" in str(exc_info.value)

    # Third call should be blocked by circuit breaker
    with pytest.raises(CircuitBreakerError) as cb_exc_info:
        await resilient_client.resolve_pipeline(
            "batch-123", PhaseName.SPELLCHECK, "550e8400-e29b-41d4-a716-446655440002"
        )
    assert "Circuit breaker" in str(cb_exc_info.value)
    assert "is OPEN" in str(cb_exc_info.value)

    # Circuit breaker should be open, preventing further HTTP calls


@pytest.mark.asyncio
async def test_circuit_breaker_recovers_after_timeout(
    mock_settings: Settings, circuit_breaker: CircuitBreaker
) -> None:
    """Test that circuit breaker attempts recovery after timeout."""
    # Create a mock session that fails initially, then succeeds
    mock_session = AsyncMock(spec=ClientSession)
    call_count = 0

    def mock_post(*args: Any, **kwargs: Any) -> AsyncMock:
        nonlocal call_count
        call_count += 1

        mock_response = AsyncMock()
        if call_count <= 2:
            # First two calls fail
            mock_response.status = 500
            mock_response.text.return_value = "Internal Server Error"
        else:
            # Third call succeeds
            mock_response.status = 200
            mock_response.text.return_value = (
                '{"batch_id": "batch-123", "final_pipeline": ["SPELLCHECK"]}'
            )

        # Create a context manager for the response
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_context.__aexit__.return_value = None
        return mock_context

    mock_session.post.side_effect = mock_post

    # Create resilient client
    base_client = BatchConductorClientImpl(mock_session, mock_settings)
    resilient_client = CircuitBreakerBatchConductorClient(base_client, circuit_breaker)

    # Fail twice to open circuit
    for _ in range(2):
        with pytest.raises(ValueError):
            await resilient_client.resolve_pipeline(
                "batch-123", PhaseName.SPELLCHECK, "550e8400-e29b-41d4-a716-446655440003"
            )

    # Circuit should be open now
    with pytest.raises(CircuitBreakerError):
        await resilient_client.resolve_pipeline(
            "batch-123", PhaseName.SPELLCHECK, "550e8400-e29b-41d4-a716-446655440004"
        )

    # Wait for recovery timeout
    await asyncio.sleep(1.5)

    # Next call should succeed (circuit in half-open, then closes)
    result = await resilient_client.resolve_pipeline(
        "batch-123", PhaseName.SPELLCHECK, "550e8400-e29b-41d4-a716-446655440005"
    )
    assert result["batch_id"] == "batch-123"
    assert result["final_pipeline"] == ["SPELLCHECK"]

    # Circuit should be closed now, subsequent calls work
    result = await resilient_client.resolve_pipeline(
        "batch-456", PhaseName.CJ_ASSESSMENT, "550e8400-e29b-41d4-a716-446655440006"
    )
    assert result["batch_id"] == "batch-123"  # Mock always returns same response


@pytest.mark.asyncio
async def test_circuit_breaker_transparent_when_service_healthy(mock_settings: Settings) -> None:
    """Test that circuit breaker is transparent when service is healthy."""
    # Create a circuit breaker with normal thresholds
    circuit_breaker = CircuitBreaker(
        name="test_batch_conductor",
        failure_threshold=5,
        recovery_timeout=timedelta(seconds=60),
        success_threshold=2,
        expected_exception=ClientError,
    )

    # Create a mock session that always succeeds
    mock_session = AsyncMock(spec=ClientSession)
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text.return_value = """{
        "batch_id": "batch-123",
        "final_pipeline": ["SPELLCHECK", "CJ_ASSESSMENT"],
        "analysis": {
            "current_status": "COMPLETED",
            "required_phases": ["SPELLCHECK", "CJ_ASSESSMENT"]
        }
    }"""
    mock_session.post.return_value.__aenter__.return_value = mock_response

    # Create resilient client
    base_client = BatchConductorClientImpl(mock_session, mock_settings)
    resilient_client = CircuitBreakerBatchConductorClient(base_client, circuit_breaker)

    # Make multiple successful calls
    for i in range(10):
        result = await resilient_client.resolve_pipeline(
            f"batch-{i}", PhaseName.CJ_ASSESSMENT, f"550e8400-e29b-41d4-a716-44665544{i:04d}"
        )
        assert result["batch_id"] == "batch-123"
        assert "SPELLCHECK" in result["final_pipeline"]
        assert "CJ_ASSESSMENT" in result["final_pipeline"]

    # Circuit should still be closed - all calls succeeded
    assert circuit_breaker.state.value == "closed"


@pytest.mark.asyncio
async def test_circuit_breaker_handles_different_error_types(mock_settings: Settings) -> None:
    """Test that circuit breaker only counts expected exceptions."""
    circuit_breaker = CircuitBreaker(
        name="test_batch_conductor",
        failure_threshold=2,
        recovery_timeout=timedelta(seconds=60),
        success_threshold=1,
        expected_exception=ClientError,  # Only count ClientError
    )

    # Create mock session
    mock_session = AsyncMock(spec=ClientSession)

    # First make it raise ValueError (not counted by circuit breaker)
    mock_response = AsyncMock()
    mock_response.status = 400
    mock_response.text.return_value = "Bad Request"
    mock_session.post.return_value.__aenter__.return_value = mock_response

    base_client = BatchConductorClientImpl(mock_session, mock_settings)
    resilient_client = CircuitBreakerBatchConductorClient(base_client, circuit_breaker)

    # These failures won't open the circuit (wrong exception type)
    for i in range(3):
        with pytest.raises(ValueError):
            await resilient_client.resolve_pipeline(
                "batch-123", PhaseName.SPELLCHECK, f"550e8400-e29b-41d4-a716-44665544{i + 10:04d}"
            )

    # Circuit should still be closed
    assert circuit_breaker.state.value == "closed"

    # Now make it raise ClientError
    mock_session.post.side_effect = ClientError("Connection failed")

    # These failures WILL count
    for i in range(2):
        with pytest.raises(ClientError):
            await resilient_client.resolve_pipeline(
                "batch-123", PhaseName.SPELLCHECK, f"550e8400-e29b-41d4-a716-44665544{i + 13:04d}"
            )

    # Circuit should now be open
    assert circuit_breaker.state.value == "open"

    # Next call blocked
    with pytest.raises(CircuitBreakerError):
        await resilient_client.resolve_pipeline(
            "batch-123", PhaseName.SPELLCHECK, "550e8400-e29b-41d4-a716-446655440015"
        )
