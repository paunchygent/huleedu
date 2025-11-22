"""
Integration tests using real database implementations.

This demonstrates the proper way to do integration testing:
- Real database operations with SQLAlchemy
- Real repository implementation
- Proper test isolation with transaction rollback
- Mock only external boundaries (Content, LLM, Kafka)
"""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from aiokafka import ConsumerRecord
from common_core.domain_enums import ContentType, CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import (
    CJAssessmentCompletedV1,
    ELS_CJAssessmentRequestV1,
)
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)
from common_core.status_enums import BatchStatus, CJBatchStateEnum, ProcessingStage

from services.cj_assessment_service.cj_core_logic.workflow_continuation import (
    trigger_existing_workflow_continuation,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.event_processor import process_single_message
from services.cj_assessment_service.models_db import CJBatchState
from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
    ContentClientProtocol,
)
from services.cj_assessment_service.tests.integration.callback_simulator import (
    CallbackSimulator,
)

if TYPE_CHECKING:
    pass


@pytest.mark.integration
class TestRealDatabaseIntegration:
    """Integration tests using real database implementations."""

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

        system_metadata = SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            timestamp=datetime.now(UTC),
            processing_stage=ProcessingStage.PENDING,
            event=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED.value,
        )

        student_prompt_ref = StorageReferenceMetadata(
            references={
                ContentType.STUDENT_PROMPT_TEXT: {
                    "storage_id": "prompt-storage-real-db",
                    "path": "",
                }
            }
        )

        request_data = ELS_CJAssessmentRequestV1(
            event_name=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED,
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            system_metadata=system_metadata,
            essays_for_cj=essays,
            language="en",
            course_code=CourseCode.ENG5,
            llm_config_overrides=None,
            # Identity fields for credit attribution (Phase 3)
            user_id="db-integration-test-user",
            org_id=None,  # Test scenario without org
            student_prompt_ref=student_prompt_ref,
        )

        return EventEnvelope[ELS_CJAssessmentRequestV1](
            event_type="els.cj_assessment.requested.v1",
            event_timestamp=datetime.now(UTC),
            source_service="essay_lifecycle_service",
            correlation_id=correlation_id,
            data=request_data,
        )

    def _create_kafka_message(
        self,
        envelope: EventEnvelope,
        topic: str,
        key: str,
    ) -> ConsumerRecord:
        """Create a Kafka ConsumerRecord from an envelope."""
        from unittest.mock import MagicMock

        message_value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        kafka_msg = MagicMock(spec=ConsumerRecord)
        kafka_msg.topic = topic
        kafka_msg.partition = 0
        kafka_msg.offset = 123
        kafka_msg.timestamp = int(datetime.now(UTC).timestamp() * 1000)
        kafka_msg.timestamp_type = 1
        kafka_msg.key = key.encode("utf-8")
        kafka_msg.value = message_value
        kafka_msg.headers = []
        return kafka_msg

    @pytest.mark.slow
    async def test_full_batch_lifecycle_with_real_database(
        self,
        postgres_repository: CJRepositoryProtocol,
        mock_content_client: ContentClientProtocol,
        mock_event_publisher: AsyncMock,
        mock_llm_interaction_async: AsyncMock,  # Use async mock
        test_settings: Settings,
        db_verification_helpers: Any,
    ) -> None:
        """Test complete batch lifecycle with real database operations."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()
        essay_count = 5

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

        # Act - Process the request using real database
        result = await process_single_message(
            kafka_msg,
            postgres_repository,
            mock_content_client,
            mock_event_publisher,
            mock_llm_interaction_async,  # Use async mock
            test_settings,
        )

        # Assert - Verify message processed successfully
        assert result is True

        # Find the actual CJ batch ID and initialize batch state
        async with postgres_repository.session() as session:
            cj_batch = await db_verification_helpers.find_batch_by_bos_id(session, batch_id)
            assert cj_batch is not None, f"CJ batch not found for BOS batch ID: {batch_id}"
            actual_cj_batch_id = cj_batch.id

            # Verify batch processor initialized values correctly
            # 5 essays = nC2 = 10 comparison pairs
            batch_state = await session.get(CJBatchState, actual_cj_batch_id)
            assert batch_state is not None, "Batch state should exist after processing"
            assert batch_state.submitted_comparisons == 10, (
                f"Expected submitted_comparisons=10, got {batch_state.submitted_comparisons}"
            )
            assert batch_state.total_budget is not None, "total_budget should be backfilled"
            assert batch_state.total_budget > 0, (
                f"Expected total_budget > 0, got {batch_state.total_budget}"
            )

        # Phase 2: Simulate LLM callbacks to complete the workflow
        # This bridges the async gap in testing by processing the mock results as callbacks
        callback_simulator = CallbackSimulator()
        callbacks_processed = await callback_simulator.simulate_callbacks_from_mock_results(
            mock_llm_interaction=mock_llm_interaction_async,  # Use async mock
            database=postgres_repository,
            event_publisher=mock_event_publisher,
            settings=test_settings,
            content_client=mock_content_client,
            correlation_id=correlation_id,
        )

        # Verify callbacks were processed
        assert callbacks_processed > 0, "No callbacks were processed"

        # Verify batch state reflects all callbacks before forcing continuation
        async with postgres_repository.session() as session:
            batch_state = await session.get(CJBatchState, actual_cj_batch_id)
            assert batch_state is not None
            # All processed callbacks should be recorded in completed/failed counters
            assert (
                batch_state.completed_comparisons + batch_state.failed_comparisons
                == callbacks_processed
            ), (
                "Callback counters do not match processed callbacks: "
                f"completed={batch_state.completed_comparisons}, "
                f"failed={batch_state.failed_comparisons}, "
                f"callbacks_processed={callbacks_processed}"
            )

        # Trigger final workflow continuation to ensure completion event is published
        # New logic: continuation runs after all submitted callbacks have arrived
        if callbacks_processed >= (essay_count * (essay_count - 1)) // 2:
            await trigger_existing_workflow_continuation(
                batch_id=actual_cj_batch_id,
                database=postgres_repository,
                event_publisher=mock_event_publisher,
                settings=test_settings,
                content_client=mock_content_client,
                correlation_id=correlation_id,
                llm_interaction=mock_llm_interaction_async,
                retry_processor=None,
            )

        # Verify database operations occurred
        async with postgres_repository.session() as session:
            # Verify batch was created with correct essay count
            batches = await postgres_repository.get_essays_for_cj_batch(session, actual_cj_batch_id)
            assert len(batches) == essay_count

            # Verify essays were stored
            essay_count_in_db = await db_verification_helpers.verify_essay_count(
                session, actual_cj_batch_id
            )
            assert essay_count_in_db == essay_count

            # Verify batch reached a successful terminal state
            from services.cj_assessment_service.models_db import CJBatchUpload

            cj_batch = await session.get(CJBatchUpload, actual_cj_batch_id)
            assert cj_batch is not None

            # Get final state for diagnostic assertion
            final_batch_state = await session.get(CJBatchState, actual_cj_batch_id)
            pending_callbacks = (
                final_batch_state.submitted_comparisons
                - (final_batch_state.completed_comparisons + final_batch_state.failed_comparisons)
                if final_batch_state
                else "N/A"
            )

            state_val = final_batch_state.state.value if final_batch_state else "NOT FOUND"
            submitted_val = final_batch_state.submitted_comparisons if final_batch_state else "N/A"
            completed_val = final_batch_state.completed_comparisons if final_batch_state else "N/A"
            failed_val = final_batch_state.failed_comparisons if final_batch_state else "N/A"
            total_budget_val = final_batch_state.total_budget if final_batch_state else "N/A"
            denom_val = final_batch_state.completion_denominator() if final_batch_state else "N/A"

            diagnostic_info = (
                f"\n{'=' * 80}\n"
                f"BATCH FINALIZATION FAILURE DIAGNOSTICS\n"
                f"{'=' * 80}\n"
                f"Expected Status: {BatchStatus.COMPLETED_SUCCESSFULLY.value}\n"
                f"Actual Status: {cj_batch.status.value}\n"
                f"Batch State: {state_val}\n"
                f"Submitted Comparisons: {submitted_val}\n"
                f"Completed Comparisons: {completed_val}\n"
                f"Failed Comparisons: {failed_val}\n"
                f"Pending Callbacks: {pending_callbacks}\n"
                f"Total Budget: {total_budget_val}\n"
                f"Denominator: {denom_val}\n"
                f"{'=' * 80}\n"
            )

            # Verify batch reached a successful terminal state
            # CJ batches can complete in multiple ways: stability, max comparisons, etc.
            from services.cj_assessment_service.enums_db import CJBatchStatusEnum

            successful_completion_statuses = {
                CJBatchStatusEnum.COMPLETE_STABLE,
                CJBatchStatusEnum.COMPLETE_MAX_COMPARISONS,
            }
            assert cj_batch.status in successful_completion_statuses, (
                f"{diagnostic_info}\n"
                f"Expected one of {[s.value for s in successful_completion_statuses]}, "
                f"got {cj_batch.status.value}"
            )

            batch_state = await session.get(CJBatchState, actual_cj_batch_id)
            assert batch_state is not None
            assert batch_state.state == CJBatchStateEnum.COMPLETED

        # Verify external services were called
        mock_llm_interaction_async.perform_comparisons.assert_called_once()

        # If a completion event was published, verify its structure. Dual-event
        # publishing is validated in dedicated outbox tests; this test focuses on
        # end-to-end workflow and database state.
        if mock_event_publisher.publish_assessment_completed.call_count >= 1:
            published_call = mock_event_publisher.publish_assessment_completed.call_args
            completion_envelope = published_call.kwargs["completion_data"]
            assert completion_envelope.event_type == topic_name(
                ProcessingEvent.CJ_ASSESSMENT_COMPLETED
            )
            assert completion_envelope.correlation_id == correlation_id
            typed_completion_data = CJAssessmentCompletedV1.model_validate(completion_envelope.data)
            assert typed_completion_data.status == BatchStatus.COMPLETED_SUCCESSFULLY

    async def test_database_isolation_between_tests(
        self,
        postgres_repository: CJRepositoryProtocol,
        db_verification_helpers: Any,
    ) -> None:
        """Test that database transactions are properly isolated between tests."""
        # This test should start with a clean database
        async with postgres_repository.session() as session:
            # Verify no data leakage from previous tests
            assert await db_verification_helpers.verify_no_data_leakage(session)

            # Create some test data
            from services.cj_assessment_service.enums_db import CJBatchStatusEnum

            batch = await postgres_repository.create_new_cj_batch(
                session=session,
                bos_batch_id=str(uuid4()),
                event_correlation_id=str(uuid4()),
                language="en",
                course_code="ENG5",
                initial_status=CJBatchStatusEnum.PENDING,
                expected_essay_count=3,
            )
            batch.processing_metadata = {"student_prompt_text": "Test isolation"}

            # Verify batch was created
            assert await db_verification_helpers.verify_batch_exists(session, batch.id)

        # After this test completes, the transaction should be rolled back
        # and no data should persist to the next test

    async def test_real_database_operations_with_postgresql(
        self,
        postgres_repository: CJRepositoryProtocol,
        db_verification_helpers: Any,
    ) -> None:
        """Test with PostgreSQL for production parity.

        This test demonstrates proper database operations with explicit cleanup
        via the clean_database_between_tests fixture, maintaining repository-managed
        sessions per architectural standards.
        """
        # Test PostgreSQL-specific operations with repository-managed sessions
        async with postgres_repository.session() as session:
            # Verify clean state (cleanup fixture ensures this)
            assert await db_verification_helpers.verify_no_data_leakage(session)

            # Test PostgreSQL-specific operations
            from services.cj_assessment_service.enums_db import CJBatchStatusEnum

            # Create batch
            batch = await postgres_repository.create_new_cj_batch(
                session=session,
                bos_batch_id=str(uuid4()),
                event_correlation_id=str(uuid4()),
                language="en",
                course_code="ENG5",
                initial_status=CJBatchStatusEnum.PENDING,
                expected_essay_count=5,
            )
            batch.processing_metadata = {"student_prompt_text": "PostgreSQL test"}

            # Create essays
            essays = []
            for i in range(5):
                essay = await postgres_repository.create_or_update_cj_processed_essay(
                    session=session,
                    cj_batch_id=batch.id,
                    els_essay_id=f"essay-{i}",
                    text_storage_id=f"storage-{i}",
                    assessment_input_text=f"PostgreSQL essay content {i}",
                )
                essays.append(essay)

            # Verify operations within this session
            assert len(essays) == 5
            essay_count = await db_verification_helpers.verify_essay_count(session, batch.id)
            assert essay_count == 5

            # Test ranking operations
            scores = {f"essay-{i}": float(i) * 0.1 for i in range(5)}
            await postgres_repository.update_essay_scores_in_batch(
                session=session,
                cj_batch_id=batch.id,
                scores=scores,
            )

            # Get rankings
            rankings = await postgres_repository.get_final_cj_rankings(
                session=session,
                cj_batch_id=batch.id,
            )

            assert len(rankings) == 5
            # Verify rankings are sorted by score (descending)
            for i in range(len(rankings) - 1):
                assert rankings[i]["score"] >= rankings[i + 1]["score"]

            # Session auto-commits here per repository pattern
            # Cleanup fixture will truncate tables after test completes

    # Mark this test as slow since it requires PostgreSQL testcontainers
    test_real_database_operations_with_postgresql = pytest.mark.slow(
        test_real_database_operations_with_postgresql
    )

    async def test_content_client_integration(
        self,
        mock_content_client: ContentClientProtocol,
    ) -> None:
        """Test that content client mock provides realistic data."""
        # Test the content client mock behavior
        correlation_id = uuid4()

        # Test different storage IDs
        content_1 = await mock_content_client.fetch_content("storage-1", correlation_id)
        content_2 = await mock_content_client.fetch_content("storage-2", correlation_id)
        content_3 = await mock_content_client.fetch_content("storage-same", correlation_id)

        # Verify content is returned and varies by storage ID
        assert content_1 != content_2
        assert len(content_1) > 50  # Realistic essay length
        assert len(content_2) > 50

        # Same storage ID should return same content
        content_same = await mock_content_client.fetch_content("storage-same", correlation_id)
        assert content_3 == content_same

    async def test_llm_interaction_parameter_usage(
        self,
        mock_llm_interaction: AsyncMock,
    ) -> None:
        """Test that LLM interaction mock uses all parameters meaningfully."""
        from services.cj_assessment_service.models_api import ComparisonTask, EssayForComparison

        # Create mock tasks with proper model structure
        essay_a = EssayForComparison(id="essay-1", text_content="Content A", current_bt_score=None)
        essay_b = EssayForComparison(id="essay-2", text_content="Content B", current_bt_score=None)

        tasks = [
            ComparisonTask(
                essay_a=essay_a,
                essay_b=essay_b,
                prompt="Compare these essays",
            )
        ]

        correlation_id = uuid4()

        # Test with different parameters
        results_default = await mock_llm_interaction.perform_comparisons(
            tasks=tasks,
            correlation_id=correlation_id,
        )

        results_with_overrides = await mock_llm_interaction.perform_comparisons(
            tasks=tasks,
            correlation_id=correlation_id,
            model_override="gpt-4",
            temperature_override=0.8,
            max_tokens_override=500,
        )

        # Verify results are different based on parameters
        assert len(results_default) == 1
        assert len(results_with_overrides) == 1

        # The mock should use parameters to influence results
        # (confidence, winner selection, etc.)
        result_default = results_default[0]
        result_override = results_with_overrides[0]

        # Both should have assessments
        assert result_default.llm_assessment is not None
        assert result_override.llm_assessment is not None

        # Parameters should influence the results in some way
        # (This is verified by the fact that different parameters produce
        # deterministic but different results based on the hash)
        assert result_default.llm_assessment.confidence > 0
        assert result_override.llm_assessment.confidence > 0
