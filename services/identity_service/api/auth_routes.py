from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from dishka import FromDishka
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.error_handling.identity_factories import (
    raise_email_already_verified_error,
    raise_invalid_credentials_error,
    raise_user_already_exists_error,
    raise_verification_token_expired_error,
    raise_verification_token_invalid_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from services.identity_service.api.schemas import (
    LoginRequest,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
    RequestEmailVerificationRequest,
    RequestEmailVerificationResponse,
    RequestPasswordResetRequest,
    RequestPasswordResetResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TokenPair,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from services.identity_service.protocols import (
    IdentityEventPublisherProtocol,
    PasswordHasher,
    SessionRepo,
    TokenIssuer,
    UserRepo,
)

bp = Blueprint("auth", __name__, url_prefix="/v1/auth")

logger = create_service_logger("identity_service.auth_routes")


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


@bp.post("/register")
@inject
async def register(
    user_repo: FromDishka[UserRepo],
    hasher: FromDishka[PasswordHasher],
    event_publisher: FromDishka[IdentityEventPublisherProtocol],
) -> tuple[Response, int]:
    try:
        correlation_id = _extract_correlation_id()

        payload = RegisterRequest(**(await request.get_json()))

        # Check if user already exists
        existing_user = await user_repo.get_user_by_email(payload.email)
        if existing_user:
            raise_user_already_exists_error(
                service="identity_service",
                operation="register",
                message=f"User with email {payload.email} already exists",
                correlation_id=correlation_id,
                email=payload.email,
            )

        # Create user (this should be transactional with event publishing)
        user = await user_repo.create_user(
            payload.email, payload.org_id, hasher.hash(payload.password)
        )

        # Publish user registered event
        await event_publisher.publish_user_registered(user, str(correlation_id))

        logger.info(
            "User registered successfully",
            extra={
                "user_id": user["id"],
                "email": payload.email,
                "org_id": payload.org_id,
                "correlation_id": str(correlation_id),
            },
        )

        return jsonify(RegisterResponse(**user).model_dump(mode="json")), 201

    except HuleEduError as e:
        logger.warning(
            f"Identity service error during registration: {e.error_detail.message}",
            extra={
                "correlation_id": str(e.error_detail.correlation_id),
                "error_code": e.error_detail.error_code,
                "operation": e.error_detail.operation,
            },
        )
        return jsonify({"error": e.error_detail.model_dump()}), 400

    except Exception as e:
        # Unexpected errors
        logger.error(
            f"Unexpected error during registration: {e}",
            exc_info=True,
            extra={
                "correlation_id": str(correlation_id) if "correlation_id" in locals() else "unknown"
            },
        )
        return jsonify({"error": "Internal server error"}), 500


@bp.post("/login")
@inject
async def login(
    user_repo: FromDishka[UserRepo],
    tokens: FromDishka[TokenIssuer],
    hasher: FromDishka[PasswordHasher],
    sessions: FromDishka[SessionRepo],
    event_publisher: FromDishka[IdentityEventPublisherProtocol],
) -> Response | tuple[Response, int]:
    try:
        correlation_id = _extract_correlation_id()

        payload = LoginRequest(**(await request.get_json()))

        # Get user by email
        user = await user_repo.get_user_by_email(payload.email)
        if not user:
            # Publish login failed event
            await event_publisher.publish_login_failed(
                payload.email, "user_not_found", str(correlation_id)
            )

            logger.warning(
                "Login attempt for non-existent user",
                extra={
                    "email": payload.email,
                    "correlation_id": str(correlation_id),
                },
            )

            raise_invalid_credentials_error(
                service="identity_service",
                operation="login",
                message="Invalid email or password",
                correlation_id=correlation_id,
                email=payload.email,
            )

        # Verify password
        if not hasher.verify(user.get("password_hash", ""), payload.password):
            # Publish login failed event
            await event_publisher.publish_login_failed(
                payload.email, "invalid_password", str(correlation_id)
            )

            logger.warning(
                "Login attempt with invalid password",
                extra={
                    "user_id": user["id"],
                    "email": payload.email,
                    "correlation_id": str(correlation_id),
                },
            )

            raise_invalid_credentials_error(
                service="identity_service",
                operation="login",
                message="Invalid email or password",
                correlation_id=correlation_id,
                email=payload.email,
            )

        # Generate tokens
        access = tokens.issue_access_token(
            user_id=user["id"], org_id=user.get("org_id"), roles=user.get("roles", [])
        )
        refresh, jti = tokens.issue_refresh_token(user_id=user["id"])

        # Store refresh session
        await sessions.store_refresh(user_id=user["id"], jti=jti, exp_ts=int(time.time()) + 86400)

        # Publish login succeeded event
        await event_publisher.publish_login_succeeded(user, str(correlation_id))

        logger.info(
            "User logged in successfully",
            extra={
                "user_id": user["id"],
                "email": payload.email,
                "org_id": user.get("org_id"),
                "correlation_id": str(correlation_id),
            },
        )

        pair = TokenPair(access_token=access, refresh_token=refresh, expires_in=3600)
        return jsonify(pair.model_dump(mode="json"))

    except HuleEduError as e:
        logger.warning(
            f"Identity service error during login: {e.error_detail.message}",
            extra={
                "correlation_id": str(e.error_detail.correlation_id),
                "error_code": e.error_detail.error_code,
                "operation": e.error_detail.operation,
            },
        )
        return jsonify({"error": e.error_detail.model_dump()}), 400

    except Exception as e:
        # Unexpected errors
        logger.error(
            f"Unexpected error during login: {e}",
            exc_info=True,
            extra={
                "correlation_id": str(correlation_id) if "correlation_id" in locals() else "unknown"
            },
        )
        return jsonify({"error": "Internal server error"}), 500


@bp.get("/me")
async def me() -> Response:
    # In production, validate JWT via API Gateway
    return jsonify(MeResponse(user_id="dev", email="dev@example.com").model_dump(mode="json"))


@bp.post("/request-email-verification")
@inject
async def request_email_verification(
    user_repo: FromDishka[UserRepo],
    event_publisher: FromDishka[IdentityEventPublisherProtocol],
) -> tuple[Response, int]:
    try:
        correlation_id = _extract_correlation_id()

        payload = RequestEmailVerificationRequest(**(await request.get_json() or {}))

        # For development: extract user from dev context
        # In production, this would come from JWT validation at API Gateway
        # For now, we'll use a development user
        dev_user_email = "dev@example.com"
        user = await user_repo.get_user_by_email(dev_user_email)

        if not user:
            # For development, create a dev user if it doesn't exist
            # In production, this would be handled by proper JWT validation
            logger.info("Development: creating dev user for email verification testing")
            user = await user_repo.create_user(dev_user_email, None, "dev_password_hash")

        # Check if email is already verified
        if user["email_verified"]:
            raise_email_already_verified_error(
                service="identity_service",
                operation="request_email_verification",
                email=user["email"],
                correlation_id=correlation_id,
            )

        # Invalidate existing tokens for this user
        await user_repo.invalidate_user_tokens(user["id"])

        # Generate new verification token
        token = str(uuid.uuid4())
        expires_at = datetime.now(UTC) + timedelta(hours=24)

        # Create verification token
        token_record = await user_repo.create_email_verification_token(
            user["id"], token, expires_at
        )

        # Publish email verification requested event
        await event_publisher.publish_email_verification_requested(
            user, token_record["id"], expires_at, str(correlation_id)
        )

        logger.info(
            "Email verification requested successfully",
            extra={
                "user_id": user["id"],
                "email": user["email"],
                "token_id": token_record["id"],
                "correlation_id": str(correlation_id),
            },
        )

        response = RequestEmailVerificationResponse(
            message="Email verification token generated successfully",
            correlation_id=str(correlation_id),
        )
        return jsonify(response.model_dump(mode="json")), 200

    except HuleEduError as e:
        logger.warning(
            f"Identity service error during email verification request: {e.error_detail.message}",
            extra={
                "correlation_id": str(e.error_detail.correlation_id),
                "error_code": e.error_detail.error_code,
                "operation": e.error_detail.operation,
            },
        )
        return jsonify({"error": e.error_detail.model_dump()}), 400

    except Exception as e:
        # Unexpected errors
        logger.error(
            f"Unexpected error during email verification request: {e}",
            exc_info=True,
            extra={
                "correlation_id": str(correlation_id) if "correlation_id" in locals() else "unknown"
            },
        )
        return jsonify({"error": "Internal server error"}), 500


@bp.post("/verify-email")
@inject
async def verify_email(
    user_repo: FromDishka[UserRepo],
    event_publisher: FromDishka[IdentityEventPublisherProtocol],
) -> tuple[Response, int]:
    try:
        correlation_id = _extract_correlation_id()

        payload = VerifyEmailRequest(**(await request.get_json()))

        # Get verification token
        token_record = await user_repo.get_email_verification_token(payload.token)

        if not token_record:
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="verify_email",
                correlation_id=correlation_id,
            )

        # Check if token is already used
        if token_record["used_at"] is not None:
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="verify_email",
                correlation_id=correlation_id,
            )

        # Check if token is expired
        if datetime.now(UTC) > token_record["expires_at"]:
            raise_verification_token_expired_error(
                service="identity_service",
                operation="verify_email",
                correlation_id=correlation_id,
            )

        # Get user for verification
        user = await user_repo.get_user_by_email("dev@example.com")  # Development user

        if not user:
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="verify_email",
                correlation_id=correlation_id,
            )

        # Check if email is already verified
        if user["email_verified"]:
            raise_email_already_verified_error(
                service="identity_service",
                operation="verify_email",
                email=user["email"],
                correlation_id=correlation_id,
            )

        # Mark token as used and set email as verified (transactional)
        await user_repo.mark_token_used(token_record["id"])
        await user_repo.set_email_verified(user["id"])

        # Publish email verified event
        await event_publisher.publish_email_verified(user, str(correlation_id))

        logger.info(
            "Email verified successfully",
            extra={
                "user_id": user["id"],
                "email": user["email"],
                "token_id": token_record["id"],
                "correlation_id": str(correlation_id),
            },
        )

        response = VerifyEmailResponse(message="Email verified successfully")
        return jsonify(response.model_dump(mode="json")), 200

    except HuleEduError as e:
        logger.warning(
            f"Identity service error during email verification: {e.error_detail.message}",
            extra={
                "correlation_id": str(e.error_detail.correlation_id),
                "error_code": e.error_detail.error_code,
                "operation": e.error_detail.operation,
            },
        )
        return jsonify({"error": e.error_detail.model_dump()}), 400

    except Exception as e:
        # Unexpected errors
        logger.error(
            f"Unexpected error during email verification: {e}",
            exc_info=True,
            extra={
                "correlation_id": str(correlation_id) if "correlation_id" in locals() else "unknown"
            },
        )
        return jsonify({"error": "Internal server error"}), 500


@bp.post("/request-password-reset")
@inject
async def request_password_reset(
    user_repo: FromDishka[UserRepo],
    event_publisher: FromDishka[IdentityEventPublisherProtocol],
) -> tuple[Response, int]:
    try:
        correlation_id = _extract_correlation_id()

        payload = RequestPasswordResetRequest(**(await request.get_json()))

        # Security: Look up user by email but don't reveal if it exists
        user = await user_repo.get_user_by_email(payload.email)

        # Always return success (security best practice)
        response = RequestPasswordResetResponse(
            message="If the email address exists, a password reset link will be sent",
            correlation_id=str(correlation_id),
        )

        # Only proceed if user exists
        if user:
            # Invalidate existing password reset tokens for this user
            await user_repo.invalidate_password_reset_tokens(user["id"])

            # Generate new password reset token
            token = str(uuid.uuid4())
            expires_at = datetime.now(UTC) + timedelta(hours=1)  # 1 hour expiry for security

            # Create password reset token
            token_record = await user_repo.create_password_reset_token(
                user["id"], token, expires_at
            )

            # Publish password reset requested event
            await event_publisher.publish_password_reset_requested(
                user, token_record["id"], expires_at, str(correlation_id)
            )

            logger.info(
                "Password reset requested successfully",
                extra={
                    "user_id": user["id"],
                    "email": user["email"],
                    "token_id": token_record["id"],
                    "correlation_id": str(correlation_id),
                },
            )
        else:
            logger.info(
                "Password reset requested for non-existent email (security: no revelation)",
                extra={
                    "email": payload.email,
                    "correlation_id": str(correlation_id),
                },
            )

        return jsonify(response.model_dump(mode="json")), 200

    except HuleEduError as e:
        logger.warning(
            f"Identity service error during password reset request: {e.error_detail.message}",
            extra={
                "correlation_id": str(e.error_detail.correlation_id),
                "error_code": e.error_detail.error_code,
                "operation": e.error_detail.operation,
            },
        )
        return jsonify({"error": e.error_detail.model_dump()}), 400

    except Exception as e:
        # Unexpected errors
        logger.error(
            f"Unexpected error during password reset request: {e}",
            exc_info=True,
            extra={
                "correlation_id": str(correlation_id) if "correlation_id" in locals() else "unknown"
            },
        )
        return jsonify({"error": "Internal server error"}), 500


@bp.post("/reset-password")
@inject
async def reset_password(
    user_repo: FromDishka[UserRepo],
    hasher: FromDishka[PasswordHasher],
    event_publisher: FromDishka[IdentityEventPublisherProtocol],
) -> tuple[Response, int]:
    try:
        correlation_id = _extract_correlation_id()

        payload = ResetPasswordRequest(**(await request.get_json()))

        # Get password reset token
        token_record = await user_repo.get_password_reset_token(payload.token)

        if not token_record:
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="reset_password",
                correlation_id=correlation_id,
            )

        # Check if token is already used
        if token_record["used_at"] is not None:
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="reset_password",
                correlation_id=correlation_id,
            )

        # Check if token is expired
        if datetime.now(UTC) > token_record["expires_at"]:
            raise_verification_token_expired_error(
                service="identity_service",
                operation="reset_password",
                correlation_id=correlation_id,
            )

        # Get user for password update
        user = await user_repo.get_user_by_email("dev@example.com")  # Development user

        if not user:
            raise_verification_token_invalid_error(
                service="identity_service",
                operation="reset_password",
                correlation_id=correlation_id,
            )

        # Hash the new password
        new_password_hash = hasher.hash(payload.new_password)

        # Update password and mark token as used (transactional)
        await user_repo.update_user_password(user["id"], new_password_hash)
        await user_repo.mark_reset_token_used(token_record["id"])

        # Publish password reset completed event
        await event_publisher.publish_password_reset_completed(user, str(correlation_id))

        logger.info(
            "Password reset completed successfully",
            extra={
                "user_id": user["id"],
                "email": user["email"],
                "token_id": token_record["id"],
                "correlation_id": str(correlation_id),
            },
        )

        response = ResetPasswordResponse(message="Password reset successfully")
        return jsonify(response.model_dump(mode="json")), 200

    except HuleEduError as e:
        logger.warning(
            f"Identity service error during password reset: {e.error_detail.message}",
            extra={
                "correlation_id": str(e.error_detail.correlation_id),
                "error_code": e.error_detail.error_code,
                "operation": e.error_detail.operation,
            },
        )
        return jsonify({"error": e.error_detail.model_dump()}), 400

    except Exception as e:
        # Unexpected errors
        logger.error(
            f"Unexpected error during password reset: {e}",
            exc_info=True,
            extra={
                "correlation_id": str(correlation_id) if "correlation_id" in locals() else "unknown"
            },
        )
        return jsonify({"error": "Internal server error"}), 500
