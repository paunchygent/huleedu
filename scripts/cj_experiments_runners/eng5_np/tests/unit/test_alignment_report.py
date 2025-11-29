"""Unit tests for alignment_report.py functions.

Tests cover grade ranking, Kendall's tau computation, inversion detection,
anchor result building, and report formatting.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.cj_experiments_runners.eng5_np.alignment_report import (
    GRADE_ORDER,
    AnchorResult,
    Inversion,
    _build_anchor_results,
    _detect_inversions,
    _format_report,
    compute_kendall_tau,
    generate_alignment_report,
    grade_to_rank,
)
from scripts.cj_experiments_runners.eng5_np.tests.test_helpers.builders import (
    BTSummaryBuilder,
    ComparisonRecordBuilder,
)


class TestGradeToRank:
    """Tests for grade_to_rank conversion function."""

    @pytest.mark.parametrize(
        "grade,expected_rank",
        [
            ("A", 0),
            ("A-", 1),
            ("B+", 2),
            ("B", 3),
            ("B-", 4),
            ("C+", 5),
            ("C", 6),
            ("C-", 7),
            ("D+", 8),
            ("D", 9),
            ("D-", 10),
            ("E+", 11),
            ("E", 12),
            ("E-", 13),
            ("F+", 14),
            ("F", 15),
        ],
    )
    def test_valid_grades_return_correct_rank(self, grade: str, expected_rank: int):
        """Each valid grade maps to its position in GRADE_ORDER."""
        assert grade_to_rank(grade) == expected_rank

    @pytest.mark.parametrize(
        "invalid_grade",
        [
            "UNKNOWN",
            "X",
            "",
            "A+",  # Not in ENG5 NP scale
            "a",  # Lowercase not supported
            "Grade A",
        ],
    )
    def test_unknown_grades_return_sentinel(self, invalid_grade: str):
        """Unknown grades return 99 sentinel value."""
        assert grade_to_rank(invalid_grade) == 99

    def test_grade_order_length(self):
        """GRADE_ORDER contains exactly 16 grades."""
        assert len(GRADE_ORDER) == 16


class TestComputeKendallTau:
    """Tests for Kendall's tau rank correlation computation."""

    def test_perfect_agreement_returns_one(self):
        """Identical rankings yield tau = 1.0."""
        actual = [1, 2, 3, 4, 5]
        expected = [1, 2, 3, 4, 5]
        assert compute_kendall_tau(actual, expected) == 1.0

    def test_perfect_disagreement_returns_negative_one(self):
        """Perfectly reversed rankings yield tau = -1.0."""
        actual = [5, 4, 3, 2, 1]
        expected = [1, 2, 3, 4, 5]
        assert compute_kendall_tau(actual, expected) == -1.0

    def test_single_element_returns_zero(self):
        """Single-element lists have no pairs to compare."""
        assert compute_kendall_tau([1], [1]) == 0.0

    def test_empty_list_returns_zero(self):
        """Empty lists return zero tau."""
        assert compute_kendall_tau([], []) == 0.0

    def test_partial_correlation_one_swap(self):
        """One adjacent swap gives tau = 0.8 for 5 elements."""
        # 5 elements = 10 pairs, one swap = one discordant pair
        actual = [1, 3, 2, 4, 5]  # Swapped positions 2 and 3
        expected = [1, 2, 3, 4, 5]
        # tau = (concordant - discordant) / total = (9 - 1) / 10 = 0.8
        assert compute_kendall_tau(actual, expected) == pytest.approx(0.8)

    def test_partial_correlation_two_swaps(self):
        """Two swaps gives tau = 0.6 for 5 elements."""
        actual = [1, 3, 2, 5, 4]  # Two adjacent swaps
        expected = [1, 2, 3, 4, 5]
        # tau = (8 - 2) / 10 = 0.6
        assert compute_kendall_tau(actual, expected) == pytest.approx(0.6)

    def test_tau_with_ties(self):
        """Tau handles tied ranks (product = 0)."""
        actual = [1, 2, 2, 4, 5]  # Tie at position 2
        expected = [1, 2, 3, 4, 5]
        # Ties are neither concordant nor discordant
        tau = compute_kendall_tau(actual, expected)
        assert -1.0 <= tau <= 1.0


class TestDetectInversions:
    """Tests for _detect_inversions inversion detection."""

    def test_detects_inversion_when_lower_grade_wins(self):
        """Inversion recorded when worse grade beats better grade."""
        comparisons = [
            ComparisonRecordBuilder()
            .with_winner("student::anchor_e")
            .with_loser("student::anchor_a")
            .with_confidence(3.5)
            .with_justification("Better structure")
            .build()
        ]
        grade_map = {"anchor_e": "E-", "anchor_a": "A"}

        inversions = _detect_inversions(comparisons, grade_map)

        assert len(inversions) == 1
        assert inversions[0].higher_grade == "A"
        assert inversions[0].lower_grade == "E-"
        assert inversions[0].winner == "anchor_e"

    def test_no_inversion_when_higher_grade_wins(self):
        """No inversion when expected winner wins."""
        comparisons = [
            ComparisonRecordBuilder()
            .with_winner("student::anchor_a")
            .with_loser("student::anchor_f")
            .build()
        ]
        grade_map = {"anchor_a": "A", "anchor_f": "F"}

        inversions = _detect_inversions(comparisons, grade_map)

        assert len(inversions) == 0

    def test_no_inversion_for_same_grade_comparison(self):
        """Same-grade matchups are not inversions."""
        comparisons = [
            ComparisonRecordBuilder()
            .with_winner("student::anchor_a1")
            .with_loser("student::anchor_a2")
            .build()
        ]
        grade_map = {"anchor_a1": "A", "anchor_a2": "A"}

        inversions = _detect_inversions(comparisons, grade_map)

        assert len(inversions) == 0

    def test_captures_confidence_and_justification(self):
        """Inversion records include confidence and justification."""
        comparisons = [
            ComparisonRecordBuilder()
            .with_winner("student::anchor_f")
            .with_loser("student::anchor_b")
            .with_confidence(4.5)
            .with_justification("Test justification text")
            .build()
        ]
        grade_map = {"anchor_f": "F", "anchor_b": "B"}

        inversions = _detect_inversions(comparisons, grade_map)

        assert len(inversions) == 1
        assert inversions[0].confidence == 4.5
        assert inversions[0].justification == "Test justification text"

    def test_handles_unknown_grades(self):
        """Comparisons with unknown grades handled gracefully."""
        comparisons = [
            ComparisonRecordBuilder()
            .with_winner("student::unknown_anchor")
            .with_loser("student::anchor_a")
            .build()
        ]
        grade_map = {"anchor_a": "A"}  # unknown_anchor not in map

        inversions = _detect_inversions(comparisons, grade_map)

        # Unknown grade gets rank 99, so beating A (rank 0) is an inversion
        assert len(inversions) == 1
        assert inversions[0].lower_grade == "UNKNOWN"

    def test_handles_none_confidence(self):
        """Handles None confidence value in comparison record."""
        comparisons = [
            {
                "winner_id": "student::anchor_f",
                "loser_id": "student::anchor_a",
                "confidence": None,
                "justification": None,
            }
        ]
        grade_map = {"anchor_f": "F", "anchor_a": "A"}

        inversions = _detect_inversions(comparisons, grade_map)

        assert len(inversions) == 1
        assert inversions[0].confidence == 0.0


class TestBuildAnchorResults:
    """Tests for _build_anchor_results internal function."""

    def test_builds_results_from_bt_summary(self):
        """Creates AnchorResult for each BT summary entry."""
        bt_summary = [
            BTSummaryBuilder()
            .with_essay_id("student::anchor_001")
            .with_theta(2.5)
            .with_rank(1)
            .build(),
            BTSummaryBuilder()
            .with_essay_id("student::anchor_002")
            .with_theta(-1.0)
            .with_rank(2)
            .build(),
        ]
        comparisons: list[dict] = []
        grade_map = {"anchor_001": "A", "anchor_002": "C"}

        results = _build_anchor_results(bt_summary, comparisons, grade_map)

        assert len(results) == 2
        # Results sorted by expected grade
        assert results[0].anchor_id == "anchor_001"
        assert results[0].expected_grade == "A"
        assert results[0].bt_score == 2.5
        assert results[1].anchor_id == "anchor_002"
        assert results[1].expected_grade == "C"

    def test_computes_win_loss_from_comparisons(self):
        """Correctly tallies wins and losses from comparison records."""
        bt_summary = [
            BTSummaryBuilder().with_essay_id("student::anchor_001").with_rank(1).build(),
            BTSummaryBuilder().with_essay_id("student::anchor_002").with_rank(2).build(),
        ]
        comparisons = [
            ComparisonRecordBuilder()
            .with_winner("student::anchor_001")
            .with_loser("student::anchor_002")
            .build(),
            ComparisonRecordBuilder()
            .with_winner("student::anchor_001")
            .with_loser("student::anchor_002")
            .build(),
        ]
        grade_map = {"anchor_001": "A", "anchor_002": "C"}

        results = _build_anchor_results(bt_summary, comparisons, grade_map)

        # anchor_001 won twice
        anchor_001_result = next(r for r in results if r.anchor_id == "anchor_001")
        assert anchor_001_result.wins == 2
        assert anchor_001_result.losses == 0

        # anchor_002 lost twice
        anchor_002_result = next(r for r in results if r.anchor_id == "anchor_002")
        assert anchor_002_result.wins == 0
        assert anchor_002_result.losses == 2

    def test_assigns_expected_ranks_by_grade_order(self):
        """Expected ranks assigned based on grade ordering."""
        bt_summary = [
            BTSummaryBuilder().with_essay_id("student::anchor_c").with_rank(1).build(),
            BTSummaryBuilder().with_essay_id("student::anchor_a").with_rank(2).build(),
        ]
        comparisons: list[dict] = []
        grade_map = {"anchor_a": "A", "anchor_c": "C"}

        results = _build_anchor_results(bt_summary, comparisons, grade_map)

        # Sorted by expected grade: A should be first
        assert results[0].anchor_id == "anchor_a"
        assert results[0].expected_rank == 1
        assert results[1].anchor_id == "anchor_c"
        assert results[1].expected_rank == 2

    def test_handles_missing_grade_in_map(self):
        """Unknown anchor IDs get 'UNKNOWN' grade."""
        bt_summary = [
            BTSummaryBuilder().with_essay_id("student::unknown_anchor").with_rank(1).build(),
        ]
        comparisons: list[dict] = []
        grade_map = {}  # Empty map

        results = _build_anchor_results(bt_summary, comparisons, grade_map)

        assert len(results) == 1
        assert results[0].expected_grade == "UNKNOWN"

    def test_calculates_win_rate_correctly(self):
        """Win rate = wins / (wins + losses)."""
        bt_summary = [
            BTSummaryBuilder().with_essay_id("student::anchor_001").with_rank(1).build(),
        ]
        comparisons = [
            ComparisonRecordBuilder()
            .with_winner("student::anchor_001")
            .with_loser("student::other")
            .build(),
            ComparisonRecordBuilder()
            .with_winner("student::other")
            .with_loser("student::anchor_001")
            .build(),
        ]
        grade_map = {"anchor_001": "A"}

        results = _build_anchor_results(bt_summary, comparisons, grade_map)

        assert results[0].wins == 1
        assert results[0].losses == 1
        assert results[0].win_rate == 0.5

    def test_handles_zero_total_comparisons(self):
        """Win rate is 0.0 when anchor has no comparisons."""
        bt_summary = [
            BTSummaryBuilder().with_essay_id("student::anchor_001").with_rank(1).build(),
        ]
        comparisons: list[dict] = []  # No comparisons
        grade_map = {"anchor_001": "A"}

        results = _build_anchor_results(bt_summary, comparisons, grade_map)

        assert results[0].wins == 0
        assert results[0].losses == 0
        assert results[0].win_rate == 0.0


class TestFormatReport:
    """Tests for _format_report markdown generation."""

    def test_includes_summary_metrics_section(self):
        """Report contains Summary Metrics table."""
        report = _format_report(
            batch_id="test-batch",
            timestamp="2025-01-01T00:00:00",
            system_prompt_text=None,
            rubric_text=None,
            total_comparisons=10,
            inversion_count=2,
            kendall_tau=0.85,
            zero_win_count=1,
            anchor_results=[],
            inversions=[],
        )

        assert "## Summary Metrics" in report
        assert "| Total comparisons | 10 |" in report
        assert "| Direct inversions | 2 |" in report
        assert "| Kendall's tau | 0.850 |" in report
        assert "| Zero-win anchors | 1 |" in report

    def test_includes_per_anchor_results_table(self):
        """Report contains Per-Anchor Results table."""
        anchor_results = [
            AnchorResult(
                anchor_id="anchor_001",
                expected_grade="A",
                bt_score=2.5,
                actual_rank=1,
                expected_rank=1,
                wins=5,
                losses=1,
                win_rate=0.833,
            )
        ]

        report = _format_report(
            batch_id="test-batch",
            timestamp="2025-01-01T00:00:00",
            system_prompt_text=None,
            rubric_text=None,
            total_comparisons=6,
            inversion_count=0,
            kendall_tau=1.0,
            zero_win_count=0,
            anchor_results=anchor_results,
            inversions=[],
        )

        assert "## Per-Anchor Results" in report
        assert "anchor_001" in report
        assert "| A |" in report

    def test_includes_inversions_section_when_present(self):
        """Inversions section appears only when inversions exist."""
        inversions = [
            Inversion(
                higher_grade_anchor="anchor_a",
                higher_grade="A",
                lower_grade_anchor="anchor_f",
                lower_grade="F",
                winner="anchor_f",
                confidence=3.5,
                justification="Better structure",
            )
        ]

        report = _format_report(
            batch_id="test-batch",
            timestamp="2025-01-01T00:00:00",
            system_prompt_text=None,
            rubric_text=None,
            total_comparisons=1,
            inversion_count=1,
            kendall_tau=0.0,
            zero_win_count=0,
            anchor_results=[],
            inversions=inversions,
        )

        assert "## Detected Inversions" in report
        assert "anchor_a (A)" in report
        assert "anchor_f (F)" in report

    def test_omits_inversions_section_when_empty(self):
        """No inversions section when inversions list is empty."""
        report = _format_report(
            batch_id="test-batch",
            timestamp="2025-01-01T00:00:00",
            system_prompt_text=None,
            rubric_text=None,
            total_comparisons=10,
            inversion_count=0,
            kendall_tau=1.0,
            zero_win_count=0,
            anchor_results=[],
            inversions=[],
        )

        assert "## Detected Inversions" not in report

    def test_includes_prompts_for_reproducibility(self):
        """System prompt and rubric included in report."""
        report = _format_report(
            batch_id="test-batch",
            timestamp="2025-01-01T00:00:00",
            system_prompt_text="Test system prompt",
            rubric_text="Test rubric content",
            total_comparisons=0,
            inversion_count=0,
            kendall_tau=0.0,
            zero_win_count=0,
            anchor_results=[],
            inversions=[],
        )

        assert "## Prompts Used (for reproducibility)" in report
        assert "### System Prompt" in report
        assert "Test system prompt" in report
        assert "### Judge Rubric" in report
        assert "Test rubric content" in report

    def test_truncates_long_justifications(self):
        """Justifications over 50 chars are truncated."""
        long_justification = "A" * 100  # 100 characters
        inversions = [
            Inversion(
                higher_grade_anchor="anchor_a",
                higher_grade="A",
                lower_grade_anchor="anchor_f",
                lower_grade="F",
                winner="anchor_f",
                confidence=3.5,
                justification=long_justification,
            )
        ]

        report = _format_report(
            batch_id="test-batch",
            timestamp="2025-01-01T00:00:00",
            system_prompt_text=None,
            rubric_text=None,
            total_comparisons=1,
            inversion_count=1,
            kendall_tau=0.0,
            zero_win_count=0,
            anchor_results=[],
            inversions=inversions,
        )

        # Should contain truncated version with "..."
        assert "A" * 50 + "..." in report
        # Should not contain full 100-char version
        assert long_justification not in report


class TestGenerateAlignmentReport:
    """Tests for generate_alignment_report main entry point."""

    def test_creates_report_file_with_correct_naming(self, tmp_path: Path):
        """Report file named anchor_align_{batch_id}_{timestamp}.md."""
        report_path = generate_alignment_report(
            hydrator=None,
            anchor_grade_map={},
            system_prompt_text=None,
            rubric_text=None,
            batch_id="test-batch-001",
            output_dir=tmp_path,
        )

        assert report_path.exists()
        assert report_path.name.startswith("anchor_align_test-batch-001_")
        assert report_path.suffix == ".md"

    def test_handles_none_hydrator(self, tmp_path: Path):
        """Generates minimal report when hydrator is None."""
        report_path = generate_alignment_report(
            hydrator=None,
            anchor_grade_map={"anchor_001": "A"},
            system_prompt_text="Test prompt",
            rubric_text="Test rubric",
            batch_id="no-hydrator-test",
            output_dir=tmp_path,
        )

        assert report_path.exists()
        content = report_path.read_text()
        assert "| Total comparisons | 0 |" in content

    def test_writes_utf8_encoded_content(self, tmp_path: Path):
        """Report written with UTF-8 encoding."""
        # Use unicode characters in prompts
        report_path = generate_alignment_report(
            hydrator=None,
            anchor_grade_map={},
            system_prompt_text="Test with émojis: 🎯",
            rubric_text="Français: été, naïve",
            batch_id="utf8-test",
            output_dir=tmp_path,
        )

        # Should read without encoding errors
        content = report_path.read_text(encoding="utf-8")
        assert "🎯" in content
        assert "été" in content
