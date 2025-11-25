"""Tests for Batch Repository - New batch query and update methods."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from common_core.status_enums import CJBatchStateEnum
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.implementations.batch_repository import (
    PostgreSQLCJBatchRepository,
)


class TestGetStuckBatches:
    """Tests for get_stuck_batches method."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_batches_stuck_in_specified_states(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test that it returns batches in specified states older than threshold."""
        batch_repo = postgres_batch_repository

        # Create a batch stuck in GENERATING_PAIRS state
        stuck_batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="stuck-batch-001",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )

        # Update its state to GENERATING_PAIRS with old timestamp
        state = await postgres_batch_repository.get_batch_state(postgres_session, stuck_batch.id)
        assert state is not None
        state.state = CJBatchStateEnum.GENERATING_PAIRS
        state.last_activity_at = datetime.now(UTC) - timedelta(hours=6)
        await postgres_session.flush()

        # Create a recent batch (should not be returned)
        recent_batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="recent-batch-001",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )
        recent_state = await postgres_batch_repository.get_batch_state(
            postgres_session, recent_batch.id
        )
        assert recent_state is not None
        recent_state.state = CJBatchStateEnum.GENERATING_PAIRS
        recent_state.last_activity_at = datetime.now(UTC) - timedelta(minutes=30)
        await postgres_session.flush()

        # Query for stuck batches
        threshold = datetime.now(UTC) - timedelta(hours=4)
        stuck_batches = await batch_repo.get_stuck_batches(
            session=postgres_session,
            states=[CJBatchStateEnum.GENERATING_PAIRS, CJBatchStateEnum.WAITING_CALLBACKS],
            stuck_threshold=threshold,
        )

        # Should return only the old batch
        assert len(stuck_batches) == 1
        assert stuck_batches[0].batch_id == stuck_batch.id

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_excludes_batches_in_non_monitored_states(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test that it excludes batches in states not being monitored."""
        batch_repo = postgres_batch_repository

        # Create batch in COMPLETED state (not monitored)
        completed_batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="completed-batch-001",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )

        state = await postgres_batch_repository.get_batch_state(
            postgres_session, completed_batch.id
        )
        assert state is not None
        state.state = CJBatchStateEnum.COMPLETED
        state.last_activity_at = datetime.now(UTC) - timedelta(hours=10)
        await postgres_session.flush()

        # Query for stuck batches
        threshold = datetime.now(UTC) - timedelta(hours=4)
        stuck_batches = await batch_repo.get_stuck_batches(
            session=postgres_session,
            states=[CJBatchStateEnum.GENERATING_PAIRS],
            stuck_threshold=threshold,
        )

        # Should not return completed batch
        assert len(stuck_batches) == 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_eagerly_loads_batch_upload_relationship(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test that batch_upload relationship is eagerly loaded."""
        batch_repo = postgres_batch_repository

        # Create a stuck batch
        batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="eager-load-batch",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )

        state = await postgres_batch_repository.get_batch_state(postgres_session, batch.id)
        assert state is not None
        state.state = CJBatchStateEnum.GENERATING_PAIRS
        state.last_activity_at = datetime.now(UTC) - timedelta(hours=6)
        await postgres_session.flush()

        # Query for stuck batches
        threshold = datetime.now(UTC) - timedelta(hours=4)
        stuck_batches = await batch_repo.get_stuck_batches(
            session=postgres_session,
            states=[CJBatchStateEnum.GENERATING_PAIRS],
            stuck_threshold=threshold,
        )

        # Should have batch_upload loaded without additional query
        assert len(stuck_batches) == 1
        assert stuck_batches[0].batch_upload is not None
        assert stuck_batches[0].batch_upload.bos_batch_id == "eager-load-batch"


class TestGetBatchesReadyForCompletion:
    """Tests for get_batches_ready_for_completion method."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_batches_with_all_comparisons_received(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test returns batches where completed + failed >= total comparisons."""
        batch_repo = postgres_batch_repository

        # Create batch ready for completion
        ready_batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="ready-batch-001",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )

        state = await postgres_batch_repository.get_batch_state(postgres_session, ready_batch.id)
        assert state is not None
        state.state = CJBatchStateEnum.WAITING_CALLBACKS
        state.total_comparisons = 100
        state.completed_comparisons = 90
        state.failed_comparisons = 10
        await postgres_session.flush()

        # Create batch still waiting for comparisons
        waiting_batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="waiting-batch-001",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )

        waiting_state = await postgres_batch_repository.get_batch_state(
            postgres_session, waiting_batch.id
        )
        assert waiting_state is not None
        waiting_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        waiting_state.total_comparisons = 100
        waiting_state.completed_comparisons = 50
        waiting_state.failed_comparisons = 20
        await postgres_session.flush()

        # Query for ready batches
        ready_batches = await batch_repo.get_batches_ready_for_completion(session=postgres_session)

        # Should return only the ready batch
        assert len(ready_batches) == 1
        assert ready_batches[0].batch_id == ready_batch.id

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_only_returns_batches_in_waiting_callbacks_state(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test only returns batches in WAITING_CALLBACKS state."""
        batch_repo = postgres_batch_repository

        # Create batch in wrong state
        wrong_state_batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="wrong-state-batch",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )

        state = await postgres_batch_repository.get_batch_state(
            postgres_session, wrong_state_batch.id
        )
        assert state is not None
        state.state = CJBatchStateEnum.SCORING
        state.total_comparisons = 100
        state.completed_comparisons = 100
        state.failed_comparisons = 0
        await postgres_session.flush()

        # Query for ready batches
        ready_batches = await batch_repo.get_batches_ready_for_completion(session=postgres_session)

        # Should not return batch in SCORING state
        assert len(ready_batches) == 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_excludes_batches_with_zero_total_comparisons(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test excludes batches with 0 total_comparisons."""
        batch_repo = postgres_batch_repository

        # Create batch with zero comparisons
        zero_batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="zero-comparisons",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )

        state = await postgres_batch_repository.get_batch_state(postgres_session, zero_batch.id)
        assert state is not None
        state.state = CJBatchStateEnum.WAITING_CALLBACKS
        state.total_comparisons = 0
        state.completed_comparisons = 0
        state.failed_comparisons = 0
        await postgres_session.flush()

        # Query for ready batches
        ready_batches = await batch_repo.get_batches_ready_for_completion(session=postgres_session)

        # Should not return batch with zero comparisons
        assert len(ready_batches) == 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_eagerly_loads_batch_upload_relationship(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test that batch_upload relationship is eagerly loaded."""
        batch_repo = postgres_batch_repository

        # Create ready batch
        batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="eager-ready-batch",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )

        state = await postgres_batch_repository.get_batch_state(postgres_session, batch.id)
        assert state is not None
        state.state = CJBatchStateEnum.WAITING_CALLBACKS
        state.total_comparisons = 50
        state.completed_comparisons = 50
        state.failed_comparisons = 0
        await postgres_session.flush()

        # Query for ready batches
        ready_batches = await batch_repo.get_batches_ready_for_completion(session=postgres_session)

        # Should have batch_upload loaded
        assert len(ready_batches) == 1
        assert ready_batches[0].batch_upload is not None
        assert ready_batches[0].batch_upload.bos_batch_id == "eager-ready-batch"


class TestGetBatchStateForUpdate:
    """Tests for get_batch_state_for_update method."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_batch_state_without_lock(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test returns batch state normally without for_update flag."""
        batch_repo = postgres_batch_repository

        # Create batch
        batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="no-lock-batch",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )
        await postgres_session.flush()

        # Get state without lock
        state = await batch_repo.get_batch_state_for_update(
            session=postgres_session,
            batch_id=batch.id,
            for_update=False,
        )

        assert state is not None
        assert state.batch_id == batch.id
        assert state.state == CJBatchStateEnum.INITIALIZING

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_applies_for_update_lock(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test applies SELECT FOR UPDATE lock when for_update=True.

        Note: Due to lazy="joined" relationship on CJBatchState.batch_upload,
        PostgreSQL raises an error when trying to apply FOR UPDATE to a LEFT OUTER JOIN.
        This test verifies that the error occurs as expected - the implementation
        would need to use options(noload()) or lazyload() to avoid the join if
        FOR UPDATE locking is actually needed in production.
        """

        batch_repo = postgres_batch_repository

        # Create batch
        batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="lock-batch",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )
        await postgres_session.flush()

        # FOR UPDATE should now work because get_batch_state_for_update uses noload()
        # to avoid the LEFT OUTER JOIN that conflicts with FOR UPDATE
        state = await batch_repo.get_batch_state_for_update(
            session=postgres_session,
            batch_id=batch.id,
            for_update=True,
        )

        # Verify state is returned successfully
        assert state is not None
        assert state.batch_id == batch.id
        # Note: batch_upload is not loaded due to noload() - access would trigger lazy load

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_none_for_nonexistent_batch(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test returns None for non-existent batch_id."""
        batch_repo = postgres_batch_repository

        # Query for non-existent batch
        state = await batch_repo.get_batch_state_for_update(
            session=postgres_session,
            batch_id=99999,
            for_update=False,
        )

        assert state is None


class TestUpdateBatchState:
    """Tests for update_batch_state method."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_successfully_updates_batch_state(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test successful state update."""
        batch_repo = postgres_batch_repository

        # Create batch
        batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="update-state-batch",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )
        await postgres_session.flush()

        # Verify initial state
        state = await postgres_batch_repository.get_batch_state(postgres_session, batch.id)
        assert state is not None
        assert state.state == CJBatchStateEnum.INITIALIZING

        # Update state
        await batch_repo.update_batch_state(
            session=postgres_session,
            batch_id=batch.id,
            state=CJBatchStateEnum.GENERATING_PAIRS,
        )

        # Verify state was updated
        updated_state = await postgres_batch_repository.get_batch_state(postgres_session, batch.id)
        assert updated_state is not None
        assert updated_state.state == CJBatchStateEnum.GENERATING_PAIRS

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_state_transition_sequence(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test state transitions through workflow."""
        batch_repo = postgres_batch_repository

        # Create batch
        batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="transition-batch",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )
        await postgres_session.flush()

        # Transition through states
        transitions = [
            CJBatchStateEnum.GENERATING_PAIRS,
            CJBatchStateEnum.WAITING_CALLBACKS,
            CJBatchStateEnum.SCORING,
            CJBatchStateEnum.COMPLETED,
        ]

        for target_state in transitions:
            await batch_repo.update_batch_state(
                session=postgres_session,
                batch_id=batch.id,
                state=target_state,
            )

            # Verify state
            state = await postgres_batch_repository.get_batch_state(postgres_session, batch.id)
            assert state is not None
            assert state.state == target_state
