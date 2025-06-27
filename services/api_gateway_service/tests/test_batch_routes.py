"""
Tests for batch routes in API Gateway Service.

Tests the POST /v1/batches/{batch_id}/pipelines endpoint with proper contract validation,
authentication, rate limiting, and error handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from fastapi.testclient import TestClient

from common_core.events.client_commands import ClientBatchPipelineRequestV1
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.kafka_client import KafkaBus
from prometheus_client import CollectorRegistry
from services.api_gateway_service.app.main import create_app
from services.api_gateway_service.app.metrics import GatewayMetrics
from services.api_gateway_service.auth import get_current_user_id


class MockProvider(Provider):
    """Test provider with mock dependencies."""

    scope = Scope.APP

    def __init__(self):
        super().__init__()
        self.mock_kafka_bus = AsyncMock()
        self.mock_kafka_bus.publish = AsyncMock()

    @provide
    def get_kafka_bus(self) -> KafkaBus:
        return self.mock_kafka_bus

    @provide
    def provide_metrics(self) -> GatewayMetrics:
        return GatewayMetrics()

    @provide
    def provide_registry(self) -> CollectorRegistry:
        from prometheus_client import REGISTRY

        return REGISTRY


@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    """Clear Prometheus registry before each test to avoid collisions."""
    from prometheus_client import REGISTRY

    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    yield


@pytest.fixture
def mock_provider():
    """Create mock provider for testing."""
    return MockProvider()


@pytest.fixture
def mock_kafka_bus(mock_provider):
    """Get mock KafkaBus from provider."""
    return mock_provider.mock_kafka_bus


@pytest.fixture
async def container(mock_provider):
    """Create test container with mock dependencies."""
    container = make_async_container(mock_provider)
    yield container
    await container.close()


@pytest.fixture
def mock_auth():
    """Mock authentication to return test user."""

    def get_test_user():
        return "test_user_123"

    return get_test_user


@pytest.fixture
def client_with_mocks(container, mock_auth):
    """Create test client with mocked dependencies."""
    app = create_app()

    # Override authentication
    app.dependency_overrides[get_current_user_id] = mock_auth

    # Set up Dishka with test container
    from dishka.integrations.fastapi import setup_dishka

    setup_dishka(container, app)

    with TestClient(app) as client:
        yield client

    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_successful_pipeline_request(client_with_mocks, mock_kafka_bus):
    """Test successful pipeline request with valid ClientBatchPipelineRequestV1."""
    batch_id = "test_batch_123"
    request_data = {
        "batch_id": batch_id,
        "requested_pipeline": "ai_feedback",
        "is_retry": False,
    }

    response = client_with_mocks.post(f"/v1/batches/{batch_id}/pipelines", json=request_data)

    # Verify response
    assert response.status_code == 202
    response_json = response.json()
    assert response_json["status"] == "accepted"
    assert response_json["batch_id"] == batch_id
    assert "correlation_id" in response_json

    # Verify Kafka publish was called
    mock_kafka_bus.publish.assert_called_once()
    call_args = mock_kafka_bus.publish.call_args

    # Verify topic and key
    assert call_args.kwargs["topic"] == "huleedu.commands.batch.pipeline.v1"
    assert call_args.kwargs["key"] == batch_id

    # Verify EventEnvelope structure
    envelope = call_args.kwargs["envelope"]
    assert isinstance(envelope, EventEnvelope)
    assert envelope.event_type == "huleedu.commands.batch.pipeline.v1"
    assert envelope.source_service == "api_gateway_service"

    # Verify ClientBatchPipelineRequestV1 data
    assert isinstance(envelope.data, ClientBatchPipelineRequestV1)
    assert envelope.data.batch_id == batch_id
    assert envelope.data.requested_pipeline == "ai_feedback"
    assert envelope.data.user_id == "test_user_123"
    assert envelope.data.is_retry is False


@pytest.mark.asyncio
async def test_batch_id_mismatch_validation(client_with_mocks):
    """Test validation when path batch_id doesn't match request body batch_id."""
    path_batch_id = "batch_from_path"
    body_batch_id = "batch_from_body"

    request_data = {
        "batch_id": body_batch_id,
        "requested_pipeline": "spellcheck",
    }

    response = client_with_mocks.post(f"/v1/batches/{path_batch_id}/pipelines", json=request_data)

    assert response.status_code == 400
    assert "Batch ID in path must match batch ID in request body" in response.json()["detail"]


@pytest.mark.asyncio
async def test_user_id_propagation(client_with_mocks, mock_kafka_bus):
    """Test that authenticated user_id is properly propagated to the event."""
    batch_id = "test_batch_456"
    request_data = {
        "batch_id": batch_id,
        "requested_pipeline": "cj_assessment",
    }

    response = client_with_mocks.post(f"/v1/batches/{batch_id}/pipelines", json=request_data)

    assert response.status_code == 202

    # Verify user_id was set in the published event
    call_args = mock_kafka_bus.publish.call_args
    envelope = call_args.kwargs["envelope"]
    assert envelope.data.user_id == "test_user_123"


@pytest.mark.asyncio
async def test_kafka_publish_failure_handling(client_with_mocks, mock_kafka_bus):
    """Test error handling when Kafka publishing fails."""
    mock_kafka_bus.publish.side_effect = Exception("Kafka connection failed")

    batch_id = "test_batch_789"
    request_data = {
        "batch_id": batch_id,
        "requested_pipeline": "spellcheck",
    }

    response = client_with_mocks.post(f"/v1/batches/{batch_id}/pipelines", json=request_data)

    assert response.status_code == 503
    assert "Failed to process pipeline request" in response.json()["detail"]


@pytest.mark.asyncio
async def test_retry_request_handling(client_with_mocks, mock_kafka_bus):
    """Test handling of retry requests with retry context."""
    batch_id = "test_batch_retry"
    request_data = {
        "batch_id": batch_id,
        "requested_pipeline": "ai_feedback",
        "is_retry": True,
        "retry_reason": "Previous attempt failed due to network error",
    }

    response = client_with_mocks.post(f"/v1/batches/{batch_id}/pipelines", json=request_data)

    assert response.status_code == 202

    # Verify retry context is preserved
    call_args = mock_kafka_bus.publish.call_args
    envelope = call_args.kwargs["envelope"]
    assert envelope.data.is_retry is True
    assert envelope.data.retry_reason == "Previous attempt failed due to network error"


@pytest.mark.asyncio
async def test_invalid_pipeline_request_validation(client_with_mocks):
    """Test validation of invalid ClientBatchPipelineRequestV1 data."""
    batch_id = "test_batch_invalid"

    # Missing required field
    invalid_request_data = {
        "batch_id": batch_id,
        # Missing requested_pipeline
    }

    response = client_with_mocks.post(
        f"/v1/batches/{batch_id}/pipelines", json=invalid_request_data
    )

    assert response.status_code == 422  # Validation error
    assert "requested_pipeline" in str(response.json())


@pytest.mark.asyncio
async def test_correlation_id_generation(client_with_mocks, mock_kafka_bus):
    """Test that correlation IDs are properly generated and used."""
    batch_id = "test_batch_correlation"
    request_data = {
        "batch_id": batch_id,
        "requested_pipeline": "spellcheck",
    }

    response = client_with_mocks.post(f"/v1/batches/{batch_id}/pipelines", json=request_data)

    assert response.status_code == 202
    response_json = response.json()

    # Verify correlation_id in response
    assert "correlation_id" in response_json
    correlation_id = response_json["correlation_id"]

    # Verify correlation_id matches EventEnvelope
    call_args = mock_kafka_bus.publish.call_args
    envelope = call_args.kwargs["envelope"]
    assert str(envelope.correlation_id) == correlation_id
    assert str(envelope.data.client_correlation_id) == correlation_id
