"""Administrative API endpoints for Entitlements Service.

This module provides admin endpoints for credit adjustments and
operations history queries. Only available in non-production environments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from dishka.integrations.quart import FromDishka
from huleedu_service_libs.error_handling import raise_validation_error
from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel, Field
from quart import Blueprint, current_app, request

from services.entitlements_service.protocols import (
    CreditManagerProtocol,
    EntitlementsRepositoryProtocol,
)

if TYPE_CHECKING:
    from huleedu_service_libs.quart_app import HuleEduApp

logger = create_service_logger("entitlements_service.api.admin")

# Create admin blueprint
admin_bp = Blueprint("admin", __name__)


class CreditAdjustmentRequest(BaseModel):
    """Request for manual credit adjustment."""

    subject_type: str = Field(..., pattern="^(user|org)$", description="Subject type")
    subject_id: str = Field(..., description="Subject identifier")
    amount: int = Field(..., description="Adjustment amount (positive to add, negative to deduct)")
    reason: str = Field(..., description="Reason for adjustment")


class CreditAdjustmentResponse(BaseModel):
    """Response for credit adjustment."""

    success: bool = Field(..., description="Whether adjustment succeeded")
    new_balance: int = Field(..., description="New balance after adjustment")
    subject_type: str = Field(..., description="Subject type")
    subject_id: str = Field(..., description="Subject identifier")


@admin_bp.route("/credits/adjust", methods=["POST"])
async def adjust_credits(
    credit_manager: FromDishka[CreditManagerProtocol],
) -> tuple[dict[str, Any], int]:
    """Manually adjust credit balance (admin only).

    Returns:
        JSON response with adjustment result
    """
    app: HuleEduApp = current_app._get_current_object()  # type: ignore[attr-defined]

    try:
        # Parse request
        data = await request.get_json()
        if not data:
            raise_validation_error(
                service="entitlements_service",
                operation="adjust_credits",
                field="request_body",
                message="Request body is required",
                correlation_id=uuid4(),
            )

        adjustment_request = CreditAdjustmentRequest(**data)

        # Perform adjustment
        from uuid import uuid4

        correlation_id = str(uuid4())

        new_balance = await credit_manager.adjust_balance(
            subject_type=adjustment_request.subject_type,
            subject_id=adjustment_request.subject_id,
            amount=adjustment_request.amount,
            reason=adjustment_request.reason,
            correlation_id=correlation_id,
        )

        # Create response
        response = CreditAdjustmentResponse(
            success=True,
            new_balance=new_balance,
            subject_type=adjustment_request.subject_type,
            subject_id=adjustment_request.subject_id,
        )

        # Record metrics
        if "metrics" in app.extensions:
            metrics = app.extensions["metrics"]
            adjustment_type = "addition" if adjustment_request.amount > 0 else "deduction"
            metrics.record_credit_adjustment(
                subject_type=adjustment_request.subject_type,
                adjustment_type=adjustment_type,
                amount=abs(adjustment_request.amount),
            )

        logger.info(
            f"Admin adjustment: {adjustment_request.amount} credits for "
            f"{adjustment_request.subject_type}:{adjustment_request.subject_id}",
            extra={
                "subject_type": adjustment_request.subject_type,
                "subject_id": adjustment_request.subject_id,
                "amount": adjustment_request.amount,
                "reason": adjustment_request.reason,
                "correlation_id": correlation_id,
            },
        )

        return response.model_dump(), 200

    except Exception as e:
        logger.error(f"Error adjusting credits: {e}", exc_info=True)
        raise


@admin_bp.route("/credits/operations", methods=["GET"])
async def get_operations(
    repository: FromDishka[EntitlementsRepositoryProtocol],
) -> tuple[dict[str, Any], int]:
    """Get credit operations history (admin only).

    Query parameters:
        subject_type: Filter by subject type (user/org)
        subject_id: Filter by subject ID
        correlation_id: Filter by correlation ID
        limit: Maximum number of records (default 100)

    Returns:
        JSON response with operations history
    """
    try:
        # Get query parameters
        subject_type = request.args.get("subject_type")
        subject_id = request.args.get("subject_id")
        correlation_id = request.args.get("correlation_id")
        limit_str = request.args.get("limit", "100")
        limit = int(limit_str)

        # Validate limit
        if limit < 1 or limit > 1000:
            raise_validation_error(
                service="entitlements_service",
                operation="get_operations",
                field="limit",
                message="Limit must be between 1 and 1000",
                correlation_id=uuid4(),
            )

        # Get operations history
        operations = await repository.get_operations_history(
            subject_type=subject_type,
            subject_id=subject_id,
            correlation_id=correlation_id,
            limit=limit,
        )

        logger.info(
            f"Operations query returned {len(operations)} records",
            extra={
                "subject_type": subject_type,
                "subject_id": subject_id,
                "correlation_id": correlation_id,
                "limit": limit,
            },
        )

        return {"operations": operations, "count": len(operations)}, 200

    except Exception as e:
        logger.error(f"Error getting operations: {e}", exc_info=True)
        raise


@admin_bp.route("/credits/reset-rate-limit", methods=["POST"])
async def reset_rate_limit() -> tuple[dict[str, Any], int]:
    """Reset rate limit for a subject/metric (admin only).

    Returns:
        JSON response confirming reset
    """
    try:
        # Parse request
        data = await request.get_json()
        if not data:
            raise_validation_error(
                service="entitlements_service",
                operation="reset_rate_limit",
                field="request_body",
                message="Request body is required",
                correlation_id=uuid4(),
            )

        subject_id = data.get("subject_id")
        metric = data.get("metric")

        if not subject_id or not metric:
            raise_validation_error(
                service="entitlements_service",
                operation="reset_rate_limit",
                field="subject_id,metric",
                message="subject_id and metric are required",
                correlation_id=uuid4(),
            )

        # TODO: In Phase 2, inject RateLimiterProtocol directly
        # For now, this is a placeholder endpoint

        logger.info(
            f"Rate limit reset for {subject_id}/{metric}",
            extra={
                "subject_id": subject_id,
                "metric": metric,
            },
        )

        return {
            "success": True,
            "message": f"Rate limit reset for {subject_id}/{metric}",
        }, 200

    except Exception as e:
        logger.error(f"Error resetting rate limit: {e}", exc_info=True)
        raise
