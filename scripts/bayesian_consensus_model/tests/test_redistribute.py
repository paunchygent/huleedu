from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scripts.bayesian_consensus_model import redistribute_core as core
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


def test_optimize_cli_writes_outputs(tmp_path: Path, pairs_csv: Path) -> None:
    optimized_csv = tmp_path / "optimized.csv"
    report_path = tmp_path / "report.json"
    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "optimize-pairs",
            "--mode",
            "synthetic",
            "--output-csv",
            str(optimized_csv),
            "--total-slots",
            "24",
            "--max-repeat",
            "2",
            "--report-json",
            str(report_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert optimized_csv.exists()
    assert report_path.exists()

    rows = list(csv.reader(optimized_csv.open()))
    assert len(rows) == 1 + 24

    report = json.loads(report_path.read_text())
    assert report["optimized"]["total_pairs"] == 24
    assert "log_det_gain" in report
