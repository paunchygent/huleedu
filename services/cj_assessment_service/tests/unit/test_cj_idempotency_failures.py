"""
Tests for handled business logic failures in CJ Assessment idempotency.

- Failures during processing should keep the idempotency lock to prevent retries.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka import ConsumerRecord
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
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
        "event_type": topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED),
        "event_timestamp": "2024-01-01T12:00:00Z",
        "source_service": "essay_lifecycle_service",
        "correlation_id": str(uuid.uuid4()),
        "data": {
            # Top-level primitive fields (required by BaseEventData)
            "entity_id": batch_id,
            "entity_type": "batch",
            "parent_id": None,
            "system_metadata": {
                "entity_id": batch_id,
                "entity_type": "batch",
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
async def test_processing_failure_keeps_lock(
    sample_cj_request_event: dict,
    mock_boundary_services: tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, MagicMock],
    mock_redis_client: MockRedisClient,
) -> None:
    """Test that business logic failures keep Redis lock to prevent infinite retries."""
    from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

    database, content_client, event_publisher, llm_interaction, settings = mock_boundary_services

    database.should_fail_create_batch = True

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

    assert result is False
    assert len(mock_redis_client.set_calls) == 1
    assert len(mock_redis_client.delete_calls) == 0

    event_publisher.publish_assessment_failed.assert_called_once()
