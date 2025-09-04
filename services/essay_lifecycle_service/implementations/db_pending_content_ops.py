"""
Database-backed pending content operations for pre-registration arrivals.

Stores content metadata keyed by batch_id + text_storage_id until batch registration,
allowing assignment processing once inventory exists.
"""

from __future__ import annotations

import json
from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

logger = create_service_logger("els.db_pending_content")


class DBPendingContentOperations:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def store_pending_content(
        self, batch_id: str, text_storage_id: str, content_metadata: dict[str, Any]
    ) -> None:
        async with self._session_factory() as session:
            # Use explicit parameter binding to avoid mixing parameter styles
            await session.execute(
                text(
                    """
                    INSERT INTO batch_pending_content (batch_id, text_storage_id, content_metadata)
                    VALUES (:batch_id, :text_storage_id, CAST(:metadata AS jsonb))
                    ON CONFLICT (batch_id, text_storage_id)
                    DO UPDATE SET content_metadata = EXCLUDED.content_metadata
                    """
                ),
                {
                    "batch_id": batch_id,
                    "text_storage_id": text_storage_id,
                    "metadata": json.dumps(content_metadata),
                },
            )
            await session.commit()

    async def get_pending_content(self, batch_id: str) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT text_storage_id, content_metadata FROM batch_pending_content WHERE batch_id = :batch_id"
                    ),
                    {"batch_id": batch_id},
                )
            ).all()
            return [
                {
                    "text_storage_id": row[0],
                    **row[1],  # content_metadata is already parsed as dict by asyncpg
                }
                for row in rows
            ]

    async def remove_pending_content(self, batch_id: str, text_storage_id: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                text(
                    "DELETE FROM batch_pending_content WHERE batch_id = :batch_id AND text_storage_id = :tsid"
                ),
                {"batch_id": batch_id, "tsid": text_storage_id},
            )
            await session.commit()
