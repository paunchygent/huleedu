"""
Factory functions for creating and raising IdentityErrorCode exceptions.

This module provides standardized factory functions for identity service
specific error codes.
"""

from typing import Any, NoReturn
from uuid import UUID

from common_core.error_enums import IdentityErrorCode

from .error_detail_factory import create_error_detail_with_context
from .huleedu_error import HuleEduError


def raise_invalid_credentials_error(
    service: str,
    operation: str,
    email: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an invalid credentials error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.INVALID_CREDENTIALS,
        message="Invalid email or password",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"email": email, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_user_not_found_error(
    service: str,
    operation: str,
    identifier: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a user not found error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.USER_NOT_FOUND,
        message=f"User not found: {identifier}",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"identifier": identifier, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_user_already_exists_error(
    service: str,
    operation: str,
    email: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a user already exists error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.USER_ALREADY_EXISTS,
        message=f"User already exists with email: {email}",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"email": email, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_email_not_verified_error(
    service: str,
    operation: str,
    email: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an email not verified error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.EMAIL_NOT_VERIFIED,
        message=f"Email not verified: {email}",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"email": email, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_account_locked_error(
    service: str,
    operation: str,
    email: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an account locked error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.ACCOUNT_LOCKED,
        message=f"Account is locked: {email}",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"email": email, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_token_expired_error(
    service: str,
    operation: str,
    token_type: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a token expired error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.TOKEN_EXPIRED,
        message=f"{token_type} token has expired",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"token_type": token_type, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_token_invalid_error(
    service: str,
    operation: str,
    token_type: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a token invalid error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.TOKEN_INVALID,
        message=f"{token_type} token is invalid",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"token_type": token_type, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_refresh_token_invalid_error(
    service: str,
    operation: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a refresh token invalid error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.REFRESH_TOKEN_INVALID,
        message="Refresh token is invalid or revoked",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_refresh_token_expired_error(
    service: str,
    operation: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a refresh token expired error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.REFRESH_TOKEN_EXPIRED,
        message="Refresh token has expired",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_verification_token_expired_error(
    service: str,
    operation: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a verification token expired error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.VERIFICATION_TOKEN_EXPIRED,
        message="Email verification token has expired",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_verification_token_invalid_error(
    service: str,
    operation: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a verification token invalid error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.VERIFICATION_TOKEN_INVALID,
        message="Email verification token is invalid",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_email_already_verified_error(
    service: str,
    operation: str,
    email: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise an email already verified error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.EMAIL_ALREADY_VERIFIED,
        message=f"Email is already verified: {email}",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"email": email, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_reset_token_expired_error(
    service: str,
    operation: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a password reset token expired error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.RESET_TOKEN_EXPIRED,
        message="Password reset token has expired",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_reset_token_invalid_error(
    service: str,
    operation: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a password reset token invalid error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.RESET_TOKEN_INVALID,
        message="Password reset token is invalid",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_password_reset_not_requested_error(
    service: str,
    operation: str,
    email: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a password reset not requested error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.PASSWORD_RESET_NOT_REQUESTED,
        message=f"Password reset was not requested for: {email}",
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details={"email": email, **additional_context},
    )
    raise HuleEduError(error_detail)


def raise_invalid_token_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a generic invalid token error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.TOKEN_INVALID,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)


def raise_missing_token_error(
    service: str,
    operation: str,
    message: str,
    correlation_id: UUID,
    **additional_context: Any,
) -> NoReturn:
    """Create and raise a missing token error."""
    error_detail = create_error_detail_with_context(
        error_code=IdentityErrorCode.TOKEN_INVALID,
        message=message,
        service=service,
        operation=operation,
        correlation_id=correlation_id,
        details=additional_context,
    )
    raise HuleEduError(error_detail)
