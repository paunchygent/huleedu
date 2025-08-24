"""Mock repository implementation for testing.

This module provides an in-memory implementation of the repository
for testing and development environments.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from huleedu_service_libs.logging_utils import create_service_logger

from services.entitlements_service.protocols import EntitlementsRepositoryProtocol

logger = create_service_logger("entitlements_service.mock_repository")


class MockEntitlementsRepositoryImpl(EntitlementsRepositoryProtocol):
    """In-memory mock repository for testing."""

    def __init__(self) -> None:
        """Initialize mock repository with empty storage."""
        self.balances: dict[tuple[str, str], int] = {}
        self.operations: list[dict[str, Any]] = []
        logger.info("Initialized mock repository")

    async def get_credit_balance(self, subject_type: str, subject_id: str) -> int:
        """Get current credit balance for a subject.

        Args:
            subject_type: "user" or "org"
            subject_id: Subject identifier

        Returns:
            Current credit balance (0 if subject doesn't exist)
        """
        key = (subject_type, subject_id)
        balance = self.balances.get(key, 0)

        logger.debug(f"Mock: Balance for {subject_type}:{subject_id} = {balance}")
        return balance

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
        key = (subject_type, subject_id)
        current_balance = self.balances.get(key, 0)

        # Check if new balance would be negative
        new_balance = current_balance + delta
        if new_balance < 0:
            raise ValueError(
                f"Insufficient credits for {subject_type}:{subject_id}. "
                f"Current: {current_balance}, Requested: {abs(delta)}"
            )

        # Update balance
        self.balances[key] = new_balance

        logger.info(
            (
                f"Mock: Updated balance for {subject_type}:{subject_id}: "
                f"{current_balance} -> {new_balance}"
            ),
            extra={"correlation_id": correlation_id, "delta": delta},
        )

        return new_balance

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
        operation = {
            "id": str(uuid4()),
            "subject_type": subject_type,
            "subject_id": subject_id,
            "metric": metric,
            "amount": amount,
            "batch_id": batch_id,
            "consumed_from": consumed_from,
            "correlation_id": correlation_id,
            "operation_status": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self.operations.append(operation)

        logger.info(
            f"Mock: Recorded operation: {metric} for {subject_type}:{subject_id}",
            extra={
                "correlation_id": correlation_id,
                "amount": amount,
                "status": status,
            },
        )

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
        # Filter operations
        filtered = self.operations.copy()

        if subject_type:
            filtered = [op for op in filtered if op["subject_type"] == subject_type]

        if subject_id:
            filtered = [op for op in filtered if op["subject_id"] == subject_id]

        if correlation_id:
            filtered = [op for op in filtered if op["correlation_id"] == correlation_id]

        # Sort by created_at descending (most recent first)
        filtered.sort(key=lambda x: x["created_at"], reverse=True)

        # Apply limit
        filtered = filtered[:limit]

        logger.debug(
            f"Mock: Retrieved {len(filtered)} operations",
            extra={
                "subject_type": subject_type,
                "subject_id": subject_id,
                "correlation_id": correlation_id,
            },
        )

        return filtered

    async def adjust_balance(
        self,
        subject_type: str,
        subject_id: str,
        amount: int,
        reason: str,
        correlation_id: str,
    ) -> int:
        """Administrative balance adjustment.

        Args:
            subject_type: "user" or "org"
            subject_id: Subject identifier
            amount: Adjustment amount (positive or negative)
            reason: Reason for adjustment
            correlation_id: Operation correlation ID

        Returns:
            New balance after adjustment
        """
        # Use the update method
        new_balance = await self.update_credit_balance(
            subject_type=subject_type,
            subject_id=subject_id,
            delta=amount,
            correlation_id=correlation_id,
        )

        # Record the adjustment as an operation
        await self.record_operation(
            subject_type=subject_type,
            subject_id=subject_id,
            metric="manual_adjustment",
            amount=amount,
            consumed_from=subject_type,
            correlation_id=correlation_id,
            status="completed",
        )

        logger.info(
            f"Mock: Admin adjustment for {subject_type}:{subject_id}: {amount} credits",
            extra={"reason": reason, "correlation_id": correlation_id, "new_balance": new_balance},
        )

        return new_balance

    def reset(self) -> None:
        """Reset the mock repository to initial state (for testing)."""
        self.balances.clear()
        self.operations.clear()
        logger.info("Mock repository reset")
