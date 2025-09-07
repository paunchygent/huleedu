"""Administrative API endpoints for Entitlements Service.

This module provides admin endpoints for credit adjustments and
operations history queries. Only available in non-production environments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dishka import FromDishka
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_processing_error,
    raise_validation_error,
)
from huleedu_service_libs.error_handling.quart import CorrelationContext
from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel, Field
from quart import Blueprint, current_app, request
from quart_dishka import inject

from services.entitlements_service.protocols import (
    CreditManagerProtocol,
    EntitlementsRepositoryProtocol,
)

if TYPE_CHECKING:
    from huleedu_service_libs.quart_app import HuleEduApp

logger = create_service_logger("entitlements_service.api.admin")

admin_bp = Blueprint("admin", __name__)
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
    correlation_id: str = Field(..., description="Operation correlation ID")


class CreditSetRequest(BaseModel):
    """Request for setting absolute credit balance."""

    subject_type: str = Field(..., pattern="^(user|org)$", description="Subject type")
    subject_id: str = Field(..., description="Subject identifier")
    balance: int = Field(..., ge=0, description="New absolute balance")


class CreditSetResponse(BaseModel):
    """Response for credit balance setting."""

    success: bool = Field(..., description="Whether setting succeeded")
    balance: int = Field(..., description="New balance")
    subject_type: str = Field(..., description="Subject type")
    subject_id: str = Field(..., description="Subject identifier")
    correlation_id: str = Field(..., description="Operation correlation ID")


@admin_bp.route("/credits/adjust", methods=["POST"])
@inject
async def adjust_credits(
    credit_manager: FromDishka[CreditManagerProtocol],
    corr: FromDishka[CorrelationContext],
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
                correlation_id=corr.uuid,
                original_correlation_id=corr.original,
            )

        adjustment_request = CreditAdjustmentRequest(**data)

        # Correlation from header if provided
        correlation_id = corr.original

        # Perform adjustment
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
            correlation_id=correlation_id,
        )

        # Record metrics (best-effort)
        if "metrics" in app.extensions:
            try:
                m = app.extensions["metrics"]
                adjustment_type = "addition" if adjustment_request.amount > 0 else "deduction"
                if "credit_adjustments_total" in m:
                    m["credit_adjustments_total"].labels(
                        subject_type=adjustment_request.subject_type,
                        adjustment_type=adjustment_type,
                    ).inc()
            except Exception as _me:
                logger.warning(f"Failed to record adjustment metrics: {_me}", exc_info=True)

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

    except ValueError as e:
        # Validation failure (e.g., would go negative)
        raise_validation_error(
            service="entitlements_service",
            operation="adjust_credits",
            field="amount",
            message=str(e),
            correlation_id=corr.uuid,
            original_correlation_id=corr.original,
        )
    except HuleEduError:
        # Preserve structured errors without wrapping
        raise
    except Exception as e:
        # Provide structured processing error for transparency
        raise_processing_error(
            service="entitlements_service",
            operation="adjust_credits",
            message="Failed to adjust credit balance",
            correlation_id=corr.uuid,
            subject_type=data.get("subject_type") if data else None,
            subject_id=data.get("subject_id") if data else None,
            amount=data.get("amount") if data else None,
            reason=data.get("reason") if data else None,
            error=str(e),
            original_correlation_id=corr.original,
        )


@admin_bp.route("/credits/set", methods=["POST"])
@inject
async def set_credits(
    credit_manager: FromDishka[CreditManagerProtocol],
    repository: FromDishka[EntitlementsRepositoryProtocol],
    corr: FromDishka[CorrelationContext],
) -> tuple[dict[str, Any], int]:
    """Set absolute credit balance (admin/testing only).

    This endpoint sets the balance to an absolute value, primarily for testing.

    Returns:
        JSON response with set result
    """
    app: HuleEduApp = current_app._get_current_object()  # type: ignore[attr-defined]

    try:
        # Parse request
        data = await request.get_json()
        if not data:
            raise_validation_error(
                service="entitlements_service",
                operation="set_credits",
                field="request_body",
                message="Request body is required",
                correlation_id=corr.uuid,
                original_correlation_id=corr.original,
            )

        set_request = CreditSetRequest(**data)

        # Correlation from header if provided
        correlation_id = corr.original

        # Get current balance using repository directly for precise control
        subject_type = set_request.subject_type
        subject_id = set_request.subject_id
        try:
            current_balance = await repository.get_credit_balance(subject_type, subject_id)
        except HuleEduError:
            raise
        except Exception as e:
            raise_processing_error(
                service="entitlements_service",
                operation="set_credits",
                message="Failed to read current balance",
                correlation_id=corr.uuid,
                subject_type=set_request.subject_type,
                subject_id=set_request.subject_id,
                error=str(e),
                original_correlation_id=corr.original,
            )

        # Calculate adjustment needed to reach target balance
        adjustment_needed = set_request.balance - current_balance

        # If no adjustment needed, return current state
        if adjustment_needed == 0:
            response = CreditSetResponse(
                success=True,
                balance=set_request.balance,
                subject_type=set_request.subject_type,
                subject_id=set_request.subject_id,
                correlation_id=correlation_id,
            )
            return response.model_dump(), 200

        # Perform adjustment to reach target balance
        reason = f"Admin balance set to {set_request.balance}"
        try:
            new_balance = await credit_manager.adjust_balance(
                subject_type=set_request.subject_type,
                subject_id=set_request.subject_id,
                amount=adjustment_needed,
                reason=reason,
                correlation_id=correlation_id,
            )
        except ValueError as e:
            raise_validation_error(
                service="entitlements_service",
                operation="set_credits",
                field="balance",
                message=str(e),
                correlation_id=corr.uuid,
                subject_type=set_request.subject_type,
                subject_id=set_request.subject_id,
                target_balance=set_request.balance,
                original_correlation_id=corr.original,
            )
        except HuleEduError:
            raise
        except Exception as e:
            raise_processing_error(
                service="entitlements_service",
                operation="set_credits",
                message="Failed to set credit balance",
                correlation_id=corr.uuid,
                subject_type=set_request.subject_type,
                subject_id=set_request.subject_id,
                target_balance=set_request.balance,
                adjustment=adjustment_needed,
                error=str(e),
                original_correlation_id=corr.original,
            )

        # Create response
        response = CreditSetResponse(
            success=True,
            balance=new_balance,
            subject_type=set_request.subject_type,
            subject_id=set_request.subject_id,
            correlation_id=correlation_id,
        )

        # Record metrics (best-effort)
        if "metrics" in app.extensions:
            try:
                m = app.extensions["metrics"]
                if "credit_adjustments_total" in m:
                    m["credit_adjustments_total"].labels(
                        subject_type=set_request.subject_type,
                        adjustment_type="set",
                    ).inc()
            except Exception as _me:
                logger.warning(f"Failed to record set metrics: {_me}", exc_info=True)

        logger.info(
            f"Admin set balance: {set_request.balance} credits for "
            f"{set_request.subject_type}:{set_request.subject_id}",
            extra={
                "subject_type": set_request.subject_type,
                "subject_id": set_request.subject_id,
                "target_balance": set_request.balance,
                "adjustment_amount": adjustment_needed,
                "correlation_id": correlation_id,
            },
        )

        return response.model_dump(), 200

    except HuleEduError:
        # Preserve structured errors without wrapping
        raise
    except Exception as e:
        # Unhandled errors should be returned as structured processing errors
        # Try to include identifiers from body if available
        try:
            body = await request.get_json()
        except Exception:
            body = None
        raise_processing_error(
            service="entitlements_service",
            operation="set_credits",
            message="Unhandled error while setting credits",
            correlation_id=corr.uuid,
            subject_type=(body or {}).get("subject_type"),
            subject_id=(body or {}).get("subject_id"),
            target_balance=(body or {}).get("balance"),
            error=str(e),
            original_correlation_id=corr.original,
        )


@admin_bp.route("/credits/operations", methods=["GET"])
@inject
async def get_operations(
    repository: FromDishka[EntitlementsRepositoryProtocol],
    corr: FromDishka[CorrelationContext],
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
                correlation_id=corr.uuid,
                original_correlation_id=corr.original,
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

        # Include header correlation in success for symmetry
        return {
            "operations": operations,
            "count": len(operations),
            "correlation_id": corr.original,
        }, 200

    except HuleEduError:
        raise
    except Exception as e:
        raise_processing_error(
            service="entitlements_service",
            operation="get_operations",
            message="Failed to get operations history",
            correlation_id=corr.uuid,
            subject_type=subject_type,
            subject_id=subject_id,
            error=str(e),
            original_correlation_id=corr.original,
        )


@admin_bp.route("/credits/reset-rate-limit", methods=["POST"])
@inject
async def reset_rate_limit(corr: FromDishka[CorrelationContext]) -> tuple[dict[str, Any], int]:
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
                correlation_id=corr.uuid,
                original_correlation_id=corr.original,
            )

        subject_id = data.get("subject_id")
        metric = data.get("metric")

        if not subject_id or not metric:
            raise_validation_error(
                service="entitlements_service",
                operation="reset_rate_limit",
                field="subject_id,metric",
                message="subject_id and metric are required",
                correlation_id=corr.uuid,
                original_correlation_id=corr.original,
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
            "correlation_id": corr.original,
        }, 200

    except HuleEduError:
        raise
    except Exception as e:
        raise_processing_error(
            service="entitlements_service",
            operation="reset_rate_limit",
            message="Failed to reset rate limit",
            correlation_id=corr.uuid,
            subject_id=subject_id if "subject_id" in locals() else None,
            metric=metric if "metric" in locals() else None,
            error=str(e),
            original_correlation_id=corr.original,
        )
