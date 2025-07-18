from __future__ import annotations

from datetime import UTC, datetime

import jwt
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("websocket.jwt_validator")


class JWTValidator:
    """
    Validates JWT tokens for WebSocket connections.
    Follows the same validation pattern as the API Gateway.
    """

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self._secret_key = secret_key
        self._algorithm = algorithm

    async def validate_token(self, token: str) -> str | None:
        """
        Validate a JWT token and return the user ID if valid.
        Returns None if the token is invalid.
        """
        try:
            # Decode and validate JWT
            payload = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])

            # Validate token expiry
            exp_timestamp = payload.get("exp")
            if exp_timestamp is None:
                logger.warning("Token missing expiration claim")
                return None

            current_time = datetime.now(UTC).timestamp()
            if current_time >= exp_timestamp:
                logger.warning("Token has expired")
                return None

            # Extract user ID
            user_id: str | None = payload.get("sub")
            if user_id is None or user_id == "":
                logger.warning("Invalid token payload: missing subject")
                return None

            logger.debug(f"Successfully validated token for user {user_id}")
            return user_id

        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired (JWT library check)")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in JWT validation: {e}", exc_info=True)
            return None
