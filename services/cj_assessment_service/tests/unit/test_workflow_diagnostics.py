"""Unit tests for workflow_diagnostics metrics helpers."""

from __future__ import annotations

from typing import Any

import pytest

from services.cj_assessment_service.cj_core_logic import workflow_context, workflow_diagnostics
from services.cj_assessment_service.cj_core_logic.workflow_decision import ContinuationDecision


class _DummyCounter:
    """Minimal counter implementation for metric increment tests."""

    def __init__(self) -> None:
        self.count = 0

    def inc(self) -> None:
        self.count += 1


class _DummyLabeledCounter:
    """Minimal labeled counter for decision metrics tests."""

    def __init__(self) -> None:
        self.count = 0
        self.labels_calls: list[dict[str, str]] = []

    def inc(self) -> None:
        self.count += 1

    def labels(self, **labels: str) -> "_DummyLabeledCounter":
        self.labels_calls.append(labels)
        return self


def _make_ctx(**overrides: Any) -> workflow_context.ContinuationContext:
    """Create a minimal ContinuationContext instance for diagnostics helpers."""
    base = dict(
        batch_id=1,
        callbacks_received=0,
        pending_callbacks=0,
        denominator=0,
        completed=0,
        failed=0,
        pairs_submitted=0,
        max_pairs_cap=0,
        pairs_remaining=0,
        budget_exhausted=False,
        callbacks_reached_cap=False,
        success_rate=None,
        success_rate_threshold=None,
        zero_successes=False,
        below_success_threshold=False,
        should_fail_due_to_success_rate=False,
        max_score_change=None,
        stability_passed=False,
        should_finalize=False,
        expected_essay_count=0,
        is_small_net=False,
        max_possible_pairs=0,
        successful_pairs_count=0,
        unique_coverage_complete=False,
        resampling_pass_count=0,
        small_net_resampling_cap=0,
        small_net_cap_reached=False,
        bt_se_summary={"mean_se": 0.1},
        bt_quality_flags=None,
        bt_se_inflated=False,
        comparison_coverage_sparse=False,
        has_isolated_items=False,
        metadata_updates={},
    )
    base.update(overrides)
    return workflow_context.ContinuationContext(**base)  # type: ignore[arg-type]


def test_record_bt_batch_quality_respects_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """BT batch-quality counters increment only when corresponding flags are True."""

    se_counter = _DummyCounter()
    sparse_counter = _DummyCounter()

    def _fake_get_business_metrics() -> dict[str, Any]:
        return {
            "cj_bt_se_inflated_batches_total": se_counter,
            "cj_bt_sparse_coverage_batches_total": sparse_counter,
        }

    monkeypatch.setattr(
        workflow_diagnostics,
        "get_business_metrics",
        _fake_get_business_metrics,
    )

    # Both flags True → both counters increment.
    ctx = _make_ctx(bt_se_inflated=True, comparison_coverage_sparse=True)
    workflow_diagnostics.record_bt_batch_quality(ctx)
    assert se_counter.count == 1
    assert sparse_counter.count == 1

    # Only SE inflated → only SE counter increments.
    ctx = _make_ctx(bt_se_inflated=True, comparison_coverage_sparse=False)
    workflow_diagnostics.record_bt_batch_quality(ctx)
    assert se_counter.count == 2
    assert sparse_counter.count == 1

    # No SE summary → nothing increments regardless of flags.
    ctx = _make_ctx(bt_se_summary=None, bt_se_inflated=True, comparison_coverage_sparse=True)
    workflow_diagnostics.record_bt_batch_quality(ctx)
    assert se_counter.count == 2
    assert sparse_counter.count == 1


def test_record_workflow_decision_uses_enum_values_for_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decision metric labels should match ContinuationDecision enum values."""

    decision_counter = _DummyLabeledCounter()

    def _fake_get_business_metrics() -> dict[str, Any]:
        return {"cj_workflow_decisions_total": decision_counter}

    monkeypatch.setattr(
        workflow_diagnostics,
        "get_business_metrics",
        _fake_get_business_metrics,
    )

    ctx = _make_ctx()

    for decision in ContinuationDecision:
        workflow_diagnostics.record_workflow_decision(ctx, decision)

    assert decision_counter.count == len(ContinuationDecision)
    seen_labels = {call["decision"] for call in decision_counter.labels_calls}
    expected_labels = {decision.value for decision in ContinuationDecision}
    assert seen_labels == expected_labels
