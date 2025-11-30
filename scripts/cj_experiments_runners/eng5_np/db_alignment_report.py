"""Generate ENG5 anchor-alignment report directly from CJ DB data.

This is a diagnostics/analysis helper that:
1. Connects to the CJ Assessment database.
2. Loads Bradley–Terry stats and comparison pairs for a given CJ batch.
3. Reconstructs ENG5-style alignment metrics (wins/losses, inversions, tau)
   using ONLY successful comparisons, matching CJ scoring semantics.
4. Writes a markdown report using the same formatting as alignment_report.py,
   but without requiring an ENG5 hydrator or rerunning CJ/LLM.

Usage (example for vt_2017 ENG5 baseline, using BOS batch ID):

    source .env
    pdm run python scripts/cj_experiments_runners/eng5_np/db_alignment_report.py \\
        --bos-batch-id anchor-align-baseline-20251130-011352

By default this assumes vt_2017 anchors live under:
  test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays
and derives expert grades from filenames via extract_grade_from_filename.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.cj_assessment_service.diagnostics.extract_cj_results import (
    connect_to_db,
    get_batch_info,
    get_bradley_terry_stats,
    get_comparison_results,
)
from scripts.cj_experiments_runners.eng5_np.alignment_report import (
    AnchorResult,
    Inversion,
    _build_anchor_results,
    _detect_inversions,
    _format_report,
    compute_kendall_tau,
)
from scripts.cj_experiments_runners.eng5_np.anchor_utils import extract_grade_from_filename
from scripts.cj_experiments_runners.eng5_np.utils import make_anchor_key, sanitize_identifier


def _build_anchor_grade_and_filename_maps(
    anchor_dir: Path,
) -> tuple[dict[str, str], dict[str, str]]:
    """Derive anchor grade and filename maps from vt_2017 anchor directory.

    Keys are normalized using make_anchor_key/sanitize_identifier so they can
    be matched against CJ els_essay_id suffixes used in anchor-align-test
    (student::<anchor_key>).
    """
    grade_map: dict[str, str] = {}
    filename_map: dict[str, str] = {}

    if not anchor_dir.exists():
        return grade_map, filename_map

    for path in sorted(anchor_dir.iterdir()):
        if not path.is_file():
            continue
        stem = path.stem
        grade = extract_grade_from_filename(path.name)
        anchor_key = make_anchor_key(stem)

        # Primary key: normalized anchor key
        grade_map[anchor_key] = grade
        filename_map[anchor_key] = path.name

        # Additional lookup keys to be safe
        norm_stem = sanitize_identifier(stem)
        filename_map.setdefault(norm_stem, path.name)
        filename_map.setdefault(stem, path.name)

    return grade_map, filename_map


def _build_bt_summary_from_db(bt_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert CJ bt_stats rows into ENG5 bt_summary entries."""

    # Sort by BT score descending to assign ranks
    sorted_rows = sorted(
        bt_rows,
        key=lambda r: (r.get("current_bt_score") is None, r.get("current_bt_score")),
        reverse=True,
    )
    bt_summary: list[dict[str, Any]] = []
    rank = 0
    for row in sorted_rows:
        score = row.get("current_bt_score")
        if score is None:
            continue
        rank += 1
        bt_summary.append(
            {
                "essay_id": row["els_essay_id"],
                "theta": float(score),
                "standard_error": float(row.get("current_bt_se") or 0.0),
                "rank": rank,
                "comparison_count": int(row.get("comparison_count") or 0),
                "is_anchor": bool(row.get("is_anchor")),
                "anchor_grade": None,
                "grade_projection": None,
            }
        )
    return bt_summary


def _build_llm_comparisons_from_db(
    comparisons: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert CJ comparison_pairs rows into ENG5 llm_comparisons records.

    Only successful comparisons (winner in {'essay_a', 'essay_b'}) are
    included; error/None winners are dropped, matching CJ scoring semantics.
    """
    records: list[dict[str, Any]] = []
    sequence = 0
    for comp in comparisons:
        winner = comp.get("winner")
        essay_a = comp["essay_a_els_id"]
        essay_b = comp["essay_b_els_id"]

        if winner == "essay_a":
            winner_id, loser_id = essay_a, essay_b
        elif winner == "essay_b":
            winner_id, loser_id = essay_b, essay_a
        else:
            # Skip errors/unknown winners; they never contribute to BT.
            continue

        sequence += 1
        records.append(
            {
                "sequence": sequence,
                "essay_a_id": essay_a,
                "essay_b_id": essay_b,
                "winner_id": winner_id,
                "loser_id": loser_id,
                "confidence": comp.get("confidence"),
                "justification": comp.get("justification"),
                "status": "succeeded",
            }
        )
    return records


async def generate_db_alignment_report(
    *,
    cj_batch_id: int | None,
    bos_batch_id: str | None,
    anchor_dir: Path,
    output_dir: Path,
    system_prompt_text: str | None = None,
    rubric_text: str | None = None,
) -> tuple[Path, Path]:
    """Generate summary and diagnostic alignment reports from CJ DB.

    Returns:
        (summary_report_path, diagnostic_report_path)
    """

    conn = await connect_to_db()
    try:
        batch_info: dict[str, Any]
        if cj_batch_id is None:
            if not bos_batch_id:
                raise ValueError("Either cj_batch_id or bos_batch_id must be provided")
            batch_info = await get_batch_info(conn, bos_batch_id)
            cj_batch_id_int = int(batch_info["id"])
        else:
            batch_info = await get_batch_info(conn, cj_batch_id)
            cj_batch_id_int = int(batch_info["id"])

        comparisons = await get_comparison_results(conn, cj_batch_id_int)
        bt_rows = await get_bradley_terry_stats(conn, cj_batch_id_int)
    finally:
        await conn.close()

    bt_summary = _build_bt_summary_from_db(bt_rows)
    llm_comparisons = _build_llm_comparisons_from_db(comparisons)

    # Build grade + filename maps from anchor directory
    anchor_grade_map, anchor_filename_map = _build_anchor_grade_and_filename_maps(anchor_dir)

    # Build anchor results and inversions using ENG5 helpers
    anchor_results: list[AnchorResult] = _build_anchor_results(
        bt_summary,
        llm_comparisons,
        anchor_grade_map,
        anchor_filename_map,
    )
    inversions: list[Inversion] = _detect_inversions(llm_comparisons, anchor_grade_map)

    actual_ranks = [r.actual_rank for r in anchor_results]
    expected_ranks = [r.expected_rank for r in anchor_results]
    kendall_tau = compute_kendall_tau(actual_ranks, expected_ranks)
    zero_win_count = sum(1 for r in anchor_results if r.wins == 0)

    timestamp_iso = datetime.now(timezone.utc).isoformat()
    batch_label = batch_info.get("bos_batch_id") or f"cj-{cj_batch_id_int}"
    # Summary report (same structure as ENG5 runner report)
    summary_content = _format_report(
        batch_id=str(batch_label),
        timestamp=timestamp_iso,
        system_prompt_text=system_prompt_text,
        rubric_text=rubric_text,
        total_comparisons=len(llm_comparisons),
        inversion_count=len(inversions),
        kendall_tau=kendall_tau,
        zero_win_count=zero_win_count,
        anchor_results=anchor_results,
        inversions=inversions,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp_slug = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    summary_path = output_dir / f"anchor_align_db_{batch_label}_{timestamp_slug}.md"
    summary_path.write_text(summary_content, encoding="utf-8")

    # Full diagnostic report with all comparisons and full justifications
    diag_lines = [
        f"# Anchor Alignment Diagnostic Report: {batch_label}",
        "",
        f"**Generated:** {timestamp_iso}",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total comparisons (successful) | {len(llm_comparisons)} |",
        f"| Direct inversions (unique pairs) | {len(inversions)} |",
        f"| Zero-win anchors | {zero_win_count} |",
        f"| Kendall's tau | {kendall_tau:.3f} |",
        "",
        "## Per-Anchor Results",
        "",
        "| Anchor ID | Grade | BT Score | Rank | Expected | Wins | Losses | Win Rate | Source |",
        "|-----------|-------|----------|------|----------|------|--------|----------|--------|",
    ]
    for r in sorted(anchor_results, key=lambda x: x.expected_rank):
        source_file = r.source_file_name or ""
        diag_lines.append(
            f"| {r.anchor_id} | {r.expected_grade} | {r.bt_score:.3f} | "
            f"{r.actual_rank} | {r.expected_rank} | {r.wins} | {r.losses} | {r.win_rate:.0%} | "
            f"{source_file} |"
        )

    diag_lines.extend(
        [
            "",
            "## All Comparisons (Full Justifications)",
            "",
            "| Seq | Winner | Winner Grade | Loser | Loser Grade | Confidence | Justification |",
            "|-----|--------|--------------|-------|-------------|------------|---------------|",
        ]
    )
    for comp in llm_comparisons:
        winner_id = str(comp.get("winner_id", ""))
        loser_id = str(comp.get("loser_id", ""))
        w_key = winner_id.replace("student::", "")
        l_key = loser_id.replace("student::", "")
        winner_grade = anchor_grade_map.get(w_key, "UNKNOWN")
        loser_grade = anchor_grade_map.get(l_key, "UNKNOWN")
        seq = comp.get("sequence", "")
        confidence = comp.get("confidence")
        justification = comp.get("justification") or ""
        diag_lines.append(
            f"| {seq} | {w_key} | {winner_grade} | {l_key} | {loser_grade} | "
            f"{confidence if confidence is not None else ''} | {justification} |"
        )

    if system_prompt_text is not None or rubric_text is not None:
        diag_lines.extend(
            [
                "",
                "## Prompts Used (for reproducibility)",
                "",
                "### System Prompt",
                "",
                "```",
                system_prompt_text or "(default)",
                "```",
                "",
                "### Judge Rubric",
                "",
                "```",
                rubric_text or "(default)",
                "```",
            ]
        )

    diag_path = output_dir / f"anchor_align_db_full_{batch_label}_{timestamp_slug}.md"
    diag_path.write_text("\n".join(diag_lines), encoding="utf-8")

    return summary_path, diag_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate ENG5 anchor-alignment report directly from CJ DB data.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--cj-batch-id",
        type=int,
        help="Numeric CJ batch_id (cj_batch_uploads.id)",
    )
    group.add_argument(
        "--bos-batch-id",
        type=str,
        help="BOS batch ID (cj_batch_uploads.bos_batch_id) used for the ENG5 run.",
    )
    parser.add_argument(
        "--anchor-dir",
        type=Path,
        default=Path(
            "test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays",
        ),
        help="Directory containing vt_2017 ENG5 anchor essays.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".claude/research/data/eng5_np_2016"),
        help="Directory where the markdown report will be written.",
    )
    parser.add_argument(
        "--system-prompt-file",
        type=Path,
        default=None,
        help="Optional system prompt file to embed in the diagnostic report.",
    )
    parser.add_argument(
        "--rubric-file",
        type=Path,
        default=None,
        help="Optional judge rubric file to embed in the diagnostic report.",
    )

    args = parser.parse_args()

    system_prompt_text = None
    rubric_text = None
    if args.system_prompt_file is not None and args.system_prompt_file.exists():
        system_prompt_text = args.system_prompt_file.read_text(encoding="utf-8")
    if args.rubric_file is not None and args.rubric_file.exists():
        rubric_text = args.rubric_file.read_text(encoding="utf-8")

    summary_path, diag_path = asyncio.run(
        generate_db_alignment_report(
            cj_batch_id=args.cj_batch_id,
            bos_batch_id=args.bos_batch_id,
            anchor_dir=args.anchor_dir,
            output_dir=args.output_dir,
            system_prompt_text=system_prompt_text,
            rubric_text=rubric_text,
        )
    )
    print(f"DB-based ENG5 alignment summary report written to {summary_path}")
    print(f"DB-based ENG5 alignment diagnostic report written to {diag_path}")


if __name__ == "__main__":
    main()
