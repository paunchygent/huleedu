from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.models_db import (
    BatchEssayTracker as BatchEssayTrackerDB,
)
from services.essay_lifecycle_service.models_db import (
    BatchPendingContent,
    BatchValidationFailure,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


async def purge_guest_batches(older_than_days: int, dry_run: bool = False) -> dict[str, int]:
    settings = Settings()
    engine: AsyncEngine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)

    async with session_factory() as session:
        # Identify guest batches to purge
        batches_stmt = select(BatchEssayTrackerDB.batch_id).where(
            BatchEssayTrackerDB.org_id.is_(None),
            BatchEssayTrackerDB.completed_at.is_not(None),
            BatchEssayTrackerDB.completed_at < cutoff,
        )
        batch_ids = [row[0] for row in (await session.execute(batches_stmt)).all()]

        if not batch_ids:
            await engine.dispose()
            return {"batches": 0, "pending": 0, "failures": 0}

        deleted_pending = 0
        deleted_failures = 0
        deleted_batches = 0

        if dry_run:
            await engine.dispose()
            return {
                "batches": len(batch_ids),
                "pending": 0,
                "failures": 0,
            }

        # Delete pending content for these batches
        pending_del = (
            delete(BatchPendingContent)
            .where(BatchPendingContent.batch_id.in_(batch_ids))
            .execution_options(synchronize_session=False)
        )
        res = await session.execute(pending_del)
        deleted_pending = res.rowcount or 0

        # Delete orphan failures with NULL tracker (tracked before registration)
        failures_del = (
            delete(BatchValidationFailure)
            .where(
                BatchValidationFailure.batch_id.in_(batch_ids),
                BatchValidationFailure.batch_tracker_id.is_(None),
            )
            .execution_options(synchronize_session=False)
        )
        res = await session.execute(failures_del)
        deleted_failures = res.rowcount or 0

        # Delete guest batch trackers (cascades to slot assignments and failures with tracker_id)
        tracker_del = (
            delete(BatchEssayTrackerDB)
            .where(BatchEssayTrackerDB.batch_id.in_(batch_ids))
            .execution_options(synchronize_session=False)
        )
        res = await session.execute(tracker_del)
        deleted_batches = res.rowcount or 0

        await session.commit()

    await engine.dispose()
    return {
        "batches": deleted_batches,
        "pending": deleted_pending,
        "failures": deleted_failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Purge completed GUEST batches older than N days (DB-only)."
    )
    parser.add_argument("--older-than-days", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    results = asyncio.run(purge_guest_batches(args.older_than_days, args.dry_run))
    print(
        f"Purged (dry_run={args.dry_run}): batches={results['batches']}, "
        f"pending={results['pending']}, failures={results['failures']}"
    )


if __name__ == "__main__":
    main()
