"""Credit manager implementation for Entitlements Service.

This module provides the core credit management logic with dual system
support (org credits first, user credits fallback) and optimistic consumption.
"""

from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger

from services.entitlements_service.protocols import (
    CreditAdjustment,
    CreditBalanceInfo,
    CreditCheckResponse,
    CreditConsumption,
    EntitlementsRepositoryProtocol,
    PolicyLoaderProtocol,
    RateLimiterProtocol,
)

logger = create_service_logger("entitlements_service.credit_manager")


class CreditManagerImpl:
    """Implementation of credit manager with dual system support."""

    def __init__(
        self,
        repository: EntitlementsRepositoryProtocol,
        policy_loader: PolicyLoaderProtocol,
        rate_limiter: RateLimiterProtocol,
    ) -> None:
        """Initialize credit manager with dependencies.

        Args:
            repository: Repository for credit data persistence
            policy_loader: Policy loader for costs and limits
            rate_limiter: Rate limiter for operation throttling
        """
        self.repository = repository
        self.policy_loader = policy_loader
        self.rate_limiter = rate_limiter

    async def check_credits(
        self,
        user_id: str,
        org_id: str | None,
        metric: str,
        amount: int,
    ) -> CreditCheckResponse:
        """Check if sufficient credits are available for operation.

        Implements dual credit system: check org credits first,
        fall back to user credits if insufficient.

        Args:
            user_id: User identifier
            org_id: Organization identifier (optional)
            metric: Operation metric name
            amount: Number of operations requested

        Returns:
            CreditCheckResponse with availability and balance info
        """
        logger.debug(
            f"Credit check: user={user_id}, org={org_id}, metric={metric}, amount={amount}"
        )

        try:
            # Get cost per unit from policy
            cost_per_unit = await self.policy_loader.get_cost(metric)
            total_cost = cost_per_unit * amount

            logger.debug(f"Total cost for {metric} x{amount}: {total_cost} credits")

            # Free operations bypass all checks
            if total_cost == 0:
                logger.debug(f"Free operation: {metric}")
                return CreditCheckResponse(
                    allowed=True,
                    required_credits=0,
                    available_credits=0,
                    source=None,
                )

            # Check rate limits first
            rate_check = await self.rate_limiter.check_rate_limit(user_id, metric, amount)
            if not rate_check.allowed:
                logger.info(
                    f"Rate limit exceeded for {metric}: {rate_check.current_count}/{rate_check.limit}",
                    extra={
                        "user_id": user_id,
                        "metric": metric,
                        "limit": rate_check.limit,
                        "current": rate_check.current_count,
                    },
                )
                return CreditCheckResponse(
                    allowed=False,
                    reason="rate_limit_exceeded",
                    required_credits=total_cost,
                    available_credits=0,
                )

            # Dual credit system: org first, then user
            if org_id:
                # Check organization credits first
                org_balance = await self.repository.get_credit_balance("org", org_id)
                logger.debug(f"Organization {org_id} balance: {org_balance}")

                if org_balance >= total_cost:
                    logger.debug(f"Sufficient org credits: {org_balance} >= {total_cost}")
                    return CreditCheckResponse(
                        allowed=True,
                        required_credits=total_cost,
                        available_credits=org_balance,
                        source="org",
                    )

                logger.debug(
                    f"Insufficient org credits: {org_balance} < {total_cost}, checking user credits"
                )

            # Check user credits (either as fallback or primary)
            user_balance = await self.repository.get_credit_balance("user", user_id)
            logger.debug(f"User {user_id} balance: {user_balance}")

            if user_balance >= total_cost:
                logger.debug(f"Sufficient user credits: {user_balance} >= {total_cost}")
                return CreditCheckResponse(
                    allowed=True,
                    required_credits=total_cost,
                    available_credits=user_balance,
                    source="user",
                )

            # Insufficient credits in both accounts
            logger.info(
                f"Insufficient credits: user={user_balance}, org={await self.repository.get_credit_balance('org', org_id) if org_id else 0}, required={total_cost}",
                extra={
                    "user_id": user_id,
                    "org_id": org_id,
                    "metric": metric,
                    "required": total_cost,
                    "user_balance": user_balance,
                },
            )

            return CreditCheckResponse(
                allowed=False,
                reason="insufficient_credits",
                required_credits=total_cost,
                available_credits=user_balance,  # Return user balance as available
            )

        except Exception as e:
            logger.error(f"Error checking credits: {e}", exc_info=True)
            # Fail safe: deny on error
            return CreditCheckResponse(
                allowed=False,
                reason="system_error",
                required_credits=0,
                available_credits=0,
            )

    async def consume_credits(self, consumption: CreditConsumption) -> bool:
        """Consume credits for completed operation.

        Uses optimistic approach: record consumption even if it fails,
        with failure status for admin resolution.

        Args:
            consumption: Credit consumption details

        Returns:
            True if consumption successful, False otherwise
        """
        logger.debug(
            f"Credit consumption: user={consumption.user_id}, org={consumption.org_id}, "
            f"metric={consumption.metric}, amount={consumption.amount}, "
            f"correlation_id={consumption.correlation_id}"
        )

        try:
            # Get cost per unit from policy
            cost_per_unit = await self.policy_loader.get_cost(consumption.metric)
            total_cost = cost_per_unit * consumption.amount

            logger.debug(f"Total consumption cost: {total_cost} credits")

            # Skip processing for free operations
            if total_cost == 0:
                logger.debug("Free operation - no credits consumed")
                await self.repository.record_operation(
                    subject_type="user",
                    subject_id=consumption.user_id,
                    metric=consumption.metric,
                    amount=0,
                    consumed_from="none",
                    correlation_id=consumption.correlation_id,
                    batch_id=consumption.batch_id,
                    status="completed",
                )
                return True

            # Determine credit source using same logic as check_credits
            source, subject_id = await self._resolve_credit_source(
                consumption.user_id,
                consumption.org_id,
                total_cost,
            )

            logger.debug(f"Consuming {total_cost} credits from {source} account: {subject_id}")

            try:
                # Optimistically consume credits
                new_balance = await self.repository.update_credit_balance(
                    subject_type=source,
                    subject_id=subject_id,
                    delta=-total_cost,  # Negative for consumption
                    correlation_id=consumption.correlation_id,
                )

                # Record successful operation
                await self.repository.record_operation(
                    subject_type=source,
                    subject_id=subject_id,
                    metric=consumption.metric,
                    amount=total_cost,
                    consumed_from=source,
                    correlation_id=consumption.correlation_id,
                    batch_id=consumption.batch_id,
                    status="completed",
                )

                # Record rate limiting usage
                await self.rate_limiter.record_usage(
                    consumption.user_id,
                    consumption.metric,
                    consumption.amount,
                )

                logger.info(
                    f"Credits consumed successfully: {total_cost} from {source}, new balance: {new_balance}",
                    extra={
                        "user_id": consumption.user_id,
                        "org_id": consumption.org_id,
                        "metric": consumption.metric,
                        "amount": total_cost,
                        "source": source,
                        "new_balance": new_balance,
                        "correlation_id": consumption.correlation_id,
                    },
                )

                return True

            except ValueError as e:
                # Balance would go negative - record as failed operation
                logger.warning(
                    f"Credit consumption failed - insufficient balance: {e}",
                    extra={
                        "user_id": consumption.user_id,
                        "org_id": consumption.org_id,
                        "metric": consumption.metric,
                        "correlation_id": consumption.correlation_id,
                    },
                )

                await self.repository.record_operation(
                    subject_type=source,
                    subject_id=subject_id,
                    metric=consumption.metric,
                    amount=total_cost,
                    consumed_from=source,
                    correlation_id=consumption.correlation_id,
                    batch_id=consumption.batch_id,
                    status="failed",
                )

                return False

        except Exception as e:
            logger.error(
                f"Error consuming credits: {e}",
                exc_info=True,
                extra={
                    "user_id": consumption.user_id,
                    "correlation_id": consumption.correlation_id,
                },
            )

            # Record failed operation for audit trail
            try:
                await self.repository.record_operation(
                    subject_type="user",
                    subject_id=consumption.user_id,
                    metric=consumption.metric,
                    amount=0,
                    consumed_from="error",
                    correlation_id=consumption.correlation_id,
                    batch_id=consumption.batch_id,
                    status="failed",
                )
            except Exception:
                logger.error("Failed to record error operation", exc_info=True)

            return False

    async def get_balance(self, user_id: str, org_id: str | None = None) -> CreditBalanceInfo:
        """Get current credit balances for user/organization.

        Args:
            user_id: User identifier
            org_id: Organization identifier (optional)

        Returns:
            CreditBalanceInfo with current balances
        """
        logger.debug(f"Getting balances for user={user_id}, org={org_id}")

        try:
            # Always get user balance
            user_balance = await self.repository.get_credit_balance("user", user_id)

            # Get org balance if org_id provided
            org_balance = None
            if org_id:
                org_balance = await self.repository.get_credit_balance("org", org_id)

            logger.debug(f"Balances - user: {user_balance}, org: {org_balance}")

            return CreditBalanceInfo(
                user_balance=user_balance,
                org_balance=org_balance,
                org_id=org_id,
            )

        except Exception as e:
            logger.error(f"Error getting balances: {e}", exc_info=True)
            # Return zero balances on error
            return CreditBalanceInfo(
                user_balance=0,
                org_balance=0 if org_id else None,
                org_id=org_id,
            )

    async def adjust_credits(self, adjustment: CreditAdjustment) -> bool:
        """Manually adjust credit balance (admin operation).

        Args:
            adjustment: Credit adjustment details

        Returns:
            True if adjustment successful, False otherwise
        """
        logger.info(
            f"Manual credit adjustment: {adjustment.subject_type} {adjustment.subject_id} "
            f"by {adjustment.amount} ({adjustment.reason})"
        )

        try:
            # Generate correlation ID for tracking
            correlation_id = f"manual_adjustment_{adjustment.subject_id}_{adjustment.amount}"

            # Apply adjustment
            new_balance = await self.repository.update_credit_balance(
                subject_type=adjustment.subject_type,
                subject_id=adjustment.subject_id,
                delta=adjustment.amount,
                correlation_id=correlation_id,
            )

            # Record adjustment operation
            await self.repository.record_operation(
                subject_type=adjustment.subject_type,
                subject_id=adjustment.subject_id,
                metric="manual_adjustment",
                amount=abs(adjustment.amount),
                consumed_from="admin",
                correlation_id=correlation_id,
                status="completed",
            )

            logger.info(
                f"Credit adjustment successful: new balance {new_balance}",
                extra={
                    "subject_type": adjustment.subject_type,
                    "subject_id": adjustment.subject_id,
                    "adjustment": adjustment.amount,
                    "new_balance": new_balance,
                    "reason": adjustment.reason,
                },
            )

            return True

        except Exception as e:
            logger.error(f"Error adjusting credits: {e}", exc_info=True)
            return False

    async def _resolve_credit_source(
        self,
        user_id: str,
        org_id: str | None,
        total_cost: int,
    ) -> tuple[str, str]:
        """Resolve which credit source to use (org or user).

        Args:
            user_id: User identifier
            org_id: Organization identifier (optional)
            total_cost: Total credit cost

        Returns:
            Tuple of (source_type, source_id) where source_type is "org" or "user"
        """
        # If no org_id provided, use user credits
        if not org_id:
            logger.debug("No org_id provided, using user credits")
            return ("user", user_id)

        # Check org balance first (dual system precedence)
        org_balance = await self.repository.get_credit_balance("org", org_id)
        if org_balance >= total_cost:
            logger.debug(f"Using org credits: {org_balance} >= {total_cost}")
            return ("org", org_id)

        # Fall back to user credits
        logger.debug(f"Insufficient org credits ({org_balance}), using user credits")
        return ("user", user_id)
