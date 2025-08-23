"""Middleware for API Gateway Service."""

from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from huleedu_service_libs.logging_utils import create_service_logger

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

    def __init__(self, app: Any, settings: Optional[Any] = None) -> None:
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
