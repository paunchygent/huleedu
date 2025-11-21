"""
Option B assignment path: Use essay_states as the inventory with a single UPDATE per assignment.

Provides an immediate-commit, DB-only operation suitable for cross-process coordination.
Adds lightweight retries to avoid false "no slot" outcomes when all slots are momentarily
locked by concurrent transactions.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from random import random
from uuid import UUID

from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import JSON, bindparam, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from services.essay_lifecycle_service.models_db import EssayStateDB

logger = create_service_logger("els.assignment_sql_b")


async def assign_via_essay_states_immediate_commit(
    session_factory: async_sessionmaker,
    batch_id: str,
    text_storage_id: str,
    original_file_name: str,
    file_size: int,
    content_hash: str | None,
    initial_status: EssayStatus = EssayStatus.READY_FOR_PROCESSING,
    correlation_id: UUID | None = None,
    *,
    _max_attempts: int = 5,
    _base_sleep_seconds: float = 0.005,
) -> tuple[bool, str | None]:
    """Assign content to the next available essay using essay_states as inventory.

    Executes with its own transaction for MVCC visibility across workers.

    Returns (was_created, essay_id). If no slot available, returns (False, None).
    """
    attempts = 0
    # Lightweight retry to ride out locked slots under contention without declaring exhaustion.
    while attempts < _max_attempts:
        async with session_factory() as session:
            try:
                from sqlalchemy import text as sqltext

                # Prepare JSON documents in Python and pass through parameters
                now_iso = datetime.now(UTC).isoformat()
                proc_meta = {
                    "text_storage_id": text_storage_id,
                    "original_file_name": original_file_name,
                    "file_size": file_size,
                    "content_hash": content_hash,
                    "slot_assignment_timestamp": now_iso,
                }
                storage_refs = {ContentType.ORIGINAL_ESSAY.value: text_storage_id}
                timeline = {initial_status.value: now_iso}

                stmt = sqltext(
                    """
                    WITH existing AS (
                        SELECT essay_id
                        FROM essay_states
                        WHERE batch_id = :batch_id
                          AND text_storage_id = :tsid
                        LIMIT 1
                    ),
                    candidate AS (
                        SELECT essay_id
                        FROM essay_states
                        WHERE batch_id = :batch_id
                          AND current_status = CAST(:available_status AS essay_status_enum)
                          AND NOT EXISTS (SELECT 1 FROM existing)
                        ORDER BY essay_id
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    ),
                    upd AS (
                        UPDATE essay_states es
                        SET current_status = CAST(:ready_status AS essay_status_enum),
                            text_storage_id = :tsid,
                            processing_metadata = CAST(:proc_meta AS json),
                            storage_references = CAST(:storage_refs AS json),
                            timeline = CAST(:timeline AS json),
                            updated_at = NOW()
                        FROM candidate c
                        WHERE es.essay_id = c.essay_id
                        RETURNING es.essay_id
                    )
                    SELECT
                        (SELECT essay_id FROM existing) AS existing_essay_id,
                        (SELECT essay_id FROM upd) AS updated_essay_id;
                    """
                )
                stmt = stmt.bindparams(
                    bindparam("proc_meta", type_=JSON),
                    bindparam("storage_refs", type_=JSON),
                    bindparam("timeline", type_=JSON),
                )

                res = await session.execute(
                    stmt,
                    {
                        "batch_id": batch_id,
                        "tsid": text_storage_id,
                        "available_status": EssayStatus.UPLOADED.value,
                        "ready_status": initial_status.value,
                        "proc_meta": proc_meta,
                        "storage_refs": storage_refs,
                        "timeline": timeline,
                    },
                )
                row = res.fetchone()
                existing_essay_id = row[0] if row else None
                updated_essay_id = row[1] if row else None

                await session.commit()

                if existing_essay_id:
                    return False, str(existing_essay_id)
                if updated_essay_id:
                    return True, str(updated_essay_id)

                # No slot claimed in this attempt. Check if another tx already assigned.
                winner_res = await session.execute(
                    select(EssayStateDB).where(
                        EssayStateDB.batch_id == batch_id,
                        EssayStateDB.text_storage_id == text_storage_id,
                    )
                )
                winner = winner_res.scalars().first()
                if winner is not None:
                    return False, winner.essay_id

                # If inventory truly exhausted, exit; otherwise retry after a short backoff.
                remaining_res = await session.execute(
                    select(func.count()).where(
                        EssayStateDB.batch_id == batch_id,
                        EssayStateDB.current_status == EssayStatus.UPLOADED,
                    )
                )
                remaining_slots = remaining_res.scalar_one()
                if remaining_slots == 0:
                    return False, None

            except IntegrityError:
                await session.rollback()
                # Another concurrent tx updated first: resolve idempotently
                res2 = await session.execute(
                    select(EssayStateDB).where(
                        EssayStateDB.batch_id == batch_id,
                        EssayStateDB.text_storage_id == text_storage_id,
                    )
                )
                winner = res2.scalars().first()
                if winner is not None:
                    return False, winner.essay_id
                raise
            except Exception:
                await session.rollback()
                raise

        attempts += 1
        sleep_seconds = _base_sleep_seconds * (2**attempts) * (1 + 0.25 * random())
        await asyncio.sleep(sleep_seconds)

    # Exhausted retries; last known state had slots but all were locked. Report no slot.
    return False, None
