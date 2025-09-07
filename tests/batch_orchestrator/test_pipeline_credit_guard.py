from dataclasses import dataclass

import pytest
from common_core.pipeline_models import PhaseName

from services.batch_orchestrator_service.domain.pipeline_cost_strategy import (
    PipelineCostStrategy,
)
from services.batch_orchestrator_service.domain.pipeline_credit_guard import (
    PipelineCreditGuard,
)


@dataclass
class FakeBatchContext:
    user_id: str
    org_id: str | None
    expected_essay_count: int
    essay_ids: list[str] | None = None


class FakeEntitlementsClient:
    def __init__(self, sufficient: bool, available: int) -> None:
        self._sufficient = sufficient
        self._available = available

    async def check_credits_bulk(self, user_id, org_id, requirements, correlation_id):  # type: ignore[no-untyped-def]
        total_required = sum(int(q) for q in requirements.values())
        return {
            "allowed": self._sufficient,
            "available_credits": self._available,
            "required_credits": total_required,
            "per_metric": {
                m: {"required": int(q), "available": self._available, "allowed": self._sufficient}
                for m, q in requirements.items()
            },
            "correlation_id": correlation_id,
        }


@pytest.mark.asyncio
async def test_credit_guard_allows_when_sufficient():
    entitlements = FakeEntitlementsClient(sufficient=True, available=100)
    guard = PipelineCreditGuard(
        entitlements_client=entitlements, cost_strategy=PipelineCostStrategy()
    )

    ctx = FakeBatchContext(user_id="u1", org_id=None, expected_essay_count=3)
    resolved = [PhaseName.CJ_ASSESSMENT, PhaseName.AI_FEEDBACK]

    outcome = await guard.evaluate(
        batch_id="b1",
        resolved_pipeline=resolved,
        batch_context=ctx,
        correlation_id="c1",
    )

    assert outcome.allowed is True
    assert outcome.denial_reason is None
    # For 3 essays: CJ comparisons = 3, AI calls = 3, total 6
    assert outcome.required_credits == 6
    assert outcome.resource_breakdown["cj_comparison"] == 3
    assert outcome.resource_breakdown["ai_feedback_generation"] == 3


@pytest.mark.asyncio
async def test_credit_guard_denies_when_insufficient():
    entitlements = FakeEntitlementsClient(sufficient=False, available=2)
    guard = PipelineCreditGuard(
        entitlements_client=entitlements, cost_strategy=PipelineCostStrategy()
    )

    ctx = FakeBatchContext(user_id="u1", org_id=None, expected_essay_count=3)
    resolved = [PhaseName.AI_FEEDBACK]

    outcome = await guard.evaluate(
        batch_id="b2",
        resolved_pipeline=resolved,
        batch_context=ctx,
        correlation_id="c2",
    )

    assert outcome.allowed is False
    assert outcome.denial_reason == "insufficient_credits"
    assert outcome.required_credits == 3  # one call per essay
    assert outcome.available_credits == 2
