from __future__ import annotations

from typing import TYPE_CHECKING, Any

from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic.workflow_context import ContinuationContext
from services.cj_assessment_service.metrics import get_business_metrics

if TYPE_CHECKING:
    from services.cj_assessment_service.cj_core_logic.workflow_decision import (
        ContinuationDecision,
    )


logger = create_service_logger("cj_assessment_service.workflow_diagnostics")


def record_bt_batch_quality(ctx: ContinuationContext) -> None:
    """Record BT SE batch-quality diagnostics based on continuation context.

    This helper is intentionally side-effect-only: it observes the
    ContinuationContext and updates Prometheus counters without mutating the
    context or influencing decision predicates.
    """
    if ctx.bt_se_summary is None:
        # When no SE summary is available, there is nothing to record.
        return

    business_metrics = get_business_metrics()
    se_inflated_counter = business_metrics.get("cj_bt_se_inflated_batches_total")
    sparse_coverage_counter = business_metrics.get("cj_bt_sparse_coverage_batches_total")

    if ctx.bt_se_inflated and se_inflated_counter is not None:
        try:
            se_inflated_counter.inc()
        except Exception as exc:  # pragma: no cover - defensive logging only
            logger.error(
                "Failed to increment bt_se_inflated counter",
                extra={"batch_id": ctx.batch_id, "error": str(exc)},
            )

    if ctx.comparison_coverage_sparse and sparse_coverage_counter is not None:
        try:
            sparse_coverage_counter.inc()
        except Exception as exc:  # pragma: no cover - defensive logging only
            logger.error(
                "Failed to increment sparse_coverage counter",
                extra={"batch_id": ctx.batch_id, "error": str(exc)},
            )


def record_workflow_decision(
    ctx: ContinuationContext,
    decision: "ContinuationDecision",
) -> None:
    """Record high-level workflow decisions derived from continuation context.

    This helper records per-decision counters for observability only. It must
    not feed back into continuation predicates, caps, or thresholds.
    """
    business_metrics = get_business_metrics()
    decisions_counter = business_metrics.get("cj_workflow_decisions_total")

    if decisions_counter is None:
        return

    # Use the enum value when available; fall back to string representation.
    decision_value: str
    decision_raw: Any = getattr(decision, "value", decision)
    if isinstance(decision_raw, str):
        decision_value = decision_raw
    else:
        decision_value = str(decision_raw)

    try:
        decisions_counter.labels(decision=decision_value).inc()
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.error(
            "Failed to increment workflow decision counter",
            extra={
                "batch_id": ctx.batch_id,
                "decision": decision_value,
                "error": str(exc),
            },
        )
