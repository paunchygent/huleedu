"""Repository implementation for Entitlements Service.

This module provides database operations for credit balances and operations
using async SQLAlchemy patterns with proper transaction management.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.entitlements_service.models_db import (
    CreditBalance,
    CreditOperation,
    OperationStatus,
    SubjectType,
)
from services.entitlements_service.protocols import EntitlementsRepositoryProtocol

logger = create_service_logger("entitlements_service.repository")


class EntitlementsRepositoryImpl(EntitlementsRepositoryProtocol):
    """Production repository implementation using PostgreSQL."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize repository with database session factory.

        Args:
            session_factory: Async session factory for database connections
        """
        self.session_factory = session_factory

    async def get_credit_balance(self, subject_type: str, subject_id: str) -> int:
        """Get current credit balance for a subject.

        Args:
            subject_type: "user" or "org"
            subject_id: Subject identifier

        Returns:
            Current credit balance (0 if subject doesn't exist)
        """
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    select(CreditBalance.balance).where(
                        and_(
                            CreditBalance.subject_type == SubjectType(subject_type),
                            CreditBalance.subject_id == subject_id,
                        )
                    )
                )
                balance = result.scalar()

                if balance is None:
                    logger.debug(f"No balance found for {subject_type}:{subject_id}, returning 0")
                    return 0

                logger.debug(f"Balance for {subject_type}:{subject_id}: {balance}")
                return balance

            except Exception as e:
                logger.error(f"Error getting credit balance: {e}", exc_info=True)
                raise

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
        async with self.session_factory() as session:
            try:
                # First, check if balance exists
                result = await session.execute(
                    select(CreditBalance).where(
                        and_(
                            CreditBalance.subject_type == SubjectType(subject_type),
                            CreditBalance.subject_id == subject_id,
                        )
                    )
                )
                balance_record = result.scalar_one_or_none()

                if balance_record is None:
                    # Create new balance record
                    if delta < 0:
                        raise ValueError(
                            f"Cannot consume credits from non-existent balance for {subject_type}:{subject_id}"
                        )

                    balance_record = CreditBalance(
                        subject_type=SubjectType(subject_type),
                        subject_id=subject_id,
                        balance=delta,
                    )
                    session.add(balance_record)
                    await session.commit()

                    logger.info(
                        f"Created new balance for {subject_type}:{subject_id}: {delta}",
                        extra={"correlation_id": correlation_id},
                    )
                    return delta

                else:
                    # Update existing balance
                    new_balance = balance_record.balance + delta

                    if new_balance < 0:
                        raise ValueError(
                            f"Insufficient credits for {subject_type}:{subject_id}. "
                            f"Current: {balance_record.balance}, Requested: {abs(delta)}"
                        )

                    balance_record.balance = new_balance
                    balance_record.updated_at = datetime.now(timezone.utc)

                    await session.commit()

                    logger.info(
                        f"Updated balance for {subject_type}:{subject_id}: {balance_record.balance} -> {new_balance}",
                        extra={"correlation_id": correlation_id, "delta": delta},
                    )
                    return new_balance

            except ValueError:
                await session.rollback()
                raise
            except Exception as e:
                await session.rollback()
                logger.error(f"Error updating credit balance: {e}", exc_info=True)
                raise

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
        async with self.session_factory() as session:
            try:
                operation = CreditOperation(
                    id=str(uuid4()),
                    subject_type=SubjectType(subject_type),
                    subject_id=subject_id,
                    metric=metric,
                    amount=amount,
                    batch_id=batch_id,
                    consumed_from=SubjectType(consumed_from),
                    correlation_id=correlation_id,
                    operation_status=OperationStatus(status),
                )

                session.add(operation)
                await session.commit()

                logger.info(
                    f"Recorded operation: {metric} for {subject_type}:{subject_id}",
                    extra={
                        "correlation_id": correlation_id,
                        "amount": amount,
                        "status": status,
                        "batch_id": batch_id,
                    },
                )

            except Exception as e:
                await session.rollback()
                logger.error(f"Error recording operation: {e}", exc_info=True)
                raise

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
        async with self.session_factory() as session:
            try:
                query = select(CreditOperation)

                # Apply filters
                conditions = []
                if subject_type:
                    conditions.append(CreditOperation.subject_type == SubjectType(subject_type))
                if subject_id:
                    conditions.append(CreditOperation.subject_id == subject_id)
                if correlation_id:
                    conditions.append(CreditOperation.correlation_id == correlation_id)

                if conditions:
                    query = query.where(and_(*conditions))

                # Order by created_at descending and apply limit
                query = query.order_by(desc(CreditOperation.created_at)).limit(limit)

                result = await session.execute(query)
                operations = result.scalars().all()

                # Convert to dict format
                history = []
                for op in operations:
                    history.append(
                        {
                            "id": op.id,
                            "subject_type": op.subject_type.value,
                            "subject_id": op.subject_id,
                            "metric": op.metric,
                            "amount": op.amount,
                            "batch_id": op.batch_id,
                            "consumed_from": op.consumed_from.value,
                            "correlation_id": op.correlation_id,
                            "operation_status": op.operation_status.value,
                            "created_at": op.created_at.isoformat() if op.created_at else None,
                        }
                    )

                logger.debug(
                    f"Retrieved {len(history)} operations",
                    extra={
                        "subject_type": subject_type,
                        "subject_id": subject_id,
                        "correlation_id": correlation_id,
                    },
                )

                return history

            except Exception as e:
                logger.error(f"Error getting operations history: {e}", exc_info=True)
                raise

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
        # Use the update method with adjustment logic
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
            f"Admin adjustment for {subject_type}:{subject_id}: {amount} credits",
            extra={"reason": reason, "correlation_id": correlation_id, "new_balance": new_balance},
        )

        return new_balance
