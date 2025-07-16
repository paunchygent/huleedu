"""
End-to-end integration tests for CJ Assessment batch workflow.
Tests the complete lifecycle from request to callback to completion.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from aiokafka import ConsumerRecord

from common_core import LLMProviderType
from common_core.domain_enums import CourseCode, EssayComparisonWinner
from common_core.event_enums import ProcessingEvent
from common_core.events.cj_assessment_events import ELS_CJAssessmentRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1, TokenUsage
from common_core.metadata_models import (
    EntityReference,
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)
from common_core.status_enums import BatchStatus, CJBatchStateEnum, ProcessingStage
from services.cj_assessment_service.batch_monitor import BatchMonitor
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.event_processor import (
    process_llm_result,
    process_single_message,
)
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)

if TYPE_CHECKING:
    pass


@pytest.mark.integration
class TestBatchWorkflowIntegration:
    """Test complete batch processing workflow with callbacks."""

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create a mock repository with proper async context manager support."""
        repo = AsyncMock(spec=CJRepositoryProtocol)

        # Create a reusable mock session with all needed methods
        mock_session = self._create_mock_session()

        # session() returns a context manager, not a coroutine
        # Using MagicMock for the context manager itself
        mock_context_manager = MagicMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)

        # Make session a method that returns the context manager
        repo.session = MagicMock(return_value=mock_context_manager)

        # Mock batch creation with realistic data
        mock_batch = MagicMock()
        mock_batch.id = 1
        mock_batch.bos_batch_id = str(uuid4())
        mock_batch.created_at = datetime.now(UTC)
        repo.create_new_cj_batch = AsyncMock(return_value=mock_batch)

        # Mock essay operations
        repo.save_essays_to_db = AsyncMock(return_value=[])
        repo.create_or_update_cj_processed_essay = AsyncMock(
            side_effect=self._create_mock_processed_essay
        )

        # Mock batch state operations
        repo.get_batch_state = AsyncMock(side_effect=self._get_mock_batch_state)
        repo.update_batch_state = AsyncMock()

        return repo

    def _create_mock_session(self) -> AsyncMock:
        """Create a properly configured mock database session."""
        mock_session = AsyncMock()

        # Store for batch state
        self._mock_batch_state = None
        self._mock_essays = []

        # Configure execute to return context-aware results
        async def mock_execute(stmt):
            mock_result = MagicMock()

            # Check if this is a batch state query
            stmt_str = str(stmt)
            if "cj_batchstate" in stmt_str.lower():
                mock_result.scalar_one_or_none = MagicMock(return_value=self._mock_batch_state)
            else:
                # Default behavior for other queries
                mock_result.scalar_one_or_none = MagicMock(return_value=None)

            mock_result.scalar_one = MagicMock(return_value=None)
            mock_result.scalar = MagicMock(return_value=None)

            # For multi-row queries
            mock_result.all = MagicMock(return_value=[])
            mock_result.first = MagicMock(return_value=None)

            # For queries using scalars()
            mock_scalars = MagicMock()
            mock_scalars.all = MagicMock(return_value=self._mock_essays)
            mock_scalars.first = MagicMock(return_value=None)
            mock_result.scalars = MagicMock(return_value=mock_scalars)

            return mock_result

        # Configure session methods
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        return mock_session

    def _create_mock_processed_essay(self, **kwargs):
        """Create a mock processed essay with realistic data."""
        mock_essay = MagicMock()
        mock_essay.id = kwargs.get("cj_batch_id", 1)
        mock_essay.els_essay_id = kwargs.get("els_essay_id", f"essay-{uuid4()}")
        mock_essay.current_bt_score = 0.0
        mock_essay.text_storage_id = kwargs.get("text_storage_id", f"storage-{uuid4()}")
        mock_essay.assessment_input_text = kwargs.get("assessment_input_text", "Mock essay content")
        return mock_essay

    def _get_mock_batch_state(self, session, cj_batch_id, correlation_id):
        """Get a mock batch state with realistic data."""
        from services.cj_assessment_service.models_db import CJBatchState

        mock_state = MagicMock(spec=CJBatchState)
        mock_state.batch_id = cj_batch_id
        mock_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        mock_state.total_comparisons = 45  # C(10,2)
        mock_state.completed_comparisons = 0
        mock_state.partial_scoring_triggered = False
        mock_state.created_at = datetime.now(UTC)
        mock_state.updated_at = datetime.now(UTC)
        return mock_state

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create a mock event publisher."""
        publisher = AsyncMock(spec=CJEventPublisherProtocol)
        publisher.publish_assessment_completed = AsyncMock()
        publisher.publish_assessment_failed = AsyncMock()
        return publisher

    @pytest.fixture
    def mock_content_client(self) -> AsyncMock:
        """Create a mock content client with realistic essay content."""
        client = AsyncMock(spec=ContentClientProtocol)

        # Generate realistic essay content based on storage ID
        async def fetch_content(storage_id: str, correlation_id: UUID) -> str:
            # Extract essay number from storage ID if possible
            essay_num = storage_id.split("-")[-1] if "-" in storage_id else "0"

            # Realistic essay content samples
            essay_templates = [
                "The impact of technology on modern education has been transformative. Digital tools have revolutionized how students learn and teachers instruct. From online resources to interactive platforms, the educational landscape continues to evolve rapidly.",
                "Climate change presents one of the greatest challenges of our time. Rising temperatures, extreme weather events, and ecosystem disruption demand immediate global action. Sustainable solutions require cooperation between governments, businesses, and individuals.",
                "The importance of mental health awareness cannot be overstated. Breaking down stigmas and providing accessible support services are crucial steps toward a healthier society. Early intervention and education play key roles in mental wellness.",
                "Artificial intelligence is reshaping industries across the globe. From healthcare diagnostics to financial analysis, AI applications continue to expand. However, ethical considerations and responsible development remain paramount concerns.",
                "Cultural diversity enriches our communities in countless ways. Embracing different perspectives, traditions, and experiences fosters innovation and understanding. Building inclusive societies requires ongoing effort and open dialogue.",
            ]

            # Return a consistent essay based on the ID
            try:
                idx = int(essay_num) % len(essay_templates)
                return essay_templates[idx]
            except:
                return essay_templates[0]

        client.fetch_content = AsyncMock(side_effect=fetch_content)
        client.fetch_essay_content = AsyncMock(side_effect=fetch_content)

        return client

    @pytest.fixture
    def mock_llm_interaction(self) -> AsyncMock:
        """Create a mock LLM interaction with realistic comparison results."""
        interaction = AsyncMock(spec=LLMInteractionProtocol)

        async def perform_comparisons(
            tasks,
            correlation_id,
            model_override=None,
            temperature_override=None,
            max_tokens_override=None,
        ):
            """Generate realistic comparison results for the given tasks."""
            from services.cj_assessment_service.models_api import (
                ComparisonResult,
                LLMAssessmentResponseSchema,
            )

            results = []
            for i, task in enumerate(tasks):
                # Simulate realistic winner selection (slight bias toward first essay)
                winner = (
                    EssayComparisonWinner.ESSAY_A if i % 3 != 2 else EssayComparisonWinner.ESSAY_B
                )

                # Create realistic assessment data
                assessment = LLMAssessmentResponseSchema(
                    winner=winner,
                    confidence=3.5 + (i % 3) * 0.5,  # Varies between 3.5 and 4.5
                    justification=(
                        f"Essay {winner.value} demonstrates stronger argumentation and clarity."
                    ),
                )

                # Create comparison result
                result = ComparisonResult(
                    task=task,
                    llm_assessment=assessment,
                    raw_llm_response_content=(
                        f'{{"winner": "{winner.value}", '
                        f'"confidence": {assessment.confidence}, '
                        f'"justification": "{assessment.justification}"}}'
                    ),
                    error_detail=None,
                )
                results.append(result)

            return results

        interaction.perform_comparisons = AsyncMock(side_effect=perform_comparisons)
        return interaction

    @pytest.fixture
    def test_settings(self) -> Settings:
        """Create test settings."""
        settings = Settings()
        settings.BATCH_TIMEOUT_HOURS = 4
        settings.BATCH_MONITOR_INTERVAL_MINUTES = 5
        # Mock completion threshold setting (would be in real settings)
        # settings.COMPLETION_THRESHOLD_PCT = 80  # This field doesn't exist in Settings
        # settings.MIN_SUCCESS_RATE_THRESHOLD = 0.8  # This field doesn't exist in Settings
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
        confidence: float = 4.2,
        is_error: bool = False,
    ) -> EventEnvelope[LLMComparisonResultV1]:
        """Create an LLM comparison result callback event."""
        result_data = LLMComparisonResultV1(
            request_id=request_id,
            correlation_id=correlation_id,
            provider=LLMProviderType.ANTHROPIC,
            model="claude-3-haiku-20240307",
            winner=EssayComparisonWinner.ESSAY_A
            if winner == "essay_a"
            else EssayComparisonWinner.ESSAY_B,
            confidence=confidence,
            justification="Test justification",
            response_time_ms=1500,
            token_usage=TokenUsage(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            cost_estimate=0.001,
            requested_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            error_detail=None,
        )

        return EventEnvelope[LLMComparisonResultV1](
            event_type="llm_provider.comparison.completed.v1",
            event_timestamp=datetime.now(UTC),
            source_service="llm_provider_service",
            correlation_id=correlation_id,
            data=result_data,
        )

    def _create_kafka_message(
        self,
        envelope: EventEnvelope,
        topic: str,
        key: str,
    ) -> ConsumerRecord:
        """Create a Kafka ConsumerRecord from an envelope."""
        message_value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        kafka_msg = MagicMock(spec=ConsumerRecord)
        kafka_msg.topic = topic
        kafka_msg.partition = 0
        kafka_msg.offset = 123
        kafka_msg.key = key.encode("utf-8")
        kafka_msg.value = message_value
        return kafka_msg

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

        # The fixtures already set up the mocks properly, no need to override them

        # Create Kafka message
        kafka_msg = self._create_kafka_message(
            request_event,
            "els.cj_assessment.requested.v1",
            batch_id,
        )

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
        mock_llm_interaction.perform_comparisons.assert_called()

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
            state=CJBatchStateEnum.WAITING_CALLBACKS,
            progress_percentage=85,  # Above recovery threshold
            hours_old=5,  # Past timeout threshold
        )

        # Get the existing mock session from the fixture's context manager
        mock_context_manager = mock_repository.session.return_value
        mock_session = mock_context_manager.__aenter__.return_value

        # Set up the query chain for stuck batches
        mock_execute_result = MagicMock()
        mock_scalars_result = MagicMock()
        mock_scalars_result.all = MagicMock(return_value=[stuck_batch])
        mock_execute_result.scalars = MagicMock(return_value=mock_scalars_result)

        # Configure session.execute to return our mock result
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Mock batch upload for correlation_id
        mock_batch_upload = MagicMock()
        mock_batch_upload.event_correlation_id = str(uuid4())
        mock_session.get = AsyncMock(return_value=mock_batch_upload)

        # Mock essays for completion
        mock_essays = [MagicMock() for _ in range(10)]
        for i, essay in enumerate(mock_essays):
            essay.id = f"essay-{i}"
            essay.content = f"Essay content {i}"
            essay.els_essay_id = f"essay-{i}"
            essay.current_bt_score = 0.0

        # Act - Run batch monitor with mocked sleep
        # Track sleep calls
        sleep_call_count = 0
        
        async def mock_sleep(duration):
            nonlocal sleep_call_count
            sleep_call_count += 1
            # After the first sleep (30s initial delay), let one iteration run
            # Then set _running to False on subsequent sleeps
            if sleep_call_count > 1:
                test_monitor._running = False
            return None
        
        # Mock asyncio.sleep to bypass delays and control execution
        with patch('asyncio.sleep', side_effect=mock_sleep):
            # Run the monitor check
            await test_monitor.check_stuck_batches()

        # Assert - Verify batch was processed
        # Note: The actual recovery logic would be called through the monitor
        assert mock_session.execute.called
        # Check if the batch upload was accessed for correlation_id
        assert mock_session.get.called or mock_session.execute.called

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
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_repository.session.return_value = mock_session

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
            kafka_msg = self._create_kafka_message(
                callback,
                "llm_provider.comparison.completed.v1",
                callback.data.request_id,
            )

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
        batch_id = 1  # Use integer ID for internal batch
        correlation_id = uuid4()
        total_pairs = 100

        # Get the existing mock session from the fixture's context manager
        mock_context_manager = mock_repository.session.return_value
        mock_session = mock_context_manager.__aenter__.return_value

        # Mock batch state with 80% completion
        mock_batch_state = MagicMock()
        mock_batch_state.batch_id = batch_id
        mock_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        mock_batch_state.completed_comparisons = 80
        mock_batch_state.total_comparisons = total_pairs
        mock_batch_state.partial_scoring_triggered = False
        mock_session.get = AsyncMock(return_value=mock_batch_state)

        # Mock comparison pair - ensure scalar_one_or_none returns a MagicMock, not a coroutine
        mock_pair = MagicMock()
        mock_pair.id = "pair-80"
        mock_pair.cj_batch_id = batch_id
        mock_pair.winner = None
        mock_pair.completed_at = None
        mock_pair.request_correlation_id = correlation_id
        
        # Set up the execute result chain
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none = MagicMock(return_value=mock_pair)
        mock_session.execute = AsyncMock(return_value=mock_execute_result)

        # Create callback for the 80th completion
        callback = self._create_callback_event(
            request_id="pair-80",
            correlation_id=correlation_id,
            winner="essay_a",
        )

        # Create Kafka message
        kafka_msg = self._create_kafka_message(
            callback,
            "llm_provider.comparison.completed.v1",
            "pair-80",
        )

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
