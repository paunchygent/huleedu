from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scripts.bayesian_consensus_model import redistribute_core as core
from scripts.bayesian_consensus_model.redistribute_pairs import app as cli_app
from scripts.bayesian_consensus_model.d_optimal_workflow import (
    DEFAULT_ANCHOR_ORDER,
    load_baseline_payload,
    optimize_from_payload,
)


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
    assert report["anchor_adjacency_pairs"] == len(DEFAULT_ANCHOR_ORDER) - 1
    assert report["required_pairs"] == 0
    assert report["min_slots_required"] == report["anchor_adjacency_pairs"]


def test_optimize_cli_accepts_baseline_json(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    output_csv = tmp_path / "optimized_baseline.csv"
    payload = {
        "total_slots": 3,
        "comparisons": [
            {
                "essay_a_id": "JA24",
                "essay_b_id": "A1",
                "comparison_type": "student_anchor",
                "status": "core",
            },
            {
                "essay_a_id": "II24",
                "essay_b_id": "B1",
                "comparison_type": "student_anchor",
                "status": "core",
            },
            {
                "essay_a_id": "JA24",
                "essay_b_id": "II24",
                "comparison_type": "student_student",
                "status": "core",
            },
        ],
        "anchor_order": [
            "F+1",
            "F+2",
            "E-",
            "E+",
            "D-",
            "D+",
            "C-",
            "C+",
            "B1",
            "B2",
            "A1",
            "A2",
        ],
    }
    baseline_path.write_text(json.dumps(payload))

    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "optimize-pairs",
            "--mode",
            "session",
            "--baseline-json",
            str(baseline_path),
            "--output-csv",
            str(output_csv),
            "--total-slots",
            "15",
            "--max-repeat",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert output_csv.exists()
    rows = list(csv.reader(output_csv.open()))
    # header + requested optimized comparisons
    assert len(rows) == 1 + 15


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
