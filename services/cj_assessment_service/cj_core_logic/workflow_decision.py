from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic import scoring_ranking
from services.cj_assessment_service.cj_core_logic.workflow_context import (
    ContinuationContext,
    build_bt_metadata_updates,
    build_small_net_context,
)
from services.cj_assessment_service.cj_core_logic.workflow_diagnostics import (
    record_bt_batch_quality,
)
from services.cj_assessment_service.protocols import CJComparisonRepositoryProtocol

if TYPE_CHECKING:
    from services.cj_assessment_service.config import Settings

logger = create_service_logger("cj_assessment_service.workflow_decision")


class ContinuationDecision(Enum):
    WAIT_FOR_CALLBACKS = "WAIT_FOR_CALLBACKS"
    FINALIZE_SCORING = "FINALIZE_SCORING"
    FINALIZE_FAILURE = "FINALIZE_FAILURE"
    REQUEST_MORE_COMPARISONS = "REQUEST_MORE_COMPARISONS"
    NO_OP = "NO_OP"


def _get_numeric_setting(settings: "Settings", name: str, default: float) -> float:
    """Safely extract a numeric settings value with a defensive fallback."""
    raw_value = getattr(settings, name, default)
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    return default


def _compute_success_metrics(
    completed: int,
    failed: int,
    callbacks_received: int,
    settings: "Settings",
) -> tuple[float | None, bool, bool, float | None]:
    """Compute success-rate related metrics without altering semantics.

    Returns:
        success_rate: completed / callbacks_received when callbacks > 0, else None
        zero_successes: True when callbacks > 0 and completed == 0
        below_success_threshold: True when success_rate < MIN_SUCCESS_RATE_THRESHOLD
        success_rate_threshold: Parsed numeric threshold or None when disabled
    """
    _ = failed  # preserved in signature for clarity, not needed directly

    success_rate: float | None = None
    success_rate_threshold_raw: Any = getattr(settings, "MIN_SUCCESS_RATE_THRESHOLD", None)
    success_rate_threshold: float | None
    if isinstance(success_rate_threshold_raw, (int, float)):
        success_rate_threshold = float(success_rate_threshold_raw)
    else:
        # Disable success-rate guard when settings are not numeric (e.g. loose mocks)
        success_rate_threshold = None

    if callbacks_received > 0:
        success_rate = completed / callbacks_received

    zero_successes = callbacks_received > 0 and completed == 0
    below_success_threshold = (
        success_rate is not None
        and success_rate_threshold is not None
        and success_rate < success_rate_threshold
    )

    return success_rate, zero_successes, below_success_threshold, success_rate_threshold


async def _derive_small_net_flags(
    *,
    batch_id: int,
    batch_state: Any,
    metadata: dict[str, Any],
    settings: "Settings",
    comparison_repository: CJComparisonRepositoryProtocol,
    session: Any,
    log_extra: dict[str, Any],
) -> tuple[
    int,
    bool,
    int,
    int,
    bool,
    int,
    int,
    bool,
]:
    """Derive small-net and coverage flags, preserving existing semantics."""

    expected_essay_count = (
        batch_state.batch_upload.expected_essay_count if batch_state.batch_upload else 0
    ) or 0

    max_possible_pairs = 0
    successful_pairs_count = 0
    unique_coverage_complete = False
    resampling_pass_count = 0

    # Prefer existing processing_metadata coverage when present (tests and
    # forward-looking specs already populate these fields), and fall back
    # to repository-derived metrics only when absent.
    if isinstance(metadata, dict):
        meta_max_pairs = metadata.get("max_possible_pairs")
        if isinstance(meta_max_pairs, int) and meta_max_pairs >= 0:
            max_possible_pairs = meta_max_pairs

        meta_successful_pairs = metadata.get("successful_pairs_count")
        if isinstance(meta_successful_pairs, int) and meta_successful_pairs >= 0:
            successful_pairs_count = meta_successful_pairs

        meta_unique_complete = metadata.get("unique_coverage_complete")
        if isinstance(meta_unique_complete, bool):
            unique_coverage_complete = meta_unique_complete

        existing_resampling_pass = metadata.get("resampling_pass_count")
        if isinstance(existing_resampling_pass, int) and existing_resampling_pass >= 0:
            resampling_pass_count = existing_resampling_pass

    coverage_metrics: tuple[int, int] | None = None

    # Refresh coverage metrics from the repository whenever coverage has not
    # yet been marked complete. This ensures that small-net metadata does not
    # get "stuck" with stale counts when additional successful comparisons
    # arrive across multiple waves.
    if not unique_coverage_complete:
        try:
            raw_coverage_metrics = await comparison_repository.get_coverage_metrics_for_batch(
                session=session,
                batch_id=batch_id,
            )
            if isinstance(raw_coverage_metrics, tuple) and len(raw_coverage_metrics) == 2:
                coverage_metrics = raw_coverage_metrics  # type: ignore[assignment]
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.error(
                "Failed to compute coverage metrics; treating coverage as incomplete",
                extra={**log_extra, "error": str(exc), "error_type": type(exc).__name__},
            )

    return build_small_net_context(
        expected_essay_count=expected_essay_count,
        max_possible_pairs=max_possible_pairs,
        successful_pairs_count=successful_pairs_count,
        unique_coverage_complete=unique_coverage_complete,
        resampling_pass_count=resampling_pass_count,
        min_resampling_net_size=getattr(settings, "MIN_RESAMPLING_NET_SIZE", 10),
        max_resampling_passes_for_small_net=getattr(
            settings,
            "MAX_RESAMPLING_PASSES_FOR_SMALL_NET",
            2,
        ),
        coverage_metrics=coverage_metrics,
    )


async def _build_continuation_context(
    *,
    batch_id: int,
    batch_state: Any,
    metadata: dict[str, Any],
    settings: "Settings",
    current_scores: dict[str, float],
    previous_scores: dict[str, float],
    callbacks_received: int,
    pending_callbacks: int,
    completed: int,
    failed: int,
    denominator: int,
    max_pairs_cap: int,
    pairs_submitted: int,
    pairs_remaining: int,
    budget_exhausted: bool,
    callbacks_reached_cap: bool,
    success_rate: float | None,
    success_rate_threshold: float | None,
    zero_successes: bool,
    below_success_threshold: bool,
    bt_se_summary: dict[str, float | int] | None,
    comparison_repository: CJComparisonRepositoryProtocol,
    session: Any,
    log_extra: dict[str, Any],
) -> ContinuationContext:
    """Compute all derived metrics and flags into a ContinuationContext."""

    max_score_change: float | None = None
    stability_passed = False

    if previous_scores:
        max_score_change = scoring_ranking.check_score_stability(
            current_scores,
            previous_scores,
            stability_threshold=settings.SCORE_STABILITY_THRESHOLD,
        )

        success_rate_ok = (
            success_rate is None
            or success_rate_threshold is None
            or success_rate >= success_rate_threshold
        )

        stability_passed = (
            callbacks_received >= settings.MIN_COMPARISONS_FOR_STABILITY_CHECK
            and max_score_change <= settings.SCORE_STABILITY_THRESHOLD
            and success_rate_ok
        )

    mean_se_threshold = _get_numeric_setting(settings, "BT_MEAN_SE_WARN_THRESHOLD", 0.4)
    max_se_threshold = _get_numeric_setting(settings, "BT_MAX_SE_WARN_THRESHOLD", 0.8)
    min_mean_comparisons_threshold = _get_numeric_setting(
        settings,
        "BT_MIN_MEAN_COMPARISONS_PER_ITEM",
        1.0,
    )

    (
        metadata_updates,
        bt_quality_flags,
        bt_se_inflated,
        comparison_coverage_sparse,
        has_isolated_items,
    ) = build_bt_metadata_updates(
        batch_state=batch_state,
        current_scores=current_scores,
        max_score_change=max_score_change,
        bt_se_summary=bt_se_summary,
        mean_se_threshold=mean_se_threshold,
        max_se_threshold=max_se_threshold,
        min_mean_comparisons_threshold=min_mean_comparisons_threshold,
    )

    (
        expected_essay_count,
        is_small_net,
        max_possible_pairs,
        successful_pairs_count,
        unique_coverage_complete,
        resampling_pass_count,
        small_net_resampling_cap,
        small_net_cap_reached,
    ) = await _derive_small_net_flags(
        batch_id=batch_id,
        batch_state=batch_state,
        metadata=metadata,
        settings=settings,
        comparison_repository=comparison_repository,
        session=session,
        log_extra=log_extra,
    )

    # Regular-batch resampling cap is derived from settings but enforced so that
    # non-small nets can never exceed the small-net resampling cap. Small nets
    # rely solely on small_net_resampling_cap and ignore the regular-batch cap.
    raw_regular_cap = int(
        _get_numeric_setting(settings, "MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH", 0.0) or 0
    )
    if is_small_net:
        regular_batch_resampling_cap = 0
    else:
        if small_net_resampling_cap > 0 and raw_regular_cap > small_net_resampling_cap:
            regular_batch_resampling_cap = small_net_resampling_cap
        else:
            regular_batch_resampling_cap = raw_regular_cap

    regular_batch_cap_reached = (
        not is_small_net
        and regular_batch_resampling_cap > 0
        and resampling_pass_count >= regular_batch_resampling_cap
    )

    # Only finalize on stability, completion denominator, global budget
    # exhaustion, or small-net Phase-2 resampling cap.
    should_finalize = (
        stability_passed or callbacks_reached_cap or budget_exhausted or small_net_cap_reached
    )

    # PR-2: when caps are reached but success-rate is too low, route to failure.
    raw_low_success = callbacks_received > 0 and (zero_successes or below_success_threshold)
    should_fail_due_to_success_rate = raw_low_success and (
        callbacks_reached_cap or budget_exhausted or small_net_cap_reached
    )

    logger.info(
        "Callback iteration complete; evaluated stability",
        extra={
            **log_extra,
            "callbacks_received": callbacks_received,
            "callbacks_reached_cap": callbacks_reached_cap,
            "denominator": denominator,
            "stability_passed": stability_passed,
            "max_score_change": max_score_change,
            "pairs_remaining": pairs_remaining,
            "budget_exhausted": budget_exhausted,
            "should_finalize": should_finalize,
            "success_rate": success_rate,
            "bt_se_inflated": bt_se_inflated,
            "comparison_coverage_sparse": comparison_coverage_sparse,
            "has_isolated_items": has_isolated_items,
            "success_rate_threshold": success_rate_threshold,
            "zero_successes": zero_successes,
            "should_fail_due_to_success_rate": should_fail_due_to_success_rate,
        },
    )

    ctx = ContinuationContext(
        batch_id=batch_id,
        callbacks_received=callbacks_received,
        pending_callbacks=pending_callbacks,
        denominator=denominator,
        completed=completed,
        failed=failed,
        pairs_submitted=pairs_submitted,
        max_pairs_cap=max_pairs_cap,
        pairs_remaining=pairs_remaining,
        budget_exhausted=budget_exhausted,
        callbacks_reached_cap=callbacks_reached_cap,
        success_rate=success_rate,
        success_rate_threshold=success_rate_threshold,
        zero_successes=zero_successes,
        below_success_threshold=below_success_threshold,
        should_fail_due_to_success_rate=should_fail_due_to_success_rate,
        max_score_change=max_score_change,
        stability_passed=stability_passed,
        should_finalize=should_finalize,
        expected_essay_count=expected_essay_count,
        is_small_net=is_small_net,
        max_possible_pairs=max_possible_pairs,
        successful_pairs_count=successful_pairs_count,
        unique_coverage_complete=unique_coverage_complete,
        resampling_pass_count=resampling_pass_count,
        small_net_resampling_cap=small_net_resampling_cap,
        small_net_cap_reached=small_net_cap_reached,
        regular_batch_resampling_cap=regular_batch_resampling_cap,
        regular_batch_cap_reached=regular_batch_cap_reached,
        bt_se_summary=bt_se_summary,
        bt_quality_flags=bt_quality_flags,
        bt_se_inflated=bt_se_inflated,
        comparison_coverage_sparse=comparison_coverage_sparse,
        has_isolated_items=has_isolated_items,
        metadata_updates=metadata_updates,
    )

    # Record diagnostic-only Prometheus counters derived from the context.
    record_bt_batch_quality(ctx)

    return ctx


def _can_attempt_small_net_resampling(ctx: ContinuationContext) -> bool:
    """Encapsulate small-net Phase-2 resampling predicate."""
    return (
        ctx.is_small_net
        and ctx.unique_coverage_complete
        and not ctx.stability_passed
        and not ctx.should_fail_due_to_success_rate
        and ctx.pairs_remaining > 0
        and ctx.small_net_resampling_cap > 0
    )


def _can_attempt_resampling(ctx: ContinuationContext) -> bool:
    """General resampling predicate for both small and regular nets.

    - Small nets delegate to the existing small-net predicate, preserving PR-7
      semantics and relying on small_net_resampling_cap.
    - Non-small nets use a conservative gating strategy that requires:
      - At least one callback received.
      - Success-rate guard not triggered.
      - Remaining budget and denominator headroom.
      - A positive regular-batch resampling cap and resampling_pass_count
        strictly below that cap.
      - Coverage sufficiently progressed relative to max_possible_pairs.
    """
    # Preserve existing behaviour for small nets.
    if ctx.is_small_net:
        return _can_attempt_small_net_resampling(ctx)

    # Non-small nets: require some signal before attempting resampling.
    if ctx.callbacks_received <= 0:
        return False

    if ctx.should_fail_due_to_success_rate:
        return False

    if ctx.stability_passed:
        return False

    if ctx.pairs_remaining <= 0 or ctx.budget_exhausted:
        return False

    if ctx.callbacks_reached_cap:
        return False

    # Enforce regular-batch resampling cap.
    regular_cap = getattr(ctx, "regular_batch_resampling_cap", 0)
    if regular_cap <= 0:
        return False

    if ctx.resampling_pass_count >= regular_cap:
        return False

    # Coverage/stability condition: require a minimum fraction of the potential
    # comparison graph to have at least one successful comparison before we
    # start resampling existing edges.
    if ctx.max_possible_pairs <= 0:
        return False

    coverage_fraction = ctx.successful_pairs_count / ctx.max_possible_pairs
    MIN_COVERAGE_FRACTION_FOR_REGULAR_RESAMPLING = 0.6
    if coverage_fraction < MIN_COVERAGE_FRACTION_FOR_REGULAR_RESAMPLING:
        return False

    return True


def _decide_continuation_action(ctx: ContinuationContext) -> ContinuationDecision:
    """Decide high-level continuation action from derived context.

    Small-net resampling is handled separately using `_can_attempt_small_net_resampling`;
    this helper captures the PR-2/PR-7 semantics once resampling is not in play.
    """
    if ctx.should_fail_due_to_success_rate:
        return ContinuationDecision.FINALIZE_FAILURE

    if ctx.should_finalize:
        return ContinuationDecision.FINALIZE_SCORING

    if ctx.pairs_remaining > 0 and not ctx.small_net_cap_reached:
        return ContinuationDecision.REQUEST_MORE_COMPARISONS

    return ContinuationDecision.NO_OP


def decide(ctx: ContinuationContext) -> ContinuationDecision:
    """Public, pure continuation decision surface.

    This function is the single entry point for continuation decisions and
    delegates to internal helpers that operate only on the immutable
    ContinuationContext.
    """
    return _decide_continuation_action(ctx)
