from __future__ import annotations

import pytest

from services.entitlements_service.implementations.credit_manager_impl import (
    CreditManagerImpl,
)
from services.entitlements_service.implementations.mock_policy_loader_impl import (
    MockPolicyLoaderImpl,
)
from services.entitlements_service.implementations.mock_repository_impl import (
    MockEntitlementsRepositoryImpl,
)
from services.entitlements_service.protocols import RateLimitCheck, RateLimiterProtocol


class _AllowAllRateLimiter(RateLimiterProtocol):
    async def check_rate_limit(
        self, subject_id: str, metric: str, amount: int = 1
    ) -> RateLimitCheck:
        return RateLimitCheck(allowed=True, limit=0, window_seconds=0, current_count=0)

    async def record_usage(
        self, subject_id: str, metric: str, amount: int = 1
    ) -> None:  # pragma: no cover - noop
        return None

    async def reset_rate_limit(
        self, subject_id: str, metric: str
    ) -> None:  # pragma: no cover - noop
        return None


@pytest.mark.asyncio
async def test_consume_credits_returns_structured_result() -> None:
    repo = MockEntitlementsRepositoryImpl()
    policy = MockPolicyLoaderImpl()
    limiter = _AllowAllRateLimiter()
    mgr = CreditManagerImpl(repository=repo, policy_loader=policy, rate_limiter=limiter)

    # Seed user balance
    user_id = "user-123"
    await repo.update_credit_balance("user", user_id, delta=100, correlation_id="seed")

    # Consume for paid metric (ai_feedback cost=5)
    result = await mgr.consume_credits(
        user_id=user_id,
        org_id=None,
        metric="ai_feedback",
        amount=2,
        batch_id=None,
        correlation_id="corr-1",
    )

    assert result.success is True
    assert result.consumed_from == "user"
    assert result.new_balance == 90  # 100 - (2 * 5)


@pytest.mark.asyncio
async def test_consume_credits_free_operation_records_none_source() -> None:
    repo = MockEntitlementsRepositoryImpl()
    policy = MockPolicyLoaderImpl()
    limiter = _AllowAllRateLimiter()
    mgr = CreditManagerImpl(repository=repo, policy_loader=policy, rate_limiter=limiter)

    user_id = "user-456"
    # Default balance is 0; free metric should not change it
    result = await mgr.consume_credits(
        user_id=user_id,
        org_id=None,
        metric="batch_create",  # cost=0 in mock
        amount=1,
        batch_id=None,
        correlation_id="corr-2",
    )

    assert result.success is True
    assert result.consumed_from == "none"
    assert result.new_balance == 0


@pytest.mark.asyncio
async def test_adjust_balance_returns_new_balance() -> None:
    repo = MockEntitlementsRepositoryImpl()
    policy = MockPolicyLoaderImpl()
    limiter = _AllowAllRateLimiter()
    mgr = CreditManagerImpl(repository=repo, policy_loader=policy, rate_limiter=limiter)

    new_balance = await mgr.adjust_balance(
        subject_type="user",
        subject_id="user-789",
        amount=50,
        reason="test",
        correlation_id="corr-3",
    )

    assert new_balance == 50
