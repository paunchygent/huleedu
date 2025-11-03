"""Unit tests for the CJ confidence analytical helpers."""

from __future__ import annotations

import math

import pytest

from .cj_confidence_analysis import (
    boundary_crossing_confidence,
    bt_standard_error_from_counts,
    generate_confidence_table,
    logistic_comparison_confidence,
    logistic_confidence_label,
    rows_to_json,
)


def test_logistic_curve_monotonic() -> None:
    assert logistic_comparison_confidence(1) < logistic_comparison_confidence(10)
    assert logistic_comparison_confidence(10) < logistic_comparison_confidence(20)


@pytest.mark.parametrize(
    "confidence,label",
    [
        (0.80, "HIGH"),
        (0.50, "MID"),
        (0.10, "LOW"),
    ],
)
def test_logistic_label_mapping(confidence: float, label: str) -> None:
    assert logistic_confidence_label(confidence) == label


@pytest.mark.parametrize(
    "comparisons,expected",
    [
        (1, pytest.approx(2.0, rel=1e-3)),
        (4, pytest.approx(1.0, rel=1e-3)),
        (16, pytest.approx(0.5, rel=1e-3)),
    ],
)
def test_bt_standard_error_scaling(comparisons: int, expected: float) -> None:
    assert bt_standard_error_from_counts(comparisons) == expected


def test_boundary_confidence_increases_with_distance() -> None:
    se = 0.5
    near = boundary_crossing_confidence(0.05, se)
    far = boundary_crossing_confidence(0.20, se)
    assert near < far < 1.0


def test_generate_confidence_table_structure() -> None:
    rows = generate_confidence_table([5, 10], [0.15])
    assert len(rows) == 2
    assert rows[0].comparisons == 5
    assert rows[1].comparisons == 10
    assert rows[0].boundary_distance == pytest.approx(0.15)


def test_rows_to_json_formatting() -> None:
    rows = generate_confidence_table([5], [0.10])
    json_rows = rows_to_json(rows)
    assert json_rows[0]["comparisons"] == 5
    assert math.isclose(json_rows[0]["approx_se"], 0.8944, rel_tol=1e-3)
