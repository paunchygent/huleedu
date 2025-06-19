"""
Integration tests for idempotency in CJ Assessment Service.

Tests the idempotency decorator applied to CJ assessment message processing.
Follows testing patterns: mock boundaries (Redis, HTTP, Kafka, Database), not business logic.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka import ConsumerRecord
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.event_processor import process_single_message
from services.cj_assessment_service.models_api import (
    ComparisonResult,
    ComparisonTask,
    EssayForComparison,
    LLMAssessmentResponseSchema,
)
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)


class MockRedisClient:
    """Mock Redis client for idempotency testing."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []
        self.delete_calls: list[str] = []
        self.should_fail_set = False
        self.should_fail_delete = False

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """Mock Redis SETNX operation."""
        self.set_calls.append((key, value, ttl_seconds or 0))

        if self.should_fail_set:
            raise Exception("Redis connection failed")

        if key in self.keys:
            return False  # Key already exists (duplicate)

        self.keys[key] = value
        return True  # Key set successfully (first time)

    async def delete_key(self, key: str) -> int:
        """Mock Redis DELETE operation."""
        self.delete_calls.append(key)

        if self.should_fail_delete:
            raise RuntimeError("Mock Redis DELETE failure")

        if key in self.keys:
            del self.keys[key]
            return 1
        return 0

    async def get(self, key: str) -> str | None:
        """Mock GET operation that retrieves values."""
        return self.keys.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """Mock SETEX operation that sets values with TTL."""
        self.keys[key] = value
        return True


class MockDatabase:
    """Mock database that simulates real CJ assessment database operations."""

    def __init__(self) -> None:
        self.batches: dict[int, dict] = {}
        self.essays: dict[int, list] = {}
        self.rankings: dict[int, list] = {}
        self.next_batch_id = 1
        self.should_fail_create_batch = False
        self._mock_session = AsyncMock()
        self._setup_mock_session()

    def _setup_mock_session(self) -> None:
        """Setup the mock session with SQLAlchemy-like behavior."""

        # Mock execute() method for SQLAlchemy queries
        async def mock_execute(stmt):
            # Return a mock result that has fetchall() method (synchronous, not async)
            mock_result = MagicMock()
            mock_result.fetchall.return_value = []  # Return empty list for queries
            return mock_result

        self._mock_session.execute = mock_execute
        self._mock_session.commit = AsyncMock()
        self._mock_session.rollback = AsyncMock()
        self._mock_session.close = AsyncMock()

        # SQLAlchemy session.add() is synchronous, not async
        self._mock_session.add = MagicMock()  # Synchronous mock
        self._mock_session.flush = AsyncMock()  # Async mock

    async def __aenter__(self):
        return self._mock_session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def session(self):
        """Return mock session as async context manager."""
        return self

    async def create_new_cj_batch(
        self,
        session: AsyncSession,
        bos_batch_id: str,
        event_correlation_id: str | None,
        language: str,
        course_code: str,
        essay_instructions: str,
        initial_status: Any,
        expected_essay_count: int,
    ) -> Any:
        """Mock creating a new CJ batch."""
        if self.should_fail_create_batch:
            raise Exception("Database error creating batch")

        batch_id = self.next_batch_id
        self.next_batch_id += 1

        batch = MagicMock()
        batch.id = batch_id
        self.batches[batch_id] = {
            "bos_batch_id": bos_batch_id,
            "event_correlation_id": event_correlation_id,
            "language": language,
            "course_code": course_code,
            "essay_instructions": essay_instructions,
            "initial_status": initial_status,
            "expected_essay_count": expected_essay_count,
        }
        self.essays[batch_id] = []
        self.rankings[batch_id] = [
            {"els_essay_id": "essay-1", "rank": 1, "score": 0.8},
            {"els_essay_id": "essay-2", "rank": 2, "score": 0.6},
        ]
        return batch

    async def create_or_update_cj_processed_essay(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        els_essay_id: str,
        text_storage_id: str,
        assessment_input_text: str,
    ) -> Any:
        """Mock creating/updating processed essay."""
        essay = MagicMock()
        essay.current_bt_score = 0.5
        if cj_batch_id in self.essays:
            self.essays[cj_batch_id].append(
                {
                    "cj_batch_id": cj_batch_id,
                    "els_essay_id": els_essay_id,
                    "text_storage_id": text_storage_id,
                    "assessment_input_text": assessment_input_text,
                }
            )
        return essay

    async def get_essays_for_cj_batch(self, session: AsyncSession, cj_batch_id: int) -> list[Any]:
        """Mock getting essays for CJ batch."""
        return self.essays.get(cj_batch_id, [])

    async def get_comparison_pair_by_essays(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        essay_a_els_id: str,
        essay_b_els_id: str,
    ) -> Any | None:
        """Mock checking if comparison pair exists."""
        return None

    async def store_comparison_results(
        self, session: AsyncSession, results: list[Any], cj_batch_id: int
    ) -> None:
        """Mock storing comparison results."""
        pass

    async def update_essay_scores_in_batch(
        self, session: AsyncSession, cj_batch_id: int, scores: dict[str, float]
    ) -> None:
        """Mock updating essay scores."""
        pass

    async def update_cj_batch_status(
        self, session: AsyncSession, cj_batch_id: int, status: Any
    ) -> None:
        """Mock updating batch status."""
        if cj_batch_id in self.batches:
            self.batches[cj_batch_id]["status"] = status

    async def get_final_cj_rankings(
        self, session: AsyncSession, cj_batch_id: int
    ) -> list[dict[str, Any]]:
        """Mock getting final rankings."""
        return self.rankings.get(cj_batch_id, [])

    async def initialize_db_schema(self) -> None:
        """Mock initializing database schema."""
        pass


def create_mock_kafka_message(event_data: dict) -> ConsumerRecord:
    """Create a mock Kafka ConsumerRecord for testing."""
    return ConsumerRecord(
        topic="huleedu.els.cj_assessment.requested.v1",
        partition=0,
        offset=12345,
        timestamp=None,
        timestamp_type=None,
        key=None,
        value=json.dumps(event_data).encode("utf-8"),
        checksum=None,
        serialized_key_size=None,
        serialized_value_size=None,
        headers=[],
    )


@pytest.fixture
def sample_cj_request_event() -> dict:
    """Sample CJ assessment request event data."""
    batch_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "huleedu.els.cj_assessment.requested.v1",
        "event_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_service": "essay_lifecycle_service",
        "correlation_id": correlation_id,
        "data": {
            "entity_ref": {"entity_id": batch_id, "entity_type": "batch"},
            "system_metadata": {
                "entity": {"entity_id": batch_id, "entity_type": "batch"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "processing_stage": "pending",
                "event": "els.cj_assessment.requested",
            },
            "essays_for_cj": [
                {"essay_id": "essay-1", "text_storage_id": "storage-1"},
                {"essay_id": "essay-2", "text_storage_id": "storage-2"},
            ],
            "language": "en",
            "course_code": "TEST_COURSE",
            "essay_instructions": "Write a test essay.",
            "llm_config_overrides": None,
        },
    }


@pytest.fixture
def mock_boundary_services() -> tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, MagicMock]:
    """Create mock boundary services (external dependencies only)."""
    # Mock database (infrastructure boundary)
    database = MockDatabase()

    # Mock content client (HTTP boundary)
    content_client = AsyncMock(spec=ContentClientProtocol)
    content_client.fetch_content.return_value = "Sample essay content for testing"

    # Mock event publisher (Kafka boundary)
    event_publisher = AsyncMock(spec=CJEventPublisherProtocol)
    event_publisher.publish_assessment_completed.return_value = None
    event_publisher.publish_assessment_failed.return_value = None

    # Mock LLM interaction (HTTP boundary)
    llm_interaction = AsyncMock(spec=LLMInteractionProtocol)
    # Return a proper comparison result instead of empty list to avoid infinite loops
    # Create mock essays for the comparison task
    essay_a = EssayForComparison(id="essay-1", text_content="Essay A content")
    essay_b = EssayForComparison(id="essay-2", text_content="Essay B content")

    # Create mock comparison task
    mock_task = ComparisonTask(essay_a=essay_a, essay_b=essay_b, prompt="Compare these essays")

    # Create mock comparison result with correct structure
    mock_comparison_result = ComparisonResult(
        task=mock_task,
        llm_assessment=LLMAssessmentResponseSchema(
            winner="Essay A",  # Must be one of the literal values
            justification="Essay A is better written",
            confidence=4.0,  # Changed from confidence_level to confidence
        ),
    )
    llm_interaction.perform_comparisons.return_value = [mock_comparison_result]

    # Mock settings (configuration boundary) - provide actual numeric values
    settings = MagicMock()
    settings.CJ_ASSESSMENT_COMPLETED_TOPIC = "huleedu.cj_assessment.completed.v1"
    settings.CJ_ASSESSMENT_FAILED_TOPIC = "huleedu.cj_assessment.failed.v1"
    settings.SERVICE_NAME = "cj_assessment_service"

    # Numeric settings that the CJ workflow needs
    settings.MAX_PAIRWISE_COMPARISONS = 100
    settings.LLM_TIMEOUT_SECONDS = 30
    settings.MAXIMUM_RETRIES = 3
    settings.EXISTING_PAIRS_THRESHOLD = 10  # For comparison logic
    settings.MIN_ESSAYS_FOR_CJ = 2  # Minimum essays needed
    settings.MAX_ITERATIONS = 5  # Maximum comparison iterations
    settings.CONVERGENCE_THRESHOLD = 0.01  # Score convergence threshold

    # Settings that are accessed via getattr() in the code
    settings.comparisons_per_stability_check_iteration = 5  # Used in pair generation
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 10  # Used in stability check
    settings.SCORE_STABILITY_THRESHOLD = 0.05  # Used in stability check

    return database, content_client, event_publisher, llm_interaction, settings


@pytest.mark.asyncio
async def test_first_time_event_processing_success(
    sample_cj_request_event: dict,
    mock_boundary_services: tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, MagicMock],
) -> None:
    """Test that first-time CJ assessment events are processed successfully with idempotency."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()
    database, content_client, event_publisher, llm_interaction, settings = mock_boundary_services

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_cj_request_event)

    # Apply idempotency decorator to real message processor
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
        return await process_single_message(
            msg=msg,
            database=database,
            content_client=content_client,
            event_publisher=event_publisher,
            llm_interaction=llm_interaction,
            settings_obj=settings,
        )

    # Process message
    result = await handle_message_idempotently(kafka_msg)

    # Assertions
    assert result is True  # Business logic succeeded
    assert len(redis_client.set_calls) == 1  # SETNX was called
    assert len(redis_client.delete_calls) == 0  # No cleanup needed

    # Verify Redis key format
    set_call = redis_client.set_calls[0]
    assert set_call[0].startswith("huleedu:events:seen:")
    assert set_call[1] == "1"
    assert set_call[2] == 86400

    # Verify boundary services were called (real business logic executed)
    content_client.fetch_content.assert_called()  # Content was fetched
    event_publisher.publish_assessment_completed.assert_called_once()  # Success event published
    assert len(database.batches) == 1  # Batch was created
    assert len(database.essays[1]) == 2  # Essays were processed


@pytest.mark.asyncio
async def test_duplicate_event_skipped(
    sample_cj_request_event: dict,
    mock_boundary_services: tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, MagicMock],
) -> None:
    """Test that duplicate events are skipped without processing business logic."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    from common_core.events.utils import generate_deterministic_event_id

    redis_client = MockRedisClient()
    database, content_client, event_publisher, llm_interaction, settings = mock_boundary_services

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_cj_request_event)

    # Pre-populate Redis with the event key to simulate duplicate
    deterministic_id = generate_deterministic_event_id(kafka_msg.value)
    redis_client.keys[f"huleedu:events:seen:{deterministic_id}"] = "1"

    # Apply idempotency decorator
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool | None:
        return await process_single_message(
            msg=msg,
            database=database,
            content_client=content_client,
            event_publisher=event_publisher,
            llm_interaction=llm_interaction,
            settings_obj=settings,
        )

    # Process message
    result = await handle_message_idempotently(kafka_msg)

    # Assertions
    assert result is None  # Should return None for duplicates
    assert len(redis_client.set_calls) == 1  # SETNX was attempted
    assert len(redis_client.delete_calls) == 0  # No cleanup needed

    # Business logic should NOT have been called
    content_client.fetch_content.assert_not_called()
    event_publisher.publish_assessment_completed.assert_not_called()
    assert len(database.batches) == 0  # No batch created


@pytest.mark.asyncio
async def test_processing_failure_keeps_lock(
    sample_cj_request_event: dict,
    mock_boundary_services: tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, MagicMock],
) -> None:
    """Test that business logic failures keep Redis lock to prevent infinite retries."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()
    database, content_client, event_publisher, llm_interaction, settings = mock_boundary_services

    # Configure database to fail (business logic failure)
    database.should_fail_create_batch = True

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_cj_request_event)

    # Apply idempotency decorator
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
        return await process_single_message(
            msg=msg,
            database=database,
            content_client=content_client,
            event_publisher=event_publisher,
            llm_interaction=llm_interaction,
            settings_obj=settings,
        )

    # Process message
    result = await handle_message_idempotently(kafka_msg)

    # Assertions
    assert result is False  # Business logic failed
    assert len(redis_client.set_calls) == 1  # SETNX was called
    assert len(redis_client.delete_calls) == 0  # Lock should be kept (no cleanup)

    # Failure event should be published
    event_publisher.publish_assessment_failed.assert_called_once()


@pytest.mark.asyncio
async def test_exception_failure_releases_lock(
    sample_cj_request_event: dict,
) -> None:
    """Test that unhandled exceptions release Redis lock to allow retry."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_cj_request_event)

    # Create a handler that raises an exception (infrastructure failure)
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
    async def handle_message_with_exception(msg: ConsumerRecord) -> bool:
        raise RuntimeError("Unexpected infrastructure failure")

    # Process message and expect exception
    with pytest.raises(RuntimeError, match="Unexpected infrastructure failure"):
        await handle_message_with_exception(kafka_msg)

    # Assertions
    assert len(redis_client.set_calls) == 1  # SETNX was called
    assert len(redis_client.delete_calls) == 1  # Lock should be released for retry


@pytest.mark.asyncio
async def test_redis_failure_fallback(
    sample_cj_request_event: dict,
    mock_boundary_services: tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, MagicMock],
) -> None:
    """Test that Redis failures result in fail-open behavior."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()
    database, content_client, event_publisher, llm_interaction, settings = mock_boundary_services

    # Configure Redis to fail
    redis_client.should_fail_set = True

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_cj_request_event)

    # Apply idempotency decorator
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
        return await process_single_message(
            msg=msg,
            database=database,
            content_client=content_client,
            event_publisher=event_publisher,
            llm_interaction=llm_interaction,
            settings_obj=settings,
        )

    # Process message
    result = await handle_message_idempotently(kafka_msg)

    # Assertions - Should process without idempotency protection
    assert result is True  # Business logic succeeded despite Redis failure
    assert len(redis_client.set_calls) == 1  # SETNX was attempted
    assert len(redis_client.delete_calls) == 0  # No cleanup needed

    # Business logic should have executed (fail-open)
    content_client.fetch_content.assert_called()
    event_publisher.publish_assessment_completed.assert_called_once()
    assert len(database.batches) == 1  # Batch was created


@pytest.mark.asyncio
async def test_deterministic_event_id_generation(
    mock_boundary_services: tuple[MockDatabase, AsyncMock, AsyncMock, AsyncMock, MagicMock],
) -> None:
    """Test that deterministic event IDs are generated correctly for CJ assessment events."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()
    database, content_client, event_publisher, llm_interaction, settings = mock_boundary_services

    # Create two identical events with same data but different envelope metadata
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

    # Event 1 - different envelope metadata
    event1 = {
        "event_id": str(uuid.uuid4()),  # Different
        "event_type": "huleedu.els.cj_assessment.requested.v1",
        "event_timestamp": "2024-01-01T12:00:00Z",  # Different
        "source_service": "essay_lifecycle_service",
        "correlation_id": str(uuid.uuid4()),  # Different
        "data": base_event_data,  # Same data
    }

    # Event 2 - different envelope metadata but same data
    event2 = {
        "event_id": str(uuid.uuid4()),  # Different
        "event_type": "huleedu.els.cj_assessment.requested.v1",
        "event_timestamp": "2024-01-01T13:00:00Z",  # Different
        "source_service": "essay_lifecycle_service",
        "correlation_id": str(uuid.uuid4()),  # Different
        "data": base_event_data,  # Same data
    }

    # Create Kafka messages
    kafka_msg1 = create_mock_kafka_message(event1)
    kafka_msg2 = create_mock_kafka_message(event2)

    # Apply idempotency decorator
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool | None:
        return await process_single_message(
            msg=msg,
            database=database,
            content_client=content_client,
            event_publisher=event_publisher,
            llm_interaction=llm_interaction,
            settings_obj=settings,
        )

    # Process first message
    result1 = await handle_message_idempotently(kafka_msg1)
    assert result1 is True  # First message processed

    # Process second message (should be detected as duplicate)
    result2 = await handle_message_idempotently(kafka_msg2)
    assert result2 is None  # Second message skipped as duplicate

    # Verify Redis calls
    assert len(redis_client.set_calls) == 2  # Both attempted SETNX
    assert len(redis_client.delete_calls) == 0  # No cleanup needed

    # Verify same deterministic key was used for both
    key1 = redis_client.set_calls[0][0]
    key2 = redis_client.set_calls[1][0]
    assert key1 == key2  # Same deterministic key despite different envelope metadata
    assert key1.startswith("huleedu:events:seen:")
    assert len(key1.split(":")[3]) == 64  # SHA256 hash length

    # Business logic should only have been called once
    assert content_client.fetch_content.call_count == 1
    # Called for the single essay in first message
    event_publisher.publish_assessment_completed.assert_called_once()  # Only once
    assert len(database.batches) == 1  # Only one batch created
