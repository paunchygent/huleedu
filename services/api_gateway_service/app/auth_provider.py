from __future__ import annotations

from typing import NewType
from uuid import UUID, uuid4

import jwt
from dishka import Provider, Scope, from_context, provide
from fastapi import Request

from huleedu_service_libs.error_handling import raise_authentication_error
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger
from services.api_gateway_service.app.jwt_utils import decode_and_validate_jwt
from services.api_gateway_service.config import Settings

# Custom type to avoid circular dependency with str
BearerToken = NewType("BearerToken", str)

logger = create_service_logger("api_gateway.auth_provider")


class AuthProvider(Provider):
    """Provider for authentication dependencies at REQUEST scope."""

    # Get FastAPI Request from context (provided by FastAPI integration)
    request = from_context(provides=Request, scope=Scope.REQUEST)

    @provide(scope=Scope.REQUEST)
    def provide_correlation_id(self, request: Request) -> UUID:
        """Provide correlation ID from request state as UUID."""
        return getattr(request.state, "correlation_id", uuid4())

    @provide(scope=Scope.REQUEST)
    def extract_bearer_token(self, request: Request) -> BearerToken:
        """Extract and validate Bearer token from request headers."""
        authorization = request.headers.get("Authorization")
        # Get correlation ID from request state (set by middleware)
        correlation_id: UUID = getattr(request.state, "correlation_id", uuid4())

        if not authorization:
            raise_authentication_error(
                service="api_gateway_service",
                operation="extract_bearer_token",
                message="Not authenticated",
                correlation_id=correlation_id,
                reason="missing_authorization_header",
            )

        # Check if it's a Bearer token
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise_authentication_error(
                service="api_gateway_service",
                operation="extract_bearer_token",
                message="Invalid authentication format",
                correlation_id=correlation_id,
                reason="invalid_authorization_format",
            )

        return BearerToken(parts[1])

    @provide(scope=Scope.REQUEST, provides=str)
    def provide_user_id(self, token: BearerToken, settings: Settings, request: Request) -> str:
        """
        Main authentication provider that validates JWT token and returns user ID.

        This is the primary provider that routes should use via FromDishka[str].
        It validates the token and extracts the user ID.

        CRITICAL: Implements architect feedback #2 for JWT expiry validation.
        """
        # Get correlation ID from request state (set by middleware)
        correlation_id: UUID = getattr(request.state, "correlation_id", uuid4())

        try:
            # Reuse payload from bridge when available to avoid re-decoding
            payload = getattr(request.state, "jwt_payload", None)
            if not isinstance(payload, dict):
                payload = decode_and_validate_jwt(token, settings, correlation_id)

            # Extract user ID
            user_id = payload.get("sub")
            if not isinstance(user_id, str) or user_id == "":
                raise_authentication_error(
                    service="api_gateway_service",
                    operation="validate_jwt",
                    message="Invalid token payload: missing subject",
                    correlation_id=correlation_id,
                    reason="missing_subject",
                )

            # At this point, user_id is guaranteed to be a non-empty string
            logger.debug(f"Successfully validated token for user {user_id}")
            return user_id

        except jwt.ExpiredSignatureError:
            raise_authentication_error(
                service="api_gateway_service",
                operation="validate_jwt",
                message="Token has expired",
                correlation_id=correlation_id,
                reason="jwt_expired",
            )
        except jwt.InvalidTokenError as e:
            raise_authentication_error(
                service="api_gateway_service",
                operation="validate_jwt",
                message=f"Could not validate credentials: {str(e)}",
                correlation_id=correlation_id,
                reason="jwt_invalid",
            )
        except HuleEduError:
            # Re-raise HuleEduError without wrapping it
            raise
        except Exception as e:
            # Log unexpected errors but don't expose internal details
            logger.error(f"Unexpected error in JWT validation: {e}", exc_info=True)
            raise_authentication_error(
                service="api_gateway_service",
                operation="validate_jwt",
                message="Authentication failed",
                correlation_id=correlation_id,
                reason="unexpected_error",
            )

    @provide(scope=Scope.REQUEST)
    def provide_org_id(
        self, token: BearerToken, settings: Settings, request: Request
    ) -> str | None:
        """
        Extract organization ID from JWT claims using configured claim names.

        Returns None when the token represents an individual user without org context.
        Performs the same JWT validation (signature, algorithm, exp) as provide_user_id.
        """
        correlation_id: UUID = getattr(request.state, "correlation_id", uuid4())

        try:
            # Reuse payload from bridge when available to avoid re-decoding
            payload = getattr(request.state, "jwt_payload", None)
            if not isinstance(payload, dict):
                payload = decode_and_validate_jwt(token, settings, correlation_id)

            # Try configured org_id claim names in order
            for claim_name in settings.JWT_ORG_ID_CLAIM_NAMES:
                value = payload.get(claim_name)
                if isinstance(value, str):
                    cleaned = value.strip()
                    if cleaned:
                        logger.debug(f"Resolved org_id from claim '{claim_name}' for token subject")
                        return cleaned
                elif value is not None:
                    # Non-string claim present; skip but log for diagnostics
                    logger.debug(
                        f"Ignoring non-string org_id claim '{claim_name}' of type {type(value).__name__}"
                    )

            # No org_id found; treat as individual user context
            logger.debug("No org_id claim present; proceeding without organizational context")
            return None

        except jwt.ExpiredSignatureError:
            raise_authentication_error(
                service="api_gateway_service",
                operation="validate_jwt",
                message="Token has expired",
                correlation_id=correlation_id,
                reason="jwt_expired",
            )
        except jwt.InvalidTokenError as e:
            raise_authentication_error(
                service="api_gateway_service",
                operation="validate_jwt",
                message=f"Could not validate credentials: {str(e)}",
                correlation_id=correlation_id,
                reason="jwt_invalid",
            )
        except HuleEduError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in JWT validation: {e}", exc_info=True)
            raise_authentication_error(
                service="api_gateway_service",
                operation="validate_jwt",
                message="Authentication failed",
                correlation_id=correlation_id,
                reason="unexpected_error",
            )
