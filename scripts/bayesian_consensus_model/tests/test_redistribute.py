from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scripts.bayesian_consensus_model import redistribute_core as core
from scripts.bayesian_consensus_model.d_optimal_workflow import (
    DEFAULT_ANCHOR_ORDER,
    ComparisonRecord,
    load_baseline_payload,
    load_dynamic_spec,
    load_previous_comparisons_from_csv,
    optimize_from_dynamic_spec,
    optimize_from_payload,
)
from scripts.bayesian_consensus_model.redistribute_pairs import app as cli_app


@pytest.fixture()
def pairs_csv(tmp_path: Path) -> Path:
    path = tmp_path / "pairs.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pair_id", "essay_a_id", "essay_b_id", "comparison_type", "status"])
        writer.writerows(
            [
                (1, "JA24", "A1", "student_anchor", "core"),
                (2, "JA24", "B1", "student_anchor", "core"),
                (3, "II24", "A1", "student_anchor", "core"),
                (4, "II24", "B1", "student_anchor", "core"),
                (5, "ES24", "A1", "student_anchor", "extra"),
                (6, "ES24", "B1", "student_anchor", "extra"),
            ]
        )
    return path


def test_read_pairs_orders_by_status(pairs_csv: Path) -> None:
    comparisons = core.read_pairs(pairs_csv)
    statuses = [comparison.status for comparison in comparisons]
    assert statuses[:4] == ["core"] * 4
    assert statuses[4:] == ["extra", "extra"]


def test_select_comparisons_respects_pool(pairs_csv: Path) -> None:
    comparisons = core.read_pairs(pairs_csv)
    selected_core = core.select_comparisons(comparisons, core.StatusSelector.CORE, total_needed=4)
    assert len(selected_core) == 4
    with pytest.raises(ValueError):
        core.select_comparisons(comparisons, core.StatusSelector.CORE, total_needed=6)


def test_compute_quota_distribution_handles_shortage() -> None:
    names = ["R1", "R2", "R3"]
    quotas = core.compute_quota_distribution(names, desired_per_rater=3, total_available=5)
    assert sum(quotas.values()) == 5
    assert max(quotas.values()) <= 3
    assert set(quotas) == set(names)


def test_assign_pairs_accepts_mixed_quotas(pairs_csv: Path) -> None:
    comparisons = core.read_pairs(pairs_csv)
    quotas = {"R1": 2, "R2": 1, "R3": 1}
    total_needed = sum(quotas.values())
    selected = core.select_comparisons(
        comparisons,
        core.StatusSelector.CORE,
        total_needed=total_needed,
    )
    assignments = core.assign_pairs(selected, list(quotas), quotas)
    assert len(assignments) == 4
    for name in quotas:
        assert sum(1 for rater, _ in assignments if rater == name) == quotas[name]


def test_assign_and_write(tmp_path: Path, pairs_csv: Path) -> None:
    comparisons = core.read_pairs(pairs_csv)
    selected = core.select_comparisons(comparisons, core.StatusSelector.ALL, total_needed=6)
    raters = core.build_rater_list(3, None)
    assignments = core.assign_pairs(selected, raters, per_rater=2)
    assert len(assignments) == 6
    output_csv = tmp_path / "assignments.csv"
    core.write_assignments(output_csv, assignments)
    lines = output_csv.read_text().strip().splitlines()
    assert len(lines) == 1 + len(assignments)


def test_cli_generates_assignments(tmp_path: Path, pairs_csv: Path) -> None:
    output_csv = tmp_path / "cli_assignments.csv"
    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "redistribute",
            "--pairs-csv",
            str(pairs_csv),
            "--output-csv",
            str(output_csv),
            "--raters",
            "2",
            "--per-rater",
            "2",
            "--include-status",
            "core",
        ],
    )
    assert result.exit_code == 0, result.output
    assert output_csv.exists()
    lines = output_csv.read_text().strip().splitlines()
    assert len(lines) == 1 + 4  # header + 4 assignments


def test_assign_pairs_balances_comparison_types() -> None:
    comparisons = [
        core.Comparison(idx, student, anchor, "student_anchor", "core")
        for idx, (student, anchor) in enumerate(
            [
                ("JA24", "A1"),
                ("JA24", "B1"),
                ("II24", "A1"),
                ("II24", "B1"),
                ("ES24", "A1"),
                ("ES24", "B1"),
            ],
            start=1,
        )
    ]
    comparisons.extend(
        [
            core.Comparison(7, "JA24", "II24", "student_student", "core"),
            core.Comparison(8, "ES24", "II24", "student_student", "core"),
            core.Comparison(9, "JA24", "ES24", "student_student", "core"),
            core.Comparison(10, "A1", "B1", "anchor_anchor", "core"),
            core.Comparison(11, "A1", "C+", "anchor_anchor", "core"),
            core.Comparison(12, "B1", "C+", "anchor_anchor", "core"),
        ]
    )
    raters = ["R1", "R2", "R3"]
    assignments = core.assign_pairs(comparisons, raters, per_rater=4)
    assert len(assignments) == 12

    per_rater_types = defaultdict(set)
    for rater, comparison in assignments:
        per_rater_types[rater].add(comparison.comparison_type)

    for types in per_rater_types.values():
        assert "student_anchor" in types
        assert len(types) >= 2  # ensure some mix of comparison types


def test_cli_handles_pair_shortage(tmp_path: Path, pairs_csv: Path) -> None:
    output_csv = tmp_path / "cli_shortage.csv"
    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "redistribute",
            "--pairs-csv",
            str(pairs_csv),
            "--output-csv",
            str(output_csv),
            "--raters",
            "3",
            "--per-rater",
            "2",
            "--include-status",
            "core",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Requested 6 comparisons but only 4 available." in result.output
    assert "min" in result.output and "max" in result.output
    lines = output_csv.read_text().strip().splitlines()
    # header + available_total assignments (4 core comparisons)
    assert len(lines) == 1 + 4


def test_optimize_payload_errors_when_slots_too_small(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline_small.json"
    payload = {
        "total_slots": 3,
        "comparisons": [
            {
                "essay_a_id": "JA24",
                "essay_b_id": "A1",
                "comparison_type": "student_anchor",
                "status": "core",
            }
        ],
        "anchor_order": DEFAULT_ANCHOR_ORDER,
    }
    baseline_path.write_text(json.dumps(payload))

    payload_obj = load_baseline_payload(baseline_path)

    with pytest.raises(ValueError, match="Minimum required slots"):
        optimize_from_payload(
            payload_obj,
            total_slots=5,
            max_repeat=2,
            anchor_order=None,
            status_filter=None,
        )


def test_load_baseline_payload_accepts_empty_array(tmp_path: Path) -> None:
    payload_path = tmp_path / "empty_payload.json"
    payload_path.write_text(
        json.dumps(
            {
                "comparisons": [],
                "anchor_order": DEFAULT_ANCHOR_ORDER,
                "status_filter": ["core"],
            }
        )
    )

    payload = load_baseline_payload(payload_path)

    assert payload.records == []
    assert payload.anchor_order == DEFAULT_ANCHOR_ORDER
    assert payload.status_filter == ["core"]
    assert payload.total_slots is None


def test_load_baseline_payload_preserves_slots_and_status_filter(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps(
            {
                "comparisons": [
                    {
                        "essay_a_id": "JA24",
                        "essay_b_id": "A1",
                        "comparison_type": "student_anchor",
                        "status": "core",
                    }
                ],
                "status_filter": ["core", "extra"],
                "total_slots": 12,
            }
        )
    )

    payload = load_baseline_payload(payload_path)

    assert len(payload.records) == 1
    assert payload.records[0]["essay_a_id"] == "JA24"
    assert payload.status_filter == ["core", "extra"]
    assert payload.total_slots == 12


# Dynamic Spec Tests


def test_load_dynamic_spec_validates_empty_students() -> None:
    with pytest.raises(ValueError, match="Students list cannot be empty"):
        load_dynamic_spec(students=[], total_slots=20)


def test_load_dynamic_spec_validates_total_slots() -> None:
    students = ["JA24", "II24"]
    # Minimum required: anchor adjacency (11) + locked pairs (0) = 11
    with pytest.raises(ValueError, match="Total slots.*insufficient"):
        load_dynamic_spec(students=students, total_slots=5)


def test_load_dynamic_spec_validates_locked_pair_essay_ids() -> None:
    students = ["JA24", "II24"]
    locked_pairs = [("JA24", "UNKNOWN")]
    with pytest.raises(ValueError, match="references unknown essay ID: UNKNOWN"):
        load_dynamic_spec(students=students, locked_pairs=locked_pairs, total_slots=20)


def test_load_dynamic_spec_defaults_to_standard_anchors() -> None:
    students = ["JA24", "II24"]
    spec = load_dynamic_spec(students=students, total_slots=20)
    assert list(spec.anchors) == list(DEFAULT_ANCHOR_ORDER)


def test_load_dynamic_spec_accepts_custom_anchors() -> None:
    students = ["JA24", "II24"]
    custom_anchors = ["A1", "B1", "C+"]
    spec = load_dynamic_spec(students=students, anchors=custom_anchors, total_slots=10)
    assert list(spec.anchors) == custom_anchors


def test_optimize_from_dynamic_spec_builds_design() -> None:
    students = ["JA24", "II24", "ES24"]
    spec = load_dynamic_spec(
        students=students,
        include_anchor_anchor=True,
        total_slots=24,
    )
    result = optimize_from_dynamic_spec(spec, max_repeat=2)

    assert result.total_comparisons == 24
    assert len(result.students) == 3
    assert result.optimized_log_det > float("-inf")
    assert "student_anchor" in result.optimized_diagnostics.type_counts


def test_optimize_from_dynamic_spec_respects_locked_pairs() -> None:
    students = ["JA24", "II24"]
    locked_pairs = [("JA24", "A1"), ("II24", "B1")]
    spec = load_dynamic_spec(
        students=students,
        locked_pairs=locked_pairs,
        total_slots=20,
    )
    result = optimize_from_dynamic_spec(spec, max_repeat=2)

    # Check that locked pairs appear in the optimized design
    design_keys = {
        (entry.candidate.essay_a, entry.candidate.essay_b) for entry in result.optimized_design
    }
    for pair in locked_pairs:
        assert pair in design_keys


def test_optimize_from_dynamic_spec_respects_anchor_toggle() -> None:
    students = ["JA24", "II24"]
    # Test with anchor-anchor disabled
    spec_no_aa = load_dynamic_spec(
        students=students,
        include_anchor_anchor=False,
        total_slots=20,
    )
    result_no_aa = optimize_from_dynamic_spec(spec_no_aa, max_repeat=2)

    # Should have no anchor-anchor pairs (except required adjacency constraints)
    aa_count = result_no_aa.optimized_diagnostics.type_counts.get("anchor_anchor", 0)
    # Anchor adjacency is 11 pairs (12 anchors - 1)
    assert aa_count == 11  # Only adjacency constraints


def test_cli_optimize_with_dynamic_spec(tmp_path: Path) -> None:
    output_csv = tmp_path / "optimized_dynamic.csv"
    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "optimize-pairs",
            "--student",
            "JA24",
            "--student",
            "II24",
            "--student",
            "ES24",
            "--total-slots",
            "24",
            "--max-repeat",
            "2",
            "--output-csv",
            str(output_csv),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output_csv.exists()
    rows = list(csv.reader(output_csv.open()))
    assert len(rows) == 1 + 24  # header + 24 pairs


def test_cli_optimize_with_locked_pairs(tmp_path: Path) -> None:
    output_csv = tmp_path / "optimized_locked.csv"
    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "optimize-pairs",
            "--student",
            "JA24",
            "--student",
            "II24",
            "--total-slots",
            "20",
            "--lock-pair",
            "JA24,A1",
            "--lock-pair",
            "II24,B1",
            "--output-csv",
            str(output_csv),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output_csv.exists()

    # Verify locked pairs are in output
    with output_csv.open() as f:
        reader = csv.DictReader(f)
        pairs = {(row["essay_a_id"], row["essay_b_id"]) for row in reader}
        assert ("JA24", "A1") in pairs
        assert ("II24", "B1") in pairs


def test_cli_optimize_with_report_includes_dynamic_spec(tmp_path: Path) -> None:
    output_csv = tmp_path / "optimized.csv"
    report_path = tmp_path / "report.json"
    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "optimize-pairs",
            "--student",
            "JA24,II24",
            "--total-slots",
            "20",
            "--output-csv",
            str(output_csv),
            "--report-json",
            str(report_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert report_path.exists()

    report = json.loads(report_path.read_text())
    assert "dynamic_spec" in report
    assert report["dynamic_spec"]["students"] == ["JA24", "II24"]
    assert report["dynamic_spec"]["total_slots"] == 20
    assert report["dynamic_spec"]["include_anchor_anchor"] is True

# ============================================================================
# Multi-Session Workflow Tests (Session 1 vs Session 2+)
# ============================================================================


def test_session1_workflow_no_previous_comparisons() -> None:
    """Session 1: Generate fresh comparisons with baseline coverage (no history)."""
    students = ["JA24", "II24", "ES24"]
    spec = load_dynamic_spec(
        students=students,
        include_anchor_anchor=True,
        previous_comparisons=[],  # Session 1: no historical data
        total_slots=84,
    )
    result = optimize_from_dynamic_spec(spec, max_repeat=3)

    # Verify baseline coverage: each student should have anchor comparisons
    student_anchor_pairs = [
        entry for entry in result.optimized_design
        if entry.candidate.comparison_type == "student_anchor"
    ]
    students_with_coverage = set()
    anchor_set = set(DEFAULT_ANCHOR_ORDER)
    for entry in student_anchor_pairs:
        a, b = entry.candidate.essay_a, entry.candidate.essay_b
        if a in anchor_set:
            students_with_coverage.add(b)
        elif b in anchor_set:
            students_with_coverage.add(a)

    # All students should have at least one anchor comparison
    for student in students:
        assert student in students_with_coverage, f"Student {student} missing anchor coverage"

    assert result.total_comparisons == 84
    assert result.optimized_log_det > float("-inf")


def test_session2_workflow_with_previous_comparisons() -> None:
    """Session 2: Build on previous session with coverage analysis."""
    students = ["JA24", "II24", "ES24"]

    # Simulate Session 1 comparisons (only JA24 has anchor coverage)
    previous_comparisons = [
        ComparisonRecord("JA24", "A1", "student_anchor", "core"),
        ComparisonRecord("JA24", "A2", "student_anchor", "core"),
    ]

    spec = load_dynamic_spec(
        students=students,
        include_anchor_anchor=True,
        previous_comparisons=previous_comparisons,
        total_slots=84,
    )
    result = optimize_from_dynamic_spec(spec, max_repeat=3)

    # Check that baseline design reflects previous comparisons
    assert len(result.baseline_design) == 2
    baseline_keys = {
        (entry.candidate.essay_a, entry.candidate.essay_b)
        for entry in result.baseline_design
    }
    assert ("JA24", "A1") in baseline_keys
    assert ("JA24", "A2") in baseline_keys

    # Verify coverage analysis: II24 and ES24 should get required anchor pairs
    # (since they had no coverage in baseline)
    student_anchor_pairs = [
        entry for entry in result.optimized_design
        if entry.candidate.comparison_type == "student_anchor"
    ]
    students_with_coverage = set()
    anchor_set = set(DEFAULT_ANCHOR_ORDER)
    for entry in student_anchor_pairs:
        a, b = entry.candidate.essay_a, entry.candidate.essay_b
        if a in anchor_set:
            students_with_coverage.add(b)
        elif b in anchor_set:
            students_with_coverage.add(a)

    # All students should have anchor coverage (combining baseline + new design)
    for student in students:
        assert student in students_with_coverage, (
            f"Student {student} missing anchor coverage in Session 2"
        )

    assert result.total_comparisons == 84
    assert result.required_pair_count > 0  # Should derive required pairs for II24, ES24


def test_load_previous_comparisons_from_csv(tmp_path: Path) -> None:
    """Test loading previous comparisons from CSV file."""
    csv_path = tmp_path / "session1.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pair_id", "essay_a_id", "essay_b_id", "comparison_type", "status"])
        writer.writerows([
            (1, "JA24", "A1", "student_anchor", "core"),
            (2, "II24", "B1", "student_anchor", "core"),
            (3, "ES24", "A2", "student_anchor", "extra"),
        ])

    records = load_previous_comparisons_from_csv(csv_path)

    assert len(records) == 2  # Only "core" status by default
    assert records[0].essay_a_id == "JA24"
    assert records[0].essay_b_id == "A1"
    assert records[0].comparison_type == "student_anchor"
    assert records[0].status == "core"


def test_cli_optimize_with_previous_csv(tmp_path: Path) -> None:
    """Test CLI with --previous-csv flag for Session 2+ workflow."""
    # Create previous session CSV
    previous_csv = tmp_path / "session1.csv"
    with previous_csv.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["pair_id", "essay_a_id", "essay_b_id", "comparison_type", "status"])
        writer.writerows([
            (1, "JA24", "A1", "student_anchor", "core"),
            (2, "JA24", "A2", "student_anchor", "core"),
        ])

    output_csv = tmp_path / "session2.csv"
    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "optimize-pairs",
            "--student", "JA24",
            "--student", "II24",
            "--student", "ES24",
            "--previous-csv", str(previous_csv),
            "--total-slots", "84",
            "--output-csv", str(output_csv),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output_csv.exists()

    # Verify output mentions loading previous comparisons
    assert "Loaded 2 previous comparisons" in result.output

    # Verify output CSV has correct number of comparisons
    with output_csv.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert len(rows) == 84
