"""Password management routes for Identity Service.

Handles password reset and change operations.
All business logic is delegated to PasswordResetHandler.
"""
from __future__ import annotations

from dishka import FromDishka
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from services.identity_service.api.request_utils import (
    extract_client_info,
    extract_correlation_id,
    extract_jwt_token,
)
from services.identity_service.api.schemas import (
    RequestPasswordResetRequest,
    ResetPasswordRequest,
)
from services.identity_service.domain_handlers.password_reset_handler import PasswordResetHandler
from services.identity_service.protocols import TokenIssuer

bp = Blueprint("password", __name__, url_prefix="/v1/auth")
logger = create_service_logger("identity_service.api.password_routes")


@bp.post("/request-password-reset")
@inject
async def request_password_reset(
    password_handler: FromDishka[PasswordResetHandler],
) -> tuple[Response, int]:
    """Request password reset token (public endpoint)."""
    try:
        correlation_id = extract_correlation_id()
        ip_address, _ = extract_client_info()

        payload = RequestPasswordResetRequest(**(await request.get_json()))

        # Delegate to password reset handler
        reset_result = await password_handler.request_password_reset(
            reset_request=payload,
            correlation_id=correlation_id,
            ip_address=ip_address,
        )

        return jsonify(reset_result.to_dict()), 200

    except HuleEduError as e:
        logger.warning(
            f"Password reset request error: {e.error_detail.message}",
            extra={
                "correlation_id": str(e.error_detail.correlation_id),
                "error_code": e.error_detail.error_code,
                "operation": e.error_detail.operation,
            },
        )
        return jsonify({"error": e.error_detail.model_dump()}), 400

    except Exception as e:
        correlation_id_str = str(correlation_id) if "correlation_id" in locals() else "unknown"
        logger.error(
            f"Unexpected error during password reset request: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id_str},
        )
        return jsonify({"error": "Internal server error"}), 500


@bp.post("/reset-password")
@inject
async def reset_password(
    password_handler: FromDishka[PasswordResetHandler],
) -> tuple[Response, int]:
    """Reset password using reset token."""
    try:
        correlation_id = extract_correlation_id()
        ip_address, _ = extract_client_info()

        payload = ResetPasswordRequest(**(await request.get_json()))

        # Delegate to password reset handler
        reset_result = await password_handler.reset_password(
            reset_request=payload,
            correlation_id=correlation_id,
            ip_address=ip_address,
        )

        return jsonify(reset_result.to_dict()), 200

    except HuleEduError as e:
        logger.warning(
            f"Password reset error: {e.error_detail.message}",
            extra={
                "correlation_id": str(e.error_detail.correlation_id),
                "error_code": e.error_detail.error_code,
                "operation": e.error_detail.operation,
            },
        )
        return jsonify({"error": e.error_detail.model_dump()}), 400

    except Exception as e:
        correlation_id_str = str(correlation_id) if "correlation_id" in locals() else "unknown"
        logger.error(
            f"Unexpected error during password reset: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id_str},
        )
        return jsonify({"error": "Internal server error"}), 500


@bp.post("/change-password")
@inject
async def change_password(
    password_handler: FromDishka[PasswordResetHandler],
    token_issuer: FromDishka[TokenIssuer],
) -> tuple[Response, int]:
    """Change password for authenticated user."""
    try:
        correlation_id = extract_correlation_id()
        ip_address, _ = extract_client_info()

        # Extract user ID from JWT token
        jwt_token = extract_jwt_token()
        if not jwt_token:
            return jsonify({"error": "Authorization token required"}), 401
        
        try:
            claims = token_issuer.verify(jwt_token)
            user_id = claims.get("sub")
            if not user_id:
                return jsonify({"error": "Invalid token"}), 401
        except Exception:
            return jsonify({"error": "Invalid or expired token"}), 401

        # Get password data from request
        data = await request.get_json()
        current_password = data.get("current_password")
        new_password = data.get("new_password")
        
        if not current_password or not new_password:
            return jsonify({"error": "Current and new passwords are required"}), 400

        # Delegate to password reset handler
        change_result = await password_handler.change_password(
            user_id=user_id,
            current_password=current_password,
            new_password=new_password,
            correlation_id=correlation_id,
            ip_address=ip_address,
        )

        return jsonify(change_result.to_dict()), 200

    except HuleEduError as e:
        logger.warning(
            f"Password change error: {e.error_detail.message}",
            extra={
                "correlation_id": str(e.error_detail.correlation_id),
                "error_code": e.error_detail.error_code,
                "operation": e.error_detail.operation,
            },
        )
        return jsonify({"error": e.error_detail.model_dump()}), 400

    except Exception as e:
        correlation_id_str = str(correlation_id) if "correlation_id" in locals() else "unknown"
        logger.error(
            f"Unexpected error during password change: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id_str},
        )
        return jsonify({"error": "Internal server error"}), 500