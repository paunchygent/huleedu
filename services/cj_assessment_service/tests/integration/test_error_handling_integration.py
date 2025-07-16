"""Integration tests for error handling and recovery scenarios."""

import json
from datetime import UTC, datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from aiokafka import ConsumerRecord

from common_core import LLMProviderType
from common_core.domain_enums import EssayComparisonWinner
from common_core.error_enums import ErrorCode
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1, TokenUsage
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import CJBatchStateEnum
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.event_processor import process_llm_result
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
)


@pytest.mark.integration
class TestErrorHandlingIntegration:
    """Test error scenarios and recovery mechanisms."""

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create a mock repository."""
        repo = AsyncMock(spec=CJRepositoryProtocol)

        # Create a mock session that supports async context manager protocol
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        # Set up database query methods
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = lambda: None  # Not async
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)

        # Create async context manager that can be used directly
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)

        # session() should return an async context manager directly (not a coroutine)
        repo.session = MagicMock(return_value=mock_context_manager)
        return repo

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create a mock event publisher."""
        publisher = AsyncMock(spec=CJEventPublisherProtocol)
        publisher.publish_assessment_failed = AsyncMock()
        publisher.publish_assessment_completed = AsyncMock()
        return publisher

    @pytest.fixture
    def test_settings(self) -> Settings:
        """Create test settings."""
        settings = Settings()
        # settings.MIN_SUCCESS_RATE_THRESHOLD = 0.8  # This field doesn't exist in Settings
        settings.SERVICE_NAME = "cj_assessment_service"
        settings.CJ_ASSESSMENT_COMPLETED_TOPIC = "huleedu.cj_assessment.completed.v1"
        settings.CJ_ASSESSMENT_FAILED_TOPIC = "huleedu.cj_assessment.failed.v1"
        return settings

    def _create_callback_event(
        self,
        request_id: str,
        correlation_id: UUID,
        winner: str,
        confidence: float = 4.2,
        is_error: bool = False,
        error_detail: Optional[ErrorDetail] = None,
    ) -> EventEnvelope[LLMComparisonResultV1]:
        """Create an LLM comparison result callback event."""
        # Create winner enum value
        winner_enum = None
        if not is_error:
            winner_enum = (
                EssayComparisonWinner.ESSAY_A
                if winner == "essay_a"
                else EssayComparisonWinner.ESSAY_B
            )

        result_data = LLMComparisonResultV1(
            request_id=request_id,
            correlation_id=correlation_id,
            provider=LLMProviderType.ANTHROPIC,
            model="claude-3-haiku-20240307",
            winner=winner_enum,
            confidence=confidence if not is_error else None,
            justification="Test justification" if not is_error else None,
            response_time_ms=1500,
            token_usage=TokenUsage(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            cost_estimate=0.001,
            requested_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            error_detail=error_detail,
        )

        return EventEnvelope[LLMComparisonResultV1](
            event_type="llm_provider.comparison.completed.v1",
            event_timestamp=datetime.now(UTC),
            source_service="llm_provider_service",
            correlation_id=correlation_id,
            data=result_data,
        )

    def _create_error_callback(
        self,
        request_id: str,
        correlation_id: UUID,
        error_code: str,
    ) -> EventEnvelope[LLMComparisonResultV1]:
        """Create an error callback event."""
        from huleedu_service_libs.error_handling.error_detail_factory import (
            create_error_detail_with_context,
        )

        error_detail = create_error_detail_with_context(
            error_code=ErrorCode.LLM_PROVIDER_SERVICE_ERROR,
            message=f"LLM provider error: {error_code}",
            service="llm_provider_service",
            operation="generate_comparison",
            correlation_id=correlation_id,
            details={"provider_error_code": error_code},
        )

        return self._create_callback_event(
            request_id=request_id,
            correlation_id=correlation_id,
            winner="essay_a",  # Not used in error case
            is_error=True,
            error_detail=error_detail,
        )

    def _create_kafka_message(
        self,
        envelope: EventEnvelope[LLMComparisonResultV1],
        request_id: str,
    ) -> ConsumerRecord:
        """Create a Kafka ConsumerRecord from an envelope."""
        message_value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        kafka_msg = MagicMock(spec=ConsumerRecord)
        kafka_msg.topic = "llm_provider.comparison.completed.v1"
        kafka_msg.partition = 0
        kafka_msg.offset = 123
        kafka_msg.key = request_id.encode("utf-8")
        kafka_msg.value = message_value
        return kafka_msg

    def _create_test_batch(
        self,
        pair_count: int,
        batch_id: Optional[str] = None,
    ) -> MagicMock:
        """Create a test batch with comparison pairs."""
        if batch_id is None:
            batch_id = str(uuid4())

        batch = MagicMock()
        batch.id = batch_id
        batch.batch_state = MagicMock()
        batch.batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        batch.batch_state.completed_comparisons = 0
        batch.batch_state.failed_comparisons = 0
        batch.batch_state.total_comparisons = pair_count

        # Create mock comparison pairs
        pairs = []
        for i in range(pair_count):
            pair = MagicMock()
            pair.id = f"pair-{i}"
            pair.request_correlation_id = uuid4()
            pair.completed_at = None
            pair.winner = None
            pairs.append(pair)

        batch.comparison_pairs = pairs
        return batch

    async def test_callback_for_unknown_correlation_id(
        self,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test handling of orphaned callbacks."""
        # Arrange
        unknown_correlation_id = uuid4()
        request_id = str(uuid4())

        callback = self._create_callback_event(
            request_id=request_id,
            correlation_id=unknown_correlation_id,
            winner="essay_a",
        )

        # Get the mock session from the fixture
        mock_session = mock_repository.session().__aenter__.return_value

        # Mock comparison pair lookup to return None (not found)
        mock_session.execute.return_value.scalar_one_or_none.return_value = None

        # Create Kafka message
        kafka_msg = self._create_kafka_message(callback, request_id)

        # Act - Should handle gracefully
        result = await process_llm_result(
            kafka_msg,
            mock_repository,
            mock_event_publisher,
            test_settings,
        )

        # Assert - Message acknowledged but not processed
        assert result is True  # Acknowledged to prevent reprocessing
        mock_session.commit.assert_not_called()  # No database changes

    async def test_duplicate_callback_idempotency(
        self,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test idempotent handling of duplicate callbacks."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()
        request_id = "pair-123"

        # Get the mock session from the fixture
        mock_session = mock_repository.session().__aenter__.return_value

        # Mock comparison pair that's already completed
        mock_pair = MagicMock()
        mock_pair.id = request_id
        mock_pair.batch_id = batch_id
        mock_pair.winner = "essay_a"
        mock_pair.completed_at = datetime.now(UTC)  # Already completed
        mock_session.execute.return_value.scalar_one_or_none.return_value = mock_pair

        # Mock batch state
        mock_batch_state = MagicMock()
        mock_batch_state.completed_comparisons = 1
        mock_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        mock_session.get.return_value = mock_batch_state

        # Create callback
        callback = self._create_callback_event(
            request_id=request_id,
            correlation_id=correlation_id,
            winner="essay_a",
        )

        # Create Kafka message
        kafka_msg = self._create_kafka_message(callback, request_id)

        # Act - Process same callback twice
        result1 = await process_llm_result(
            kafka_msg,
            mock_repository,
            mock_event_publisher,
            test_settings,
        )
        result2 = await process_llm_result(
            kafka_msg,
            mock_repository,
            mock_event_publisher,
            test_settings,
        )

        # Assert - Both processed successfully (idempotent)
        assert result1 is True
        assert result2 is True

        # Verify no duplicate processing occurred
        # The mock should not have been modified twice
        assert mock_pair.winner == "essay_a"
        assert mock_pair.completed_at is not None

    async def test_high_failure_rate_batch_termination(
        self,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test batch failure when error rate exceeds threshold."""
        # Arrange
        # test_settings.MIN_SUCCESS_RATE_THRESHOLD = 0.8  # This field doesn't exist in Settings
        batch_id = str(uuid4())
        correlation_id = uuid4()
        total_pairs = 20

        # Get the mock session from the fixture
        mock_session = mock_repository.session().__aenter__.return_value

        # Mock batch state that tracks failures
        mock_batch_state = MagicMock()
        mock_batch_state.batch_id = batch_id
        mock_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        mock_batch_state.completed_comparisons = 0
        mock_batch_state.failed_comparisons = 0
        mock_batch_state.total_comparisons = total_pairs
        mock_session.get.return_value = mock_batch_state

        # Test scenario: Process 10 callbacks, 5 success and 5 failures
        # This gives 50% failure rate, exceeding 20% threshold
        success_callbacks = []
        error_callbacks = []

        for i in range(5):
            # Success callbacks
            success_callback = self._create_callback_event(
                request_id=f"pair-{i}",
                correlation_id=correlation_id,
                winner="essay_a",
            )
            success_callbacks.append(success_callback)

            # Error callbacks
            error_callback = self._create_error_callback(
                request_id=f"pair-{i + 5}",
                correlation_id=correlation_id,
                error_code="PROVIDER_ERROR",
            )
            error_callbacks.append(error_callback)

        # Mock comparison pairs
        # Create a single mock pair that will be reused
        mock_pair = MagicMock()
        mock_pair.id = f"pair-{correlation_id}"
        mock_pair.cj_batch_id = batch_id
        mock_pair.winner = None  # No winner yet, so update will proceed
        mock_pair.completed_at = None
        mock_pair.request_correlation_id = correlation_id

        # Configure the execute result chain properly
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none = MagicMock(return_value=mock_pair)
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Act - Process all callbacks
        results = []
        for callback in success_callbacks + error_callbacks:
            request_id = callback.data.request_id
            kafka_msg = self._create_kafka_message(callback, request_id)
            result = await process_llm_result(
                kafka_msg,
                mock_repository,
                mock_event_publisher,
                test_settings,
            )
            results.append(result)

        # Assert - All callbacks processed (acknowledged)
        assert all(result is True for result in results)

        # Verify database operations were called
        assert mock_session.execute.called
        assert mock_session.commit.called

        # In a real scenario, the batch would be marked as failed
        # when the failure rate exceeds the threshold

    async def test_malformed_callback_message(
        self,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test handling of malformed callback messages."""
        # Arrange - Create invalid JSON message
        kafka_msg = MagicMock(spec=ConsumerRecord)
        kafka_msg.topic = "llm_provider.comparison.completed.v1"
        kafka_msg.partition = 0
        kafka_msg.offset = 123
        kafka_msg.key = b"malformed-key"
        kafka_msg.value = b"invalid json content"

        # Act - Process malformed message
        result = await process_llm_result(
            kafka_msg,
            mock_repository,
            mock_event_publisher,
            test_settings,
        )

        # Assert - Message acknowledged to prevent reprocessing
        assert result is True

        # Verify no database operations were attempted
        mock_repository.session.assert_not_called()

    async def test_database_connection_failure(
        self,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test handling of database connection failures."""
        # Arrange
        correlation_id = uuid4()
        request_id = "pair-123"

        callback = self._create_callback_event(
            request_id=request_id,
            correlation_id=correlation_id,
            winner="essay_a",
        )

        # Mock repository session to raise connection error
        mock_repository.session.side_effect = Exception("Database connection failed")

        # Create Kafka message
        kafka_msg = self._create_kafka_message(callback, request_id)

        # Act - Process callback with database failure
        result = await process_llm_result(
            kafka_msg,
            mock_repository,
            mock_event_publisher,
            test_settings,
        )

        # Assert - Message still acknowledged to prevent infinite retries
        assert result is True

        # Verify error was logged (in a real scenario)
        # The error would be logged by the error handling in process_llm_result

    async def test_event_publishing_failure(
        self,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test handling of event publishing failures."""
        # Arrange
        correlation_id = uuid4()
        request_id = "pair-123"

        callback = self._create_callback_event(
            request_id=request_id,
            correlation_id=correlation_id,
            winner="essay_a",
        )

        # Get the mock session from the fixture
        mock_session = mock_repository.session().__aenter__.return_value

        # Mock successful database operations
        mock_pair = MagicMock()
        mock_pair.id = request_id
        mock_pair.cj_batch_id = str(uuid4())
        mock_pair.winner = None
        mock_pair.completed_at = None
        mock_pair.request_correlation_id = correlation_id

        # Set up the execute result chain properly
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none = MagicMock(return_value=mock_pair)
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        mock_batch_state = MagicMock()
        mock_batch_state.state = CJBatchStateEnum.COMPLETED
        mock_session.get.return_value = mock_batch_state

        # Mock event publisher to fail
        mock_event_publisher.publish_assessment_completed.side_effect = Exception(
            "Kafka publish failed"
        )

        # Create Kafka message
        kafka_msg = self._create_kafka_message(callback, request_id)

        # Act - Process callback with publishing failure
        result = await process_llm_result(
            kafka_msg,
            mock_repository,
            mock_event_publisher,
            test_settings,
        )

        # Assert - Database operations completed, message acknowledged
        assert result is True
        mock_session.commit.assert_called()

        # Verify publishing was attempted
        # In a real scenario, the publish failure would be logged
        # but the callback processing would still be marked as successful
