"""
Tests for infrastructure outage scenarios in CJ Assessment idempotency.

- Unhandled exceptions should release the lock to allow retries.
- Redis failures should result in fail-open behavior (processing continues).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka import ConsumerRecord

from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent
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
            "course_code": CourseCode.ENG5.value,
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
        return_value="Sample essay content for testing CJ assessment."
    )
    mock_event_publisher = AsyncMock()
    mock_event_publisher.publish_assessment_completed = AsyncMock()
    mock_event_publisher.publish_assessment_failed = AsyncMock()
    mock_llm_interaction = AsyncMock()

    # Configure mock to return valid comparison results to prevent infinite loops
    from common_core import EssayComparisonWinner
    from services.cj_assessment_service.models_api import (
        ComparisonResult,
        ComparisonTask,
        EssayForComparison,
        LLMAssessmentResponseSchema,
    )

    mock_comparison_result = ComparisonResult(
        task=ComparisonTask(
            essay_a=EssayForComparison(
                id="essay_1", text_content="Sample essay A", current_bt_score=0.5
            ),
            essay_b=EssayForComparison(
                id="essay_2", text_content="Sample essay B", current_bt_score=0.5
            ),
            prompt="Compare these essays",
        ),
        llm_assessment=LLMAssessmentResponseSchema(
            winner=EssayComparisonWinner.ESSAY_A,
            justification="Essay A demonstrates better structure",
            confidence=3.5,
        ),
        error_detail=None,
        raw_llm_response_content="Essay A is better",
    )

    mock_llm_interaction.perform_comparisons = AsyncMock(return_value=[mock_comparison_result])

    class Settings:
        MAX_PAIRWISE_COMPARISONS = 100
        CJ_ASSESSMENT_FAILED_TOPIC = ProcessingEvent.CJ_ASSESSMENT_FAILED.value
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
async def test_exception_failure_releases_lock(
    sample_cj_request_event: dict,
    mock_redis_client: MockRedisClient,
) -> None:
    """Test that unhandled exceptions release Redis lock to allow retry."""
    from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer_v2

    # Setup mock process with exception
    mock_process = AsyncMock(side_effect=Exception("Unhandled processing error"))
    kafka_msg = create_mock_kafka_message(sample_cj_request_event)

    config = IdempotencyConfig(
        service_name="cj-assessment-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer_v2(redis_client=mock_redis_client, config=config)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
        await mock_process(msg)
        return True  # Should never reach this due to exception

    with pytest.raises(Exception, match="Unhandled processing error"):
        await handle_message_idempotently(kafka_msg)

    # Lock should be set when message is first seen
    assert len(mock_redis_client.set_calls) == 1
    # Lock should be released when unhandled exception occurs
    assert len(mock_redis_client.delete_calls) == 1
    # Ensure the same key was set and deleted
    assert mock_redis_client.set_calls[0][0] == mock_redis_client.delete_calls[0]


@pytest.mark.asyncio
async def test_redis_failure_fallback(
    sample_cj_request_event: dict,
    mock_boundary_services: tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, MagicMock],
    mock_redis_client: MockRedisClient,
) -> None:
    """Test that Redis failures result in fail-open behavior."""
    from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer_v2

    # Set the mock redis client to fail on set operation
    mock_redis_client.should_fail_set = True

    database, content_client, event_publisher, llm_interaction, settings = mock_boundary_services

    kafka_msg = create_mock_kafka_message(sample_cj_request_event)

    config = IdempotencyConfig(
        service_name="cj-assessment-service",
        default_ttl=86400,
        enable_debug_logging=True,
    )

    @idempotent_consumer_v2(redis_client=mock_redis_client, config=config)
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

    content_client.fetch_content.assert_called()
    event_publisher.publish_assessment_completed.assert_called_once()
    assert len(database.batches) == 1
