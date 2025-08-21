"""Session management routes for Identity Service.

Handles session listing, revocation, and monitoring operations.
All business logic is delegated to SessionManagementHandler.

New endpoints for production-ready session management.
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
from services.identity_service.domain_handlers.session_management_handler import SessionManagementHandler
from services.identity_service.protocols import TokenIssuer

bp = Blueprint("sessions", __name__, url_prefix="/v1/auth")
logger = create_service_logger("identity_service.api.session_routes")


def _extract_user_from_jwt(token_issuer: TokenIssuer, jwt_token: str | None) -> tuple[str | None, str | None]:
    """Extract user ID and JTI from JWT token.
    
    Returns:
        tuple: (user_id, jti) or (None, None) if invalid
    """
    if not jwt_token:
        return None, None
    
    try:
        claims = token_issuer.verify(jwt_token)
        user_id = claims.get("sub")
        jti = claims.get("jti")  # May be None for access tokens
        return user_id, jti
    except Exception:
        return None, None


@bp.get("/sessions")
@inject
async def list_sessions(
    session_handler: FromDishka[SessionManagementHandler],
    token_issuer: FromDishka[TokenIssuer],
) -> Response | tuple[Response, int]:
    """List all active sessions for the authenticated user."""
    try:
        correlation_id = extract_correlation_id()
        
        # Extract user ID from JWT token
        jwt_token = extract_jwt_token()
        user_id, current_jti = _extract_user_from_jwt(token_issuer, jwt_token)
        
        if not user_id:
            return jsonify({"error": "Invalid or expired token"}), 401

        # Delegate to session management handler
        session_result = await session_handler.list_user_sessions(
            user_id=user_id,
            current_jti=current_jti,
            correlation_id=correlation_id,
        )

        return jsonify(session_result.to_dict())

    except HuleEduError as e:
        logger.warning(
            f"Session list error: {e.error_detail.message}",
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
            f"Unexpected error during session listing: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id_str},
        )
        return jsonify({"error": "Internal server error"}), 500


@bp.delete("/sessions/<session_id>")
@inject
async def revoke_session(
    session_id: str,
    session_handler: FromDishka[SessionManagementHandler],
    token_issuer: FromDishka[TokenIssuer],
) -> Response | tuple[Response, int]:
    """Revoke a specific session by ID."""
    try:
        correlation_id = extract_correlation_id()
        ip_address, _ = extract_client_info()
        
        # Extract user ID from JWT token
        jwt_token = extract_jwt_token()
        user_id, _ = _extract_user_from_jwt(token_issuer, jwt_token)
        
        if not user_id:
            return jsonify({"error": "Invalid or expired token"}), 401

        # Delegate to session management handler
        revoke_result = await session_handler.revoke_session(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
            ip_address=ip_address,
        )

        return jsonify(revoke_result.to_dict())

    except HuleEduError as e:
        logger.warning(
            f"Session revocation error: {e.error_detail.message}",
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
            f"Unexpected error during session revocation: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id_str},
        )
        return jsonify({"error": "Internal server error"}), 500


@bp.delete("/sessions")
@inject
async def revoke_all_sessions(
    session_handler: FromDishka[SessionManagementHandler],
    token_issuer: FromDishka[TokenIssuer],
) -> Response | tuple[Response, int]:
    """Revoke all sessions for the authenticated user."""
    try:
        correlation_id = extract_correlation_id()
        ip_address, _ = extract_client_info()
        
        # Extract user ID from JWT token
        jwt_token = extract_jwt_token()
        user_id, current_jti = _extract_user_from_jwt(token_issuer, jwt_token)
        
        if not user_id:
            return jsonify({"error": "Invalid or expired token"}), 401

        # Check if should exclude current session
        data = await request.get_json() if request.is_json else {}
        exclude_current = data.get("exclude_current", True)

        # Delegate to session management handler
        revoke_result = await session_handler.revoke_all_sessions(
            user_id=user_id,
            correlation_id=correlation_id,
            exclude_current=exclude_current,
            current_jti=current_jti,
            ip_address=ip_address,
        )

        return jsonify(revoke_result.to_dict())

    except HuleEduError as e:
        logger.warning(
            f"Bulk session revocation error: {e.error_detail.message}",
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
            f"Unexpected error during bulk session revocation: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id_str},
        )
        return jsonify({"error": "Internal server error"}), 500


@bp.get("/sessions/active")
@inject
async def get_active_session_count(
    session_handler: FromDishka[SessionManagementHandler],
    token_issuer: FromDishka[TokenIssuer],
) -> Response | tuple[Response, int]:
    """Get count of active sessions for the authenticated user."""
    try:
        correlation_id = extract_correlation_id()
        
        # Extract user ID from JWT token
        jwt_token = extract_jwt_token()
        user_id, _ = _extract_user_from_jwt(token_issuer, jwt_token)
        
        if not user_id:
            return jsonify({"error": "Invalid or expired token"}), 401

        # Delegate to session management handler
        count_result = await session_handler.get_active_session_count(
            user_id=user_id,
            correlation_id=correlation_id,
        )

        return jsonify(count_result.to_dict())

    except HuleEduError as e:
        logger.warning(
            f"Session count error: {e.error_detail.message}",
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
            f"Unexpected error during session count: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id_str},
        )
        return jsonify({"error": "Internal server error"}), 500