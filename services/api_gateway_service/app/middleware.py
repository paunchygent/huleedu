"""Middleware for API Gateway Service."""

from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from prometheus_client import REGISTRY, Counter
from starlette.middleware.base import BaseHTTPMiddleware

from huleedu_service_libs.logging_utils import create_service_logger
from services.api_gateway_service.app.jwt_utils import try_decode_and_validate_jwt
from services.api_gateway_service.config import settings

logger = create_service_logger("api_gateway.middleware")


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Middleware to ensure every request has a correlation ID as UUID."""

    async def dispatch(self, request: Request, call_next):
        """Extract or generate correlation ID and store as UUID in request state."""
        # Extract or generate correlation ID as UUID
        x_correlation_id = request.headers.get("X-Correlation-ID")
        if x_correlation_id:
            try:
                correlation_id = UUID(x_correlation_id)
            except ValueError:
                logger.warning(
                    f"Invalid correlation ID format: {x_correlation_id}, generating new one"
                )
                correlation_id = uuid4()
        else:
            correlation_id = uuid4()

        # Store in request state as UUID
        request.state.correlation_id = correlation_id

        # Process request
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = str(correlation_id)

        return response


class DevelopmentMiddleware(BaseHTTPMiddleware):
    """Middleware for development-specific features and debugging."""

    def __init__(self, app: Any, settings: Any | None = None) -> None:
        """Initialize development middleware with settings."""
        super().__init__(app)
        self.settings = settings

    def is_development_environment(self) -> bool:
        """Check if running in development environment."""
        if not self.settings:
            return False
        # Ensure we return a proper boolean, not Any
        return bool(self.settings.is_development())

    async def dispatch(self, request: Request, call_next):
        """Add development-specific features and headers."""
        if not self.is_development_environment():
            return await call_next(request)

        # Add development debug info to request state
        request.state.development_mode = True
        request.state.cors_origins = getattr(self.settings, "CORS_ORIGINS", [])

        # Process request
        response = await call_next(request)

        # Add development-specific headers
        response.headers["X-HuleEdu-Environment"] = "development"
        response.headers["X-HuleEdu-Dev-Mode"] = "enabled"
        response.headers["X-HuleEdu-CORS-Origins"] = ",".join(
            getattr(self.settings, "CORS_ORIGINS", [])
        )

        # Add service info for debugging
        response.headers["X-HuleEdu-Service"] = getattr(
            self.settings, "SERVICE_NAME", "api-gateway-service"
        )

        # Log development request for debugging
        logger.debug(
            f"Development request: {request.method} {request.url.path} "
            f"from {request.client.host if request.client else 'unknown'}"
        )

        return response


class AuthBridgeMiddleware(BaseHTTPMiddleware):
    """
    Bridge Dishka-auth data into request.state for middleware consumers.

    - Decodes JWT once and caches payload on request.state.jwt_payload
    - Sets request.state.user_id (and optional org_id) for rate limiter keying
    - Does not raise on auth errors; route-level DI handles strict auth
    """

    # Middleware-specific metrics (kept separate from GatewayMetrics to avoid DI coupling)
    _auth_bridge_success = Counter(
        "gateway_auth_bridge_success_total",
        "Number of successful AuthBridge resolutions",
        ["method"],
        registry=REGISTRY,
    )
    _auth_bridge_miss = Counter(
        "gateway_auth_bridge_miss_total",
        "Number of AuthBridge misses by reason",
        ["reason"],
        registry=REGISTRY,
    )

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # Only attempt when Authorization header present
        authorization = request.headers.get("Authorization")
        if authorization:
            parts = authorization.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
                correlation_id = getattr(request.state, "correlation_id", uuid4())
                payload = try_decode_and_validate_jwt(token, settings, correlation_id)
                if isinstance(payload, dict):
                    # Cache payload for DI to reuse and avoid re-decode
                    try:
                        request.state.jwt_payload = payload
                    except Exception:  # pragma: no cover - defensive
                        pass

                    # Bridge user_id for rate-limiter keying
                    sub = payload.get("sub")
                    if isinstance(sub, str) and sub:
                        request.state.user_id = sub
                        # Metrics: successful bridge via JWT
                        self._auth_bridge_success.labels(method="jwt").inc()
                    else:
                        # Metrics: JWT had no subject
                        self._auth_bridge_miss.labels(reason="no_sub").inc()

                    # Optionally bridge org_id when present
                    for claim_name in settings.JWT_ORG_ID_CLAIM_NAMES:
                        value = payload.get(claim_name)
                        if isinstance(value, str) and value.strip():
                            request.state.org_id = value.strip()
                            break
                else:
                    # Metrics: JWT invalid or could not decode
                    self._auth_bridge_miss.labels(reason="jwt_invalid").inc()
            else:
                # Metrics: malformed Authorization header
                self._auth_bridge_miss.labels(reason="bad_auth_format").inc()
        else:
            # Metrics: no Authorization header
            self._auth_bridge_miss.labels(reason="no_token").inc()

        return await call_next(request)
