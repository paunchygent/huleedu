"""
Tests for basic idempotency scenarios in the CJ Assessment Service.

- First-time event processing success.
- Duplicate event detection and skipping.
- Deterministic event ID generation.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiokafka import ConsumerRecord
from common_core.domain_enums import CourseCode, EssayComparisonWinner
from huleedu_service_libs.event_utils import generate_deterministic_event_id
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.event_processor import process_single_message
from services.cj_assessment_service.models_api import ComparisonResult, LLMAssessmentResponseSchema
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
            "course_code": CourseCode.ENG5.value,
            "essay_instructions": "Compare and rank the essays.",
            "llm_config_overrides": None,
        },
    }


@pytest.fixture
def mock_boundary_services(
    mock_cj_repository: MockDatabase,
) -> tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, Settings]:
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

    async def mock_perform_comparisons(tasks: list[Any], **kwargs: Any) -> list[ComparisonResult]:
        results = []
        for task in tasks:
            results.append(
                ComparisonResult(
                    task=task,
                    llm_assessment=LLMAssessmentResponseSchema(
                        winner=EssayComparisonWinner.ESSAY_A,
                        confidence=3.0,  # Must be >= 1.0 and <= 5.0
                        justification="Mock comparison result",
                    ),
                    raw_llm_response_content="Mock LLM response",
                    error_detail=None,
                ),
            )
        return results

    mock_llm_interaction.perform_comparisons = AsyncMock(side_effect=mock_perform_comparisons)

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
    mock_boundary_services: tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, Settings],
    mock_redis_client: MockRedisClient,
) -> None:
    """Test that first-time CJ assessment events are processed successfully with idempotency."""
    database, content_client, event_publisher, llm_interaction, settings = mock_boundary_services

    kafka_msg = create_mock_kafka_message(sample_cj_request_event)

    config = IdempotencyConfig(
        service_name="cj-assessment-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Coroutine[Any, Any, None]]
    ) -> bool:
        result = await process_single_message(
            msg=msg,
            database=database,
            content_client=content_client,
            event_publisher=event_publisher,
            llm_interaction=llm_interaction,
            settings_obj=settings,
        )
        await confirm_idempotency()  # Confirm after successful processing
        return result

    result = await handle_message_idempotently(kafka_msg)

    assert result is True
    assert len(mock_redis_client.set_calls) == 1
    assert len(mock_redis_client.delete_calls) == 0

    set_call = mock_redis_client.set_calls[0]
    assert set_call[0].startswith("huleedu:idempotency:v2:cj-assessment-service:")
    # V2 stores JSON metadata instead of "1"
    import json

    stored_data = json.loads(set_call[1])
    # Transaction-aware pattern starts with "started_at" in processing state
    assert "started_at" in stored_data
    assert "processed_by" in stored_data
    assert stored_data["processed_by"] == "cj-assessment-service"
    assert stored_data["status"] == "processing"  # Initial status before confirmation
    # Transaction-aware pattern: initial SETNX uses 300s for processing state
    assert set_call[2] == 300  # Processing state TTL

    content_client.fetch_content.assert_called()
    event_publisher.publish_assessment_completed.assert_called_once()
    assert len(database.batches) == 1
    assert len(database.essays[1]) == 2


@pytest.mark.asyncio
async def test_duplicate_event_skipped(
    sample_cj_request_event: dict,
    mock_boundary_services: tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, Settings],
    mock_redis_client: MockRedisClient,
) -> None:
    """Test that duplicate events are skipped without processing business logic."""
    database, content_client, event_publisher, llm_interaction, settings = mock_boundary_services

    kafka_msg = create_mock_kafka_message(sample_cj_request_event)

    deterministic_id = generate_deterministic_event_id(kafka_msg.value)
    # Update key format for v2
    # Store with transaction-aware format indicating completed status
    mock_redis_client.keys[
        f"huleedu:idempotency:v2:cj-assessment-service:huleedu_els_cj_assessment_requested_v1:{deterministic_id}"
    ] = '{"status": "completed", "processed_at": 1640995200.0, "processed_by": "cj-assessment-service"}'

    config = IdempotencyConfig(
        service_name="cj-assessment-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Coroutine[Any, Any, None]]
    ) -> bool | None:
        result = await process_single_message(
            msg=msg,
            database=database,
            content_client=content_client,
            event_publisher=event_publisher,
            llm_interaction=llm_interaction,
            settings_obj=settings,
        )
        await confirm_idempotency()  # Confirm after successful processing
        return result

    result = await handle_message_idempotently(kafka_msg)

    assert result is None
    # With transaction-aware pattern, duplicate detection happens via GET, no SETNX attempted
    assert len(mock_redis_client.set_calls) == 0  # No SET attempted for duplicates
    assert len(mock_redis_client.delete_calls) == 0

    content_client.fetch_content.assert_not_called()
    event_publisher.publish_assessment_completed.assert_not_called()
    assert len(database.batches) == 0


@pytest.mark.asyncio
async def test_deterministic_event_id_generation(
    mock_boundary_services: tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, Settings],
    mock_redis_client: MockRedisClient,
) -> None:
    """Test that deterministic event IDs are generated correctly for CJ assessment events."""
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
        "course_code": CourseCode.ENG6.value,
        "essay_instructions": "Test instructions",
        "llm_config_overrides": None,
    }

    # Use the same event_id to test true duplicate detection (retry scenario)
    shared_event_id = str(uuid.uuid4())
    event1 = {
        "event_id": shared_event_id,
        "event_type": "huleedu.els.cj_assessment.requested.v1",
        "event_timestamp": "2024-01-01T12:00:00Z",
        "source_service": "essay_lifecycle_service",
        "correlation_id": str(uuid.uuid4()),
        "data": base_event_data,
    }

    event2 = {
        "event_id": shared_event_id,  # Same event_id = same event (retry)
        "event_type": "huleedu.els.cj_assessment.requested.v1",
        "event_timestamp": "2024-01-01T13:00:00Z",  # Different timestamp (retry delay)
        "source_service": "essay_lifecycle_service",
        "correlation_id": str(uuid.uuid4()),
        "data": base_event_data,
    }

    kafka_msg1 = create_mock_kafka_message(event1)
    kafka_msg2 = create_mock_kafka_message(event2)

    config = IdempotencyConfig(
        service_name="cj-assessment-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Coroutine[Any, Any, None]]
    ) -> bool | None:
        result = await process_single_message(
            msg=msg,
            database=database,
            content_client=content_client,
            event_publisher=event_publisher,
            llm_interaction=llm_interaction,
            settings_obj=settings,
        )
        await confirm_idempotency()  # Confirm after successful processing
        return result

    result1 = await handle_message_idempotently(kafka_msg1)
    assert result1 is True

    result2 = await handle_message_idempotently(kafka_msg2)
    assert result2 is None

    # With transaction-aware pattern, only first message attempts SETNX
    # Second message detects duplicate via GET and doesn't attempt SETNX
    assert len(mock_redis_client.set_calls) == 1  # Only first message sets key
    assert len(mock_redis_client.delete_calls) == 0

    key1 = mock_redis_client.set_calls[0][0]
    assert key1.startswith("huleedu:idempotency:v2:cj-assessment-service:")
    # Key format: huleedu:idempotency:v2:service:event_type:hash
    key_parts = key1.split(":")
    assert len(key_parts) == 6  # prefix:idempotency:v2:service:event_type:hash
    assert len(key_parts[5]) == 64  # SHA-256 hash is 64 chars

    assert content_client.fetch_content.call_count == 1
    event_publisher.publish_assessment_completed.assert_called_once()
    assert len(database.batches) == 1
