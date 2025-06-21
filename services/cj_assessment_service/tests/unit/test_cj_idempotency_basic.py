"""
Tests for basic idempotency scenarios in the CJ Assessment Service.

- First-time event processing success.
- Duplicate event detection and skipping.
- Deterministic event ID generation.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka import ConsumerRecord

from services.cj_assessment_service.event_processor import process_single_message
from services.cj_assessment_service.tests.unit.mocks import MockDatabase, MockRedisClient

# --- Test Helpers ---


def create_mock_kafka_message(event_data: dict) -> ConsumerRecord:
    """Create a mock Kafka ConsumerRecord for testing."""
    return ConsumerRecord(
        topic="cj-assessment",
        partition=0,
        offset=0,
        timestamp=int(datetime.now(UTC).timestamp() * 1000),
        timestamp_type=0,
        key=None,
        value=json.dumps(event_data).encode(),
        checksum=None,
        serialized_key_size=0,
        serialized_value_size=len(json.dumps(event_data)),
        headers=[],
    )


@pytest.fixture
def sample_cj_request_event() -> dict:
    """Sample CJ assessment request event envelope data."""
    batch_id = str(uuid.uuid4())
    essay1_id = str(uuid.uuid4())
    essay2_id = str(uuid.uuid4())
    storage1_id = str(uuid.uuid4())
    storage2_id = str(uuid.uuid4())
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "huleedu.els.cj_assessment.requested.v1",
        "event_timestamp": "2024-01-01T12:00:00Z",
        "source_service": "essay_lifecycle_service",
        "correlation_id": str(uuid.uuid4()),
        "data": {
            "entity_ref": {"entity_id": batch_id, "entity_type": "batch"},
            "system_metadata": {
                "entity": {"entity_id": batch_id, "entity_type": "batch"},
                "timestamp": "2024-01-01T12:00:00Z",
                "processing_stage": "pending",
                "event": "els.cj_assessment.requested",
            },
            "essays_for_cj": [
                {"essay_id": essay1_id, "text_storage_id": storage1_id},
                {"essay_id": essay2_id, "text_storage_id": storage2_id},
            ],
            "language": "en",
            "course_code": "ENG101",
            "essay_instructions": "Compare and rank the essays.",
            "llm_config_overrides": None,
        },
    }


@pytest.fixture
def mock_boundary_services(
    mock_cj_repository: MockDatabase,
) -> tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, Any]:
    """Create mock boundary services (external dependencies only)."""
    mock_content_client = AsyncMock()
    mock_content_client.fetch_content = AsyncMock(
        return_value="Sample essay content for testing CJ assessment.",
    )
    mock_event_publisher = AsyncMock()
    mock_event_publisher.publish_assessment_completed = AsyncMock()
    mock_event_publisher.publish_assessment_failed = AsyncMock()
    mock_llm_interaction = AsyncMock()
    # Configure LLM to return valid comparison results to prevent infinite loop
    from services.cj_assessment_service.models_api import (
        ComparisonResult,
        LLMAssessmentResponseSchema,
    )

    async def mock_perform_comparisons(tasks, **kwargs):
        results = []
        for task in tasks:
            results.append(
                ComparisonResult(
                    task=task,
                    llm_assessment=LLMAssessmentResponseSchema(
                        winner="Essay A",
                        confidence=3.0,  # Must be >= 1.0 and <= 5.0
                        justification="Mock comparison result",
                    ),
                    prompt_hash="mock_hash",
                    raw_llm_response_content="Mock LLM response",
                    error_message=None,
                    from_cache=False,
                ),
            )
        return results

    mock_llm_interaction.perform_comparisons = AsyncMock(side_effect=mock_perform_comparisons)

    class Settings:
        MAX_PAIRWISE_COMPARISONS = 100
        CJ_ASSESSMENT_FAILED_TOPIC = "cj_assessment_failed"
        CJ_ASSESSMENT_COMPLETED_TOPIC = "cj_assessment_completed"
        SERVICE_NAME = "cj_assessment_service"

    settings = Settings()
    return (
        mock_cj_repository,
        mock_content_client,
        mock_event_publisher,
        mock_llm_interaction,
        settings,
    )


# --- Test Cases ---


@pytest.mark.asyncio
async def test_first_time_event_processing_success(
    sample_cj_request_event: dict,
    mock_boundary_services: tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, MagicMock],
    mock_redis_client: MockRedisClient,
) -> None:
    """Test that first-time CJ assessment events are processed successfully with idempotency."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    database, content_client, event_publisher, llm_interaction, settings = mock_boundary_services

    kafka_msg = create_mock_kafka_message(sample_cj_request_event)

    @idempotent_consumer(redis_client=mock_redis_client, ttl_seconds=86400)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
        return await process_single_message(
            msg=msg,
            database=database,
            content_client=content_client,
            event_publisher=event_publisher,
            llm_interaction=llm_interaction,
            settings_obj=settings,
        )

    result = await handle_message_idempotently(kafka_msg)

    assert result is True
    assert len(mock_redis_client.set_calls) == 1
    assert len(mock_redis_client.delete_calls) == 0

    set_call = mock_redis_client.set_calls[0]
    assert set_call[0].startswith("huleedu:events:seen:")
    assert set_call[1] == "1"
    assert set_call[2] == 86400

    content_client.fetch_content.assert_called()
    event_publisher.publish_assessment_completed.assert_called_once()
    assert len(database.batches) == 1
    assert len(database.essays[1]) == 2


@pytest.mark.asyncio
async def test_duplicate_event_skipped(
    sample_cj_request_event: dict,
    mock_boundary_services: tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, MagicMock],
    mock_redis_client: MockRedisClient,
) -> None:
    """Test that duplicate events are skipped without processing business logic."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    from common_core.events.utils import generate_deterministic_event_id

    database, content_client, event_publisher, llm_interaction, settings = mock_boundary_services

    kafka_msg = create_mock_kafka_message(sample_cj_request_event)

    deterministic_id = generate_deterministic_event_id(kafka_msg.value)
    mock_redis_client.keys[f"huleedu:events:seen:{deterministic_id}"] = "1"

    @idempotent_consumer(redis_client=mock_redis_client, ttl_seconds=86400)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool | None:
        return await process_single_message(
            msg=msg,
            database=database,
            content_client=content_client,
            event_publisher=event_publisher,
            llm_interaction=llm_interaction,
            settings_obj=settings,
        )

    result = await handle_message_idempotently(kafka_msg)

    assert result is None
    assert len(mock_redis_client.set_calls) == 1
    assert len(mock_redis_client.delete_calls) == 0

    content_client.fetch_content.assert_not_called()
    event_publisher.publish_assessment_completed.assert_not_called()
    assert len(database.batches) == 0


@pytest.mark.asyncio
async def test_deterministic_event_id_generation(
    mock_boundary_services: tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, MagicMock],
    mock_redis_client: MockRedisClient,
) -> None:
    """Test that deterministic event IDs are generated correctly for CJ assessment events."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    database, content_client, event_publisher, llm_interaction, settings = mock_boundary_services

    base_event_data = {
        "entity_ref": {"entity_id": "test-batch-123", "entity_type": "batch"},
        "system_metadata": {
            "entity": {"entity_id": "test-batch-123", "entity_type": "batch"},
            "timestamp": "2024-01-01T12:00:00Z",
            "processing_stage": "pending",
            "event": "els.cj_assessment.requested",
        },
        "essays_for_cj": [{"essay_id": "essay-1", "text_storage_id": "storage-1"}],
        "language": "en",
        "course_code": "TEST",
        "essay_instructions": "Test instructions",
        "llm_config_overrides": None,
    }

    event1 = {
        "event_id": str(uuid.uuid4()),
        "event_type": "huleedu.els.cj_assessment.requested.v1",
        "event_timestamp": "2024-01-01T12:00:00Z",
        "source_service": "essay_lifecycle_service",
        "correlation_id": str(uuid.uuid4()),
        "data": base_event_data,
    }

    event2 = {
        "event_id": str(uuid.uuid4()),
        "event_type": "huleedu.els.cj_assessment.requested.v1",
        "event_timestamp": "2024-01-01T13:00:00Z",
        "source_service": "essay_lifecycle_service",
        "correlation_id": str(uuid.uuid4()),
        "data": base_event_data,
    }

    kafka_msg1 = create_mock_kafka_message(event1)
    kafka_msg2 = create_mock_kafka_message(event2)

    @idempotent_consumer(redis_client=mock_redis_client, ttl_seconds=86400)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool | None:
        return await process_single_message(
            msg=msg,
            database=database,
            content_client=content_client,
            event_publisher=event_publisher,
            llm_interaction=llm_interaction,
            settings_obj=settings,
        )

    result1 = await handle_message_idempotently(kafka_msg1)
    assert result1 is True

    result2 = await handle_message_idempotently(kafka_msg2)
    assert result2 is None

    assert len(mock_redis_client.set_calls) == 2
    assert len(mock_redis_client.delete_calls) == 0

    key1 = mock_redis_client.set_calls[0][0]
    key2 = mock_redis_client.set_calls[1][0]
    assert key1 == key2
    assert key1.startswith("huleedu:events:seen:")
    assert len(key1.split(":")[3]) == 64

    assert content_client.fetch_content.call_count == 1
    event_publisher.publish_assessment_completed.assert_called_once()
    assert len(database.batches) == 1
