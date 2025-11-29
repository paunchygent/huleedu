#!/usr/bin/env python3
"""Extract CJ assessment comparison results and Bradley-Terry statistics from database."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import asyncpg


async def connect_to_db() -> asyncpg.Connection:
    """Connect to CJ assessment database using asyncpg."""
    db_host = os.getenv("HULEEDU_DB_HOST", "localhost")
    db_port_str = os.getenv("HULEEDU_DB_PORT", "5440")
    db_user = os.getenv("HULEEDU_DB_USER", "huleedu_user")
    db_password = os.getenv("HULEEDU_DB_PASSWORD", "huleedu_dev_password")

    try:
        db_port = int(db_port_str)
    except ValueError:
        db_port = 5440

    return await asyncpg.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        database="huleedu_cj_assessment",
    )


async def get_batch_info(conn: asyncpg.Connection, batch_identifier: str | int) -> dict[str, Any]:
    """Get batch information by batch ID or BOS batch ID."""
    if isinstance(batch_identifier, int) or (
        isinstance(batch_identifier, str) and batch_identifier.isdigit()
    ):
        row = await conn.fetchrow(
            "SELECT * FROM cj_batch_uploads WHERE id = $1",
            int(batch_identifier),
        )
    else:
        row = await conn.fetchrow(
            "SELECT * FROM cj_batch_uploads WHERE bos_batch_id = $1",
            batch_identifier,
        )

    if row is None:
        raise ValueError(f"Batch not found: {batch_identifier}")

    return dict(row)


async def get_comparison_results(
    conn: asyncpg.Connection, cj_batch_id: int
) -> list[dict[str, Any]]:
    """Get all comparison results for a batch."""
    rows = await conn.fetch(
        """
        SELECT
            id,
            essay_a_els_id,
            essay_b_els_id,
            winner,
            confidence,
            justification,
            request_correlation_id,
            submitted_at,
            completed_at,
            error_code
        FROM cj_comparison_pairs
        WHERE cj_batch_id = $1
        ORDER BY id
        """,
        cj_batch_id,
    )
    return [dict(row) for row in rows]


async def get_bradley_terry_stats(
    conn: asyncpg.Connection, cj_batch_id: int
) -> list[dict[str, Any]]:
    """Get Bradley-Terry statistics for all essays in batch."""
    rows = await conn.fetch(
        """
        SELECT
            els_essay_id,
            current_bt_score,
            current_bt_se,
            comparison_count,
            is_anchor
        FROM cj_processed_essays
        WHERE cj_batch_id = $1
        ORDER BY current_bt_score DESC NULLS LAST
        """,
        cj_batch_id,
    )
    return [dict(row) for row in rows]


def calculate_wins_losses(comparisons: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Calculate wins and losses for each essay."""
    stats: dict[str, dict[str, int]] = {}

    for comp in comparisons:
        essay_a = comp["essay_a_els_id"]
        essay_b = comp["essay_b_els_id"]
        winner = comp["winner"]

        # Initialize if needed
        if essay_a not in stats:
            stats[essay_a] = {"wins": 0, "losses": 0, "total": 0}
        if essay_b not in stats:
            stats[essay_b] = {"wins": 0, "losses": 0, "total": 0}

        # Count result
        if winner == "essay_a":
            stats[essay_a]["wins"] += 1
            stats[essay_a]["total"] += 1
            stats[essay_b]["losses"] += 1
            stats[essay_b]["total"] += 1
        elif winner == "essay_b":
            stats[essay_b]["wins"] += 1
            stats[essay_b]["total"] += 1
            stats[essay_a]["losses"] += 1
            stats[essay_a]["total"] += 1
        elif winner == "tie":
            # Ties don't count as wins or losses
            stats[essay_a]["total"] += 1
            stats[essay_b]["total"] += 1

    return stats


def format_output(
    batch_info: dict[str, Any],
    comparisons: list[dict[str, Any]],
    bt_stats: list[dict[str, Any]],
    wins_losses: dict[str, dict[str, int]],
    output_format: str = "text",
) -> str:
    """Format results for output."""

    if output_format == "json":
        return json.dumps(
            {
                "batch_info": batch_info,
                "comparisons": comparisons,
                "bradley_terry_stats": bt_stats,
                "wins_losses": wins_losses,
            },
            indent=2,
            default=str,
        )

    # Text format
    lines = []
    lines.append("=" * 100)
    lines.append(f"CJ ASSESSMENT RESULTS: {batch_info['bos_batch_id']}")
    lines.append("=" * 100)
    lines.append(f"Batch ID: {batch_info['id']}")
    lines.append(f"Status: {batch_info['status']}")
    lines.append(f"Created: {batch_info['created_at']}")
    lines.append("")

    # Comparison Results
    lines.append("=" * 100)
    lines.append("PAIRWISE COMPARISON RESULTS")
    lines.append("=" * 100)
    lines.append("")

    for i, comp in enumerate(comparisons, 1):
        lines.append(f"Comparison #{i} (ID: {comp['id']})")
        lines.append(f"  Essay A: {comp['essay_a_els_id']}")
        lines.append(f"  Essay B: {comp['essay_b_els_id']}")
        lines.append(f"  Winner: {comp['winner']}")
        lines.append(f"  Confidence: {comp['confidence']}/5.0")
        lines.append("  Justification:")
        if comp["justification"]:
            # Indent justification
            for line in comp["justification"].split("\n"):
                lines.append(f"    {line}")
        else:
            lines.append("    (No justification provided)")

        if comp["error_code"]:
            lines.append(f"  ERROR: {comp['error_code']}")

        lines.append(f"  Correlation ID: {comp['request_correlation_id']}")
        lines.append(f"  Submitted: {comp['submitted_at']}")
        lines.append(f"  Completed: {comp['completed_at']}")
        lines.append("")

    # Bradley-Terry Statistics
    lines.append("=" * 100)
    lines.append("BRADLEY-TERRY RANKING & STATISTICS")
    lines.append("=" * 100)
    lines.append("")
    lines.append(
        (
            f"{'Rank':<6} {'Essay ID':<38} {'BT Score':<12} {'BT SE':<12} "
            f"{'Wins':<6} {'Losses':<8} {'Total':<6} {'Anchor':<8}"
        )
    )
    lines.append("-" * 100)

    for rank, essay in enumerate(bt_stats, 1):
        essay_id = essay["els_essay_id"]
        bt_score = (
            f"{essay['current_bt_score']:.4f}" if essay["current_bt_score"] is not None else "N/A"
        )
        bt_se = f"{essay['current_bt_se']:.4f}" if essay["current_bt_se"] is not None else "N/A"
        wl = wins_losses.get(essay_id, {"wins": 0, "losses": 0, "total": 0})
        is_anchor = "Yes" if essay["is_anchor"] else "No"

        lines.append(
            f"{rank:<6} {essay_id:<38} {bt_score:<12} {bt_se:<12} "
            f"{wl['wins']:<6} {wl['losses']:<8} {wl['total']:<6} {is_anchor:<8}"
        )

    lines.append("")
    lines.append("=" * 100)
    lines.append(f"Total Essays: {len(bt_stats)}")
    lines.append(f"Total Comparisons: {len(comparisons)}")
    lines.append(
        f"Successful Comparisons: {sum(1 for c in comparisons if c['winner'] is not None)}"
    )
    lines.append(
        f"Failed Comparisons: {sum(1 for c in comparisons if c['error_code'] is not None)}"
    )
    lines.append("=" * 100)

    return "\n".join(lines)


async def main_async(args: argparse.Namespace) -> int:
    """Async entry point that orchestrates extraction."""
    conn: asyncpg.Connection | None = None
    try:
        conn = await connect_to_db()

        # Get batch info
        batch_info = await get_batch_info(conn, args.batch_identifier)
        cj_batch_id = batch_info["id"]

        # Get comparison results
        comparisons = await get_comparison_results(conn, cj_batch_id)

        # Get Bradley-Terry stats
        bt_stats = await get_bradley_terry_stats(conn, cj_batch_id)

        # Calculate wins/losses
        wins_losses = calculate_wins_losses(comparisons)

        # Format output
        output = format_output(batch_info, comparisons, bt_stats, wins_losses, args.format)

        # Write output
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output)
            print(f"Results written to: {args.output}", file=sys.stderr)
        else:
            print(output)

        return 0
    except Exception as e:  # noqa: BLE001
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            await conn.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Extract CJ assessment comparison results and Bradley-Terry statistics"
    )
    parser.add_argument(
        "batch_identifier",
        help="Batch ID (integer) or BOS batch ID (string)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file (default: stdout)",
    )

    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
