"""Protocol definitions for Entitlements Service dependency injection.

This module defines behavioral contracts used by the DI container to provide
implementations following the Repository and Strategy patterns.
"""

from __future__ import annotations

from typing import Any, NamedTuple, Protocol

from pydantic import BaseModel


class SubjectRef(BaseModel):
    """Reference to a credit subject (user or organization)."""

    type: str  # "user" or "org"
    id: str  # UUID


class CreditCheckRequest(BaseModel):
    """Request to check credit availability."""

    user_id: str
    org_id: str | None = None
    metric: str
    amount: int = 1


class CreditCheckResponse(BaseModel):
    """Response from credit availability check."""

    allowed: bool
    reason: str | None = None
    required_credits: int
    available_credits: int
    source: str | None = None  # "user" or "org"


class CreditConsumption(BaseModel):
    """Request to consume credits."""

    user_id: str
    org_id: str | None = None
    metric: str
    amount: int
    batch_id: str | None = None
    correlation_id: str


class CreditBalanceInfo(BaseModel):
    """Credit balance information for a subject."""

    user_balance: int
    org_balance: int | None = None
    org_id: str | None = None


class CreditAdjustment(BaseModel):
    """Request for manual credit adjustment."""

    subject_type: str  # "user" or "org"
    subject_id: str
    amount: int  # positive to add, negative to deduct
    reason: str


class PolicyConfig(BaseModel):
    """Policy configuration data."""

    costs: dict[str, int]
    rate_limits: dict[str, str]
    signup_bonuses: dict[str, int]
    cache_ttl: int


class RateLimitCheck(NamedTuple):
    """Result of rate limit check."""

    allowed: bool
    limit: int
    window_seconds: int
    current_count: int


# Core Protocols


class CreditManagerProtocol(Protocol):
    """Protocol for credit management operations."""

    async def check_credits(
        self,
        user_id: str,
        org_id: str | None,
        metric: str,
        amount: int,
    ) -> CreditCheckResponse:
        """Check if sufficient credits are available for operation.

        Args:
            user_id: User identifier
            org_id: Organization identifier (optional)
            metric: Operation metric name
            amount: Number of operations requested

        Returns:
            CreditCheckResponse with availability and balance info
        """
        ...

    async def consume_credits(self, consumption: CreditConsumption) -> bool:
        """Consume credits for completed operation.

        Args:
            consumption: Credit consumption details

        Returns:
            True if consumption successful, False otherwise
        """
        ...

    async def get_balance(self, user_id: str, org_id: str | None = None) -> CreditBalanceInfo:
        """Get current credit balances for user/organization.

        Args:
            user_id: User identifier
            org_id: Organization identifier (optional)

        Returns:
            CreditBalanceInfo with current balances
        """
        ...

    async def adjust_credits(self, adjustment: CreditAdjustment) -> bool:
        """Manually adjust credit balance (admin operation).

        Args:
            adjustment: Credit adjustment details

        Returns:
            True if adjustment successful, False otherwise
        """
        ...


class PolicyLoaderProtocol(Protocol):
    """Protocol for policy configuration loading."""

    async def load_policies(self) -> PolicyConfig:
        """Load and cache policy configuration from file.

        Returns:
            PolicyConfig with current policy settings
        """
        ...

    async def get_cost(self, metric: str) -> int:
        """Get credit cost for a specific metric.

        Args:
            metric: Operation metric name

        Returns:
            Credit cost (0 for free operations)
        """
        ...

    async def get_rate_limit(self, metric: str) -> tuple[int, int]:
        """Get rate limit configuration for a metric.

        Args:
            metric: Operation metric name

        Returns:
            Tuple of (count, window_seconds), (0, 0) for unlimited
        """
        ...

    async def reload_policies(self) -> None:
        """Force reload of policies from file and update cache."""
        ...


class RateLimiterProtocol(Protocol):
    """Protocol for rate limiting operations."""

    async def check_rate_limit(
        self,
        subject_id: str,
        metric: str,
        amount: int = 1,
    ) -> RateLimitCheck:
        """Check if operation is within rate limits.

        Args:
            subject_id: Subject performing the operation
            metric: Operation metric name
            amount: Number of operations requested

        Returns:
            RateLimitCheck with limit status and current usage
        """
        ...

    async def record_usage(
        self,
        subject_id: str,
        metric: str,
        amount: int = 1,
    ) -> None:
        """Record usage for rate limiting calculations.

        Args:
            subject_id: Subject performing the operation
            metric: Operation metric name
            amount: Number of operations performed
        """
        ...

    async def reset_rate_limit(self, subject_id: str, metric: str) -> None:
        """Reset rate limit for subject/metric (admin operation).

        Args:
            subject_id: Subject identifier
            metric: Operation metric name
        """
        ...


class EntitlementsRepositoryProtocol(Protocol):
    """Protocol for entitlements data persistence."""

    async def get_credit_balance(self, subject_type: str, subject_id: str) -> int:
        """Get current credit balance for a subject.

        Args:
            subject_type: "user" or "org"
            subject_id: Subject identifier

        Returns:
            Current credit balance (0 if subject doesn't exist)
        """
        ...

    async def update_credit_balance(
        self,
        subject_type: str,
        subject_id: str,
        delta: int,
        correlation_id: str,
    ) -> int:
        """Update credit balance atomically.

        Args:
            subject_type: "user" or "org"
            subject_id: Subject identifier
            delta: Change amount (negative for consumption)
            correlation_id: Operation correlation ID

        Returns:
            New balance after update

        Raises:
            ValueError: If balance would go negative
        """
        ...

    async def record_operation(
        self,
        subject_type: str,
        subject_id: str,
        metric: str,
        amount: int,
        consumed_from: str,
        correlation_id: str,
        batch_id: str | None = None,
        status: str = "completed",
    ) -> None:
        """Record credit operation for audit trail.

        Args:
            subject_type: "user" or "org"
            subject_id: Subject identifier
            metric: Operation metric name
            amount: Credits consumed/added
            consumed_from: Which balance was used ("user" or "org")
            correlation_id: Operation correlation ID
            batch_id: Optional batch identifier
            status: Operation status
        """
        ...

    async def get_operations_history(
        self,
        subject_type: str | None = None,
        subject_id: str | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get credit operations history.

        Args:
            subject_type: Optional filter by subject type
            subject_id: Optional filter by subject ID
            correlation_id: Optional filter by correlation ID
            limit: Maximum number of records

        Returns:
            List of operation records
        """
        ...
