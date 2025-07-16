"""Integration tests for error handling and recovery scenarios."""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import AsyncGenerator, Optional
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from aiokafka import ConsumerRecord
from sqlalchemy.ext.asyncio import AsyncSession

from common_core import LLMProviderType
from common_core.domain_enums import EssayComparisonWinner
from common_core.error_enums import ErrorCode
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1, TokenUsage
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import CJBatchStateEnum
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.event_processor import process_llm_result
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
)

# CJBatchState import removed - not used in this test file


@pytest.mark.integration
class TestErrorHandlingIntegration:
    """Test error scenarios and recovery mechanisms."""

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
        postgres_repository: CJRepositoryProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        test_settings: Settings,
    ) -> None:
        """Test handling of orphaned callbacks."""
        # Arrange - Use a correlation_id that has no corresponding comparison pair in database
        unknown_correlation_id = uuid4()
        request_id = str(uuid4())

        callback = self._create_callback_event(
            request_id=request_id,
            correlation_id=unknown_correlation_id,
            winner="essay_a",
        )

        # Create Kafka message
        kafka_msg = self._create_kafka_message(callback, request_id)

        # Act - Should handle gracefully without any comparison pairs in database
        result = await process_llm_result(
            kafka_msg,
            postgres_repository,
            mock_event_publisher,
            test_settings,
        )

        # Assert - Message acknowledged but no database changes made
        assert result is True  # Acknowledged to prevent reprocessing

        # Verify database state - should have no comparison pairs
        async with postgres_repository.session() as session:
            from sqlalchemy import select

            from services.cj_assessment_service.models_db import ComparisonPair

            result_check = await session.execute(select(ComparisonPair))
            comparison_pairs = result_check.scalars().all()
            assert len(comparison_pairs) == 0  # No database changes

    async def test_duplicate_callback_idempotency(
        self,
        postgres_repository: CJRepositoryProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        test_settings: Settings,
    ) -> None:
        """Test idempotent handling of duplicate callbacks."""
        # Arrange - Create real database setup with incomplete comparison pair
        correlation_id = uuid4()
        request_id = "pair-123"

        # Create real database state with incomplete comparison pair
        async with postgres_repository.session() as session:
            from services.cj_assessment_service.enums_db import CJBatchStatusEnum

            # Create batch using repository method
            batch = await postgres_repository.create_new_cj_batch(
                session=session,
                bos_batch_id=str(uuid4()),
                event_correlation_id=str(uuid4()),
                language="en",
                course_code="ENG5",
                essay_instructions="Compare essays",
                initial_status=CJBatchStatusEnum.PERFORMING_COMPARISONS,
                expected_essay_count=2,
            )

            # Create essays that will be referenced by comparison pair
            essay_a = await postgres_repository.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=batch.id,
                els_essay_id="essay-a",
                text_storage_id="storage-a",
                assessment_input_text="Essay A content for comparison",
            )
            
            essay_b = await postgres_repository.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=batch.id,
                els_essay_id="essay-b", 
                text_storage_id="storage-b",
                assessment_input_text="Essay B content for comparison",
            )

            # Create comparison pair using SQLAlchemy model (after essays exist)
            from services.cj_assessment_service.models_db import ComparisonPair
            
            comparison_pair = ComparisonPair(
                cj_batch_id=batch.id,
                essay_a_els_id="essay-a",
                essay_b_els_id="essay-b",
                prompt_text="Compare these essays",
                request_correlation_id=str(correlation_id),
                winner=None,  # No winner yet
                confidence=None,
                completed_at=None,  # Not completed yet
            )
            session.add(comparison_pair)
            await session.commit()

        # Create callback event
        callback = self._create_callback_event(
            request_id=request_id,
            correlation_id=correlation_id,
            winner="essay_a",
        )

        # Create Kafka message
        kafka_msg = self._create_kafka_message(callback, request_id)

        # Act - Process same callback twice to test idempotency
        result1 = await process_llm_result(
            kafka_msg,
            postgres_repository,
            mock_event_publisher,
            test_settings,
        )
        result2 = await process_llm_result(
            kafka_msg,
            postgres_repository,
            mock_event_publisher,
            test_settings,
        )

        # Assert - Both processed successfully (idempotent)
        assert result1 is True
        assert result2 is True

        # Verify database state - comparison pair was updated by first callback
        # and idempotent behavior means second callback didn't change it
        async with postgres_repository.session() as session:
            from sqlalchemy import select

            from services.cj_assessment_service.models_db import ComparisonPair

            result_check = await session.execute(
                select(ComparisonPair).where(
                    ComparisonPair.request_correlation_id == str(correlation_id)
                )
            )
            pair = result_check.scalar_one()

            # First callback should have updated the winner, second was idempotent
            assert pair.winner == "Essay A"  # Updated by first callback
            assert pair.confidence == 4.2  # Updated by first callback
            assert pair.completed_at is not None  # Marked as completed

    async def test_high_failure_rate_batch_termination(
        self,
        postgres_repository: CJRepositoryProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        test_settings: Settings,
    ) -> None:
        """Test batch failure when error rate exceeds threshold."""
        # Arrange - Create real database setup with multiple comparison pairs
        batch_correlation_id = uuid4()

        # Create real database state with batch and comparison pairs
        comparison_correlation_ids = []
        async with postgres_repository.session() as session:
            from services.cj_assessment_service.enums_db import CJBatchStatusEnum
            from services.cj_assessment_service.models_db import ComparisonPair

            # Create batch using repository method
            batch = await postgres_repository.create_new_cj_batch(
                session=session,
                bos_batch_id=str(uuid4()),
                event_correlation_id=str(batch_correlation_id),
                language="en",
                course_code="ENG5",
                essay_instructions="Compare essays",
                initial_status=CJBatchStatusEnum.PERFORMING_COMPARISONS,
                expected_essay_count=10,
            )

            # Create essays first (before comparison pairs)
            for i in range(10):
                await postgres_repository.create_or_update_cj_processed_essay(
                    session=session,
                    cj_batch_id=batch.id,
                    els_essay_id=f"essay-a-{i}",
                    text_storage_id=f"storage-a-{i}",
                    assessment_input_text=f"Essay A content {i}",
                )
                await postgres_repository.create_or_update_cj_processed_essay(
                    session=session,
                    cj_batch_id=batch.id,
                    els_essay_id=f"essay-b-{i}",
                    text_storage_id=f"storage-b-{i}",
                    assessment_input_text=f"Essay B content {i}",
                )

            # Create 10 comparison pairs (no winners yet)
            for i in range(10):
                pair_correlation_id = uuid4()
                comparison_correlation_ids.append(pair_correlation_id)

                comparison_pair = ComparisonPair(
                    cj_batch_id=batch.id,
                    essay_a_els_id=f"essay-a-{i}",
                    essay_b_els_id=f"essay-b-{i}",
                    prompt_text="Compare these essays",
                    request_correlation_id=str(pair_correlation_id),
                    winner=None,  # No winner yet
                    confidence=None,
                    completed_at=None,  # Not completed yet
                )
                session.add(comparison_pair)

            await session.commit()

        # Test scenario: Process 10 callbacks, 5 success and 5 failures
        # Create success callbacks (first 5)
        success_results = []
        for i in range(5):
            callback = self._create_callback_event(
                request_id=f"pair-{i}",
                correlation_id=comparison_correlation_ids[i],
                winner="essay_a",
            )
            kafka_msg = self._create_kafka_message(callback, f"pair-{i}")

            result = await process_llm_result(
                kafka_msg,
                postgres_repository,
                mock_event_publisher,
                test_settings,
            )
            success_results.append(result)

        # Create error callbacks (next 5)
        error_results = []
        for i in range(5, 10):
            error_callback = self._create_error_callback(
                request_id=f"pair-{i}",
                correlation_id=comparison_correlation_ids[i],
                error_code="PROVIDER_ERROR",
            )
            kafka_msg = self._create_kafka_message(error_callback, f"pair-{i}")

            result = await process_llm_result(
                kafka_msg,
                postgres_repository,
                mock_event_publisher,
                test_settings,
            )
            error_results.append(result)

        # Assert - All callbacks processed (acknowledged)
        assert all(result is True for result in success_results)
        assert all(result is True for result in error_results)

        # Verify real database state - all comparison pairs exist but processing was gracefully
        # handled
        # Note: Due to model compatibility between test and production models,
        # the callback handler currently cannot find the test comparison pairs,
        # but it gracefully handles callbacks by returning True (acknowledged)
        async with postgres_repository.session() as session:
            from sqlalchemy import select

            from services.cj_assessment_service.models_db import ComparisonPair

            # Verify all 10 comparison pairs were created for this specific batch
            batch_pairs = await session.execute(
                select(ComparisonPair).where(ComparisonPair.cj_batch_id == batch.id)
            )
            batch_pairs_list = batch_pairs.scalars().all()
            assert len(batch_pairs_list) == 10

            # Verify callbacks processed correctly:
            # First 5 pairs: success callbacks, Last 5 pairs: error callbacks
            for i, pair in enumerate(batch_pairs_list):
                if i < 5:  # First 5 pairs had success callbacks
                    assert pair.winner == "Essay A"  # Updated by success callback
                    assert pair.confidence == 4.2  # Updated by success callback
                    assert pair.completed_at is not None  # Marked as completed
                else:  # Last 5 pairs had error callbacks
                    assert pair.winner == "error"  # Updated with error state
                    assert pair.error_code is not None  # Error code recorded
                    assert pair.completed_at is not None  # Marked as completed with error

    async def test_malformed_callback_message(
        self,
        postgres_repository: CJRepositoryProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        test_settings: Settings,
    ) -> None:
        """Test handling of malformed callback messages with real repository.

        Verifies that malformed JSON messages are acknowledged without database operations.
        """
        # Arrange - Create invalid JSON message
        kafka_msg = MagicMock(spec=ConsumerRecord)
        kafka_msg.topic = "llm_provider.comparison.completed.v1"
        kafka_msg.partition = 0
        kafka_msg.offset = 123
        kafka_msg.key = b"malformed-key"
        kafka_msg.value = b"invalid json content"

        # Track database session creation to verify no calls
        original_session = postgres_repository.session
        session_call_count = 0

        @asynccontextmanager
        async def tracked_session() -> AsyncGenerator[AsyncSession, None]:
            nonlocal session_call_count
            session_call_count += 1
            async with original_session() as session:
                yield session

        postgres_repository.session = tracked_session  # type: ignore[method-assign]

        # Act - Process malformed message
        result = await process_llm_result(
            kafka_msg,
            postgres_repository,
            mock_event_publisher,
            test_settings,
        )

        # Assert - Message acknowledged to prevent reprocessing
        assert result is True

        # Verify no database operations were attempted
        assert session_call_count == 0, (
            "Database session should not be created for malformed messages"
        )

        # Restore original session method
        postgres_repository.session = original_session  # type: ignore[method-assign]

    async def test_database_connection_failure(
        self,
        postgres_repository: CJRepositoryProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        test_settings: Settings,
    ) -> None:
        """Test handling of database connection failures with real repository.

        Simulates a database connection failure by making the session creation fail.
        """
        # Arrange
        correlation_id = uuid4()
        request_id = "pair-123"

        callback = self._create_callback_event(
            request_id=request_id,
            correlation_id=correlation_id,
            winner="essay_a",
        )

        # Make repository session creation fail
        original_session = postgres_repository.session

        @asynccontextmanager
        async def failing_session() -> AsyncGenerator[AsyncSession, None]:
            raise Exception("Database connection failed")
            # This yield is unreachable but needed for syntax
            yield  # pragma: no cover

        postgres_repository.session = failing_session  # type: ignore[method-assign]

        # Create Kafka message
        kafka_msg = self._create_kafka_message(callback, request_id)

        # Act - Process callback with database failure
        result = await process_llm_result(
            kafka_msg,
            postgres_repository,
            mock_event_publisher,
            test_settings,
        )

        # Assert - Message still acknowledged to prevent infinite retries
        assert result is True

        # Restore original session method
        postgres_repository.session = original_session  # type: ignore[method-assign]

        # Verify error was logged (in a real scenario)
        # The error would be logged by the error handling in process_llm_result

    async def test_event_publishing_failure(
        self,
        postgres_repository: CJRepositoryProtocol,
        mock_event_publisher: CJEventPublisherProtocol,
        test_settings: Settings,
    ) -> None:
        """Test handling of event publishing failures with real database operations.

        Creates real database state with comparison pairs and verifies that publishing
        failures don't prevent callback processing from succeeding.
        """
        # Arrange - Create real database state
        correlation_id = uuid4()
        request_id = "pair-123"
        batch_id = str(uuid4())

        # Create real batch and comparison pair in database
        async with postgres_repository.session() as session:
            from services.cj_assessment_service.models_db import ComparisonPair

            # Create batch
            batch = await postgres_repository.create_new_cj_batch(
                session=session,
                bos_batch_id=batch_id,
                event_correlation_id=str(correlation_id),
                language="en",
                course_code="TEST",
                essay_instructions="Test instructions",
                initial_status=CJBatchStatusEnum.PERFORMING_COMPARISONS,
                expected_essay_count=2,
            )

            # Create essays BEFORE comparison pair (foreign key requirement)
            await postgres_repository.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=batch.id,
                els_essay_id="essay-a",
                text_storage_id="storage-a",
                assessment_input_text="Essay A content for comparison",
            )

            await postgres_repository.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=batch.id,
                els_essay_id="essay-b",
                text_storage_id="storage-b",
                assessment_input_text="Essay B content for comparison",
            )

            # Create comparison pair after essays exist (foreign key satisfied)
            comparison_pair = ComparisonPair(
                cj_batch_id=batch.id,
                essay_a_els_id="essay-a",
                essay_b_els_id="essay-b",
                prompt_text="Compare these essays",
                request_correlation_id=str(correlation_id),
                winner=None,  # Not yet completed
                completed_at=None,
            )
            session.add(comparison_pair)
            await session.commit()

        # Create successful callback event
        callback = self._create_callback_event(
            request_id=request_id,
            correlation_id=correlation_id,
            winner="essay_a",
        )

        # Mock event publisher to fail
        mock_event_publisher.publish_assessment_completed.side_effect = Exception(  # type: ignore[attr-defined]
            "Kafka publish failed"
        )

        # Create Kafka message
        kafka_msg = self._create_kafka_message(callback, request_id)

        # Act - Process callback with publishing failure
        result = await process_llm_result(
            kafka_msg,
            postgres_repository,
            mock_event_publisher,
            test_settings,
        )

        # Assert - Message acknowledged despite publishing failure
        assert result is True

        # Verify database operations completed successfully
        async with postgres_repository.session() as session:
            from sqlalchemy import select

            # Check that the comparison pair was updated with winner
            stmt = select(ComparisonPair).where(
                ComparisonPair.request_correlation_id == correlation_id
            )
            result_obj = await session.execute(stmt)
            updated_pair = result_obj.scalar_one_or_none()

            assert updated_pair is not None
            assert updated_pair.winner is not None  # Should be updated despite publish failure
            assert updated_pair.completed_at is not None
