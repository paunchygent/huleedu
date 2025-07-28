"""Metrics middleware for FastAPI applications."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram, CollectorRegistry, REGISTRY

if TYPE_CHECKING:
    from fastapi import FastAPI


class StandardMetricsMiddleware(BaseHTTPMiddleware):
    """Standard HTTP metrics middleware for FastAPI applications.
    
    Collects standard HTTP metrics following HuleEdu service library patterns:
    - Request count by method, endpoint, and status code
    - Request duration histogram by method and endpoint
    """

    def __init__(self, app: Any, service_name: str, registry: Optional[CollectorRegistry] = None):
        """Initialize metrics middleware.

        Args:
            app: FastAPI application instance
            service_name: Name of the service for metric labeling
            registry: Optional Prometheus registry for metric isolation
        """
        super().__init__(app)
        self.service_name = service_name
        
        # Use provided registry or default global registry
        if registry is None:
            registry = REGISTRY
        
        # Standard HTTP metrics following service library patterns
        self.http_requests_total = Counter(
            f"{service_name}_http_requests_total",
            "Total number of HTTP requests",
            ["method", "endpoint", "status_code"],
            registry=registry
        )
        
        self.http_request_duration_seconds = Histogram(
            f"{service_name}_http_request_duration_seconds", 
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            registry=registry
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process the request with metrics collection.

        Args:
            request: The incoming request
            call_next: The next middleware or route handler

        Returns:
            The response with metrics recorded
        """
        start_time = time.time()
        
        # Get endpoint path (normalized without query params)
        endpoint = request.url.path
        method = request.method
        
        try:
            # Process the request
            response = await call_next(request)
            status_code = str(response.status_code)
            
            # Record metrics
            duration = time.time() - start_time
            
            self.http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code
            ).inc()
            
            self.http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)
            
            return response
            
        except Exception:
            # Record error metrics
            duration = time.time() - start_time
            
            self.http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status_code="500"
            ).inc()
            
            self.http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)
            
            raise


def setup_standard_service_metrics_middleware(
    app: FastAPI, service_name: str, registry: Optional[CollectorRegistry] = None
) -> None:
    """Set up standard HTTP metrics middleware for a FastAPI app.

    Args:
        app: The FastAPI application
        service_name: Name of the service for metric prefixes
        registry: Optional Prometheus registry for metric isolation
    """
    app.add_middleware(StandardMetricsMiddleware, service_name=service_name, registry=registry)