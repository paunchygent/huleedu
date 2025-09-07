"""Credit manager implementation for Entitlements Service.

This module provides the core credit management logic with dual system
support (org credits first, user credits fallback) and optimistic consumption.
"""

from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger

from services.entitlements_service.protocols import (
    BulkCreditCheckResult,
    CreditAdjustment,
    CreditBalanceInfo,
    CreditCheckResponse,
    CreditConsumptionResult,
    EntitlementsRepositoryProtocol,
    EventPublisherProtocol,
    PerMetricCreditStatus,
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
        event_publisher: EventPublisherProtocol,
    ) -> None:
        """Initialize credit manager with dependencies.

        Args:
            repository: Repository for credit data persistence
            policy_loader: Policy loader for costs and limits
            rate_limiter: Rate limiter for operation throttling
            event_publisher: Event publisher for domain events
        """
        self.repository = repository
        self.policy_loader = policy_loader
        self.rate_limiter = rate_limiter
        self.event_publisher = event_publisher

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
                # Publish rate limit exceeded event
                try:
                    # Generate correlation ID for rate limit event if not provided
                    rate_limit_correlation_id = (
                        f"rate_limit_{user_id}_{metric}_{rate_check.current_count}"
                    )

                    await self.event_publisher.publish_rate_limit_exceeded(
                        subject_id=user_id,
                        metric=metric,
                        limit=rate_check.limit,
                        current_count=rate_check.current_count,
                        window_seconds=rate_check.window_seconds,
                        correlation_id=rate_limit_correlation_id,
                    )
                    logger.debug(
                        f"Rate limit exceeded event published: {rate_limit_correlation_id}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to publish rate limit exceeded event: {e}",
                        exc_info=True,
                        extra={"user_id": user_id, "metric": metric},
                    )
                    # Continue - don't fail the check due to event publishing issues

                logger.info(
                    (
                        f"Rate limit exceeded for {metric}: "
                        f"{rate_check.current_count}/{rate_check.limit}"
                    ),
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
            org_current_balance = (
                await self.repository.get_credit_balance("org", org_id) if org_id else 0
            )
            logger.info(
                (
                    f"Insufficient credits: user={user_balance}, org={org_current_balance}, "
                    f"required={total_cost}"
                ),
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

    async def consume_credits(
        self,
        user_id: str,
        org_id: str | None,
        metric: str,
        amount: int,
        batch_id: str | None,
        correlation_id: str,
    ) -> CreditConsumptionResult:
        """Consume credits for completed operation.

        Uses optimistic approach: record consumption even if it fails,
        with failure status for admin resolution.

        Args:
            consumption: Credit consumption details

        Returns:
            True if consumption successful, False otherwise
        """
        logger.debug(
            f"Credit consumption: user={user_id}, org={org_id}, "
            f"metric={metric}, amount={amount}, correlation_id={correlation_id}"
        )

        try:
            # Get cost per unit from policy
            cost_per_unit = await self.policy_loader.get_cost(metric)
            total_cost = cost_per_unit * amount

            logger.debug(f"Total consumption cost: {total_cost} credits")

            # Skip processing for free operations
            if total_cost == 0:
                logger.debug("Free operation - no credits consumed")
                # Still resolve credit source for consistency in reporting
                source, subject_id = await self._resolve_credit_source(
                    user_id,
                    org_id,
                    total_cost,
                )
                await self.repository.record_operation(
                    subject_type=source,
                    subject_id=subject_id,
                    metric=metric,
                    amount=0,
                    consumed_from=source,  # Use actual resolved source
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                    status="completed",
                )
                # Return current balance for the resolved source
                current_balance = await self.repository.get_credit_balance(source, subject_id)
                return CreditConsumptionResult(
                    success=True,
                    new_balance=current_balance,
                    consumed_from=source,  # Use actual resolved source
                )

            # Determine credit source using same logic as check_credits
            source, subject_id = await self._resolve_credit_source(
                user_id,
                org_id,
                total_cost,
            )

            logger.debug(f"Consuming {total_cost} credits from {source} account: {subject_id}")

            # Capture old balance before consumption for event publishing
            old_balance = await self.repository.get_credit_balance(source, subject_id)

            try:
                # Optimistically consume credits
                new_balance = await self.repository.update_credit_balance(
                    subject_type=source,
                    subject_id=subject_id,
                    delta=-total_cost,  # Negative for consumption
                    correlation_id=correlation_id,
                )

                # Record successful operation
                await self.repository.record_operation(
                    subject_type=source,
                    subject_id=subject_id,
                    metric=metric,
                    amount=total_cost,
                    consumed_from=source,
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                    status="completed",
                )

                # Record rate limiting usage
                await self.rate_limiter.record_usage(user_id, metric, amount)

                # Publish domain events for successful consumption
                try:
                    # Publish credit balance changed event
                    await self.event_publisher.publish_credit_balance_changed(
                        subject_type=source,
                        subject_id=subject_id,
                        old_balance=old_balance,
                        new_balance=new_balance,
                        delta=-total_cost,
                        correlation_id=correlation_id,
                    )

                    # Publish usage recorded event for analytics
                    await self.event_publisher.publish_usage_recorded(
                        subject_type=source,
                        subject_id=subject_id,
                        metric=metric,
                        amount=amount,  # Use original amount, not total_cost
                        correlation_id=correlation_id,
                    )

                    logger.debug(f"Events published for credit consumption: {correlation_id}")
                except Exception as e:
                    logger.warning(
                        f"Failed to publish events for credit consumption: {e}",
                        exc_info=True,
                        extra={"correlation_id": correlation_id},
                    )
                    # Continue - don't fail the operation due to event publishing issues

                logger.info(
                    (
                        f"Credits consumed successfully: {total_cost} from {source}, "
                        f"new balance: {new_balance}"
                    ),
                    extra={
                        "user_id": user_id,
                        "org_id": org_id,
                        "metric": metric,
                        "amount": total_cost,
                        "source": source,
                        "new_balance": new_balance,
                        "correlation_id": correlation_id,
                    },
                )

                return CreditConsumptionResult(
                    success=True,
                    new_balance=new_balance,
                    consumed_from=source,
                )

            except ValueError as e:
                # Balance would go negative - record as failed operation
                logger.warning(
                    f"Credit consumption failed - insufficient balance: {e}",
                    extra={
                        "user_id": user_id,
                        "org_id": org_id,
                        "metric": metric,
                        "correlation_id": correlation_id,
                    },
                )

                await self.repository.record_operation(
                    subject_type=source,
                    subject_id=subject_id,
                    metric=metric,
                    amount=total_cost,
                    consumed_from=source,
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                    status="failed",
                )

                current_balance = await self.repository.get_credit_balance(source, subject_id)
                return CreditConsumptionResult(
                    success=False,
                    new_balance=current_balance,
                    consumed_from=source,
                )

        except Exception as e:
            logger.error(
                f"Error consuming credits: {e}",
                exc_info=True,
                extra={"user_id": user_id, "correlation_id": correlation_id},
            )

            # Record failed operation for audit trail
            # In error case, we don't know the source, so fallback to user as default
            # This preserves the user_id which is always available
            fallback_source = "user"
            fallback_subject = user_id
            
            try:
                await self.repository.record_operation(
                    subject_type=fallback_source,
                    subject_id=fallback_subject,
                    metric=metric,
                    amount=0,
                    consumed_from=fallback_source,  # Use fallback source
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                    status="failed",
                )
            except Exception:
                logger.error("Failed to record error operation", exc_info=True)

            current_balance = await self.repository.get_credit_balance(fallback_source, fallback_subject)
            return CreditConsumptionResult(
                success=False,
                new_balance=current_balance,
                consumed_from=fallback_source,  # Use fallback source
            )

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
        """Backward-compatible method; delegates to adjust_balance and returns success."""
        try:
            await self.adjust_balance(
                subject_type=adjustment.subject_type,
                subject_id=adjustment.subject_id,
                amount=adjustment.amount,
                reason=adjustment.reason,
                correlation_id=f"manual_adjustment_{adjustment.subject_id}_{adjustment.amount}",
            )
            return True
        except Exception:
            return False

    async def adjust_balance(
        self,
        subject_type: str,
        subject_id: str,
        amount: int,
        reason: str,
        correlation_id: str,
    ) -> int:
        """Manually adjust credit balance (admin operation)."""
        logger.info(f"Manual credit adjustment: {subject_type} {subject_id} by {amount} ({reason})")

        # Capture old balance before adjustment for event publishing
        old_balance = await self.repository.get_credit_balance(subject_type, subject_id)

        # Apply adjustment via repository
        new_balance = await self.repository.update_credit_balance(
            subject_type=subject_type,
            subject_id=subject_id,
            delta=amount,
            correlation_id=correlation_id,
        )

        # Record adjustment operation
        await self.repository.record_operation(
            subject_type=subject_type,
            subject_id=subject_id,
            metric="manual_adjustment",
            amount=abs(amount),
            consumed_from=subject_type,
            correlation_id=correlation_id,
            status="completed",
        )

        # Publish domain event for manual adjustment
        try:
            await self.event_publisher.publish_credit_balance_changed(
                subject_type=subject_type,
                subject_id=subject_id,
                old_balance=old_balance,
                new_balance=new_balance,
                delta=amount,
                correlation_id=correlation_id,
            )
            logger.debug(f"Credit balance changed event published for adjustment: {correlation_id}")
        except Exception as e:
            logger.warning(
                f"Failed to publish event for credit adjustment: {e}",
                exc_info=True,
                extra={"correlation_id": correlation_id},
            )
            # Continue - don't fail the operation due to event publishing issues

        logger.info(
            f"Credit adjustment successful: new balance {new_balance}",
            extra={
                "subject_type": subject_type,
                "subject_id": subject_id,
                "adjustment": amount,
                "new_balance": new_balance,
                "reason": reason,
            },
        )

        return new_balance

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

    async def reload_policies(self) -> None:
        """Force reload of policies from file and update cache."""
        await self.policy_loader.reload_policies()

    async def check_credits_bulk(
        self,
        user_id: str,
        org_id: str | None,
        requirements: dict[str, int],
        correlation_id: str | None = None,
    ) -> BulkCreditCheckResult:
        """Evaluate multiple metrics atomically with org-first attribution.

        - Computes total required credits using policy costs.
        - Performs rate-limit checks per metric for the user subject.
        - Chooses a single source (org, then user) that must cover the total.
        - Does not reserve/consume credits; advisory only.
        """
        # Compute per-metric required credits using policy costs
        per_metric_required: dict[str, int] = {}
        total_required = 0
        for metric, qty in requirements.items():
            cost = await self.policy_loader.get_cost(metric)
            required = max(0, cost * max(0, qty))
            per_metric_required[metric] = required
            total_required += required

        # Short-circuit for all-free operations
        if total_required == 0:
            free_per_metric_status = {
                m: PerMetricCreditStatus(
                    required=req,
                    available=0,
                    allowed=True,
                    source=None,
                    reason=None,
                )
                for m, req in per_metric_required.items()
            }
            return BulkCreditCheckResult(
                allowed=True,
                required_credits=0,
                available_credits=0,
                per_metric=free_per_metric_status,
                denial_reason=None,
                correlation_id=correlation_id,
            )

        # Rate-limit checks per metric (user-scoped)
        rate_limited_any = False
        per_metric_status: dict[str, PerMetricCreditStatus] = {}
        for metric, qty in requirements.items():
            rl = await self.rate_limiter.check_rate_limit(user_id, metric, max(0, qty))
            if not rl.allowed:
                rate_limited_any = True
                # Publish RL exceeded event (best-effort)
                try:
                    self_event_correlation = (
                        correlation_id or f"rate_limit_{user_id}_{metric}_{rl.current_count}"
                    )
                    await self.event_publisher.publish_rate_limit_exceeded(
                        subject_id=user_id,
                        metric=metric,
                        limit=rl.limit,
                        current_count=rl.current_count,
                        window_seconds=rl.window_seconds,
                        correlation_id=self_event_correlation,
                    )
                except Exception:
                    logger.warning("Failed to publish rate limit event", exc_info=True)

            # Fill status with allowed tentative; credit availability filled later
            per_metric_status[metric] = PerMetricCreditStatus(
                required=per_metric_required[metric],
                available=0,
                allowed=rl.allowed,
                source=None,
                reason=None if rl.allowed else "rate_limit_exceeded",
            )

        if rate_limited_any:
            # Aggregate response for RL: 429, no credit source selection
            # Available credits remains 0 in per-metric (advisory)
            return BulkCreditCheckResult(
                allowed=False,
                required_credits=total_required,
                available_credits=0,
                per_metric=per_metric_status,
                denial_reason="rate_limit_exceeded",
                correlation_id=correlation_id,
            )

        # Determine org-first source that can cover the total
        org_balance = await self.repository.get_credit_balance("org", org_id) if org_id else 0
        user_balance = await self.repository.get_credit_balance("user", user_id)

        chosen_source: str | None = None
        available_credits = 0
        if org_id and org_balance >= total_required:
            chosen_source = "org"
            available_credits = org_balance
        elif user_balance >= total_required:
            chosen_source = "user"
            available_credits = user_balance
        else:
            chosen_source = None
            available_credits = user_balance

        # Populate per-metric metadata with chosen source and availability
        for metric, status in per_metric_status.items():
            status.source = chosen_source
            status.available = available_credits
            if chosen_source is None:
                status.allowed = False
                status.reason = "insufficient_credits"

        if chosen_source is None:
            return BulkCreditCheckResult(
                allowed=False,
                required_credits=total_required,
                available_credits=available_credits,
                per_metric=per_metric_status,
                denial_reason="insufficient_credits",
                correlation_id=correlation_id,
            )

        return BulkCreditCheckResult(
            allowed=True,
            required_credits=total_required,
            available_credits=available_credits,
            per_metric=per_metric_status,
            denial_reason=None,
            correlation_id=correlation_id,
        )
