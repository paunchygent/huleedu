"""Quick diagnostics for CJ batch lifecycle state.

This script intentionally avoids application-level dependencies so it can be
run directly against a developer stack. It inspects database tables to help
debug situations where the high-level upload status, CJ internal state, grade
projections, and comparison counters diverge.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# Ensure repository root is importable when script is invoked via `python path/to/script.py`
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.cj_assessment_service.config import Settings  # noqa: E402


@dataclass
class BatchSnapshot:
    batch_id: int
    upload_status: str | None
    state: str | None
    totals: dict[str, Any]
    grade_projection_count: int
    anchor_counts: dict[str, int]


async def _fetch_one(engine: AsyncEngine, query: str, **params: Any) -> Result:
    async with engine.connect() as conn:
        return await conn.execute(text(query), params)


async def capture_snapshot(engine: AsyncEngine, batch_id: int) -> BatchSnapshot:
    """Gather upload status, state row, anchor stats, and grade projections."""

    upload_status = None
    status_result = await _fetch_one(
        engine,
        "SELECT status::text FROM cj_batch_uploads WHERE id = :batch_id",
        batch_id=batch_id,
    )
    if row := status_result.one_or_none():
        upload_status = row.status

    state_row = await _fetch_one(
        engine,
        """
        SELECT state::text,
               total_comparisons,
               submitted_comparisons,
               completed_comparisons,
               failed_comparisons,
               partial_scoring_triggered,
               completion_threshold_pct,
               current_iteration
        FROM cj_batch_states
        WHERE batch_id = :batch_id
        """,
        batch_id=batch_id,
    )
    state_values = state_row.one_or_none()

    totals: dict[str, Any] = {}
    state_value = None
    if state_values:
        totals = {
            "total": state_values.total_comparisons,
            "submitted": state_values.submitted_comparisons,
            "completed": state_values.completed_comparisons,
            "failed": state_values.failed_comparisons,
            "partial_scoring_triggered": state_values.partial_scoring_triggered,
            "threshold_pct": state_values.completion_threshold_pct,
            "iteration": state_values.current_iteration,
        }
        state_value = state_values.state

    projection_count_result = await _fetch_one(
        engine,
        "SELECT COUNT(*) AS cnt FROM grade_projections WHERE cj_batch_id = :batch_id",
        batch_id=batch_id,
    )
    grade_projection_count = projection_count_result.scalar_one()

    anchor_counts_result = await _fetch_one(
        engine,
        """
        SELECT COUNT(*) FILTER (WHERE is_anchor) AS anchors_by_flag,
               COUNT(*) FILTER (WHERE els_essay_id LIKE 'ANCHOR_%') AS anchors_by_id,
               COUNT(*) AS total
        FROM cj_processed_essays
        WHERE cj_batch_id = :batch_id
        """,
        batch_id=batch_id,
    )
    anchor_counts_row = anchor_counts_result.one()
    anchor_counts = {
        "anchors_by_flag": anchor_counts_row.anchors_by_flag,
        "anchors_by_id": anchor_counts_row.anchors_by_id,
        "total_essays": anchor_counts_row.total,
    }

    return BatchSnapshot(
        batch_id=batch_id,
        upload_status=upload_status,
        state=state_value,
        totals=totals,
        grade_projection_count=grade_projection_count,
        anchor_counts=anchor_counts,
    )


def format_snapshot(snapshot: BatchSnapshot) -> str:
    total = snapshot.totals.get("total")
    submitted = snapshot.totals.get("submitted")
    completed = snapshot.totals.get("completed")
    failed = snapshot.totals.get("failed")
    threshold = snapshot.totals.get("threshold_pct")
    partial_flag = snapshot.totals.get("partial_scoring_triggered")
    anchors_by_flag = snapshot.anchor_counts["anchors_by_flag"]
    total_essays = snapshot.anchor_counts["total_essays"]
    anchors_by_id = snapshot.anchor_counts["anchors_by_id"]

    lines = [
        f"CJ Batch {snapshot.batch_id}",
        f"  upload_status        : {snapshot.upload_status}",
        f"  state                : {snapshot.state}",
        f"  total/submitted      : {total} / {submitted}",
        f"  completed/failed     : {completed} / {failed}",
        f"  completion threshold : {threshold}%",
        f"  partial scoring flag : {partial_flag}",
        f"  grade projections    : {snapshot.grade_projection_count}",
        f"  anchor essays (flag) : {anchors_by_flag} of {total_essays}",
        f"  anchor essays (id)   : {anchors_by_id} inferred by ID prefix",
    ]
    return "\n".join(lines)


async def main(batch_id: int) -> None:
    settings = Settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)

    snapshot = await capture_snapshot(engine, batch_id)
    print(format_snapshot(snapshot))

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect CJ batch lifecycle state")
    parser.add_argument("batch_id", type=int, help="Internal CJ batch ID")
    args = parser.parse_args()

    asyncio.run(main(args.batch_id))
