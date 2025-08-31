"""Unit tests for credit consumption logic in Entitlements Service.

This module tests the CreditManagerImpl.consume_credits() method with comprehensive
scenarios including identity handling, org vs user priority, Swedish characters,
and error conditions following Rule 075 methodology.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.entitlements_service.implementations.credit_manager_impl import (
    CreditManagerImpl,
)
from services.entitlements_service.protocols import (
    EntitlementsRepositoryProtocol,
    EventPublisherProtocol,
    PolicyLoaderProtocol,
    RateLimitCheck,
    RateLimiterProtocol,
)


class TestCreditConsumptionLogic:
    """Tests for CreditManagerImpl consume_credits method with identity handling."""

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock repository with spec-based AsyncMock."""
        mock_repo = AsyncMock(spec=EntitlementsRepositoryProtocol)
        # Default balance returns
        mock_repo.get_credit_balance.return_value = 0
        mock_repo.update_credit_balance.return_value = 0
        mock_repo.record_operation.return_value = None
        return mock_repo

    @pytest.fixture
    def mock_policy_loader(self) -> AsyncMock:
        """Create mock policy loader with default cost configurations."""
        mock_loader = AsyncMock(spec=PolicyLoaderProtocol)
        # Default cost mapping: ai_feedback=5, batch_create=0, essay_scoring=10
        cost_map = {
            "ai_feedback": 5,
            "batch_create": 0,
            "essay_scoring": 10,
            "grammar_check": 2,
        }
        mock_loader.get_cost.side_effect = lambda metric: cost_map.get(metric, 1)
        return mock_loader

    @pytest.fixture
    def mock_rate_limiter(self) -> AsyncMock:
        """Create mock rate limiter that allows all operations by default."""
        mock_limiter = AsyncMock(spec=RateLimiterProtocol)
        mock_limiter.check_rate_limit.return_value = RateLimitCheck(
            allowed=True, limit=0, window_seconds=0, current_count=0
        )
        mock_limiter.record_usage.return_value = None
        return mock_limiter

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher that tracks published events."""
        mock_publisher = AsyncMock(spec=EventPublisherProtocol)
        mock_publisher.published_events = []

        async def track_balance_change(**kwargs: Any) -> None:
            mock_publisher.published_events.append({"type": "balance_changed", **kwargs})

        async def track_usage_recorded(**kwargs: Any) -> None:
            mock_publisher.published_events.append({"type": "usage_recorded", **kwargs})

        mock_publisher.publish_credit_balance_changed.side_effect = track_balance_change
        mock_publisher.publish_usage_recorded.side_effect = track_usage_recorded
        return mock_publisher

    @pytest.fixture
    def credit_manager(
        self,
        mock_repository: AsyncMock,
        mock_policy_loader: AsyncMock,
        mock_rate_limiter: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> CreditManagerImpl:
        """Create CreditManagerImpl with all dependencies mocked."""
        return CreditManagerImpl(
            repository=mock_repository,
            policy_loader=mock_policy_loader,
            rate_limiter=mock_rate_limiter,
            event_publisher=mock_event_publisher,
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_id, org_id, user_balance, org_balance, expected_source, expected_new_balance, description",
        [
            # Org credits used first when both available and sufficient
            (
                "user-123",
                "org-456",
                100,  # user has credits
                150,  # org has more credits
                "org",
                125,  # 150 - (5 * 5) = 125
                "Org credits used when both available and org sufficient",
            ),
            # User credits as fallback when org insufficient
            (
                "user-789",
                "org-111",
                200,  # user has sufficient credits
                10,  # org has insufficient credits (need 25 for 5*5)
                "user",
                175,  # 200 - 25 = 175
                "User credits as fallback when org credits insufficient",
            ),
            # User credits when no org_id provided
            (
                "user-only",
                None,
                80,
                0,  # no org to check
                "user",
                55,  # 80 - 25 = 55
                "User credits when no org_id provided",
            ),
            # Swedish characters in identity fields
            (
                "användare-åäö",
                "organisation-ÅÄÖ",
                75,
                50,  # org has sufficient credits for 25 credits needed
                "org",
                25,  # 50 - 25 = 25
                "Swedish characters in user and org identifiers",
            ),
        ],
    )
    async def test_org_vs_user_priority_logic(
        self,
        credit_manager: CreditManagerImpl,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        user_id: str,
        org_id: str | None,
        user_balance: int,
        org_balance: int,
        expected_source: str,
        expected_new_balance: int,
        description: str,
    ) -> None:
        """Test org credits are used before user credits when available and sufficient."""
        # Arrange
        correlation_id = str(uuid4())
        metric = "ai_feedback"
        amount = 5

        def balance_side_effect(subject_type: str, subject_id: str) -> int:
            if subject_type == "user" and subject_id == user_id:
                return user_balance
            elif subject_type == "org" and subject_id == org_id:
                return org_balance
            return 0

        def update_balance_side_effect(
            subject_type: str, subject_id: str, delta: int, correlation_id: str
        ) -> int:
            current = balance_side_effect(subject_type, subject_id)
            return current + delta

        mock_repository.get_credit_balance.side_effect = balance_side_effect
        mock_repository.update_credit_balance.side_effect = update_balance_side_effect

        # Act
        result = await credit_manager.consume_credits(
            user_id=user_id,
            org_id=org_id,
            metric=metric,
            amount=amount,
            batch_id=None,
            correlation_id=correlation_id,
        )

        # Assert
        assert result.success is True
        assert result.consumed_from == expected_source
        assert result.new_balance == expected_new_balance

        # Verify repository calls
        expected_subject_id = org_id if expected_source == "org" else user_id
        mock_repository.update_credit_balance.assert_called_once_with(
            subject_type=expected_source,
            subject_id=expected_subject_id,
            delta=-25,  # 5 * 5 credits consumed
            correlation_id=correlation_id,
        )

        mock_repository.record_operation.assert_called_once_with(
            subject_type=expected_source,
            subject_id=expected_subject_id,
            metric=metric,
            amount=25,
            consumed_from=expected_source,
            correlation_id=correlation_id,
            batch_id=None,
            status="completed",
        )

        # Verify events published
        balance_events = [
            e for e in mock_event_publisher.published_events if e["type"] == "balance_changed"
        ]
        usage_events = [
            e for e in mock_event_publisher.published_events if e["type"] == "usage_recorded"
        ]

        assert len(balance_events) == 1
        assert len(usage_events) == 1
        assert balance_events[0]["subject_type"] == expected_source
        assert balance_events[0]["subject_id"] == expected_subject_id
        assert balance_events[0]["delta"] == -25

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "metric, cost_per_unit, amount, expected_total_cost, expected_consumed_from",
        [
            # Free operations
            ("batch_create", 0, 3, 0, "none"),
            # Low cost operations
            ("grammar_check", 2, 1, 2, "user"),
            # High cost operations
            ("essay_scoring", 10, 2, 20, "user"),
            # Swedish course metric with special characters
            ("svenska_bedömning", 1, 5, 5, "user"),
        ],
    )
    async def test_credit_deduction_calculations(
        self,
        credit_manager: CreditManagerImpl,
        mock_repository: AsyncMock,
        mock_policy_loader: AsyncMock,
        metric: str,
        cost_per_unit: int,
        amount: int,
        expected_total_cost: int,
        expected_consumed_from: str,
    ) -> None:
        """Test proper credit deduction amounts for various metrics and amounts."""
        # Arrange
        user_id = "test-user"
        user_balance = 100
        correlation_id = str(uuid4())

        # Configure mock policy loader for the test metric
        mock_policy_loader.get_cost.return_value = cost_per_unit

        mock_repository.get_credit_balance.return_value = user_balance
        mock_repository.update_credit_balance.return_value = user_balance - expected_total_cost

        # Act
        result = await credit_manager.consume_credits(
            user_id=user_id,
            org_id=None,
            metric=metric,
            amount=amount,
            batch_id=None,
            correlation_id=correlation_id,
        )

        # Assert
        assert result.success is True
        assert result.consumed_from == expected_consumed_from

        if expected_total_cost == 0:
            # Free operations
            assert result.new_balance == user_balance  # No change for free ops
            mock_repository.update_credit_balance.assert_not_called()
        else:
            # Paid operations
            assert result.new_balance == user_balance - expected_total_cost
            mock_repository.update_credit_balance.assert_called_once_with(
                subject_type="user",
                subject_id=user_id,
                delta=-expected_total_cost,
                correlation_id=correlation_id,
            )

        # Verify operation recorded with correct amount
        mock_repository.record_operation.assert_called_once()
        call_args = mock_repository.record_operation.call_args
        assert call_args.kwargs["amount"] == expected_total_cost
        assert call_args.kwargs["status"] == "completed"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_balance, org_balance, required_credits, expected_error_type",
        [
            # Insufficient user credits, no org
            (10, 0, 50, ValueError),
            # Insufficient credits in both accounts
            (15, 20, 50, ValueError),
            # Zero balance scenario
            (0, 0, 1, ValueError),
        ],
    )
    async def test_insufficient_credits_handling(
        self,
        credit_manager: CreditManagerImpl,
        mock_repository: AsyncMock,
        user_balance: int,
        org_balance: int,
        required_credits: int,
        expected_error_type: type[Exception],
    ) -> None:
        """Test behavior when credits are insufficient for consumption."""
        # Arrange
        user_id = "poor-user"
        org_id = "poor-org"
        correlation_id = str(uuid4())
        amount = required_credits // 5 if required_credits >= 5 else required_credits

        def balance_side_effect(subject_type: str, subject_id: str) -> int:
            if subject_type == "user":
                return user_balance
            elif subject_type == "org":
                return org_balance
            return 0

        mock_repository.get_credit_balance.side_effect = balance_side_effect
        mock_repository.update_credit_balance.side_effect = expected_error_type(
            "Insufficient credits"
        )

        # Act
        result = await credit_manager.consume_credits(
            user_id=user_id,
            org_id=org_id,
            metric="ai_feedback",
            amount=amount,
            batch_id=None,
            correlation_id=correlation_id,
        )

        # Assert
        assert result.success is False
        assert result.new_balance in [user_balance, org_balance]

        # Verify failed operation recorded
        mock_repository.record_operation.assert_called_once()
        call_args = mock_repository.record_operation.call_args
        assert call_args.kwargs["status"] == "failed"

    @pytest.mark.asyncio
    async def test_event_publishing_for_successful_consumption(
        self,
        credit_manager: CreditManagerImpl,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that credit balance changed and usage recorded events are published correctly."""
        # Arrange
        user_id = "event-user-åäö"
        org_id = "event-org-ÅÄÖ"
        correlation_id = str(uuid4())
        old_org_balance = 100
        new_org_balance = 75  # 100 - 25

        mock_repository.get_credit_balance.side_effect = lambda st, si: (
            old_org_balance if st == "org" else 50
        )
        mock_repository.update_credit_balance.return_value = new_org_balance

        # Act
        result = await credit_manager.consume_credits(
            user_id=user_id,
            org_id=org_id,
            metric="ai_feedback",
            amount=5,
            batch_id="test-batch",
            correlation_id=correlation_id,
        )

        # Assert
        assert result.success is True
        assert result.consumed_from == "org"

        # Verify event publishing calls
        mock_event_publisher.publish_credit_balance_changed.assert_called_once_with(
            subject_type="org",
            subject_id=org_id,
            old_balance=old_org_balance,
            new_balance=new_org_balance,
            delta=-25,
            correlation_id=correlation_id,
        )

        mock_event_publisher.publish_usage_recorded.assert_called_once_with(
            subject_type="org",
            subject_id=org_id,
            metric="ai_feedback",
            amount=5,  # Original amount, not total cost
            correlation_id=correlation_id,
        )

    @pytest.mark.asyncio
    async def test_database_error_recovery(
        self,
        credit_manager: CreditManagerImpl,
        mock_repository: AsyncMock,
    ) -> None:
        """Test behavior when database operations fail during consumption."""
        # Arrange
        user_id = "error-user"
        correlation_id = str(uuid4())
        mock_repository.get_credit_balance.return_value = 100
        mock_repository.update_credit_balance.side_effect = Exception("Database connection lost")

        # Act
        result = await credit_manager.consume_credits(
            user_id=user_id,
            org_id=None,
            metric="ai_feedback",
            amount=1,
            batch_id=None,
            correlation_id=correlation_id,
        )

        # Assert
        assert result.success is False
        assert result.consumed_from == "error"
        assert result.new_balance == 100  # Fallback to current balance

        # Verify error operation attempted to be recorded
        mock_repository.record_operation.assert_called()
        call_args = mock_repository.record_operation.call_args
        assert call_args.kwargs["status"] == "failed"
        assert call_args.kwargs["consumed_from"] == "error"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_id, org_id, batch_id, expected_batch_id",
        [
            ("batch-user", None, "batch-123", "batch-123"),
            ("batch-user", "batch-org", None, None),
            ("användare-batch", "org-batch", "svenska-batch-åäö", "svenska-batch-åäö"),
        ],
    )
    async def test_batch_id_propagation(
        self,
        credit_manager: CreditManagerImpl,
        mock_repository: AsyncMock,
        user_id: str,
        org_id: str | None,
        batch_id: str | None,
        expected_batch_id: str | None,
    ) -> None:
        """Test that batch_id is correctly propagated to operation records."""
        # Arrange
        correlation_id = str(uuid4())
        mock_repository.get_credit_balance.return_value = 100
        mock_repository.update_credit_balance.return_value = 95

        # Act
        result = await credit_manager.consume_credits(
            user_id=user_id,
            org_id=org_id,
            metric="ai_feedback",
            amount=1,
            batch_id=batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result.success is True
        mock_repository.record_operation.assert_called_once()
        call_args = mock_repository.record_operation.call_args
        assert call_args.kwargs["batch_id"] == expected_batch_id

    @pytest.mark.asyncio
    async def test_rate_limiter_integration(
        self,
        credit_manager: CreditManagerImpl,
        mock_rate_limiter: AsyncMock,
    ) -> None:
        """Test rate limiter usage recording during successful consumption."""
        # Arrange
        user_id = "rate-limited-user"
        correlation_id = str(uuid4())

        # Act
        await credit_manager.consume_credits(
            user_id=user_id,
            org_id=None,
            metric="ai_feedback",
            amount=2,
            batch_id=None,
            correlation_id=correlation_id,
        )

        # Assert
        mock_rate_limiter.record_usage.assert_called_once_with(user_id, "ai_feedback", 2)

    @pytest.mark.asyncio
    async def test_comprehensive_swedish_character_support(
        self,
        credit_manager: CreditManagerImpl,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test comprehensive support for Swedish characters in all identity fields."""
        # Arrange - All Swedish characters in identifiers
        user_id = "användare_åäöÅÄÖ_123"
        org_id = "organisation_åäöÅÄÖ_456"
        correlation_id = str(uuid4())
        batch_id = "batch_svenska_åäöÅÄÖ"

        mock_repository.get_credit_balance.side_effect = lambda st, si: (
            200 if st == "org" else 100
        )
        mock_repository.update_credit_balance.return_value = 175

        # Act
        result = await credit_manager.consume_credits(
            user_id=user_id,
            org_id=org_id,
            metric="ai_feedback",
            amount=5,
            batch_id=batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result.success is True
        assert result.consumed_from == "org"  # Org credits used first

        # Verify all Swedish characters preserved in repository calls
        mock_repository.update_credit_balance.assert_called_once_with(
            subject_type="org",
            subject_id=org_id,  # Should preserve Swedish characters
            delta=-25,
            correlation_id=correlation_id,
        )

        mock_repository.record_operation.assert_called_once_with(
            subject_type="org",
            subject_id=org_id,  # Should preserve Swedish characters
            metric="ai_feedback",
            amount=25,
            consumed_from="org",
            correlation_id=correlation_id,
            batch_id=batch_id,  # Should preserve Swedish characters
            status="completed",
        )

        # Verify Swedish characters preserved in events
        mock_event_publisher.publish_credit_balance_changed.assert_called_once()
        balance_call = mock_event_publisher.publish_credit_balance_changed.call_args
        assert balance_call.kwargs["subject_id"] == org_id

        mock_event_publisher.publish_usage_recorded.assert_called_once()
        usage_call = mock_event_publisher.publish_usage_recorded.call_args
        assert usage_call.kwargs["subject_id"] == org_id
