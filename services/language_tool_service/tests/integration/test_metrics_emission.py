"""Integration tests for Prometheus metrics emission in Language Tool Service.

These tests validate real metrics emission by parsing actual /metrics endpoint output.
No mocking of metrics infrastructure - tests real Prometheus format compliance.

Tests follow Rule 070: behavioral testing of actual metrics collection, parsing, and validation.
All tests use real Quart application with actual DI container and Prometheus collectors.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator
from typing import Any
from uuid import UUID

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling.correlation import CorrelationContext
from huleedu_service_libs.error_handling.quart import register_error_handlers
from prometheus_client import REGISTRY, CollectorRegistry
from prometheus_client.parser import text_string_to_metric_families
from quart import Quart
from quart_dishka import QuartDishka

from services.language_tool_service.api.grammar_routes import grammar_bp
from services.language_tool_service.api.health_routes import health_bp
from services.language_tool_service.config import Settings
from services.language_tool_service.implementations.stub_wrapper import StubLanguageToolWrapper
from services.language_tool_service.metrics import METRICS
from services.language_tool_service.protocols import (
    LanguageToolManagerProtocol,
    LanguageToolWrapperProtocol,
)


class MetricsAwareStubWrapper(StubLanguageToolWrapper):
    """Test-specific stub wrapper that emits metrics like the real wrapper."""

    def __init__(self, settings: Settings, metrics: dict[str, Any] | None = None) -> None:
        """Initialize with metrics support."""
        super().__init__(settings)
        self.metrics = metrics

    async def check_text(
        self, text: str, correlation_context: CorrelationContext, language: str = "en-US"
    ) -> list[dict[str, Any]]:
        """Check text and emit wrapper duration metrics like real wrapper."""
        import time

        # Start timing like real wrapper
        wrapper_start = time.perf_counter()

        # Call the actual stub implementation
        result = await super().check_text(text, correlation_context, language)

        # Emit metrics like real wrapper
        wrapper_duration = time.perf_counter() - wrapper_start
        if self.metrics and "wrapper_duration_seconds" in self.metrics:
            self.metrics["wrapper_duration_seconds"].labels(language=language).observe(
                wrapper_duration
            )

        return result


def _clear_prometheus_registry() -> None:
    """Clear Prometheus registry to prevent metric conflicts between tests."""
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except KeyError:
            # Collector already unregistered
            pass


class IntegrationTestProvider(Provider):
    """Test provider for integration testing with real metrics but stubbed LanguageTool."""

    scope = Scope.APP

    @provide
    def provide_settings(self) -> Settings:
        """Provide test settings configured for integration testing."""
        # Use environment variables or defaults for integration testing
        return Settings(
            SERVICE_NAME="language-tool-service",
            ENVIRONMENT="testing",
            LOG_LEVEL="INFO",
            HOST="127.0.0.1",
            PORT=8085,
            LANGUAGE_TOOL_JAR_PATH="/nonexistent/path/to/test.jar",  # Forces stub mode
            LANGUAGE_TOOL_HOST="localhost",
            LANGUAGE_TOOL_PORT=8081,
            LANGUAGE_TOOL_HEAP_SIZE="1g",
        )

    @provide
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide the real Prometheus metrics registry."""
        return REGISTRY

    @provide
    def provide_metrics(self) -> dict[str, Any]:
        """Provide the real Prometheus metrics dictionary."""
        return METRICS

    @provide
    def provide_language_tool_wrapper(
        self, settings: Settings, metrics: dict[str, Any]
    ) -> LanguageToolWrapperProtocol:
        """Provide metrics-aware stub Language Tool wrapper for integration testing."""
        return MetricsAwareStubWrapper(settings, metrics)

    @provide
    def provide_language_tool_manager(self, settings: Settings) -> LanguageToolManagerProtocol:
        """Provide a mock Language Tool manager for integration testing."""
        from unittest.mock import AsyncMock

        mock_manager = AsyncMock(spec=LanguageToolManagerProtocol)
        mock_manager.get_jvm_heap_usage.return_value = 128.0  # Mock heap usage
        return mock_manager

    @provide(scope=Scope.REQUEST)
    def provide_correlation_context(self) -> CorrelationContext:
        """Provide correlation context for request tracking."""
        return CorrelationContext(
            original="integration-test-correlation-id",
            uuid=UUID("12345678-1234-1234-1234-123456789012"),
            source="generated",
        )


@pytest.fixture
def clear_registry() -> Generator[None, None, None]:
    """Clear Prometheus registry before each test to prevent conflicts."""
    _clear_prometheus_registry()
    yield
    _clear_prometheus_registry()


@pytest.fixture
async def integration_app() -> AsyncGenerator[Quart, None]:
    """Create real Quart application with actual DI container for integration testing.

    This fixture creates a real application instance with:
    - Actual Prometheus metrics collection
    - Real DI container with test providers
    - Real HTTP routes and error handling
    - Stubbed LanguageTool implementation for reliability
    """
    # Force stub mode for reliable integration testing
    os.environ["USE_STUB_LANGUAGE_TOOL"] = "true"

    app = Quart(__name__)
    app.config.update({"TESTING": True})

    # Register actual blueprints
    app.register_blueprint(grammar_bp)
    app.register_blueprint(health_bp)

    # Register real error handlers
    register_error_handlers(app)

    # Set up real DI container with integration test providers
    container = make_async_container(IntegrationTestProvider())
    QuartDishka(app=app, container=container)

    # Store real metrics in app extensions (like production)
    app.extensions = getattr(app, "extensions", {})
    app.extensions["metrics"] = METRICS

    # Setup HTTP metrics middleware like in production
    from huleedu_service_libs.metrics_middleware import setup_metrics_middleware

    setup_metrics_middleware(
        app=app,
        request_count_metric_name="request_count",
        request_duration_metric_name="request_duration",
        status_label_name="status",
        logger_name="language_tool_service.metrics",
    )

    try:
        yield app
    finally:
        await container.close()
        # Clean up environment
        os.environ.pop("USE_STUB_LANGUAGE_TOOL", None)


@pytest.fixture
async def client(integration_app: Quart) -> AsyncGenerator[Any, None]:
    """Create test client for real HTTP requests."""
    async with integration_app.test_client() as test_client:
        yield test_client


async def _parse_metrics_from_endpoint(client: Any) -> list[Any]:
    """Parse real Prometheus metrics from /metrics endpoint.

    Args:
        client: Quart test client for making HTTP requests

    Returns:
        List of parsed metric families from Prometheus text format
    """
    response = await client.get("/metrics")
    assert response.status_code == 200

    metrics_text = await response.get_data(as_text=True)
    assert metrics_text, "Metrics endpoint returned empty response"

    # Parse actual Prometheus format
    return list(text_string_to_metric_families(metrics_text))


def _find_metric_by_name(metric_families: list[Any], name: str) -> Any | None:
    """Find a specific metric by name in parsed metric families.

    Args:
        metric_families: List of parsed metric families from Prometheus
        name: Name of metric to find

    Returns:
        Metric family if found, None otherwise
    """
    for family in metric_families:
        if family.name == name:
            return family
    return None


def _get_metric_value(metric_family: Any, labels: dict[str, str] | None = None) -> float:
    """Extract metric value matching specified labels.

    Args:
        metric_family: Parsed metric family
        labels: Optional labels to match

    Returns:
        Metric value for matching labels
    """
    labels = labels or {}

    for sample in metric_family.samples:
        sample_labels = dict(sample.labels) if hasattr(sample, "labels") else {}
        if all(sample_labels.get(k) == v for k, v in labels.items()):
            # Handle potential Any type from Prometheus parser
            value = sample.value
            if isinstance(value, (int, float)):
                return float(value)
            return float(value) if value is not None else 0.0

    return 0.0


class TestMetricsEmission:
    """Integration tests for Prometheus metrics emission with real parsing."""

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_wrapper_duration_metrics_recorded(self, client: Any) -> None:
        """Verify timing metrics appear in /metrics endpoint after real requests.

        Tests that wrapper_duration_seconds histogram is properly recorded
        when the LanguageTool wrapper is called during grammar checking.
        """
        # Arrange: Get initial metrics baseline
        initial_families = await _parse_metrics_from_endpoint(client)
        initial_metric = _find_metric_by_name(
            initial_families, "language_tool_service_wrapper_duration_seconds"
        )
        initial_count = 0.0
        if initial_metric:
            initial_count = _get_metric_value(initial_metric, {"language": "en-US"})

        # Act: Make request to trigger wrapper duration measurement
        request_body = {
            "text": "This is a test sentence for duration measurement.",
            "language": "en-US",
        }
        response = await client.post("/v1/check", json=request_body)

        # Assert: Request succeeded
        assert response.status_code == 200
        response_data = await response.get_json()
        assert "total_grammar_errors" in response_data
        assert "processing_time_ms" in response_data

        # Verify: Wrapper duration metrics were recorded
        final_families = await _parse_metrics_from_endpoint(client)
        wrapper_duration_metric = _find_metric_by_name(
            final_families, "language_tool_service_wrapper_duration_seconds"
        )

        assert wrapper_duration_metric is not None, (
            "wrapper_duration_seconds metric not found in /metrics output"
        )
        assert wrapper_duration_metric.type == "histogram", (
            "wrapper_duration_seconds should be histogram type"
        )

        # Check that histogram count increased (indicating measurement was recorded)
        final_count = _get_metric_value(wrapper_duration_metric, {"language": "en-US"})
        assert final_count > initial_count, (
            "wrapper_duration_seconds count should increase after request"
        )

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_api_error_metrics_increment(self, client: Any) -> None:
        """Check error counters increase on real error conditions.

        Tests that api_errors_total counter increments when actual validation
        errors occur during request processing.
        """
        # Arrange: Get initial error metrics
        initial_families = await _parse_metrics_from_endpoint(client)
        initial_metric = _find_metric_by_name(initial_families, "language_tool_service_api_errors")
        initial_count = 0.0
        if initial_metric:
            initial_count = _get_metric_value(
                initial_metric, {"endpoint": "/v1/check", "error_type": "validation_error"}
            )

        # Act: Trigger validation error with empty text
        request_body = {"text": "", "language": "en-US"}  # Empty text triggers validation error
        response = await client.post("/v1/check", json=request_body)

        # Assert: Request failed with validation error
        assert response.status_code == 400
        response_data = await response.get_json()
        assert "error" in response_data
        assert response_data["error"]["code"] == "VALIDATION_ERROR"

        # Verify: API error metrics incremented
        final_families = await _parse_metrics_from_endpoint(client)
        error_metric = _find_metric_by_name(final_families, "language_tool_service_api_errors")

        assert error_metric is not None, "api_errors_total metric not found in /metrics output"
        assert error_metric.type == "counter", "api_errors_total should be counter type"

        final_count = _get_metric_value(
            error_metric, {"endpoint": "/v1/check", "error_type": "validation_error"}
        )
        assert final_count > initial_count, (
            "api_errors_total should increment after validation error"
        )

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_metrics_persist_across_requests(self, client: Any) -> None:
        """Validate metric accumulation across multiple requests.

        Tests that metrics properly accumulate values across multiple
        requests without being reset between calls.
        """
        # Act: Make multiple successful requests
        request_body = {"text": "This is test text for accumulation testing.", "language": "en-US"}

        responses = []
        for _ in range(3):
            response = await client.post("/v1/check", json=request_body)
            assert response.status_code == 200
            responses.append(response)

        # Verify: All requests succeeded
        for response in responses:
            response_data = await response.get_json()
            assert "total_grammar_errors" in response_data

        # Check: Grammar analysis metrics accumulated
        families = await _parse_metrics_from_endpoint(client)
        analysis_metric = _find_metric_by_name(families, "language_tool_service_grammar_analysis")

        assert analysis_metric is not None, "grammar_analysis metric not found"
        success_count = _get_metric_value(
            analysis_metric, {"status": "success", "text_length_range": "0-100_words"}
        )
        assert success_count >= 3.0, f"Expected at least 3 successful analyses, got {success_count}"

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_prometheus_format_compliance(self, client: Any) -> None:
        """Parse actual /metrics output to verify Prometheus format compliance.

        Tests that the /metrics endpoint returns valid Prometheus text format
        that can be successfully parsed by the official Prometheus client.
        """
        # Act: Get metrics from real endpoint
        response = await client.get("/metrics")

        # Assert: Metrics endpoint responded successfully
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "text/plain; version=0.0.4; charset=utf-8"

        metrics_text = await response.get_data(as_text=True)
        assert metrics_text, "Metrics response should not be empty"
        assert "language_tool_service_" in metrics_text, "Should contain service-specific metrics"

        # Verify: Prometheus format compliance
        try:
            metric_families = list(text_string_to_metric_families(metrics_text))
            assert len(metric_families) > 0, "Should contain at least one metric family"

            # Check for expected metric types
            metric_names = [family.name for family in metric_families]
            expected_metrics = [
                "language_tool_service_wrapper_duration_seconds",
                "language_tool_service_api_errors",
                "language_tool_service_grammar_analysis",
                "language_tool_service_grammar_analysis_duration_seconds",
            ]

            for expected in expected_metrics:
                assert expected in metric_names, f"Expected metric {expected} not found in output"

        except Exception as e:
            pytest.fail(f"Failed to parse Prometheus format: {e}")

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_metric_labels_contain_values(self, client: Any) -> None:
        """Verify label accuracy in real metric output.

        Tests that metrics contain expected label values that match
        the actual request parameters and processing results.
        """
        # Act: Make requests with different languages to generate labeled metrics
        test_cases = [
            {"text": "English test text for label verification.", "language": "en-US"},
            {"text": "Svensk testtext för etikettverifiering.", "language": "sv-SE"},
        ]

        for request_body in test_cases:
            response = await client.post("/v1/check", json=request_body)
            assert response.status_code == 200

        # Verify: Metrics contain accurate labels
        families = await _parse_metrics_from_endpoint(client)

        # Check wrapper duration metrics have correct language labels
        wrapper_metric = _find_metric_by_name(
            families, "language_tool_service_wrapper_duration_seconds"
        )
        assert wrapper_metric is not None, "wrapper_duration_seconds metric not found"

        # Verify language labels are present
        language_labels = set()
        for sample in wrapper_metric.samples:
            if hasattr(sample, "labels") and "language" in sample.labels:
                language_labels.add(sample.labels["language"])

        assert "en-US" in language_labels, "Should contain en-US language label"
        assert "sv-SE" in language_labels, "Should contain sv-SE language label"

        # Check API error metrics have correct endpoint labels
        error_metric = _find_metric_by_name(families, "language_tool_service_api_errors_total")
        if error_metric:  # May not exist if no errors occurred
            endpoint_labels = set()
            for sample in error_metric.samples:
                if hasattr(sample, "labels") and "endpoint" in sample.labels:
                    endpoint_labels.add(sample.labels["endpoint"])

            if endpoint_labels:  # Only check if errors were recorded
                assert "/v1/check" in endpoint_labels, "Should contain /v1/check endpoint label"

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_http_request_metrics_recorded(self, client: Any) -> None:
        """Verify HTTP request metrics are recorded for all endpoints.

        Additional test to verify that basic HTTP request counting and timing
        metrics work correctly across different endpoints.
        """
        # Arrange: Get initial HTTP metrics
        initial_families = await _parse_metrics_from_endpoint(client)
        initial_request_metric = _find_metric_by_name(
            initial_families, "language_tool_service_http_requests"
        )
        initial_request_count = 0.0
        if initial_request_metric:
            initial_request_count = _get_metric_value(
                initial_request_metric, {"method": "POST", "endpoint": "/v1/check", "status": "200"}
            )

        # Act: Make successful request
        request_body = {"text": "Test text for HTTP metrics verification.", "language": "en-US"}
        response = await client.post("/v1/check", json=request_body)
        assert response.status_code == 200

        # Verify: HTTP request metrics were recorded
        final_families = await _parse_metrics_from_endpoint(client)

        request_metric = _find_metric_by_name(final_families, "language_tool_service_http_requests")
        assert request_metric is not None, "http_requests metric not found"

        final_request_count = _get_metric_value(
            request_metric, {"method": "POST", "endpoint": "/v1/check", "status": "200"}
        )
        assert final_request_count > initial_request_count, "HTTP request count should increment"

        # Check duration metrics exist
        duration_metric = _find_metric_by_name(
            final_families, "language_tool_service_http_request_duration_seconds"
        )
        assert duration_metric is not None, "http_request_duration_seconds metric not found"
        assert duration_metric.type == "histogram", "request_duration should be histogram type"
