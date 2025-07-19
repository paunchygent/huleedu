"""Middleware for API Gateway Service."""

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
