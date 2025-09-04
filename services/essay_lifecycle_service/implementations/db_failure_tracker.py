"""
Database-backed validation failure tracking for batch coordination.

Stores validation failures and reduces available slot inventory by marking
slots as 'failed' to maintain correct completion semantics.
"""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.essay_lifecycle_service.models_db import (
    BatchEssayTracker as BatchEssayTrackerDB,
)

logger = create_service_logger("els.db_failure_tracker")


class DBFailureTracker:
    """DB-backed failure tracker with slot inventory adjustment."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def _get_tracker_id(self, session: AsyncSession, batch_id: str) -> int | None:
        stmt = select(BatchEssayTrackerDB.id).where(BatchEssayTrackerDB.batch_id == batch_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def track_validation_failure(self, batch_id: str, failure: dict[str, Any]) -> None:
        """Persist failure and consume one available slot by marking it as failed."""
        async with self._session_factory() as session:
            tracker_id = await self._get_tracker_id(session, batch_id)

            # Insert failure row
            await session.execute(
                text(
                    """
                    INSERT INTO batch_validation_failures (
                        batch_id, batch_tracker_id, file_upload_id, validation_error_code, validation_error_detail
                    ) VALUES (:batch_id, :tracker_id, :file_upload_id, :code, :detail::jsonb)
                    """
                ),
                {
                    "batch_id": batch_id,
                    "tracker_id": tracker_id,
                    "file_upload_id": failure.get("file_upload_id"),
                    "code": failure.get("validation_error_code"),
                    "detail": failure.get("validation_error_detail"),
                },
            )

            # If tracker exists, mark one slot as failed to reduce availability
            if tracker_id is not None:
                await session.execute(
                    text(
                        """
                        WITH target_slot AS (
                            SELECT id
                            FROM slot_assignments
                            WHERE batch_tracker_id = :tracker_id AND status = 'available'
                            ORDER BY internal_essay_id
                            LIMIT 1
                            FOR UPDATE SKIP LOCKED
                        )
                        UPDATE slot_assignments
                        SET status = 'failed'
                        FROM target_slot
                        WHERE slot_assignments.id = target_slot.id
                        """
                    ),
                    {"tracker_id": tracker_id},
                )

            await session.commit()

    async def get_validation_failure_count(self, batch_id: str) -> int:
        async with self._session_factory() as session:
            stmt = text("SELECT COUNT(1) FROM batch_validation_failures WHERE batch_id = :batch_id")
            res = await session.execute(stmt, {"batch_id": batch_id})
            count_val = int(res.scalar_one() or 0)
            return count_val

    async def get_validation_failures(self, batch_id: str) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            stmt = text(
                """
                SELECT file_upload_id, validation_error_code, validation_error_detail, created_at
                FROM batch_validation_failures WHERE batch_id = :batch_id ORDER BY created_at
                """
            )
            rows = (await session.execute(stmt, {"batch_id": batch_id})).all()
            return [
                {
                    "file_upload_id": row[0],
                    "validation_error_code": row[1],
                    "validation_error_detail": row[2],
                    "created_at": row[3].isoformat() if row[3] else None,
                }
                for row in rows
            ]
