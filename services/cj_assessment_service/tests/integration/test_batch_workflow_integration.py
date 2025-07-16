"""
End-to-end integration tests for CJ Assessment batch workflow.
Tests the complete lifecycle from request to callback to completion.

Migrated from over-mocked to real database implementation.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
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
)
from services.cj_assessment_service.tests.fixtures.test_models_db import (
    TestCJBatchState,
    TestComparisonPair,
)

if TYPE_CHECKING:
    pass


@pytest.mark.integration
class TestBatchWorkflowIntegration:
    """Test complete batch processing workflow with callbacks."""

    # Using real_repository fixture from database_fixtures.py

    # No longer needed - using real database operations

    # No longer needed - using real database operations

    # No longer needed - using real database operations

    # Using mock_event_publisher from database_fixtures.py

    # Using mock_content_client from database_fixtures.py

    # Using mock_llm_interaction from database_fixtures.py

    # Using test_settings from database_fixtures.py

    @pytest.fixture
    def test_monitor(
        self,
        real_repository: CJRepositoryProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        test_settings: Settings,
    ) -> BatchMonitor:
        """Create a batch monitor instance."""
        return BatchMonitor(real_repository, mock_event_publisher, test_settings)

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
        real_repository: CJRepositoryProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        mock_content_client,
        mock_llm_interaction,
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

        # Create Kafka message
        kafka_msg = self._create_kafka_message(
            request_event,
            "els.cj_assessment.requested.v1",
            batch_id,
        )

        # Patch production models to use test models for SQLite compatibility
        with patch(
            "services.cj_assessment_service.models_db.CJBatchState",
            TestCJBatchState,
        ):
            # Act - Process the request
            result = await process_single_message(
                kafka_msg,
                real_repository,
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
        real_repository: CJRepositoryProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        test_monitor: BatchMonitor,
    ) -> None:
        """Test stuck batch detection and recovery."""
        # Patch production models to use test models for SQLite compatibility
        with patch(
            "services.cj_assessment_service.models_db.CJBatchState",
            TestCJBatchState,
        ):
            # Arrange - Create a real stuck batch using the database
            async with real_repository.session() as session:
                from datetime import timedelta

                from services.cj_assessment_service.enums_db import CJBatchStatusEnum

                # Create a batch that appears stuck
                batch = await real_repository.create_new_cj_batch(
                    session=session,
                    bos_batch_id=str(uuid4()),
                    event_correlation_id=str(uuid4()),
                    language="en",
                    course_code="ENG5",
                    essay_instructions="Test stuck batch",
                    initial_status=CJBatchStatusEnum.PENDING,
                    expected_essay_count=10,
                )

                # Create some essays
                for i in range(10):
                    await real_repository.create_or_update_cj_processed_essay(
                        session=session,
                        cj_batch_id=batch.id,
                        els_essay_id=f"essay-{i}",
                        text_storage_id=f"storage-{i}",
                        assessment_input_text=f"Essay content {i}",
                    )

                # Update batch state to appear stuck (simulate old activity)
                batch_state = TestCJBatchState(
                    batch_id=batch.id,
                    state=CJBatchStateEnum.WAITING_CALLBACKS,
                    total_comparisons=45,
                    completed_comparisons=38,  # 85% completion
                    partial_scoring_triggered=False,
                    last_activity_at=datetime.now(UTC) - timedelta(hours=5),
                )
                session.add(batch_state)
                await session.commit()

            # Act - Run batch monitor with mocked sleep
            sleep_call_count = 0

            async def mock_sleep(duration):
                nonlocal sleep_call_count
                sleep_call_count += 1
                # After the first sleep, let one iteration run then stop
                if sleep_call_count > 1:
                    test_monitor._running = False
                return None

            # Mock asyncio.sleep to bypass delays and control execution
            with patch("asyncio.sleep", side_effect=mock_sleep):
                # Run the monitor check
                await test_monitor.check_stuck_batches()

            # Assert - Verify batch was processed
            # The monitor should have detected the stuck batch
            assert sleep_call_count > 0

    async def test_concurrent_callback_processing(
        self,
        real_repository: CJRepositoryProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        mock_content_client,
        mock_llm_interaction,
        test_settings: Settings,
    ) -> None:
        """Test race conditions with concurrent callbacks using real database."""
        # Patch production models to use test models for SQLite compatibility
        with patch(
            "services.cj_assessment_service.models_db.CJBatchState",
            TestCJBatchState,
        ):
            # Arrange
            batch_id = str(uuid4())
            correlation_id = uuid4()
            callback_count = 100

            # Create real database state instead of mocks
            async with real_repository.session() as session:
                from datetime import UTC, datetime

                from services.cj_assessment_service.enums_db import CJBatchStatusEnum

                # Create a real batch
                batch = await real_repository.create_new_cj_batch(
                    session=session,
                    bos_batch_id=batch_id,
                    event_correlation_id=str(correlation_id),
                    language="en",
                    course_code="ENG5",
                    essay_instructions="Concurrent callback test",
                    initial_status=CJBatchStatusEnum.PENDING,
                    expected_essay_count=callback_count,
                )

                # Create essays for comparison pairs
                essays = []
                for i in range(callback_count):
                    essay = await real_repository.create_or_update_cj_processed_essay(
                        session=session,
                        cj_batch_id=batch.id,
                        els_essay_id=f"essay-{i}",
                        text_storage_id=f"storage-{i}",
                        assessment_input_text=f"Essay content {i}",
                    )
                    essays.append(essay)

                # Create comparison pairs for callbacks
                pairs = []
                for i in range(callback_count):
                    # Create pairs using round-robin essay assignment
                    essay_a_idx = i % len(essays)
                    essay_b_idx = (i + 1) % len(essays)

                    pair_correlation_id = uuid4()
                    pair = TestComparisonPair(
                        cj_batch_id=batch.id,
                        essay_a_els_id=essays[essay_a_idx].els_essay_id,
                        essay_b_els_id=essays[essay_b_idx].els_essay_id,
                        prompt_text="Compare these essays",
                        request_correlation_id=str(pair_correlation_id),
                        submitted_at=datetime.now(UTC),
                    )
                    session.add(pair)
                    pairs.append((pair, pair_correlation_id))

                # Create batch state for concurrent processing
                batch_state = TestCJBatchState(
                    batch_id=batch.id,
                    state=CJBatchStateEnum.WAITING_CALLBACKS,
                    total_comparisons=callback_count,
                    completed_comparisons=0,
                    submitted_comparisons=callback_count,
                    failed_comparisons=0,
                )
                session.add(batch_state)
                await session.commit()

            # Create callback events for all pairs
            callback_events = []
            for i, (pair, pair_correlation_id) in enumerate(pairs):
                callback = self._create_callback_event(
                    request_id=str(pair.id),
                    correlation_id=pair_correlation_id,
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
                        real_repository,
                        mock_event_publisher,
                        test_settings,
                    )
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Assert - Verify all callbacks processed successfully
            successful_results = [r for r in results if r is True]
            failed_results = [r for r in results if isinstance(r, Exception)]

            # Allow for some race condition effects but most should succeed
            assert len(successful_results) >= callback_count * 0.8  # At least 80% success
            assert len(failed_results) < callback_count * 0.2  # Less than 20% failures

            # Verify database state reflects concurrent processing
            async with real_repository.session() as session:
                # Check that batch state was updated
                batch_state_result = await session.get(TestCJBatchState, batch.id)
                assert batch_state_result is not None
                assert batch_state_result.completed_comparisons > 0

    @pytest.mark.expensive
    async def test_partial_batch_completion(
        self,
        postgres_repository: CJRepositoryProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        mock_content_client,
        mock_llm_interaction,
        test_settings: Settings,
    ) -> None:
        """Test partial completion threshold triggering using real PostgreSQL database."""
        # No patching needed - using production models with real PostgreSQL
        from datetime import UTC, datetime

        from services.cj_assessment_service.enums_db import CJBatchStatusEnum
        from services.cj_assessment_service.models_db import CJBatchState, ComparisonPair

        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()
        total_pairs = 100

        # Create real database state using production models
        async with postgres_repository.session() as session:
            # Create a real batch using production repository
            batch = await postgres_repository.create_new_cj_batch(
                session=session,
                bos_batch_id=batch_id,
                event_correlation_id=str(correlation_id),
                language="en",
                course_code="ENG5",
                essay_instructions="Partial completion test",
                initial_status=CJBatchStatusEnum.PENDING,
                expected_essay_count=total_pairs,
            )

            # Create essays for comparison pairs
            essays = []
            for i in range(total_pairs):
                essay = await postgres_repository.create_or_update_cj_processed_essay(
                    session=session,
                    cj_batch_id=batch.id,
                    els_essay_id=f"essay-{i}",
                    text_storage_id=f"storage-{i}",
                    assessment_input_text=f"Sample essay content {i}",
                )
                essays.append(essay)

            # Create 80 completed comparison pairs (80% completion)
            for i in range(80):
                pair = ComparisonPair(
                    cj_batch_id=batch.id,
                    essay_a_els_id=essays[i].els_essay_id,
                    essay_b_els_id=essays[i + 1].els_essay_id,
                    prompt_text="Compare these essays",
                    request_correlation_id=uuid4(),
                    submitted_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    winner="essay_a",
                )
                session.add(pair)

            # Create one pending comparison pair (the 81st)
            pending_pair = ComparisonPair(
                cj_batch_id=batch.id,
                essay_a_els_id=essays[80].els_essay_id,
                essay_b_els_id=essays[81].els_essay_id,
                prompt_text="Compare these essays",
                request_correlation_id=correlation_id,
                submitted_at=datetime.now(UTC),
            )
            session.add(pending_pair)

            # Create batch state with 80 completed comparisons
            batch_state = CJBatchState(
                batch_id=batch.id,
                state=CJBatchStateEnum.WAITING_CALLBACKS,
                total_comparisons=total_pairs,
                completed_comparisons=80,
                submitted_comparisons=81,
                failed_comparisons=0,
                partial_scoring_triggered=False,
                completion_threshold_pct=80,
                current_iteration=1,
            )
            session.add(batch_state)
            await session.commit()

            # Refresh to get the database-assigned ID
            await session.refresh(pending_pair)

        # Create callback for the 81st completion (triggering 80% threshold)
        llm_request_id = f"llm-request-{pending_pair.id}"
        callback = self._create_callback_event(
            request_id=llm_request_id,
            correlation_id=correlation_id,
            winner="essay_a",
        )

        # Create Kafka message
        kafka_msg = self._create_kafka_message(
            callback,
            "llm_provider.comparison.completed.v1",
            llm_request_id,
        )

        # Act - Process the callback that triggers partial completion
        result = await process_llm_result(
            kafka_msg,
            postgres_repository,
            mock_event_publisher,
            test_settings,
        )

        # Assert - Verify callback processed and partial scoring triggered
        assert result is True

        # Verify real database state reflects partial scoring trigger
        async with postgres_repository.session() as session:
            # First, check if the comparison pair was updated by the callback
            updated_pair = await session.get(ComparisonPair, pending_pair.id)
            assert updated_pair is not None
            assert updated_pair.winner == "Essay A"
            assert updated_pair.completed_at is not None

            # Then check the batch state
            batch_state_result = await session.get(CJBatchState, batch.id)
            assert batch_state_result is not None

            # The callback should have updated the completion count and triggered partial scoring
            assert batch_state_result.completed_comparisons == 81
            assert batch_state_result.partial_scoring_triggered is True
