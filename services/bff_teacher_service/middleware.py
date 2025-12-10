"""BFF Teacher Service middleware components."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Middleware to ensure every request has a correlation ID."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Extract or generate correlation ID and store in request state."""
        x_correlation_id = request.headers.get("X-Correlation-ID")
        if x_correlation_id:
            try:
                correlation_id = UUID(x_correlation_id)
            except ValueError:
                correlation_id = uuid4()
        else:
            correlation_id = uuid4()

        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = str(correlation_id)
        return response
