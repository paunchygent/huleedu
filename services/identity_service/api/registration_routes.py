"""User registration routes for Identity Service.

Handles user registration operations.
All business logic is delegated to RegistrationHandler.
"""
from __future__ import annotations

from dishka import FromDishka
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from services.identity_service.api.request_utils import extract_correlation_id
from services.identity_service.api.schemas import RegisterRequest
from services.identity_service.domain_handlers.registration_handler import RegistrationHandler

bp = Blueprint("registration", __name__, url_prefix="/v1/auth")
logger = create_service_logger("identity_service.api.registration_routes")


@bp.post("/register")
@inject
async def register(
    registration_handler: FromDishka[RegistrationHandler],
) -> tuple[Response, int]:
    """User registration with email uniqueness validation."""
    try:
        correlation_id = extract_correlation_id()

        payload = RegisterRequest(**(await request.get_json()))

        # Delegate to registration handler
        registration_result = await registration_handler.register_user(
            register_request=payload,
            correlation_id=correlation_id,
        )

        return jsonify(registration_result.to_dict()), 201

    except HuleEduError as e:
        logger.warning(
            f"Registration error: {e.error_detail.message}",
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
            f"Unexpected error during registration: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id_str},
        )
        return jsonify({"error": "Internal server error"}), 500