"""Batch aggregate repository implementation for CJ Assessment Service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from common_core.status_enums import CJBatchStateEnum
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload, selectinload

from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import CJBatchState, CJBatchUpload
from services.cj_assessment_service.protocols import CJBatchRepositoryProtocol

logger = create_service_logger("cj_assessment_service.repositories.batch")


class PostgreSQLCJBatchRepository(CJBatchRepositoryProtocol):
    """PostgreSQL implementation for batch and batch-state persistence."""

    async def create_new_cj_batch(
        self,
        session: AsyncSession,
        bos_batch_id: str,
        event_correlation_id: str,
        language: str,
        course_code: str,
        initial_status: CJBatchStatusEnum,
        expected_essay_count: int,
        user_id: str | None = None,
        org_id: str | None = None,
    ) -> CJBatchUpload:
        """Create a new CJ batch and its initial state record."""
        cj_batch = CJBatchUpload(
            bos_batch_id=bos_batch_id,
            event_correlation_id=event_correlation_id,
            language=language,
            course_code=course_code,
            status=initial_status,
            expected_essay_count=expected_essay_count,
            processing_metadata={},
            user_id=user_id,
            org_id=org_id,
        )
        session.add(cj_batch)
        await session.flush()

        batch_state = CJBatchState(
            batch_id=cj_batch.id,
            state=CJBatchStateEnum.INITIALIZING,
            total_budget=None,
            total_comparisons=0,
            submitted_comparisons=0,
            completed_comparisons=0,
            failed_comparisons=0,
            partial_scoring_triggered=False,
            completion_threshold_pct=95,
            current_iteration=0,
            last_activity_at=datetime.now(UTC),
        )
        session.add(batch_state)
        await session.flush()

        logger.debug(
            "Created CJ batch and initial state",
            extra={"cj_batch_id": cj_batch.id, "bos_batch_id": bos_batch_id},
        )
        return cj_batch

    async def get_cj_batch_upload(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> CJBatchUpload | None:
        """Fetch CJ batch upload by identifier."""
        return await session.get(CJBatchUpload, cj_batch_id)

    async def get_batch_state(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> CJBatchState | None:
        """Fetch batch state by batch identifier."""
        stmt = select(CJBatchState).where(CJBatchState.batch_id == batch_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_cj_batch_status(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        status: Any,
    ) -> None:
        """Update CJ batch status."""
        stmt = update(CJBatchUpload).where(CJBatchUpload.id == cj_batch_id).values(status=status)
        await session.execute(stmt)
        await session.flush()

    async def get_stuck_batches(
        self,
        session: AsyncSession,
        states: list[CJBatchStateEnum],
        stuck_threshold: datetime,
    ) -> list[CJBatchState]:
        """Get batches stuck in specified states past the threshold time.

        Args:
            session: Database session
            states: List of batch states to check for stuck batches
            stuck_threshold: Datetime threshold - batches inactive before this are considered stuck

        Returns:
            List of CJBatchState records that are stuck
        """
        stmt = (
            select(CJBatchState)
            .where(
                and_(
                    CJBatchState.state.in_(states),
                    CJBatchState.last_activity_at < stuck_threshold,
                )
            )
            .options(selectinload(CJBatchState.batch_upload))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_batches_ready_for_completion(
        self,
        session: AsyncSession,
    ) -> list[CJBatchState]:
        """Get batches in WAITING_CALLBACKS state with all comparisons received.

        Returns:
            List of CJBatchState records ready for completion
        """
        stmt = (
            select(CJBatchState)
            .options(selectinload(CJBatchState.batch_upload))
            .where(
                CJBatchState.state == CJBatchStateEnum.WAITING_CALLBACKS,
                CJBatchState.total_comparisons > 0,
                (CJBatchState.completed_comparisons + CJBatchState.failed_comparisons)
                >= CJBatchState.total_comparisons,
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_batch_state_for_update(
        self,
        session: AsyncSession,
        batch_id: int,
        for_update: bool = False,
    ) -> CJBatchState | None:
        """Get batch state with optional FOR UPDATE lock.

        Args:
            session: Database session
            batch_id: Batch identifier
            for_update: If True, applies SELECT FOR UPDATE lock

        Returns:
            CJBatchState record or None if not found

        Note:
            When for_update=True, the batch_upload relationship is not loaded
            because PostgreSQL forbids FOR UPDATE on nullable (LEFT OUTER) joins.
            Access batch_upload via separate query or lazy load if needed.
        """
        stmt = select(CJBatchState).where(CJBatchState.batch_id == batch_id)
        if for_update:
            # Disable eager loading to avoid LEFT OUTER JOIN which is
            # incompatible with FOR UPDATE in PostgreSQL
            stmt = stmt.options(noload(CJBatchState.batch_upload)).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_batch_state(
        self,
        session: AsyncSession,
        batch_id: int,
        state: CJBatchStateEnum,
    ) -> None:
        """Update batch state enum value.

        Args:
            session: Database session
            batch_id: Batch identifier
            state: New state value
        """
        stmt = update(CJBatchState).where(CJBatchState.batch_id == batch_id).values(state=state)
        await session.execute(stmt)
        await session.flush()
