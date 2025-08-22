"""
Identity service specific enums.

Follows the established pattern of using str, Enum inheritance for all enums
as seen throughout the HuleEdu codebase (status_enums.py, error_enums.py, etc.).
"""

from enum import Enum


class LoginFailureReason(str, Enum):
    """
    Standardized reasons for login failure.

    These values are used in LoginFailedV1 events and throughout the
    authentication flow for consistent failure categorization.
    """

    USER_NOT_FOUND = "user_not_found"
    INVALID_PASSWORD = "invalid_password"
    ACCOUNT_LOCKED = "account_locked"
    EMAIL_UNVERIFIED = "email_unverified"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
