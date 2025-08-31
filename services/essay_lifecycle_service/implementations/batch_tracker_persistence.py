"""
Database persistence operations for BatchEssayTracker.

Extracted from DefaultBatchEssayTracker to maintain <400 LoC limit.
Handles all database operations for batch expectations and slot assignments.
"""

from __future__ import annotations

from uuid import UUID

from common_core.domain_enums import CourseCode
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from services.essay_lifecycle_service.implementations.batch_expectation import BatchExpectation
from services.essay_lifecycle_service.models_db import (
    BatchEssayTracker as BatchEssayTrackerDB,
)
from services.essay_lifecycle_service.models_db import (
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
                    correlation_id=str(expectation.correlation_id),
                    timeout_seconds=expectation.timeout_seconds,
                )

                session.add(tracker_db)
                await session.commit()

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

                # Create slot assignment record
                slot_db = SlotAssignmentDB(
                    batch_tracker_id=tracker_db.id,
                    internal_essay_id=internal_essay_id,
                    text_storage_id=text_storage_id,
                    original_file_name=original_file_name,
                )

                db_session.add(slot_db)

                # Update available slots (assigned count now tracked in Redis)
                tracker_db.available_slots = [
                    slot for slot in tracker_db.available_slots if slot != internal_essay_id
                ]

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
            org_id=tracker_db.org_id if hasattr(tracker_db, 'org_id') else None,
            correlation_id=UUID(tracker_db.correlation_id),
            created_at=tracker_db.created_at,  # Fixed: Added missing required field
            timeout_seconds=tracker_db.timeout_seconds,
        )

        # Note: Slot assignments are now tracked in Redis coordinator, not in memory
        # The database slot assignments are used for persistence only

        return expectation
