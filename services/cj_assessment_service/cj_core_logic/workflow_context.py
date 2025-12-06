from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ContinuationContext:
    """Derived continuation state used for internal decision making.

    This context is built from CJ batch state, processing metadata, BT scoring
    diagnostics, and coverage/small-net flags. It is intentionally JSON- and
    Pydantic-friendly so that it can be logged or persisted as needed.
    """

    batch_id: int
    callbacks_received: int
    pending_callbacks: int
    denominator: int

    completed: int
    failed: int

    pairs_submitted: int
    max_pairs_cap: int
    pairs_remaining: int
    budget_exhausted: bool
    callbacks_reached_cap: bool

    success_rate: float | None
    success_rate_threshold: float | None
    zero_successes: bool
    below_success_threshold: bool
    should_fail_due_to_success_rate: bool

    max_score_change: float | None
    stability_passed: bool
    should_finalize: bool

    expected_essay_count: int
    is_small_net: bool
    max_possible_pairs: int
    successful_pairs_count: int
    unique_coverage_complete: bool
    resampling_pass_count: int
    small_net_resampling_cap: int
    small_net_cap_reached: bool
    regular_batch_resampling_cap: int
    regular_batch_cap_reached: bool

    bt_se_summary: dict[str, float | int] | None
    bt_quality_flags: dict[str, bool] | None
    bt_se_inflated: bool
    comparison_coverage_sparse: bool
    has_isolated_items: bool

    metadata_updates: dict[str, Any]


def build_bt_metadata_updates(
    *,
    batch_state: Any,
    current_scores: dict[str, float],
    max_score_change: float | None,
    bt_se_summary: dict[str, float | int] | None,
    mean_se_threshold: float,
    max_se_threshold: float,
    min_mean_comparisons_threshold: float,
) -> tuple[dict[str, Any], dict[str, bool] | None, bool, bool, bool]:
    """Build BT scoring-related metadata and quality flags.

    This helper is intentionally pure and JSON-safe. It derives the metadata
    structure and boolean quality flags from the current BT scores and
    optional SE diagnostics summary, using numeric thresholds that have
    already been resolved from Settings by the caller.
    """

    metadata_updates: dict[str, Any] = {
        "bt_scores": current_scores,
        "last_scored_iteration": batch_state.current_iteration,
        "last_score_change": max_score_change,
    }

    bt_quality_flags: dict[str, bool] | None = None
    bt_se_inflated = False
    comparison_coverage_sparse = False
    has_isolated_items = False

    if bt_se_summary is not None:
        metadata_updates["bt_se_summary"] = bt_se_summary
        mean_se = float(bt_se_summary.get("mean_se", 0.0))
        max_se = float(bt_se_summary.get("max_se", 0.0))
        mean_comparisons_per_item = float(bt_se_summary.get("mean_comparisons_per_item", 0.0))
        isolated_items = int(bt_se_summary.get("isolated_items", 0))

        bt_se_inflated = mean_se > mean_se_threshold or max_se > max_se_threshold
        comparison_coverage_sparse = mean_comparisons_per_item < min_mean_comparisons_threshold
        has_isolated_items = isolated_items > 0

        bt_quality_flags = {
            "bt_se_inflated": bt_se_inflated,
            "comparison_coverage_sparse": comparison_coverage_sparse,
            "has_isolated_items": has_isolated_items,
        }
        metadata_updates["bt_quality_flags"] = bt_quality_flags

    return (
        metadata_updates,
        bt_quality_flags,
        bt_se_inflated,
        comparison_coverage_sparse,
        has_isolated_items,
    )


def build_small_net_context(
    *,
    expected_essay_count: int,
    max_possible_pairs: int,
    successful_pairs_count: int,
    unique_coverage_complete: bool,
    resampling_pass_count: int,
    min_resampling_net_size: int,
    max_resampling_passes_for_small_net: int,
    coverage_metrics: tuple[int, int] | None = None,
) -> tuple[int, bool, int, int, bool, int, int, bool]:
    """Build small-net and coverage-related continuation context.

    This helper is intentionally pure and JSON-safe. It combines the raw
    expected essay count, coverage metadata, and optional repository-derived
    coverage metrics into the fields used by ContinuationContext while
    preserving existing PR-2/PR-7 semantics:

    - Prefer metadata values when present, but allow coverage_metrics to
      "refresh" them when coverage has progressed further in the database.
    - Mark unique_coverage_complete when max_possible_pairs > 0 and
      successful_pairs_count >= max_possible_pairs, using the effective
      values after any coverage_metrics merge.
    - Compute is_small_net from expected_essay_count and the
      MIN_RESAMPLING_NET_SIZE threshold.
    - Derive the small-net resampling cap and cap-reached flag from
      MAX_RESAMPLING_PASSES_FOR_SMALL_NET.
    """

    # Normalize essay count.
    normalized_expected_essay_count = expected_essay_count or 0

    # Treat nets with essay_count <= MIN_RESAMPLING_NET_SIZE as small nets.
    # This aligns with ENG5 LOWER5 semantics where a "small batch" size of N
    # means all nets with N or fewer essays should follow small-net resampling
    # behaviour.
    is_small_net = normalized_expected_essay_count <= min_resampling_net_size

    # Prefer metadata coverage metrics but allow repository-derived
    # coverage_metrics to update them when coverage progresses between
    # iterations. This keeps metadata monotonic and avoids stale coverage
    # counts for small nets that accumulate successful pairs over multiple
    # waves.
    effective_max_possible_pairs = max_possible_pairs
    effective_successful_pairs_count = successful_pairs_count
    effective_unique_coverage_complete = unique_coverage_complete
    effective_resampling_pass_count = resampling_pass_count

    if coverage_metrics is not None and len(coverage_metrics) == 2:
        coverage_max_pairs, coverage_successful_pairs = coverage_metrics

        # Use the larger of metadata vs repository-derived values so that
        # coverage counts only ever move forwards.
        if isinstance(coverage_max_pairs, int) and coverage_max_pairs >= 0:
            effective_max_possible_pairs = max(effective_max_possible_pairs, coverage_max_pairs)
        if isinstance(coverage_successful_pairs, int) and coverage_successful_pairs >= 0:
            effective_successful_pairs_count = max(
                effective_successful_pairs_count,
                coverage_successful_pairs,
            )

    if (
        effective_max_possible_pairs > 0
        and effective_successful_pairs_count >= effective_max_possible_pairs
    ):
        effective_unique_coverage_complete = True

    small_net_resampling_cap = int(max_resampling_passes_for_small_net or 0)
    small_net_cap_reached = (
        is_small_net
        and effective_unique_coverage_complete
        and effective_resampling_pass_count >= small_net_resampling_cap
    )

    return (
        normalized_expected_essay_count,
        is_small_net,
        effective_max_possible_pairs,
        effective_successful_pairs_count,
        effective_unique_coverage_complete,
        effective_resampling_pass_count,
        small_net_resampling_cap,
        small_net_cap_reached,
    )
