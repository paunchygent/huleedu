"""
Tests for batch routes in API Gateway Service.

Tests the POST /v1/batches/{batch_id}/pipelines endpoint with proper contract validation,
authentication, rate limiting, and error handling.
"""

from __future__ import annotations

import pytest
from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi.testclient import TestClient

from common_core.events.client_commands import ClientBatchPipelineRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.pipeline_models import PhaseName
from huleedu_service_libs.kafka_client import KafkaBus
from services.api_gateway_service.app.main import create_app
from services.api_gateway_service.tests.test_provider import (
    AuthTestProvider,
    InfrastructureTestProvider,
)

USER_ID = "test_user_123"


@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    """Clear Prometheus registry before each test to avoid collisions."""
    from prometheus_client import REGISTRY

    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    yield


@pytest.fixture
async def container():
    """Create test container with standardized test providers."""
    container = make_async_container(
        InfrastructureTestProvider(),
        AuthTestProvider(user_id=USER_ID),
        FastapiProvider(),  # Required for Request context
    )
    yield container
    await container.close()


@pytest.fixture
async def mock_kafka_bus(container):
    """Get mock KafkaBus from container."""
    async with container() as request_container:
        kafka_bus = await request_container.get(KafkaBus)
        yield kafka_bus


@pytest.fixture
def client_with_mocks(container):
    """Create test client with pure Dishka container."""
    app = create_app()

    # Set up Dishka with test container - this replaces the production container
    setup_dishka(container, app)

    with TestClient(app) as client:
        yield client


@pytest.mark.asyncio
async def test_successful_pipeline_request(client_with_mocks, mock_kafka_bus):
    """Test successful pipeline request with valid ClientBatchPipelineRequestV1."""
    batch_id = "test_batch_123"
    request_data = {
        "batch_id": batch_id,
        "requested_pipeline": PhaseName.AI_FEEDBACK.value,
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
    assert envelope.data.requested_pipeline == PhaseName.AI_FEEDBACK.value
    assert envelope.data.user_id == "test_user_123"
    assert envelope.data.is_retry is False


@pytest.mark.asyncio
async def test_batch_id_mismatch_validation(client_with_mocks):
    """Test validation when path batch_id doesn't match request body batch_id."""
    path_batch_id = "batch_from_path"
    body_batch_id = "batch_from_body"

    request_data = {
        "batch_id": body_batch_id,
        "requested_pipeline": PhaseName.SPELLCHECK.value,
    }

    response = client_with_mocks.post(f"/v1/batches/{path_batch_id}/pipelines", json=request_data)

    assert response.status_code == 400
    response_json = response.json()
    assert "error" in response_json
    error = response_json["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "Batch ID in path must match batch ID in request body" in error["message"]


@pytest.mark.asyncio
async def test_user_id_propagation(client_with_mocks, mock_kafka_bus):
    """Test that authenticated user_id is properly propagated to the event."""
    batch_id = "test_batch_456"
    request_data = {
        "batch_id": batch_id,
        "requested_pipeline": PhaseName.CJ_ASSESSMENT.value,
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
        "requested_pipeline": PhaseName.SPELLCHECK.value,
    }

    response = client_with_mocks.post(f"/v1/batches/{batch_id}/pipelines", json=request_data)

    assert response.status_code == 503
    response_json = response.json()
    assert "error" in response_json
    error = response_json["error"]
    assert error["code"] == "KAFKA_PUBLISH_ERROR"
    assert "Failed to publish pipeline request" in error["message"]


@pytest.mark.asyncio
async def test_retry_request_handling(client_with_mocks, mock_kafka_bus):
    """Test handling of retry requests with retry context."""
    batch_id = "test_batch_retry"
    request_data = {
        "batch_id": batch_id,
        "requested_pipeline": PhaseName.AI_FEEDBACK.value,
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
async def test_missing_pipeline_field_validation(client_with_mocks):
    """Test validation when the requested_pipeline field is missing."""
    batch_id = "test_batch_invalid"

    # Missing required field
    invalid_request_data = {
        "batch_id": batch_id,
        # Missing requested_pipeline
    }

    response = client_with_mocks.post(
        f"/v1/batches/{batch_id}/pipelines", json=invalid_request_data
    )

    assert response.status_code == 422  # Unprocessable Entity
    assert "Field required" in str(response.json())
    assert "requested_pipeline" in str(response.json())


@pytest.mark.asyncio
async def test_invalid_enum_value_for_pipeline(client_with_mocks):
    """Test validation when an invalid string is provided for the pipeline enum."""
    batch_id = "test_batch_invalid_enum"
    request_data = {
        "batch_id": batch_id,
        "requested_pipeline": "invalid_pipeline_name",
    }

    response = client_with_mocks.post(f"/v1/batches/{batch_id}/pipelines", json=request_data)

    assert response.status_code == 422  # Unprocessable Entity
    response_json = response.json()
    assert "error" in response_json
    error = response_json["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert (
        "Input should be 'spellcheck', 'ai_feedback', 'cj_assessment', 'nlp' or 'student_matching'"
        in error["message"]
    )

    # Check validation error details
    assert "details" in error
    assert "validation_errors" in error["details"]
    validation_error = error["details"]["validation_errors"][0]
    assert validation_error["type"] == "enum"
    assert validation_error["loc"] == ["body", "requested_pipeline"]


@pytest.mark.asyncio
async def test_correlation_id_generation(client_with_mocks, mock_kafka_bus):
    """Test that correlation IDs are properly generated and used."""
    batch_id = "test_batch_correlation"
    request_data = {
        "batch_id": batch_id,
        "requested_pipeline": PhaseName.SPELLCHECK.value,
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
