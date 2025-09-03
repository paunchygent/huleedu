"""
Database-backed slot assignment operations using PostgreSQL transactions.

Implements atomic slot selection with FOR UPDATE SKIP LOCKED and idempotency
enforcement via partial unique indexes, replacing Redis-based assignment.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.exc import IntegrityError
import asyncio
from services.essay_lifecycle_service.config import settings

from services.essay_lifecycle_service.models_db import (
    BatchEssayTracker as BatchEssayTrackerDB,
)
from services.essay_lifecycle_service.models_db import SlotAssignmentDB

logger = create_service_logger("els.db_slot_ops")


ASSIGN_SLOT_SQL = """
WITH target_slot AS (
    SELECT id, internal_essay_id
    FROM slot_assignments
    WHERE batch_tracker_id = :tracker_id
      AND status = 'available'
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE slot_assignments
SET status = 'assigned',
    text_storage_id = :text_storage_id,
    original_file_name = :file_name,
    assigned_at = NOW()
FROM target_slot
WHERE slot_assignments.id = target_slot.id
RETURNING target_slot.internal_essay_id
"""


class DatabaseSlotOperations:
    """Direct database slot operations without Redis dependencies."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def _get_tracker_id(self, session: AsyncSession, batch_id: str) -> int | None:
        stmt = select(BatchEssayTrackerDB.id).where(BatchEssayTrackerDB.batch_id == batch_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def assign_slot_atomic(
        self, batch_id: str, content_metadata: dict[str, Any], correlation_id: UUID | None = None
    ) -> str | None:
        """
        Atomically assign the next available slot for a batch to the given content.

        Idempotent per (batch_id, text_storage_id). Returns existing essay_id if already assigned.
        """
        text_storage_id = content_metadata.get("text_storage_id")
        if not text_storage_id:
            logger.warning(
                "Missing text_storage_id in content metadata for assignment",
                extra={
                    "batch_id": batch_id,
                    "correlation_id": str(correlation_id) if correlation_id else None,
                },
            )
            return None

        file_name = content_metadata.get("original_file_name", "unknown")

        async with self._session_factory() as session:
            # Resolve tracker id
            tracker_id = await self._get_tracker_id(session, batch_id)
            if tracker_id is None:
                logger.warning("Batch tracker not found for batch", extra={"batch_id": batch_id})
                return None

            existing_stmt = (
                select(SlotAssignmentDB.internal_essay_id)
                .where(
                    SlotAssignmentDB.batch_tracker_id == tracker_id,
                    SlotAssignmentDB.text_storage_id == text_storage_id,
                )
                .limit(1)
            )
            # Fast idempotency path: if an existing assignment is already committed, return it
            existing_stmt = (
                select(SlotAssignmentDB.internal_essay_id)
                .where(
                    SlotAssignmentDB.batch_tracker_id == tracker_id,
                    SlotAssignmentDB.text_storage_id == text_storage_id,
                )
                .limit(1)
            )
            existing_res = await session.execute(existing_stmt)
            existing_essay_id: str | None = existing_res.scalar_one_or_none()
            if existing_essay_id:
                return existing_essay_id

            # Optional: serialize duplicates with transaction-scoped advisory lock
            if settings.USE_ADVISORY_LOCKS_FOR_ASSIGNMENT:
                try:
                    lock_res = await session.execute(
                        text(
                            "SELECT pg_try_advisory_xact_lock(hashtext(:b), hashtext(:t)) AS got"
                        ),
                        {"b": batch_id, "t": text_storage_id},
                    )
                    got_lock = bool(lock_res.scalar_one())
                except Exception:
                    got_lock = False

                if not got_lock:
                    # Another tx is handling this content; wait briefly for winner and return idempotently
                    retry_delays = [0.005, 0.01, 0.02, 0.04, 0.08]
                    last_seen: str | None = None
                    for delay in retry_delays:
                        existing_res = await session.execute(existing_stmt)
                        last_seen = existing_res.scalar_one_or_none()
                        if last_seen:
                            return last_seen
                        await asyncio.sleep(delay)

                    existing_res = await session.execute(existing_stmt)
                    last_seen = existing_res.scalar_one_or_none()
                    if last_seen:
                        return last_seen

                    # If still nothing, proceed without lock fallback

            # Atomic selection + update. Handle unique race idempotently.
            try:
                result = await session.execute(
                    text(ASSIGN_SLOT_SQL),
                    {
                        "tracker_id": tracker_id,
                        "text_storage_id": text_storage_id,
                        "file_name": file_name,
                    },
                )
                essay_id_row = result.fetchone()
                assigned_essay_id: str | None = essay_id_row[0] if essay_id_row else None

                # Commit only if we changed something
                if assigned_essay_id:
                    await session.commit()
                    logger.info(
                        "Assigned content to slot",
                        extra={
                            "batch_id": batch_id,
                            "text_storage_id": text_storage_id,
                            "internal_essay_id": assigned_essay_id,
                        },
                    )
                    return assigned_essay_id
                else:
                    # No row updated (all slots locked/assigned). Try idempotent read of existing assignment.
                    await session.rollback()

                    retry_delays = [0.005, 0.01, 0.02, 0.04, 0.08]
                    last_seen = None
                    for delay in retry_delays:
                        existing_res = await session.execute(existing_stmt)
                        last_seen = existing_res.scalar_one_or_none()
                        if last_seen:
                            return last_seen
                        await asyncio.sleep(delay)

                    existing_res = await session.execute(existing_stmt)
                    last_seen = existing_res.scalar_one_or_none()
                    if last_seen:
                        return last_seen

                    # Truly no slots and no existing assignment
                    return None

            except IntegrityError as exc:
                # Unique constraint on (batch_tracker_id, text_storage_id) was violated.
                # Another concurrent transaction assigned this content. Treat as idempotent success.
                await session.rollback()

                # Retry reading the now-existing assignment (winner may not have committed yet).
                retry_delays = [0.005, 0.01, 0.02, 0.04, 0.08]
                last_seen = None
                for delay in retry_delays:
                    existing_res = await session.execute(existing_stmt)
                    last_seen = existing_res.scalar_one_or_none()
                    if last_seen:
                        return last_seen
                    await asyncio.sleep(delay)

                # Final attempt after backoff window
                existing_res = await session.execute(existing_stmt)
                last_seen = existing_res.scalar_one_or_none()
                if last_seen:
                    return last_seen

                # As a last resort, re-raise to surface unexpected errors
                raise

    async def get_available_slot_count(self, batch_id: str) -> int:
        async with self._session_factory() as session:
            tracker_id = await self._get_tracker_id(session, batch_id)
            if tracker_id is None:
                return 0
            stmt = (
                select(text("count(1)"))
                .select_from(SlotAssignmentDB)
                .where(
                    SlotAssignmentDB.batch_tracker_id == tracker_id,
                    SlotAssignmentDB.status == "available",
                )
            )
            res = await session.execute(stmt)
            count_val: int = int(res.scalar_one() or 0)
            return count_val

    async def get_assigned_count(self, batch_id: str) -> int:
        async with self._session_factory() as session:
            tracker_id = await self._get_tracker_id(session, batch_id)
            if tracker_id is None:
                return 0
            stmt = (
                select(text("count(1)"))
                .select_from(SlotAssignmentDB)
                .where(
                    SlotAssignmentDB.batch_tracker_id == tracker_id,
                    SlotAssignmentDB.status == "assigned",
                )
            )
            res = await session.execute(stmt)
            count_val: int = int(res.scalar_one() or 0)
            return count_val

    async def get_essay_id_for_content(self, batch_id: str, text_storage_id: str) -> str | None:
        async with self._session_factory() as session:
            tracker_id = await self._get_tracker_id(session, batch_id)
            if tracker_id is None:
                return None
            stmt = (
                select(SlotAssignmentDB.internal_essay_id)
                .where(
                    SlotAssignmentDB.batch_tracker_id == tracker_id,
                    SlotAssignmentDB.text_storage_id == text_storage_id,
                )
                .limit(1)
            )
            res = await session.execute(stmt)
            essay_id: str | None = res.scalar_one_or_none()
            return essay_id
