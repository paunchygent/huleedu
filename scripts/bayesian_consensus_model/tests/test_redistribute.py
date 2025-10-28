from __future__ import annotations

import csv
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
