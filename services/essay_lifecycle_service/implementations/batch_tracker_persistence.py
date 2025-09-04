"""
Database persistence operations for BatchEssayTracker.

Extracted from DefaultBatchEssayTracker to maintain <400 LoC limit.
Handles all database operations for batch expectations and slot assignments.
"""

from __future__ import annotations

from uuid import UUID

from common_core.domain_enums import CourseCode
from common_core.status_enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from services.essay_lifecycle_service.implementations.batch_expectation import BatchExpectation
from services.essay_lifecycle_service.metrics import get_metrics
from services.essay_lifecycle_service.models_db import (
    BatchEssayTracker as BatchEssayTrackerDB,
)
from services.essay_lifecycle_service.models_db import (
    EssayStateDB,
    SlotAssignmentDB,
)


class BatchTrackerPersistence:
    """Handles database persistence operations for batch expectations."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._logger = create_service_logger("batch_tracker_persistence")
        self._engine = engine
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def get_batch_from_database(self, batch_id: str) -> BatchEssayTrackerDB | None:
        """Retrieve batch expectation from database for idempotency checking."""
        try:
            async with self._session_factory() as session:
                stmt = select(BatchEssayTrackerDB).where(BatchEssayTrackerDB.batch_id == batch_id)
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
        except Exception as e:
            self._logger.error(f"Failed to query batch from database {batch_id}: {e}")
            return None

    async def get_tracker_by_batch_id(self, batch_id: str) -> BatchEssayTrackerDB | None:
        """Fetch full tracker row by external batch_id."""
        try:
            async with self._session_factory() as session:
                stmt = select(BatchEssayTrackerDB).where(BatchEssayTrackerDB.batch_id == batch_id)
                res = await session.execute(stmt)
                return res.scalar_one_or_none()
        except Exception as e:
            self._logger.error(f"Failed to fetch tracker by batch_id {batch_id}: {e}")
            return None

    async def get_status_counts(self, batch_id: str) -> tuple[int, int, int] | None:
        """
        Return (assigned_count, available_count, expected_count) for a batch.
        """
        try:
            async with self._session_factory() as session:
                tracker_stmt = select(BatchEssayTrackerDB).where(
                    BatchEssayTrackerDB.batch_id == batch_id
                )
                tracker_res = await session.execute(tracker_stmt)
                tracker = tracker_res.scalar_one_or_none()
                if tracker is None:
                    return None

                assigned_stmt = select(func.count(EssayStateDB.essay_id)).where(
                    EssayStateDB.batch_id == batch_id,
                    EssayStateDB.current_status == EssayStatus.READY_FOR_PROCESSING,
                )
                available_stmt = select(func.count(EssayStateDB.essay_id)).where(
                    EssayStateDB.batch_id == batch_id,
                    EssayStateDB.current_status == EssayStatus.UPLOADED,
                )
                assigned_count = (await session.execute(assigned_stmt)).scalar() or 0
                available_count = (await session.execute(available_stmt)).scalar() or 0
                expected_count = tracker.expected_count
                return assigned_count, available_count, expected_count
        except Exception as e:
            self._logger.error(f"Failed to get status counts for {batch_id}: {e}")
            return None

    async def get_assigned_essays(self, batch_id: str) -> list[dict[str, str | None]]:
        """Return list of {internal_essay_id, text_storage_id} for assigned rows."""
        try:
            async with self._session_factory() as session:
                tracker_stmt = select(BatchEssayTrackerDB).where(
                    BatchEssayTrackerDB.batch_id == batch_id
                )
                tracker_res = await session.execute(tracker_stmt)
                tracker = tracker_res.scalar_one_or_none()
                if tracker is None:
                    return []

                rows = (
                    await session.execute(
                        select(EssayStateDB.essay_id, EssayStateDB.text_storage_id).where(
                            EssayStateDB.batch_id == batch_id,
                            EssayStateDB.current_status == EssayStatus.READY_FOR_PROCESSING,
                        )
                    )
                ).all()
                return [{"internal_essay_id": row[0], "text_storage_id": row[1]} for row in rows]
        except Exception as e:
            self._logger.error(f"Failed to get assigned essays for {batch_id}: {e}")
            return []

    async def get_missing_slot_ids(self, batch_id: str) -> list[str]:
        """Return list of expected essay IDs that are not yet assigned."""
        try:
            async with self._session_factory() as session:
                tracker_stmt = select(BatchEssayTrackerDB).where(
                    BatchEssayTrackerDB.batch_id == batch_id
                )
                tracker_res = await session.execute(tracker_stmt)
                tracker = tracker_res.scalar_one_or_none()
                if tracker is None:
                    return []

                assigned_ids_stmt = select(EssayStateDB.essay_id).where(
                    EssayStateDB.batch_id == batch_id,
                    EssayStateDB.current_status == EssayStatus.READY_FOR_PROCESSING,
                )
                assigned_ids = {row[0] for row in (await session.execute(assigned_ids_stmt)).all()}
                expected_ids = set(tracker.expected_essay_ids)
                return sorted(expected_ids - assigned_ids)
        except Exception as e:
            self._logger.error(f"Failed to get missing slots for {batch_id}: {e}")
            return []

    async def get_user_id_for_essay(self, internal_essay_id: str) -> str | None:
        """Resolve user_id for a given essay via essay_states → batch tracker.

        Option B path: join essay_states to batch_essay_trackers by batch_id.
        """
        try:
            async with self._session_factory() as session:
                tracker_join_stmt = (
                    select(BatchEssayTrackerDB.user_id)
                    .join(
                        EssayStateDB,
                        EssayStateDB.batch_id == BatchEssayTrackerDB.batch_id,
                    )
                    .where(EssayStateDB.essay_id == internal_essay_id)
                    .limit(1)
                )
                res = await session.execute(tracker_join_stmt)
                return res.scalar_one_or_none()
        except Exception as e:
            self._logger.error(f"Failed to resolve user_id for essay {internal_essay_id}: {e}")
            return None

    async def list_active_batch_ids(self) -> list[str]:
        """Return list of active batch IDs (basic implementation)."""
        try:
            async with self._session_factory() as session:
                stmt = select(BatchEssayTrackerDB.batch_id)
                rows = (await session.execute(stmt)).scalars().all()
                return list(rows)
        except Exception as e:
            self._logger.error(f"Failed to list active batch ids: {e}")
            return []

    async def persist_batch_expectation(self, expectation: BatchExpectation) -> None:
        """Persist batch expectation to database (dual-write pattern)."""
        try:
            async with self._session_factory() as session:
                # Create database record
                tracker_db = BatchEssayTrackerDB(
                    batch_id=expectation.batch_id,
                    expected_essay_ids=list(expectation.expected_essay_ids),
                    available_slots=list(
                        expectation.expected_essay_ids
                    ),  # Initialize with all slots available
                    expected_count=expectation.expected_count,
                    course_code=expectation.course_code.value,
                    essay_instructions=expectation.essay_instructions,
                    user_id=expectation.user_id,
                    org_id=expectation.org_id,
                    correlation_id=str(expectation.correlation_id),
                    timeout_seconds=expectation.timeout_seconds,
                )

                session.add(tracker_db)
                await session.flush()

                # Pre-seed inventory rows for each expected essay slot
                for essay_id in expectation.expected_essay_ids:
                    session.add(
                        SlotAssignmentDB(
                            batch_tracker_id=tracker_db.id,
                            internal_essay_id=essay_id,
                            status="available",
                        )
                    )

                await session.commit()
                # Refresh gauges: a new active batch has been added
                await self.refresh_batch_metrics()

                self._logger.debug(f"Persisted batch expectation: {expectation.batch_id}")

        except Exception as e:
            self._logger.error(f"Failed to persist batch expectation {expectation.batch_id}: {e}")
            # Don't fail the operation if database persistence fails

    async def persist_slot_assignment(
        self,
        batch_id: str,
        internal_essay_id: str,
        text_storage_id: str,
        original_file_name: str,
        session: AsyncSession | None = None,
    ) -> None:
        """Persist slot assignment to database."""
        try:

            async def _do_persist(db_session: AsyncSession) -> None:
                # Get batch tracker record
                stmt = select(BatchEssayTrackerDB).where(BatchEssayTrackerDB.batch_id == batch_id)
                result = await db_session.execute(stmt)
                tracker_db = result.scalar_one_or_none()

                if not tracker_db:
                    self._logger.warning(f"Batch tracker not found for slot assignment: {batch_id}")
                    return

                # Update existing inventory row for this slot
                slot_stmt = (
                    select(SlotAssignmentDB)
                    .where(
                        SlotAssignmentDB.batch_tracker_id == tracker_db.id,
                        SlotAssignmentDB.internal_essay_id == internal_essay_id,
                    )
                    .limit(1)
                )
                slot_res = await db_session.execute(slot_stmt)
                slot_db = slot_res.scalar_one_or_none()

                if slot_db is None:
                    # Fallback: create if missing (should not happen after pre-seed)
                    slot_db = SlotAssignmentDB(
                        batch_tracker_id=tracker_db.id,
                        internal_essay_id=internal_essay_id,
                    )
                    db_session.add(slot_db)

                slot_db.status = "assigned"
                slot_db.text_storage_id = text_storage_id
                slot_db.original_file_name = original_file_name

            # Use provided session or create a new one
            if session is not None:
                await _do_persist(session)
                # Don't commit when using provided session - let the outer transaction handle it
            else:
                async with self._session_factory() as new_session:
                    await _do_persist(new_session)
                    await new_session.commit()

                self._logger.debug(
                    f"Persisted slot assignment: {internal_essay_id} -> {text_storage_id}"
                )

        except Exception as e:
            self._logger.error(f"Failed to persist slot assignment {internal_essay_id}: {e}")

    async def remove_batch_from_database(self, batch_id: str) -> None:
        """Remove completed batch from database (cascades to slot assignments)."""
        try:
            async with self._session_factory() as session:
                stmt = delete(BatchEssayTrackerDB).where(BatchEssayTrackerDB.batch_id == batch_id)
                await session.execute(stmt)
                await session.commit()

                self._logger.debug(f"Removed completed batch from database: {batch_id}")

        except Exception as e:
            self._logger.error(f"Failed to remove batch from database {batch_id}: {e}")

    async def mark_batch_completed(
        self, batch_id: str, session: AsyncSession | None = None
    ) -> None:
        """Mark a batch as completed by setting completed_at timestamp."""
        from datetime import UTC, datetime

        async def _do_mark(db_session: AsyncSession) -> None:
            # Use explicit UPDATE statement to ensure change is tracked
            from sqlalchemy import update

            update_stmt = (
                update(BatchEssayTrackerDB)
                .where(BatchEssayTrackerDB.batch_id == batch_id)
                .values(completed_at=datetime.now(UTC))
            )
            await db_session.execute(update_stmt)

        try:
            if session is not None:
                await _do_mark(session)
            else:
                async with self._session_factory() as new_session:
                    await _do_mark(new_session)
                    await new_session.commit()
            # Refresh gauges after completion
            await self.refresh_batch_metrics()
        except Exception as e:
            self._logger.error(f"Failed to mark batch completed {batch_id}: {e}")

    async def refresh_batch_metrics(self) -> None:
        """Recompute and publish batch inventory gauges (active/completed, guest/regular)."""
        metrics = get_metrics()
        batches_active = metrics.get("batches_active")
        batches_completed = metrics.get("batches_completed")
        if batches_active is None or batches_completed is None:
            return

        async with self._session_factory() as session:
            # Active counts
            active_guest_count = await session.execute(
                select(func.count())
                .select_from(BatchEssayTrackerDB)
                .where(
                    BatchEssayTrackerDB.completed_at.is_(None),
                    BatchEssayTrackerDB.org_id.is_(None),
                )
            )
            active_regular_count = await session.execute(
                select(func.count())
                .select_from(BatchEssayTrackerDB)
                .where(
                    BatchEssayTrackerDB.completed_at.is_(None),
                    BatchEssayTrackerDB.org_id.is_not(None),
                )
            )
            # Completed counts
            completed_guest_count = await session.execute(
                select(func.count())
                .select_from(BatchEssayTrackerDB)
                .where(
                    BatchEssayTrackerDB.completed_at.is_not(None),
                    BatchEssayTrackerDB.org_id.is_(None),
                )
            )
            completed_regular_count = await session.execute(
                select(func.count())
                .select_from(BatchEssayTrackerDB)
                .where(
                    BatchEssayTrackerDB.completed_at.is_not(None),
                    BatchEssayTrackerDB.org_id.is_not(None),
                )
            )

            ag = active_guest_count.scalar()
            ar = active_regular_count.scalar()
            cg = completed_guest_count.scalar()
            cr = completed_regular_count.scalar()

            batches_active.labels(class_type="GUEST").set(ag)
            batches_active.labels(class_type="REGULAR").set(ar)
            batches_completed.labels(class_type="GUEST").set(cg)
            batches_completed.labels(class_type="REGULAR").set(cr)

    async def initialize_from_database(self) -> list[BatchExpectation]:
        """Load active batch expectations from database (recovery mechanism)."""
        try:
            async with self._session_factory() as session:
                # Load active batch expectations from database
                stmt = select(BatchEssayTrackerDB).options(
                    selectinload(BatchEssayTrackerDB.slot_assignments)
                )
                result = await session.execute(stmt)
                batch_trackers = result.scalars().all()

                expectations = []
                for tracker_db in batch_trackers:
                    # Convert database model to memory model
                    expectation = self.expectation_from_db(tracker_db)
                    expectations.append(expectation)

                self._logger.info(f"Loaded {len(expectations)} active batches from database")
                return expectations

        except Exception as e:
            self._logger.error(f"Failed to initialize from database: {e}")
            return []

    def expectation_from_db(self, tracker_db: BatchEssayTrackerDB) -> BatchExpectation:
        """Convert database model to memory BatchExpectation."""
        # Create expectation
        expectation = BatchExpectation(
            batch_id=tracker_db.batch_id,
            expected_essay_ids=frozenset(
                tracker_db.expected_essay_ids
            ),  # Convert list to immutable frozenset
            expected_count=tracker_db.expected_count,  # Fixed: Added missing required field
            course_code=CourseCode(tracker_db.course_code),
            essay_instructions=tracker_db.essay_instructions,
            user_id=tracker_db.user_id,
            org_id=tracker_db.org_id if hasattr(tracker_db, "org_id") else None,
            correlation_id=UUID(tracker_db.correlation_id),
            created_at=tracker_db.created_at,  # Fixed: Added missing required field
            timeout_seconds=tracker_db.timeout_seconds,
        )

        # Note: Slot assignments are now tracked in Redis coordinator, not in memory
        # The database slot assignments are used for persistence only

        return expectation
