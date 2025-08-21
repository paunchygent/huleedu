"""Email verification routes for Identity Service.

Handles email verification token generation and validation.
All business logic is delegated to VerificationHandler.
"""
from __future__ import annotations

from dishka import FromDishka
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from services.identity_service.api.request_utils import extract_correlation_id, extract_jwt_token
from services.identity_service.api.schemas import (
    RequestEmailVerificationRequest,
    VerifyEmailRequest,
)
from services.identity_service.domain_handlers.verification_handler import VerificationHandler
from services.identity_service.protocols import TokenIssuer

bp = Blueprint("verification", __name__, url_prefix="/v1/auth")
logger = create_service_logger("identity_service.api.verification_routes")


@bp.post("/request-email-verification")
@inject
async def request_email_verification(
    verification_handler: FromDishka[VerificationHandler],
    token_issuer: FromDishka[TokenIssuer],
) -> tuple[Response, int]:
    """Request email verification token for authenticated user."""
    try:
        correlation_id = extract_correlation_id()

        payload = RequestEmailVerificationRequest(**(await request.get_json() or {}))

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

        # Delegate to verification handler
        verification_result = await verification_handler.request_email_verification(
            request_data=payload,
            user_id=user_id,
            correlation_id=correlation_id,
        )

        return jsonify(verification_result.to_dict()), 200

    except HuleEduError as e:
        logger.warning(
            f"Email verification request error: {e.error_detail.message}",
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
            f"Unexpected error during email verification request: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id_str},
        )
        return jsonify({"error": "Internal server error"}), 500


@bp.post("/verify-email")
@inject
async def verify_email(
    verification_handler: FromDishka[VerificationHandler],
) -> tuple[Response, int]:
    """Verify email using verification token."""
    try:
        correlation_id = extract_correlation_id()

        payload = VerifyEmailRequest(**(await request.get_json()))

        # Delegate to verification handler
        verification_result = await verification_handler.verify_email(
            verify_request=payload,
            correlation_id=correlation_id,
        )

        return jsonify(verification_result.to_dict()), 200

    except HuleEduError as e:
        logger.warning(
            f"Email verification error: {e.error_detail.message}",
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
            f"Unexpected error during email verification: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id_str},
        )
        return jsonify({"error": "Internal server error"}), 500