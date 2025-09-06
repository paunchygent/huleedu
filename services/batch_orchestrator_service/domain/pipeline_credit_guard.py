"""Credit guard for pipeline execution.

Separates credit calculation and entitlements checks from request handling
to satisfy SRP and keep orchestration logic clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from common_core.pipeline_models import PhaseName

from .pipeline_cost_strategy import PipelineCostStrategy, ResourceRequirements

if TYPE_CHECKING:
    from services.batch_orchestrator_service.protocols import EntitlementsServiceProtocol


@dataclass(frozen=True)
class CreditCheckOutcome:
    allowed: bool
    denial_reason: str | None
    required_credits: int
    available_credits: int
    resource_breakdown: dict[str, int]


class PipelineCreditGuard:
    """Domain service to evaluate whether a pipeline may proceed given credits.

    - Computes resource requirements using `PipelineCostStrategy`.
    - Calls EntitlementsService to check sufficiency.
    - Returns a simple outcome object, leaving event publishing to callers.
    """

    def __init__(
        self,
        entitlements_client: "EntitlementsServiceProtocol",
        cost_strategy: PipelineCostStrategy | None = None,
    ) -> None:
        self._entitlements = entitlements_client
        self._costs = cost_strategy or PipelineCostStrategy()

    def _essay_count_from_context(self, batch_context: Any) -> int:
        """Derive essay count robustly from registration context.

        Prefers explicit essay_ids length; falls back to expected_essay_count.
        """
        try:
            if getattr(batch_context, "essay_ids", None):
                return len(batch_context.essay_ids)
            if hasattr(batch_context, "expected_essay_count"):
                return int(batch_context.expected_essay_count)
        except Exception:
            pass
        return 0

    def calculate_requirements(
        self,
        resolved_pipeline: list[PhaseName],
        batch_context: Any,
    ) -> ResourceRequirements:
        steps = [p.value for p in resolved_pipeline]
        essay_count = self._essay_count_from_context(batch_context)
        return self._costs.calculate_requirements(
            pipeline_steps=steps,
            essay_count=essay_count,
            batch_context=batch_context,
        )

    async def evaluate(
        self,
        *,
        batch_id: str,
        resolved_pipeline: list[PhaseName],
        batch_context: Any,
        correlation_id: str,
    ) -> CreditCheckOutcome:
        """Evaluate credits for a pipeline request and return outcome.

        This method never raises for business outcomes; it returns `allowed=False`
        only when Entitlements explicitly indicates insufficiency. Communication
        errors are raised to the caller to be handled at a higher level.
        """
        # Compute requirements
        reqs = self.calculate_requirements(resolved_pipeline, batch_context)

        if not reqs.has_billable_resources():
            return CreditCheckOutcome(
                allowed=True,
                denial_reason=None,
                required_credits=0,
                available_credits=0,
                resource_breakdown={},
            )

        user_id = getattr(batch_context, "user_id", None)
        org_id = getattr(batch_context, "org_id", None)
        if not user_id:
            raise ValueError(
                f"Cannot perform credit check: no user_id in batch context for batch {batch_id}"
            )

        # Call entitlements service
        result = await self._entitlements.check_credits(
            user_id=user_id,
            org_id=org_id,
            required_credits=reqs.to_entitlement_checks(),
            correlation_id=correlation_id,
        )

        sufficient = bool(result.get("sufficient", False))
        available = int(result.get("available_credits", 0))
        required_total = int(reqs.total_cost_units)

        if sufficient:
            return CreditCheckOutcome(
                allowed=True,
                denial_reason=None,
                required_credits=required_total,
                available_credits=available,
                resource_breakdown={
                    "cj_comparison": reqs.cj_comparisons,
                    "ai_feedback_generation": reqs.ai_feedback_calls,
                },
            )

        return CreditCheckOutcome(
            allowed=False,
            denial_reason="insufficient_credits",
            required_credits=required_total,
            available_credits=available,
            resource_breakdown={
                "cj_comparison": reqs.cj_comparisons,
                "ai_feedback_generation": reqs.ai_feedback_calls,
            },
        )
