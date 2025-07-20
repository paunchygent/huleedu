from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import jwt
from huleedu_service_libs.error_handling import raise_authentication_error
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("websocket.jwt_validator")


class JWTValidator:
    """
    Validates JWT tokens for WebSocket connections.
    Follows the same validation pattern as the API Gateway.
    """

    def __init__(self, secret_key: str, algorithm: str = "HS256") -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm

    async def validate_token(self, token: str) -> str:
        """
        Validate a JWT token and return the user ID if valid.
        Raises HuleEduError if the token is invalid.
        """
        correlation_id = uuid4()
        try:
            # Decode and validate JWT
            payload = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])

            # Validate token expiry
            exp_timestamp = payload.get("exp")
            if exp_timestamp is None:
                logger.warning("Token missing expiration claim")
                raise_authentication_error(
                    service="websocket_service",
                    operation="validate_token",
                    message="Token missing expiration claim",
                    correlation_id=correlation_id,
                    reason="missing_exp",
                )

            current_time = datetime.now(UTC).timestamp()
            if current_time >= exp_timestamp:
                logger.warning("Token has expired")
                raise_authentication_error(
                    service="websocket_service",
                    operation="validate_token",
                    message="Token has expired",
                    correlation_id=correlation_id,
                    reason="token_expired",
                )

            # Extract user ID
            user_id: str | None = payload.get("sub")
            if user_id is None or user_id == "":
                logger.warning("Invalid token payload: missing subject")
                raise_authentication_error(
                    service="websocket_service",
                    operation="validate_token",
                    message="Invalid token payload: missing subject",
                    correlation_id=correlation_id,
                    reason="missing_subject",
                )

            logger.debug(f"Successfully validated token for user {user_id}")
            return user_id

        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired (JWT library check)")
            raise_authentication_error(
                service="websocket_service",
                operation="validate_token",
                message="Token has expired",
                correlation_id=correlation_id,
                reason="jwt_expired",
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            raise_authentication_error(
                service="websocket_service",
                operation="validate_token",
                message=f"Invalid token: {str(e)}",
                correlation_id=correlation_id,
                reason="jwt_invalid",
            )
        except Exception as e:
            logger.error(f"Unexpected error in JWT validation: {e}", exc_info=True)
            raise_authentication_error(
                service="websocket_service",
                operation="validate_token",
                message=f"Unexpected error in JWT validation: {str(e)}",
                correlation_id=correlation_id,
                reason="unexpected_error",
            )
