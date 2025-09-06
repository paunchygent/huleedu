"""Core entitlements API endpoints.

This module provides the main API endpoints for credit checking,
consumption, and balance queries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from common_core.entitlements_models import (
    CreditCheckRequestV1,
    CreditCheckResponseV1,
    CreditConsumptionV1,
)
from dishka import FromDishka
from huleedu_service_libs.error_handling import raise_validation_error
from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel, Field
from quart import Blueprint, current_app, request
from quart_dishka import inject

from services.entitlements_service.protocols import CreditManagerProtocol

if TYPE_CHECKING:
    from huleedu_service_libs.quart_app import HuleEduApp

logger = create_service_logger("entitlements_service.api.entitlements")

# Create entitlements blueprint
entitlements_bp = Blueprint("entitlements", __name__)


# Local response models (not in common_core)
class CreditConsumptionResponse(BaseModel):
    """Response for credit consumption."""

    success: bool = Field(..., description="Whether consumption succeeded")
    new_balance: int = Field(..., description="New balance after consumption")
    consumed_from: str = Field(..., description="Which balance was used")


class BalanceResponse(BaseModel):
    """Response for balance query."""

    user_balance: int = Field(..., description="User's credit balance")
    org_balance: int | None = Field(None, description="Organization's credit balance")
    org_id: str | None = Field(None, description="Organization ID if applicable")


@entitlements_bp.route("/check-credits", methods=["POST"])
@inject
async def check_credits(
    credit_manager: FromDishka[CreditManagerProtocol],
) -> tuple[dict[str, Any], int]:
    """Check if sufficient credits are available for an operation.

    Returns:
        JSON response with credit check result
    """
    app: HuleEduApp = current_app._get_current_object()  # type: ignore[attr-defined]

    try:
        # Parse request
        data = await request.get_json()
        if not data:
            raise_validation_error(
                service="entitlements_service",
                operation="check_credits",
                field="request_body",
                message="Request body is required",
                correlation_id=uuid4(),
            )

        check_request = CreditCheckRequestV1(**data)

        # Perform credit check
        result = await credit_manager.check_credits(
            user_id=check_request.user_id,
            org_id=check_request.org_id,
            metric=check_request.metric,
            amount=check_request.amount,
        )

        # Map to response model
        response = CreditCheckResponseV1(
            allowed=result.allowed,
            reason=result.reason,
            required_credits=result.required_credits,
            available_credits=result.available_credits,
            source=result.source,
        )

        # Record metrics
        if hasattr(app, "metrics"):
            app.metrics.record_credit_check(
                result="allowed" if result.allowed else "denied",
                source=result.source or "none",
            )

        logger.info(
            f"Credit check for {check_request.user_id}: {result.allowed}",
            extra={
                "user_id": check_request.user_id,
                "metric": check_request.metric,
                "allowed": result.allowed,
            },
        )

        return response.model_dump(), 200

    except Exception as e:
        logger.error(f"Error checking credits: {e}", exc_info=True)
        raise


@entitlements_bp.route("/consume-credits", methods=["POST"])
@inject
async def consume_credits(
    credit_manager: FromDishka[CreditManagerProtocol],
) -> tuple[dict[str, Any], int]:
    """Consume credits for an operation.

    Returns:
        JSON response with consumption result
    """
    app: HuleEduApp = current_app._get_current_object()  # type: ignore[attr-defined]

    try:
        # Parse request
        data = await request.get_json()
        if not data:
            raise_validation_error(
                service="entitlements_service",
                operation="consume_credits",
                field="request_body",
                message="Request body is required",
                correlation_id=uuid4(),
            )

        consumption_request = CreditConsumptionV1(**data)

        # Consume credits
        result = await credit_manager.consume_credits(
            user_id=consumption_request.user_id,
            org_id=consumption_request.org_id,
            metric=consumption_request.metric,
            amount=consumption_request.amount,
            batch_id=consumption_request.batch_id,
            correlation_id=consumption_request.correlation_id,
        )

        # Map to response model
        response = CreditConsumptionResponse(
            success=result.success,
            new_balance=result.new_balance,
            consumed_from=result.consumed_from,
        )

        # Record metrics
        if hasattr(app, "metrics"):
            app.metrics.record_credit_consumption(
                metric=consumption_request.metric,
                source=result.consumed_from,
                amount=consumption_request.amount,
            )

        logger.info(
            f"Credits consumed for {consumption_request.user_id}: {consumption_request.amount}",
            extra={
                "user_id": consumption_request.user_id,
                "metric": consumption_request.metric,
                "amount": consumption_request.amount,
                "correlation_id": consumption_request.correlation_id,
            },
        )

        return response.model_dump(), 200

    except Exception as e:
        logger.error(f"Error consuming credits: {e}", exc_info=True)
        raise


@entitlements_bp.route("/balance/<user_id>", methods=["GET"])
@inject
async def get_balance(
    user_id: str,
    credit_manager: FromDishka[CreditManagerProtocol],
) -> tuple[dict[str, Any], int]:
    """Get credit balance for a user.

    Args:
        user_id: User identifier

    Returns:
        JSON response with balance information
    """
    try:
        # Get user balance
        balances = await credit_manager.get_balance(
            user_id=user_id,
            org_id=None,
        )

        # TODO: Get org_id from user context/token
        # For now, return user balance only
        response = BalanceResponse(
            user_balance=balances.user_balance,
            org_balance=balances.org_balance,
            org_id=balances.org_id,
        )

        logger.info(
            f"Balance query for {user_id}: {balances.user_balance}",
            extra={"user_id": user_id, "balance": balances.user_balance},
        )

        return response.model_dump(), 200

    except Exception as e:
        logger.error(f"Error getting balance: {e}", exc_info=True)
        raise
