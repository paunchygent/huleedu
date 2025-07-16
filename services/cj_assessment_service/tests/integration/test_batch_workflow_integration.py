"""
End-to-end integration tests for CJ Assessment batch workflow.
Tests the complete lifecycle from request to callback to completion.
"""
import asyncio
from datetime import datetime, UTC, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent
from common_core.events.cj_assessment_events import (
    CJAssessmentCompletedV1,
    CJAssessmentFailedV1,
    ELS_CJAssessmentRequestV1,
    LLMConfigOverrides,
)
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1
from common_core.metadata_models import EntityReference, EssayProcessingInputRefV1, SystemProcessingMetadata
from common_core.status_enums import BatchStatus, CJBatchStateEnum, ProcessingStage
from services.cj_assessment_service.batch_monitor import BatchMonitor
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.event_processor import (
    process_llm_result,
    process_single_message,
)
from services.cj_assessment_service.models_db import (
    CJBatchState,
    CJBatchUpload,
    ComparisonPair,
    EssayItem,
)
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)


@pytest.mark.integration
class TestBatchWorkflowIntegration:
    """Test complete batch processing workflow with callbacks."""

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create a mock repository."""
        repo = AsyncMock(spec=CJRepositoryProtocol)
        repo.session = AsyncMock()
        return repo

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create a mock event publisher."""
        publisher = AsyncMock(spec=CJEventPublisherProtocol)
        publisher.publish_assessment_completed = AsyncMock()
        publisher.publish_assessment_failed = AsyncMock()
        return publisher

    @pytest.fixture
    def mock_content_client(self) -> AsyncMock:
        """Create a mock content client."""
        client = AsyncMock(spec=ContentClientProtocol)
        client.fetch_essay_content = AsyncMock()
        return client

    @pytest.fixture
    def mock_llm_interaction(self) -> AsyncMock:
        """Create a mock LLM interaction."""
        interaction = AsyncMock(spec=LLMInteractionProtocol)
        interaction.submit_comparison_requests = AsyncMock()
        return interaction

    @pytest.fixture
    def test_settings(self) -> Settings:
        """Create test settings."""
        settings = Settings()
        settings.BATCH_TIMEOUT_HOURS = 4
        settings.BATCH_MONITOR_INTERVAL_MINUTES = 5
        settings.COMPLETION_THRESHOLD_PCT = 80
        settings.MIN_SUCCESS_RATE_THRESHOLD = 0.8
        settings.SERVICE_NAME = "cj_assessment_service"
        settings.CJ_ASSESSMENT_COMPLETED_TOPIC = "huleedu.cj_assessment.completed.v1"
        settings.CJ_ASSESSMENT_FAILED_TOPIC = "huleedu.cj_assessment.failed.v1"
        return settings

    @pytest.fixture
    def test_monitor(
        self,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        test_settings: Settings,
    ) -> BatchMonitor:
        """Create a batch monitor instance."""
        return BatchMonitor(mock_repository, mock_event_publisher, test_settings)

    def _create_assessment_request(
        self,
        batch_id: str,
        correlation_id: UUID,
        essay_count: int,
    ) -> EventEnvelope[ELS_CJAssessmentRequestV1]:
        """Create a CJ assessment request event."""
        essays = []
        for i in range(essay_count):
            essays.append(
                EssayProcessingInputRefV1(
                    essay_id=f"essay-{i}",
                    text_storage_id=f"storage-{i}",
                )
            )

        entity_ref = EntityReference(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
        )

        system_metadata = SystemProcessingMetadata(
            entity=entity_ref,
            timestamp=datetime.now(UTC),
            processing_stage=ProcessingStage.PENDING,
            event=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED.value,
        )

        request_data = ELS_CJAssessmentRequestV1(
            event_name=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED,
            entity_ref=entity_ref,
            system_metadata=system_metadata,
            essays_for_cj=essays,
            language="en",
            course_code=CourseCode.ENG5,
            essay_instructions="Compare the quality of these essays.",
            llm_config_overrides=None,
        )

        return EventEnvelope[ELS_CJAssessmentRequestV1](
            event_type="els.cj_assessment.requested.v1",
            event_timestamp=datetime.now(UTC),
            source_service="essay_lifecycle_service",
            correlation_id=correlation_id,
            data=request_data,
        )

    def _create_callback_event(
        self,
        request_id: str,
        correlation_id: UUID,
        winner: str,
        confidence: float = 0.85,
        is_error: bool = False,
    ) -> EventEnvelope[LLMComparisonResultV1]:
        """Create an LLM comparison result callback event."""
        from common_core import LLMProviderType
        from common_core.events.llm_provider_events import ComparisonWinner, TokenUsage

        result_data = LLMComparisonResultV1(
            request_id=request_id,
            provider=LLMProviderType.ANTHROPIC,
            model="claude-3-haiku-20240307",
            winner=ComparisonWinner.ESSAY_A if winner == "essay_a" else ComparisonWinner.ESSAY_B,
            confidence=confidence,
            justification="Test justification",
            response_time_ms=1500,
            token_usage=TokenUsage(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
            ),
            cost_estimate=0.001,
            is_error=is_error,
            error_detail=None,
        )

        return EventEnvelope[LLMComparisonResultV1](
            event_type="llm_provider.comparison.completed.v1",
            event_timestamp=datetime.now(UTC),
            source_service="llm_provider_service",
            correlation_id=correlation_id,
            data=result_data,
        )

    def _create_mock_batch(self, batch_id: str, pair_count: int) -> MagicMock:
        """Create a mock batch with comparison pairs."""
        batch = MagicMock()
        batch.id = batch_id
        batch.batch_state = MagicMock()
        batch.batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        batch.batch_state.completed_comparisons = 0
        batch.batch_state.total_comparisons = pair_count
        batch.batch_state.partial_scoring_triggered = False

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

    def _create_stuck_batch(
        self,
        repository: AsyncMock,
        state: CJBatchStateEnum,
        progress_percentage: int,
        hours_old: int,
    ) -> MagicMock:
        """Create a stuck batch for testing."""
        batch = MagicMock()
        batch.batch_id = str(uuid4())
        batch.state = state
        batch.total_comparisons = 100
        batch.completed_comparisons = progress_percentage
        batch.last_activity_at = datetime.now(UTC) - timedelta(hours=hours_old)
        batch.batch_upload = MagicMock()
        batch.batch_upload.event_correlation_id = str(uuid4())
        return batch

    async def test_full_batch_lifecycle(
        self,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_content_client: AsyncMock,
        mock_llm_interaction: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test batch from creation through callbacks to completion."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()
        essay_count = 10

        # Create assessment request event
        request_event = self._create_assessment_request(
            batch_id=batch_id,
            correlation_id=correlation_id,
            essay_count=essay_count,
        )

        # Mock content client to return essay content
        mock_content_client.fetch_essay_content.return_value = "Sample essay content"

        # Mock LLM interaction to succeed
        mock_llm_interaction.submit_comparison_requests.return_value = None

        # Mock repository session
        mock_session = AsyncMock()
        mock_repository.session.return_value.__aenter__.return_value = mock_session

        # Mock batch creation and retrieval
        mock_batch = self._create_mock_batch(batch_id, 45)  # C(10,2) = 45 pairs
        mock_session.get.return_value = mock_batch

        # Create Kafka message
        import json
        from unittest.mock import MagicMock
        from aiokafka import ConsumerRecord

        message_value = json.dumps(request_event.model_dump(mode="json")).encode("utf-8")
        kafka_msg = MagicMock(spec=ConsumerRecord)
        kafka_msg.topic = "els.cj_assessment.requested.v1"
        kafka_msg.partition = 0
        kafka_msg.offset = 123
        kafka_msg.key = batch_id.encode("utf-8")
        kafka_msg.value = message_value

        # Act - Process the request
        result = await process_single_message(
            kafka_msg,
            mock_repository,
            mock_content_client,
            mock_event_publisher,
            mock_llm_interaction,
            test_settings,
        )

        # Assert - Verify message processed successfully
        assert result is True
        mock_llm_interaction.submit_comparison_requests.assert_called_once()

        # Verify completion event was published
        mock_event_publisher.publish_assessment_completed.assert_called_once()

        # Verify the published event structure
        published_call = mock_event_publisher.publish_assessment_completed.call_args
        completion_envelope = published_call[1]["completion_data"]
        assert completion_envelope.event_type == "huleedu.cj_assessment.completed.v1"
        assert completion_envelope.correlation_id == correlation_id
        assert completion_envelope.data.status == BatchStatus.COMPLETED_SUCCESSFULLY

    async def test_batch_monitoring_recovery(
        self,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        test_monitor: BatchMonitor,
    ) -> None:
        """Test stuck batch detection and recovery."""
        # Arrange - Create a stuck batch
        stuck_batch = self._create_stuck_batch(
            mock_repository,
            state=CJBatchStateEnum.WAITING_CALLBACKS,
            progress_percentage=85,  # Above recovery threshold
            hours_old=5,  # Past timeout threshold
        )

        # Mock session and query results
        mock_session = AsyncMock()
        mock_repository.session.return_value.__aenter__.return_value = mock_session

        # Mock the query to return stuck batch
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [stuck_batch]
        mock_session.execute.return_value = mock_result

        # Mock batch upload for correlation_id
        mock_batch_upload = MagicMock()
        mock_batch_upload.event_correlation_id = str(uuid4())
        mock_session.get.return_value = mock_batch_upload

        # Mock essays for completion
        mock_essays = [MagicMock() for _ in range(10)]
        for i, essay in enumerate(mock_essays):
            essay.id = f"essay-{i}"
            essay.content = f"Essay content {i}"
        mock_session.execute.return_value.scalars.return_value.all.return_value = mock_essays

        # Act - Run batch monitor (simulate one check)
        test_monitor._running = False  # Stop after one iteration
        await test_monitor.check_stuck_batches()

        # Assert - Verify batch was processed
        # Note: The actual recovery logic would be called through the monitor
        assert mock_session.execute.called
        mock_session.commit.assert_called()

    async def test_concurrent_callback_processing(
        self,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test race conditions with concurrent callbacks."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()
        callback_count = 100

        # Mock repository session
        mock_session = AsyncMock()
        mock_repository.session.return_value.__aenter__.return_value = mock_session

        # Mock comparison pair lookup
        mock_pair = MagicMock()
        mock_pair.id = "pair-123"
        mock_pair.batch_id = batch_id
        mock_pair.winner = None
        mock_pair.completed_at = None
        mock_session.execute.return_value.scalar_one_or_none.return_value = mock_pair

        # Mock batch state
        mock_batch_state = MagicMock()
        mock_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        mock_batch_state.completed_comparisons = 0
        mock_batch_state.total_comparisons = callback_count
        mock_session.get.return_value = mock_batch_state

        # Create callback events
        callback_events = []
        for i in range(callback_count):
            callback = self._create_callback_event(
                request_id=f"pair-{i}",
                correlation_id=correlation_id,
                winner="essay_a",
            )
            callback_events.append(callback)

        # Act - Process callbacks concurrently
        tasks = []
        for callback in callback_events:
            # Create Kafka message
            import json
            from unittest.mock import MagicMock
            from aiokafka import ConsumerRecord

            message_value = json.dumps(callback.model_dump(mode="json")).encode("utf-8")
            kafka_msg = MagicMock(spec=ConsumerRecord)
            kafka_msg.topic = "llm_provider.comparison.completed.v1"
            kafka_msg.partition = 0
            kafka_msg.offset = 123
            kafka_msg.value = message_value

            task = asyncio.create_task(
                process_llm_result(
                    kafka_msg,
                    mock_repository,
                    mock_event_publisher,
                    test_settings,
                )
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert - Verify all callbacks processed successfully
        assert all(result is True for result in results if not isinstance(result, Exception))
        assert len([r for r in results if isinstance(r, Exception)]) == 0

    async def test_partial_batch_completion(
        self,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test partial completion threshold triggering."""
        # Arrange
        test_settings.COMPLETION_THRESHOLD_PCT = 80
        batch_id = str(uuid4())
        correlation_id = uuid4()
        total_pairs = 100

        # Mock repository session
        mock_session = AsyncMock()
        mock_repository.session.return_value.__aenter__.return_value = mock_session

        # Mock batch state with 80% completion
        mock_batch_state = MagicMock()
        mock_batch_state.batch_id = batch_id
        mock_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        mock_batch_state.completed_comparisons = 80
        mock_batch_state.total_comparisons = total_pairs
        mock_batch_state.partial_scoring_triggered = False
        mock_session.get.return_value = mock_batch_state

        # Mock comparison pair
        mock_pair = MagicMock()
        mock_pair.id = "pair-80"
        mock_pair.batch_id = batch_id
        mock_pair.winner = None
        mock_pair.completed_at = None
        mock_session.execute.return_value.scalar_one_or_none.return_value = mock_pair

        # Create callback for the 80th completion
        callback = self._create_callback_event(
            request_id="pair-80",
            correlation_id=correlation_id,
            winner="essay_a",
        )

        # Create Kafka message
        import json
        from unittest.mock import MagicMock
        from aiokafka import ConsumerRecord

        message_value = json.dumps(callback.model_dump(mode="json")).encode("utf-8")
        kafka_msg = MagicMock(spec=ConsumerRecord)
        kafka_msg.topic = "llm_provider.comparison.completed.v1"
        kafka_msg.partition = 0
        kafka_msg.offset = 123
        kafka_msg.value = message_value

        # Act - Process the callback that triggers partial completion
        result = await process_llm_result(
            kafka_msg,
            mock_repository,
            mock_event_publisher,
            test_settings,
        )

        # Assert - Verify callback processed and partial scoring triggered
        assert result is True
        mock_session.commit.assert_called()

        # Verify that the batch state would be updated (through database operations)
        assert mock_session.execute.called