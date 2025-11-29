"""Anchor alignment report generator for prompt tuning experiments.

This module generates markdown reports analyzing the alignment between
LLM comparative judgments and expert anchor grades.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scripts.cj_experiments_runners.eng5_np.hydrator import AssessmentRunHydrator

# Grade ordering from highest to lowest (lower index = better grade)
GRADE_ORDER = [
    "A",
    "A-",
    "B+",
    "B",
    "B-",
    "C+",
    "C",
    "C-",
    "D+",
    "D",
    "D-",
    "E+",
    "E",
    "E-",
    "F+",
    "F",
]


def grade_to_rank(grade: str) -> int:
    """Convert grade to numeric rank (lower = better).

    Args:
        grade: Letter grade string (e.g., "A", "B-", "E+")

    Returns:
        Rank index (0 = A, 15 = F), or 99 for unknown grades
    """
    try:
        return GRADE_ORDER.index(grade)
    except ValueError:
        return 99  # Unknown grades sorted last


@dataclass
class AnchorResult:
    """Result data for a single anchor essay."""

    anchor_id: str
    expected_grade: str
    bt_score: float
    actual_rank: int
    expected_rank: int
    wins: int
    losses: int
    win_rate: float


@dataclass
class Inversion:
    """A head-to-head comparison where lower grade beats higher grade."""

    higher_grade_anchor: str
    higher_grade: str
    lower_grade_anchor: str
    lower_grade: str
    winner: str
    confidence: float
    justification: str


def compute_kendall_tau(actual_ranks: list[int], expected_ranks: list[int]) -> float:
    """Compute Kendall's tau rank correlation coefficient.

    Args:
        actual_ranks: List of actual ranks from BT scoring
        expected_ranks: List of expected ranks from expert grades

    Returns:
        Kendall's tau coefficient (-1 to 1, where 1 = perfect agreement)
    """
    n = len(actual_ranks)
    if n < 2:
        return 0.0

    concordant = 0
    discordant = 0

    for i in range(n):
        for j in range(i + 1, n):
            actual_diff = actual_ranks[i] - actual_ranks[j]
            expected_diff = expected_ranks[i] - expected_ranks[j]
            product = actual_diff * expected_diff
            if product > 0:
                concordant += 1
            elif product < 0:
                discordant += 1

    total_pairs = n * (n - 1) / 2
    if total_pairs == 0:
        return 0.0
    return (concordant - discordant) / total_pairs


def _build_anchor_results(
    bt_summary: list[dict[str, Any]],
    llm_comparisons: list[dict[str, Any]],
    anchor_grade_map: dict[str, str],
) -> list[AnchorResult]:
    """Build structured anchor results from BT summary.

    Args:
        bt_summary: List of BT score entries from hydrator
        llm_comparisons: List of comparison records from hydrator
        anchor_grade_map: Mapping of anchor_id to expected grade

    Returns:
        List of AnchorResult objects sorted by expected rank
    """
    # Build win/loss counts from comparisons
    wins: dict[str, int] = {}
    losses: dict[str, int] = {}

    for comp in llm_comparisons:
        winner = comp.get("winner_id", "")
        loser = comp.get("loser_id", "")
        if winner:
            wins[winner] = wins.get(winner, 0) + 1
        if loser:
            losses[loser] = losses.get(loser, 0) + 1

    results: list[AnchorResult] = []

    for entry in bt_summary:
        essay_id = entry.get("essay_id", "")
        # Extract anchor ID from essay_id (format: "student::anchor_xxx" or similar)
        anchor_id = essay_id.replace("student::", "").replace("anchor::", "")

        expected_grade = anchor_grade_map.get(anchor_id, "UNKNOWN")
        bt_score = entry.get("theta", 0.0)
        actual_rank = entry.get("rank", 0)

        essay_wins = wins.get(essay_id, 0)
        essay_losses = losses.get(essay_id, 0)
        total = essay_wins + essay_losses
        win_rate = essay_wins / total if total > 0 else 0.0

        results.append(
            AnchorResult(
                anchor_id=anchor_id,
                expected_grade=expected_grade,
                bt_score=bt_score,
                actual_rank=actual_rank,
                expected_rank=0,  # Will be filled in below
                wins=essay_wins,
                losses=essay_losses,
                win_rate=win_rate,
            )
        )

    # Sort by expected grade and assign expected ranks
    results.sort(key=lambda r: grade_to_rank(r.expected_grade))
    for i, result in enumerate(results, start=1):
        result.expected_rank = i

    return results


def _detect_inversions(
    llm_comparisons: list[dict[str, Any]],
    anchor_grade_map: dict[str, str],
) -> list[Inversion]:
    """Detect head-to-head inversions from comparison data.

    An inversion occurs when an essay with a lower expert grade
    beats an essay with a higher expert grade.

    Args:
        llm_comparisons: List of comparison records
        anchor_grade_map: Mapping of anchor_id to expected grade

    Returns:
        List of Inversion objects
    """
    inversions: list[Inversion] = []

    for comp in llm_comparisons:
        winner_id = comp.get("winner_id", "")
        loser_id = comp.get("loser_id", "")
        confidence = comp.get("confidence", 0.0) or 0.0
        justification = comp.get("justification", "") or ""

        # Extract anchor IDs
        winner_anchor = winner_id.replace("student::", "").replace("anchor::", "")
        loser_anchor = loser_id.replace("student::", "").replace("anchor::", "")

        winner_grade = anchor_grade_map.get(winner_anchor, "UNKNOWN")
        loser_grade = anchor_grade_map.get(loser_anchor, "UNKNOWN")

        winner_rank = grade_to_rank(winner_grade)
        loser_rank = grade_to_rank(loser_grade)

        # Inversion: winner has worse (higher number) expected rank than loser
        if winner_rank > loser_rank:
            inversions.append(
                Inversion(
                    higher_grade_anchor=loser_anchor,
                    higher_grade=loser_grade,
                    lower_grade_anchor=winner_anchor,
                    lower_grade=winner_grade,
                    winner=winner_anchor,
                    confidence=confidence,
                    justification=justification,
                )
            )

    return inversions


def _format_report(
    *,
    batch_id: str,
    timestamp: str,
    system_prompt_text: str | None,
    rubric_text: str | None,
    total_comparisons: int,
    inversion_count: int,
    kendall_tau: float,
    zero_win_count: int,
    anchor_results: list[AnchorResult],
    inversions: list[Inversion],
) -> str:
    """Format alignment report as markdown.

    Args:
        batch_id: Batch identifier
        timestamp: ISO timestamp
        system_prompt_text: System prompt used (for reproducibility)
        rubric_text: Rubric used (for reproducibility)
        total_comparisons: Total number of comparisons
        inversion_count: Number of grade inversions detected
        kendall_tau: Kendall's tau correlation coefficient
        zero_win_count: Number of anchors with zero wins
        anchor_results: List of per-anchor results
        inversions: List of detected inversions

    Returns:
        Formatted markdown report
    """
    lines = [
        f"# Anchor Alignment Report: {batch_id}",
        "",
        f"**Generated:** {timestamp}",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total comparisons | {total_comparisons} |",
        f"| Direct inversions | {inversion_count} |",
        f"| Zero-win anchors | {zero_win_count} |",
        f"| Kendall's tau | {kendall_tau:.3f} |",
        "",
        "## Per-Anchor Results",
        "",
        "| Anchor | Grade | BT Score | Rank | Expected | Wins | Losses | Win Rate |",
        "|--------|-------|----------|------|----------|------|--------|----------|",
    ]

    for r in sorted(anchor_results, key=lambda x: x.expected_rank):
        lines.append(
            f"| {r.anchor_id} | {r.expected_grade} | {r.bt_score:.3f} | "
            f"{r.actual_rank} | {r.expected_rank} | {r.wins} | {r.losses} | {r.win_rate:.0%} |"
        )

    if inversions:
        lines.extend(
            [
                "",
                "## Detected Inversions",
                "",
                "| Higher Grade | Lower Grade | Winner | Confidence | Justification |",
                "|--------------|-------------|--------|------------|---------------|",
            ]
        )
        for inv in inversions:
            justification_short = (
                inv.justification[:50] + "..." if len(inv.justification) > 50 else inv.justification
            )
            lines.append(
                f"| {inv.higher_grade_anchor} ({inv.higher_grade}) | "
                f"{inv.lower_grade_anchor} ({inv.lower_grade}) | "
                f"{inv.winner} | {inv.confidence:.1f} | {justification_short} |"
            )

    lines.extend(
        [
            "",
            "---",
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

    return "\n".join(lines)


def generate_alignment_report(
    *,
    hydrator: AssessmentRunHydrator | None,
    anchor_grade_map: dict[str, str],
    system_prompt_text: str | None,
    rubric_text: str | None,
    batch_id: str,
    output_dir: Path,
) -> Path:
    """Generate markdown alignment report from CJ results.

    Args:
        hydrator: AssessmentRunHydrator with collected results
        anchor_grade_map: Mapping of anchor_id to expert grade
        system_prompt_text: Full system prompt used
        rubric_text: Full rubric used
        batch_id: Unique batch identifier
        output_dir: Directory for report output

    Returns:
        Path to generated report file
    """
    if hydrator is None:
        # Create minimal report for no-data case
        timestamp = datetime.now(timezone.utc).isoformat()
        report_content = _format_report(
            batch_id=batch_id,
            timestamp=timestamp,
            system_prompt_text=system_prompt_text,
            rubric_text=rubric_text,
            total_comparisons=0,
            inversion_count=0,
            kendall_tau=0.0,
            zero_win_count=0,
            anchor_results=[],
            inversions=[],
        )
    else:
        artefact = hydrator.get_run_artefact()
        bt_summary = artefact.get("bt_summary", [])
        llm_comparisons = artefact.get("llm_comparisons", [])

        # Build anchor results
        anchor_results = _build_anchor_results(bt_summary, llm_comparisons, anchor_grade_map)

        # Detect inversions
        inversions = _detect_inversions(llm_comparisons, anchor_grade_map)

        # Compute metrics
        actual_ranks = [r.actual_rank for r in anchor_results]
        expected_ranks = [r.expected_rank for r in anchor_results]
        kendall_tau = compute_kendall_tau(actual_ranks, expected_ranks)

        zero_win_count = sum(1 for r in anchor_results if r.wins == 0)

        timestamp = datetime.now(timezone.utc).isoformat()
        report_content = _format_report(
            batch_id=batch_id,
            timestamp=timestamp,
            system_prompt_text=system_prompt_text,
            rubric_text=rubric_text,
            total_comparisons=len(llm_comparisons),
            inversion_count=len(inversions),
            kendall_tau=kendall_tau,
            zero_win_count=zero_win_count,
            anchor_results=anchor_results,
            inversions=inversions,
        )

    # Write report
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"anchor_align_{batch_id}_{timestamp_str}.md"
    report_path.write_text(report_content, encoding="utf-8")

    return report_path
