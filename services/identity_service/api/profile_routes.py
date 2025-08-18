from __future__ import annotations

import uuid
from uuid import UUID

from dishka import FromDishka
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from services.identity_service.api.schemas import ProfileRequest, ProfileResponse
from services.identity_service.domain_handlers.profile_handler import (
    ProfileRequest as DomainProfileRequest,
)
from services.identity_service.domain_handlers.profile_handler import (
    UserProfileHandler,
)

bp = Blueprint("profile", __name__, url_prefix="/v1/users")

logger = create_service_logger("identity_service.profile_routes")


def _extract_correlation_id() -> UUID:
    """Extract correlation ID from request headers or generate new one."""
    correlation_header = request.headers.get("X-Correlation-ID")
    if correlation_header:
        try:
            return UUID(correlation_header)
        except ValueError:
            logger.warning(
                f"Invalid correlation ID format in header: {correlation_header}, generating new one"
            )
            return uuid.uuid4()
    return uuid.uuid4()


@bp.route("/<user_id>/profile", methods=["GET"])
@inject
async def get_profile(
    user_id: str,
    handler: FromDishka[UserProfileHandler],
) -> tuple[Response, int]:
    """Get user profile with PersonNameV1 structure.

    Args:
        user_id: The user's ID
        handler: Injected profile handler

    Returns:
        Profile response with PersonNameV1, display_name, and locale
    """
    try:
        correlation_id = _extract_correlation_id()

        profile_response = await handler.get_profile(user_id, correlation_id)

        # Convert domain response to API schema
        response_data = ProfileResponse(
            person_name=profile_response.person_name.model_dump(),
            display_name=profile_response.display_name,
            locale=profile_response.locale,
        )

        logger.info(
            "Profile retrieved successfully",
            extra={
                "user_id": user_id,
                "correlation_id": str(correlation_id),
            },
        )

        return jsonify(response_data.model_dump()), 200

    except HuleEduError as e:
        logger.error(
            "Failed to retrieve profile",
            extra={
                "user_id": user_id,
                "error": str(e),
                "correlation_id": str(correlation_id),
            },
        )
        return jsonify({"error": e.error_detail.model_dump()}), 400


@bp.route("/<user_id>/profile", methods=["PUT"])
@inject
async def update_profile(
    user_id: str,
    handler: FromDishka[UserProfileHandler],
) -> tuple[Response, int]:
    """Update user profile with PersonNameV1 data.

    Args:
        user_id: The user's ID
        handler: Injected profile handler

    Returns:
        Updated profile response with PersonNameV1, display_name, and locale
    """
    try:
        correlation_id = _extract_correlation_id()

        # Parse request body
        payload = ProfileRequest(**(await request.get_json()))

        # Convert API schema to domain request
        domain_request = DomainProfileRequest(
            first_name=payload.first_name,
            last_name=payload.last_name,
            display_name=payload.display_name,
            locale=payload.locale,
        )

        profile_response = await handler.update_profile(user_id, domain_request, correlation_id)

        # Convert domain response to API schema
        response_data = ProfileResponse(
            person_name=profile_response.person_name.model_dump(),
            display_name=profile_response.display_name,
            locale=profile_response.locale,
        )

        logger.info(
            "Profile updated successfully",
            extra={
                "user_id": user_id,
                "correlation_id": str(correlation_id),
            },
        )

        return jsonify(response_data.model_dump()), 200

    except HuleEduError as e:
        logger.error(
            "Failed to update profile",
            extra={
                "user_id": user_id,
                "error": str(e),
                "correlation_id": str(correlation_id),
            },
        )
        return jsonify({"error": e.error_detail.model_dump()}), 400
    except ValueError as e:
        # Handle domain validation errors
        logger.error(
            "Invalid profile data",
            extra={
                "user_id": user_id,
                "error": str(e),
                "correlation_id": str(correlation_id),
            },
        )
        # Return 400 for validation errors
        return jsonify({"error": str(e)}), 400
