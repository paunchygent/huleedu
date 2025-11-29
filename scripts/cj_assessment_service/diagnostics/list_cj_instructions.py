#!/usr/bin/env python3
"""List CJ assessment instructions and anchors directly from database.

Usage (from repo root):
    source .env
    pdm run python scripts/cj_assessment_service/diagnostics/list_cj_instructions.py

    # List anchors for specific assignment:
    pdm run python scripts/cj_assessment_service/diagnostics/list_cj_instructions.py \
        --anchors 00000000-0000-0000-0000-000000000001

Requires:
    - CJ database running (docker ps | grep cj_assessment_db)
    - Environment sourced (source .env)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import asyncpg


async def connect_to_db() -> asyncpg.Connection:
    """Connect to CJ assessment database using asyncpg."""
    db_host = os.getenv("HULEEDU_DB_HOST", "localhost")
    db_port_str = os.getenv("HULEEDU_CJ_DB_PORT", os.getenv("HULEEDU_DB_PORT", "5434"))
    db_user = os.getenv("HULEEDU_DB_USER", "huleedu_user")
    db_password = os.getenv("HULEEDU_DB_PASSWORD", "huleedu_dev_password")

    try:
        db_port = int(db_port_str)
    except ValueError:
        db_port = 5434

    return await asyncpg.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        database="huleedu_cj_assessment",
    )


async def list_instructions(conn: asyncpg.Connection) -> None:
    """List assessment instructions with anchor counts."""
    rows = await conn.fetch("""
        SELECT
            ai.id,
            ai.assignment_id,
            ai.course_id,
            ai.grade_scale,
            LEFT(ai.instructions_text, 40) as instructions_preview,
            ai.student_prompt_storage_id IS NOT NULL as has_prompt,
            ai.judge_rubric_storage_id IS NOT NULL as has_rubric,
            ai.created_at,
            COALESCE(anchor_counts.count, 0) as anchor_count
        FROM assessment_instructions ai
        LEFT JOIN (
            SELECT assignment_id, COUNT(*) as count
            FROM anchor_essay_references
            GROUP BY assignment_id
        ) anchor_counts ON ai.assignment_id = anchor_counts.assignment_id
        ORDER BY ai.created_at DESC
        LIMIT 20;
    """)

    if not rows:
        print("No assessment instructions found.")
        return

    # Print header
    print("\n" + "=" * 120)
    print("ASSESSMENT INSTRUCTIONS (from CJ Database)")
    print("=" * 120)
    print(
        f"{'ID':<4} {'assignment_id':<38} {'grade_scale':<25} "
        f"{'Prompt':<7} {'Rubric':<8} {'Anchors':<8} {'Created':<20}"
    )
    print("-" * 120)

    first_assignment_id = None
    for row in rows:
        db_id = row["id"]
        assignment_id = row["assignment_id"] or "-"
        grade_scale = row["grade_scale"]
        has_prompt = "✓" if row["has_prompt"] else "-"
        has_rubric = "✓" if row["has_rubric"] else "-"
        anchor_count = row["anchor_count"]
        created_at = row["created_at"].strftime("%Y-%m-%d %H:%M") if row["created_at"] else "-"

        if first_assignment_id is None and row["assignment_id"]:
            first_assignment_id = row["assignment_id"]

        print(
            f"{db_id:<4} {assignment_id:<38} {grade_scale:<25} "
            f"{has_prompt:<7} {has_rubric:<8} {anchor_count:<8} {created_at:<20}"
        )

    print("=" * 120)

    # Print copy-paste hint
    if first_assignment_id:
        print("\n\033[36mCopy-paste for ENG5 runner:\033[0m")
        print(f"  --assignment-id {first_assignment_id}")
        print("  --course-id 00000000-0000-0000-0000-000000000002  # placeholder")


async def list_anchors(conn: asyncpg.Connection, assignment_id: str) -> None:
    """List anchor essays for a specific assignment."""
    rows = await conn.fetch(
        """
        SELECT
            id,
            anchor_label,
            grade,
            text_storage_id,
            grade_scale,
            created_at
        FROM anchor_essay_references
        WHERE assignment_id = $1
        ORDER BY grade, created_at;
        """,
        assignment_id,
    )

    if not rows:
        print(f"No anchors found for assignment {assignment_id}")
        return

    print("\n" + "=" * 110)
    print(f"ANCHOR ESSAYS for {assignment_id}")
    print("=" * 110)
    print(f"{'ID':<6} {'anchor_label':<30} {'grade':<8} {'grade_scale':<25} {'Created':<20}")
    print("-" * 110)

    for row in rows:
        db_id = row["id"]
        anchor_label = row["anchor_label"] or "-"
        grade = row["grade"] or "-"
        grade_scale = row["grade_scale"] or "-"
        created_at = row["created_at"].strftime("%Y-%m-%d %H:%M") if row["created_at"] else "-"

        print(f"{db_id:<6} {anchor_label:<30} {grade:<8} {grade_scale:<25} {created_at:<20}")

    print("=" * 110)
    print(f"\nTotal anchors: {len(rows)}")


async def main_async(args: argparse.Namespace) -> int:
    """Async entry point."""
    conn: asyncpg.Connection | None = None
    try:
        conn = await connect_to_db()

        if args.anchors:
            await list_anchors(conn, args.anchors)
        else:
            await list_instructions(conn)

        return 0
    except asyncpg.PostgresError as e:
        print(f"Database error: {e}", file=sys.stderr)
        print("Ensure CJ database is running: docker ps | grep cj_assessment_db", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            await conn.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="List CJ assessment instructions and anchors from database"
    )
    parser.add_argument(
        "--anchors",
        metavar="ASSIGNMENT_ID",
        help="List anchors for specific assignment ID",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
