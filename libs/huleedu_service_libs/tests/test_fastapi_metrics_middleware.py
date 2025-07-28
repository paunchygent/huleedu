"""
Unit tests for FastAPI Metrics Middleware.

Tests request counting, duration tracking, error scenarios, and registry isolation.
Follows HuleEdu testing patterns with real handler functions and boundary mocking.
"""

from __future__ import annotations

import asyncio
import pytest
from typing import Any
from unittest.mock import MagicMock

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, REGISTRY

from huleedu_service_libs.middleware.frameworks.fastapi_metrics_middleware import (
    StandardMetricsMiddleware,
    setup_standard_service_metrics_middleware,
)


def create_mock_request(method: str = "GET", path: str = "/test") -> Any:
    """Create a mock FastAPI Request for testing."""
    mock_request = MagicMock()
    mock_request.method = method
    mock_request.url.path = path
    return mock_request


def create_mock_response(status_code: int = 200) -> Any:
    """Create a mock FastAPI Response for testing."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    return mock_response


@pytest.fixture
def isolated_registry() -> CollectorRegistry:
    """Provide isolated Prometheus registry to prevent test metric collisions."""
    return CollectorRegistry()


@pytest.fixture
def test_service_name() -> str:
    """Provide consistent service name for testing."""
    return "test_service"


@pytest.fixture
def metrics_middleware(isolated_registry: CollectorRegistry, test_service_name: str) -> StandardMetricsMiddleware:
    """Create StandardMetricsMiddleware instance with isolated registry."""
    # Create a dummy app (the middleware doesn't use it directly)
    app = object()
    return StandardMetricsMiddleware(
        app=app,
        service_name=test_service_name,
        registry=isolated_registry
    )


@pytest.fixture
def fastapi_app_with_metrics(isolated_registry: CollectorRegistry, test_service_name: str) -> FastAPI:
    """Create FastAPI app with metrics middleware for integration testing."""
    app = FastAPI()
    
    # Add metrics middleware
    setup_standard_service_metrics_middleware(
        app, 
        service_name=test_service_name,
        registry=isolated_registry
    )
    
    # Add test routes
    @app.get("/test")
    async def test_endpoint() -> dict[str, str]:
        return {"message": "success"}
    
    @app.get("/error")
    async def error_endpoint() -> None:
        raise HTTPException(status_code=500, detail="Test error")
    
    @app.get("/slow")
    async def slow_endpoint() -> dict[str, str]:
        await asyncio.sleep(0.1)  # 100ms delay
        return {"message": "slow"}
    
    return app


class TestStandardMetricsMiddleware:
    """Test StandardMetricsMiddleware with proper boundary mocking."""

    @pytest.mark.asyncio
    async def test_successful_request_metrics(
        self, 
        metrics_middleware: StandardMetricsMiddleware,
        isolated_registry: CollectorRegistry
    ) -> None:
        """Test that successful requests are tracked correctly."""
        request = create_mock_request("GET", "/api/users")
        response = create_mock_response(200)
        
        # Mock call_next function
        async def mock_call_next(req: Any) -> Any:
            return response
        
        # Process request through middleware
        result = await metrics_middleware.dispatch(request, mock_call_next)
        
        # Verify response
        assert result == response
        
        # Verify metrics were recorded
        # Check request counter (filter for _total sample, ignore _created)
        counter_samples = list(metrics_middleware.http_requests_total.collect())[0].samples
        total_sample = next(s for s in counter_samples if s.name.endswith("_total"))
        assert total_sample.labels["method"] == "GET"
        assert total_sample.labels["endpoint"] == "/api/users"
        assert total_sample.labels["status_code"] == "200"
        assert total_sample.value == 1.0
        
        # Check duration histogram
        histogram_samples = list(metrics_middleware.http_request_duration_seconds.collect())[0].samples
        # Histogram creates multiple samples (_count, _sum, _bucket)
        count_sample = next(s for s in histogram_samples if s.name.endswith("_count"))
        assert count_sample.labels["method"] == "GET"
        assert count_sample.labels["endpoint"] == "/api/users"
        assert count_sample.value == 1.0

    @pytest.mark.asyncio
    async def test_error_request_metrics(
        self, 
        metrics_middleware: StandardMetricsMiddleware,
        isolated_registry: CollectorRegistry
    ) -> None:
        """Test that failed requests are tracked with proper error status."""
        request = create_mock_request("POST", "/api/create")
        
        # Mock call_next function that raises exception
        async def mock_call_next_error(req: Any) -> Any:
            raise ValueError("Test processing error")
        
        # Process request through middleware (should raise exception)
        with pytest.raises(ValueError, match="Test processing error"):
            await metrics_middleware.dispatch(request, mock_call_next_error)
        
        # Verify error metrics were recorded
        counter_samples = list(metrics_middleware.http_requests_total.collect())[0].samples
        total_sample = next(s for s in counter_samples if s.name.endswith("_total"))
        assert total_sample.labels["method"] == "POST"
        assert total_sample.labels["endpoint"] == "/api/create"
        assert total_sample.labels["status_code"] == "500"  # Default error status
        assert total_sample.value == 1.0
        
        # Duration should still be tracked for errors
        histogram_samples = list(metrics_middleware.http_request_duration_seconds.collect())[0].samples
        count_sample = next(s for s in histogram_samples if s.name.endswith("_count"))
        assert count_sample.value == 1.0

    @pytest.mark.asyncio
    async def test_multiple_requests_accumulate_metrics(
        self, 
        metrics_middleware: StandardMetricsMiddleware,
        isolated_registry: CollectorRegistry
    ) -> None:
        """Test that multiple requests accumulate metrics correctly."""
        # Process multiple requests
        requests_data: list[tuple[str, str, int]] = [
            ("GET", "/users", 200),
            ("GET", "/users", 200),  # Same endpoint, should accumulate
            ("POST", "/users", 201),  # Different method/status
            ("GET", "/posts", 200),   # Different endpoint
        ]
        
        for method, path, status in requests_data:
            request = create_mock_request(method, path)
            response = create_mock_response(status)
            
            async def mock_call_next(req: Any) -> Any:
                return response
            
            await metrics_middleware.dispatch(request, mock_call_next)
        
        # Verify accumulated metrics
        counter_samples = list(metrics_middleware.http_requests_total.collect())[0].samples
        total_samples = [s for s in counter_samples if s.name.endswith("_total")]
        assert len(total_samples) == 3  # Three unique combinations
        
        # Check specific accumulations
        get_users_200 = next(s for s in total_samples 
                           if s.labels["method"] == "GET" 
                           and s.labels["endpoint"] == "/users"
                           and s.labels["status_code"] == "200")
        assert get_users_200.value == 2.0  # Two GET /users 200 requests
        
        post_users_201 = next(s for s in total_samples 
                            if s.labels["method"] == "POST"
                            and s.labels["endpoint"] == "/users"
                            and s.labels["status_code"] == "201")
        assert post_users_201.value == 1.0

    @pytest.mark.asyncio
    async def test_duration_measurement_accuracy(
        self, 
        metrics_middleware: StandardMetricsMiddleware,
        isolated_registry: CollectorRegistry
    ) -> None:
        """Test that duration measurements are reasonably accurate."""
        request = create_mock_request("GET", "/slow-endpoint")
        response = create_mock_response(200)
        
        # Mock call_next with known delay
        async def mock_call_next_slow(req: Any) -> Any:
            await asyncio.sleep(0.05)  # 50ms delay
            return response
        
        # Process request
        await metrics_middleware.dispatch(request, mock_call_next_slow)
        
        # Check duration histogram
        histogram_samples = list(metrics_middleware.http_request_duration_seconds.collect())[0].samples
        sum_sample = next(s for s in histogram_samples if s.name.endswith("_sum"))
        
        # Duration should be roughly 50ms (0.05 seconds) but allow for variance
        assert 0.04 <= sum_sample.value <= 0.15  # Allow significant variance for test stability

    @pytest.mark.asyncio
    async def test_registry_isolation(self, test_service_name: str) -> None:
        """Test that using isolated registry prevents metric collisions."""
        # Create two middleware instances with different registries
        registry1 = CollectorRegistry()
        registry2 = CollectorRegistry()
        
        middleware1 = StandardMetricsMiddleware(
            app=object(), 
            service_name=test_service_name,
            registry=registry1
        )
        middleware2 = StandardMetricsMiddleware(
            app=object(), 
            service_name=test_service_name,
            registry=registry2
        )
        
        # Process requests through both middleware instances
        request = create_mock_request("GET", "/test")
        response = create_mock_response(200)
        
        async def mock_call_next(req: Any) -> Any:
            return response
        
        await middleware1.dispatch(request, mock_call_next)
        await middleware2.dispatch(request, mock_call_next)
        
        # Verify each registry has its own metrics
        registry1_counter = list(middleware1.http_requests_total.collect())[0].samples
        registry2_counter = list(middleware2.http_requests_total.collect())[0].samples
        
        # Filter for _total samples
        registry1_total = next(s for s in registry1_counter if s.name.endswith("_total"))
        registry2_total = next(s for s in registry2_counter if s.name.endswith("_total"))
        
        assert registry1_total.value == 1.0
        assert registry2_total.value == 1.0

    def test_middleware_uses_global_registry_by_default(self, test_service_name: str) -> None:
        """Test that middleware uses global REGISTRY when none provided.""" 
        middleware = StandardMetricsMiddleware(
            app=object(),
            service_name=test_service_name
            # No registry parameter - should use global REGISTRY
        )
        
        # Test by checking if metrics are available in global registry
        global_metrics = list(REGISTRY.collect())
        metric_names = [metric.name for metric in global_metrics]
        
        # Verify our service metrics are registered in global registry
        # Note: The actual metric name may be truncated without "_total" suffix
        expected_counter_base = f"{test_service_name}_http_requests"
        expected_histogram_name = f"{test_service_name}_http_request_duration_seconds"
        
        # Check if the base counter name exists (with or without _total suffix)
        counter_found = any(name.startswith(expected_counter_base) for name in metric_names)
        assert counter_found, f"Counter metric not found. Available metrics: {metric_names}"
        assert expected_histogram_name in metric_names


class TestSetupStandardServiceMetricsMiddleware:
    """Test the setup function for FastAPI integration."""

    def test_setup_function_adds_middleware(self, isolated_registry: CollectorRegistry, test_service_name: str) -> None:
        """Test that setup function properly adds middleware to FastAPI app."""
        app = FastAPI()
        
        # Verify no middleware initially
        assert len(app.user_middleware) == 0
        
        # Add middleware using setup function
        setup_standard_service_metrics_middleware(
            app, 
            service_name=test_service_name,
            registry=isolated_registry
        )
        
        # Verify middleware was added
        assert len(app.user_middleware) == 1
        assert app.user_middleware[0].cls is StandardMetricsMiddleware

    def test_setup_function_with_default_registry(self, test_service_name: str) -> None:
        """Test setup function works with default registry."""
        app = FastAPI()
        
        # Setup without explicit registry (should use global REGISTRY)
        setup_standard_service_metrics_middleware(app, service_name=test_service_name)
        
        # Verify middleware was added
        assert len(app.user_middleware) == 1
        assert app.user_middleware[0].cls is StandardMetricsMiddleware


class TestFastAPIIntegration:
    """Integration tests using real FastAPI TestClient."""

    def test_real_fastapi_integration(self, fastapi_app_with_metrics: FastAPI, isolated_registry: CollectorRegistry) -> None:
        """Test metrics middleware with real FastAPI application."""
        client = TestClient(fastapi_app_with_metrics)
        
        # Make test requests
        response1 = client.get("/test")
        assert response1.status_code == 200
        
        response2 = client.get("/test")  # Same endpoint again
        assert response2.status_code == 200
        
        response3 = client.get("/slow")  # Different endpoint
        assert response3.status_code == 200
        
        # Check that metrics were recorded in isolated registry
        # Find the metrics in the isolated registry
        collected_metrics = list(isolated_registry.collect())
        metric_names = [m.name for m in collected_metrics]
        
        # Find request counter - filter metrics by name pattern (try different patterns)
        counter_metrics = [m for m in collected_metrics if "http_requests" in m.name]
        assert len(counter_metrics) > 0, f"No counter metrics found. Available metrics: {metric_names}"
        
        counter_metric = counter_metrics[0]
        counter_samples = counter_metric.samples
        
        # Filter for _total samples only
        total_samples = [s for s in counter_samples if s.name.endswith("_total")]
        
        # Should have metrics for both endpoints
        test_endpoint_samples = [s for s in total_samples if s.labels.get("endpoint") == "/test"]
        slow_endpoint_samples = [s for s in total_samples if s.labels.get("endpoint") == "/slow"]
        
        test_endpoint_count = sum(s.value for s in test_endpoint_samples)
        slow_endpoint_count = sum(s.value for s in slow_endpoint_samples)
        
        assert test_endpoint_count == 2.0  # Two requests to /test
        assert slow_endpoint_count == 1.0  # One request to /slow

    def test_error_endpoint_metrics(self, fastapi_app_with_metrics: FastAPI, isolated_registry: CollectorRegistry) -> None:
        """Test that error responses are properly tracked."""
        client = TestClient(fastapi_app_with_metrics)
        
        # Make request to error endpoint
        response = client.get("/error")
        assert response.status_code == 500
        
        # Check error metrics
        collected_metrics = list(isolated_registry.collect())
        metric_names = [m.name for m in collected_metrics]
        counter_metrics = [m for m in collected_metrics if "http_requests" in m.name]
        assert len(counter_metrics) > 0, f"No counter metrics found. Available metrics: {metric_names}"
        
        counter_metric = counter_metrics[0]
        total_samples = [s for s in counter_metric.samples if s.name.endswith("_total")]
        
        error_samples = [s for s in total_samples 
                        if s.labels.get("endpoint") == "/error"
                        and s.labels.get("status_code") == "500"]
        assert len(error_samples) > 0, "No error samples found"
        assert error_samples[0].value == 1.0