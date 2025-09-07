"""
Verify shared outbox index names exist and match expectations.

Usage:
    python services/entitlements_service/scripts/verify_outbox_indexes.py \
        --database-url postgresql+asyncpg://user:pass@host:port/db

Or set env var DATABASE_URL / ENTITLEMENTS_SERVICE_DATABASE_URL.

Exit codes:
    0 = OK
    1 = Missing required indexes
    2 = Predicate/columns mismatch
    3 = Connection or unexpected error
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

EXPECTED_INDEXES = {
    "ix_event_outbox_unpublished": {
        "columns": ["published_at", "created_at"],
        "predicate": "published_at IS NULL",
    },
    "ix_event_outbox_aggregate": {
        "columns": ["aggregate_type", "aggregate_id"],
        "predicate": None,
    },
}


async def _fetch_indexes(engine: AsyncEngine) -> dict[str, dict[str, Any]]:
    """Return a mapping of indexname -> {indexdef, predicate, columns} for event_outbox."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        # Fetch index definitions
        idx_rows = (
            (
                await conn.execute(
                    text(
                        """
                SELECT i.relname AS indexname,
                       pg_get_indexdef(ix.indexrelid) AS indexdef,
                       pg_get_expr(ix.indpred, ix.indrelid) AS predicate
                FROM pg_index ix
                JOIN pg_class t ON t.oid = ix.indrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                JOIN pg_class i ON i.oid = ix.indexrelid
                WHERE n.nspname = current_schema() AND t.relname = 'event_outbox';
                """
                    )
                )
            )
            .mappings()
            .all()
        )

    result: dict[str, dict[str, Any]] = {}
    for row in idx_rows:
        name = row["indexname"]
        indexdef: str = row["indexdef"] or ""
        predicate: str | None = row["predicate"]
        # Extract columns from the indexdef using regex to handle partial indexes
        # Pattern matches "USING btree (columns)" and captures the columns part
        btree_match = re.search(r"USING btree \(([^)]+)\)", indexdef)
        if btree_match:
            cols_part = btree_match.group(1)
            columns = [c.strip().strip('"') for c in cols_part.split(",")]
        else:
            # Fallback for unexpected format
            columns = []
        result[name] = {"indexdef": indexdef, "predicate": predicate, "columns": columns}
    return result


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", dest="database_url", default=None)
    args = parser.parse_args()

    database_url = (
        args.database_url
        or os.getenv("DATABASE_URL")
        or os.getenv("ENTITLEMENTS_SERVICE_DATABASE_URL")
    )

    if not database_url:
        print(
            "ERROR: Provide --database-url or set DATABASE_URL/ENTITLEMENTS_SERVICE_DATABASE_URL",
            file=sys.stderr,
        )
        return 3

    engine = create_async_engine(database_url, echo=False)
    try:
        idx_map = await _fetch_indexes(engine)

        missing = [name for name in EXPECTED_INDEXES.keys() if name not in idx_map]
        if missing:
            print(f"MISSING: {', '.join(missing)}", file=sys.stderr)
            return 1

        mismatches: list[str] = []
        for name, spec in EXPECTED_INDEXES.items():
            actual = idx_map[name]
            exp_cols = spec["columns"]
            act_cols = actual["columns"]
            if [c.lower() for c in act_cols] != [c.lower() for c in exp_cols]:
                mismatches.append(
                    f"{name}: columns mismatch (expected {exp_cols}, actual {act_cols})"
                )
            exp_pred = spec["predicate"]
            act_pred = actual["predicate"]
            # Normalize predicates by stripping surrounding parentheses for comparison
            normalized_exp = (exp_pred or "").strip().strip("()")
            normalized_act = (act_pred or "").strip().strip("()")
            if normalized_exp != normalized_act:
                mismatches.append(
                    f"{name}: predicate mismatch (expected {exp_pred!r}, actual {act_pred!r})"
                )

        if mismatches:
            print("MISMATCHES:", file=sys.stderr)
            for m in mismatches:
                print(f"  - {m}", file=sys.stderr)
            return 2

        print("OK: Outbox indexes aligned with shared conventions.")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    finally:
        await engine.dispose()


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
