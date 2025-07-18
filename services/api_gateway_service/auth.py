from __future__ import annotations

from datetime import UTC, datetime

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from huleedu_service_libs.logging_utils import create_service_logger
from services.api_gateway_service.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/token")
logger = create_service_logger("api_gateway.auth")


async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
    """
    Validate JWT token with expiry check and comprehensive error handling.

    CRITICAL: Implements architect feedback #2 for JWT expiry validation.
    """
    try:
        # Decode and validate JWT
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

        # CRITICAL: Validate token expiry (Architect Feedback #2)
        exp_timestamp = payload.get("exp")
        if exp_timestamp is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing expiration claim"
            )

        current_time = datetime.now(UTC).timestamp()
        if current_time >= exp_timestamp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
            )

        # Extract user ID
        user_id: str | None = payload.get("sub")
        if user_id is None or user_id == "":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload: missing subject",
            )

        return user_id

    except HTTPException:
        # Re-raise specific HTTPExceptions with their original error messages
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        ) from None
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
        ) from e
    except Exception as e:
        # Log unexpected errors but don't expose internal details
        logger.error(f"Unexpected error in JWT validation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed"
        ) from None
