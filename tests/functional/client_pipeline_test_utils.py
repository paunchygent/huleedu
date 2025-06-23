"""
Client Pipeline Test Utilities

Utility functions for creating and publishing ClientBatchPipelineRequestV1 events
in E2E integration tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from common_core.events.client_commands import ClientBatchPipelineRequestV1
from common_core.events.envelope import EventEnvelope
from tests.utils.kafka_test_manager import KafkaTestManager


async def create_client_pipeline_request_event(
    batch_id: str,
    requested_pipeline: str,
    correlation_id: str | None = None,
) -> EventEnvelope[ClientBatchPipelineRequestV1]:
    """Create a ClientBatchPipelineRequestV1 event for testing."""
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    return EventEnvelope(
        event_id=uuid.uuid4(),
        event_type="huleedu.commands.batch.pipeline.v1",
        event_timestamp=datetime.fromisoformat("2025-01-01T00:00:00Z".replace("Z", "+00:00")),
        source_service="api_gateway_service",
        correlation_id=uuid.UUID(correlation_id) if correlation_id else None,
        data=ClientBatchPipelineRequestV1(
            batch_id=batch_id,
            requested_pipeline=requested_pipeline,
            user_id="test_user_123",
        ),
    )


async def publish_client_pipeline_request(
    kafka_manager: KafkaTestManager,
    batch_id: str,
    requested_pipeline: str,
    correlation_id: str | None = None,
) -> str:
    """Publish ClientBatchPipelineRequestV1 event and return correlation ID."""
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    event = await create_client_pipeline_request_event(batch_id, requested_pipeline, correlation_id)

    # Convert to JSON-serializable format using Pydantic's JSON mode
    event_dict = event.model_dump(mode="json")

    await kafka_manager.publish_event("huleedu.commands.batch.pipeline.v1", event_dict)

    print(f"📤 Published ClientBatchPipelineRequestV1 for batch {batch_id}")
    return correlation_id
