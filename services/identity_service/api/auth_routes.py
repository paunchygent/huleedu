"""Core authentication routes for Identity Service.

Handles login, logout, and token refresh operations.
All business logic is delegated to AuthenticationHandler.

This replaces the monolithic auth_routes.py with focused, thin routes.
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
    extract_token_from_body_or_header,
    parse_device_info,
)
from services.identity_service.api.schemas import (
    LoginRequest,
    RefreshTokenRequest,
)
from services.identity_service.domain_handlers.authentication_handler import AuthenticationHandler

bp = Blueprint("auth", __name__, url_prefix="/v1/auth")
logger = create_service_logger("identity_service.api.auth_routes")


@bp.post("/login")
@inject
async def login(
    auth_handler: FromDishka[AuthenticationHandler],
) -> Response | tuple[Response, int]:
    """User login with security features (rate limiting, lockout, audit)."""
    try:
        correlation_id = extract_correlation_id()
        ip_address, user_agent = extract_client_info()
        device_name, device_type = parse_device_info(user_agent)
        
        payload = LoginRequest(**(await request.get_json()))
        
        # Delegate to authentication handler
        login_result = await auth_handler.login(
            login_request=payload,
            correlation_id=correlation_id,
            ip_address=ip_address,
            user_agent=user_agent,
            device_name=device_name,
            device_type=device_type,
        )
        
        return jsonify(login_result.to_dict())

    except HuleEduError as e:
        logger.warning(
            f"Authentication error during login: {e.error_detail.message}",
            extra={
                "correlation_id": str(e.error_detail.correlation_id),
                "error_code": e.error_detail.error_code,
                "operation": e.error_detail.operation,
            },
        )
        status_code = getattr(e.error_detail, "status_code", 400)
        return jsonify({"error": e.error_detail.model_dump()}), status_code

    except Exception as e:
        correlation_id_str = str(correlation_id) if "correlation_id" in locals() else "unknown"
        logger.error(
            f"Unexpected error during login: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id_str},
        )
        return jsonify({"error": "Internal server error"}), 500


@bp.post("/logout")
@inject
async def logout(
    auth_handler: FromDishka[AuthenticationHandler],
) -> Response | tuple[Response, int]:
    """User logout with token revocation."""
    try:
        correlation_id = extract_correlation_id()
        
        # Get token from Authorization header first
        token = extract_token_from_body_or_header()
        
        # If not in header, check request body
        if not token:
            try:
                data = await request.get_json() or {}
                token = data.get("refresh_token")
            except Exception:
                pass  # Invalid JSON or no body
        
        # Delegate to authentication handler
        logout_result = await auth_handler.logout(
            token=token or "",
            correlation_id=correlation_id,
        )
        
        return jsonify(logout_result.to_dict())
        
    except HuleEduError as e:
        logger.warning(
            f"Authentication error during logout: {e.error_detail.message}",
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
            f"Unexpected error during logout: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id_str},
        )
        return jsonify({"error": "Internal server error"}), 500


@bp.post("/refresh")
@inject
async def refresh_token(
    auth_handler: FromDishka[AuthenticationHandler],
) -> Response | tuple[Response, int]:
    """Exchange refresh token for new access token."""
    try:
        correlation_id = extract_correlation_id()
        
        payload = RefreshTokenRequest(**(await request.get_json()))
        
        # Delegate to authentication handler
        refresh_result = await auth_handler.refresh_token(
            refresh_request=payload,
            correlation_id=correlation_id,
        )
        
        return jsonify(refresh_result.to_dict())
        
    except HuleEduError as e:
        logger.warning(
            f"Authentication error during token refresh: {e.error_detail.message}",
            extra={
                "correlation_id": str(e.error_detail.correlation_id),
                "error_code": e.error_detail.error_code,
                "operation": e.error_detail.operation,
            },
        )
        return jsonify({"error": e.error_detail.model_dump()}), 401
        
    except Exception as e:
        correlation_id_str = str(correlation_id) if "correlation_id" in locals() else "unknown"
        logger.error(
            f"Unexpected error during token refresh: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id_str},
        )
        return jsonify({"error": "Internal server error"}), 500