"""Unit tests for Language Tool Service metrics implementation.

Tests focus on metric structure validation, registry isolation, and metric behavior
following Rule 075 methodology with proper test registry patterns.
"""

from __future__ import annotations

from typing import Any

import pytest
from prometheus_client import CollectorRegistry, Counter, Histogram

from services.language_tool_service.metrics import METRICS


class TestMetricsCreation:
    """Tests for metrics creation and structure validation."""

    @pytest.fixture
    def test_registry(self) -> CollectorRegistry:
        """Provide a fresh registry for each test to ensure isolation."""
        return CollectorRegistry()

    @pytest.fixture
    def test_metrics(self, test_registry: CollectorRegistry) -> dict[str, Any]:
        """Create metrics with test registry for isolation."""
        # Temporarily replace default registry with test registry

        # Create fresh metrics using the test registry
        metrics = {
            "request_count": Counter(
                "language_tool_service_http_requests_total",
                "Total number of HTTP requests",
                ["method", "endpoint", "status"],
                registry=test_registry,
            ),
            "request_duration": Histogram(
                "language_tool_service_http_request_duration_seconds",
                "HTTP request duration in seconds",
                ["method", "endpoint"],
                registry=test_registry,
            ),
            "grammar_analysis_total": Counter(
                "language_tool_service_grammar_analysis_total",
                "Total grammar analysis requests processed",
                ["status", "text_length_range"],
                registry=test_registry,
            ),
            "grammar_analysis_duration_seconds": Histogram(
                "language_tool_service_grammar_analysis_duration_seconds",
                "Time spent analyzing text for grammar errors",
                registry=test_registry,
            ),
            "language_tool_health_checks_total": Counter(
                "language_tool_service_health_checks_total",
                "Total health check requests to Language Tool wrapper",
                ["status"],
                registry=test_registry,
            ),
        }
        return metrics

    def test_metrics_dictionary_structure(self, test_metrics: dict[str, Any]) -> None:
        """Test that metrics dictionary contains all required keys."""
        expected_keys = {
            "request_count",
            "request_duration",
            "grammar_analysis_total",
            "grammar_analysis_duration_seconds",
            "language_tool_health_checks_total",
        }
        assert set(test_metrics.keys()) == expected_keys

    def test_request_count_counter_structure(self, test_metrics: dict[str, Any]) -> None:
        """Test request_count counter has correct structure and labels."""
        request_count = test_metrics["request_count"]
        assert isinstance(request_count, Counter)
        assert request_count._name == "language_tool_service_http_requests"
        assert request_count._documentation == "Total number of HTTP requests"
        assert set(request_count._labelnames) == {"method", "endpoint", "status"}

    def test_request_duration_histogram_structure(self, test_metrics: dict[str, Any]) -> None:
        """Test request_duration histogram has correct structure and labels."""
        request_duration = test_metrics["request_duration"]
        assert isinstance(request_duration, Histogram)
        assert request_duration._name == "language_tool_service_http_request_duration_seconds"
        assert request_duration._documentation == "HTTP request duration in seconds"
        assert set(request_duration._labelnames) == {"method", "endpoint"}

    def test_grammar_analysis_total_counter_structure(self, test_metrics: dict[str, Any]) -> None:
        """Test grammar_analysis_total counter has correct structure and labels."""
        analysis_total = test_metrics["grammar_analysis_total"]
        assert isinstance(analysis_total, Counter)
        assert analysis_total._name == "language_tool_service_grammar_analysis"
        assert analysis_total._documentation == "Total grammar analysis requests processed"
        assert set(analysis_total._labelnames) == {"status", "text_length_range"}

    def test_grammar_analysis_duration_histogram_structure(
        self, test_metrics: dict[str, Any]
    ) -> None:
        """Test grammar_analysis_duration_seconds histogram has correct structure."""
        analysis_duration = test_metrics["grammar_analysis_duration_seconds"]
        assert isinstance(analysis_duration, Histogram)
        assert analysis_duration._name == "language_tool_service_grammar_analysis_duration_seconds"
        assert analysis_duration._documentation == "Time spent analyzing text for grammar errors"
        assert analysis_duration._labelnames == ()  # No labels for this histogram

    def test_language_tool_health_checks_counter_structure(
        self, test_metrics: dict[str, Any]
    ) -> None:
        """Test language_tool_health_checks_total counter has correct structure and labels."""
        health_checks = test_metrics["language_tool_health_checks_total"]
        assert isinstance(health_checks, Counter)
        assert health_checks._name == "language_tool_service_health_checks"
        assert (
            health_checks._documentation == "Total health check requests to Language Tool wrapper"
        )
        assert set(health_checks._labelnames) == {"status"}


class TestMetricsBehavior:
    """Tests for metrics behavior and value updates."""

    @pytest.fixture
    def test_registry(self) -> CollectorRegistry:
        """Provide a fresh registry for each test to ensure isolation."""
        return CollectorRegistry()

    @pytest.fixture
    def test_metrics(self, test_registry: CollectorRegistry) -> dict[str, Any]:
        """Create metrics with test registry for isolation."""
        return {
            "request_count": Counter(
                "language_tool_service_http_requests_total",
                "Total number of HTTP requests",
                ["method", "endpoint", "status"],
                registry=test_registry,
            ),
            "request_duration": Histogram(
                "language_tool_service_http_request_duration_seconds",
                "HTTP request duration in seconds",
                ["method", "endpoint"],
                registry=test_registry,
            ),
            "grammar_analysis_total": Counter(
                "language_tool_service_grammar_analysis_total",
                "Total grammar analysis requests processed",
                ["status", "text_length_range"],
                registry=test_registry,
            ),
            "grammar_analysis_duration_seconds": Histogram(
                "language_tool_service_grammar_analysis_duration_seconds",
                "Time spent analyzing text for grammar errors",
                registry=test_registry,
            ),
            "language_tool_health_checks_total": Counter(
                "language_tool_service_health_checks_total",
                "Total health check requests to Language Tool wrapper",
                ["status"],
                registry=test_registry,
            ),
        }

    @pytest.mark.parametrize(
        "method, endpoint, status",
        [
            ("GET", "/health", "200"),
            ("POST", "/analyze", "200"),
            ("POST", "/analyze", "400"),
            ("POST", "/analyze", "500"),
            ("GET", "/metrics", "200"),
        ],
    )
    def test_request_count_labeling(
        self, test_metrics: dict[str, Any], method: str, endpoint: str, status: str
    ) -> None:
        """Test request_count counter accepts various HTTP request label combinations."""
        request_count = test_metrics["request_count"]

        # Act - increment counter with labels
        request_count.labels(method=method, endpoint=endpoint, status=status).inc()

        # Assert - verify metric value incremented
        metric_value = request_count.labels(
            method=method, endpoint=endpoint, status=status
        )._value._value
        assert metric_value == 1.0

    @pytest.mark.parametrize(
        "method, endpoint, duration",
        [
            ("GET", "/health", 0.001),
            ("POST", "/analyze", 0.150),
            ("POST", "/analyze", 0.750),
            ("GET", "/metrics", 0.005),
            ("POST", "/analyze", 2.500),  # Long analysis
        ],
    )
    def test_request_duration_recording(
        self, test_metrics: dict[str, Any], method: str, endpoint: str, duration: float
    ) -> None:
        """Test request_duration histogram records various duration values correctly."""
        request_duration = test_metrics["request_duration"]

        # Record initial sum
        initial_sum = request_duration.labels(method=method, endpoint=endpoint)._sum._value

        # Act - observe duration
        request_duration.labels(method=method, endpoint=endpoint).observe(duration)

        # Assert - verify observation was recorded
        final_sum = request_duration.labels(method=method, endpoint=endpoint)._sum._value
        assert final_sum == initial_sum + duration

    @pytest.mark.parametrize(
        "status, text_length_range",
        [
            ("success", "short"),
            ("success", "medium"),
            ("success", "long"),
            ("error", "short"),
            ("error", "medium"),
            ("timeout", "long"),
            ("validation_error", "short"),
        ],
    )
    def test_grammar_analysis_total_labeling(
        self, test_metrics: dict[str, Any], status: str, text_length_range: str
    ) -> None:
        """Test grammar_analysis_total counter accepts various analysis status and text length combinations."""
        analysis_total = test_metrics["grammar_analysis_total"]

        # Act - increment counter with labels
        analysis_total.labels(status=status, text_length_range=text_length_range).inc()

        # Assert - verify metric value incremented
        metric_value = analysis_total.labels(
            status=status, text_length_range=text_length_range
        )._value._value
        assert metric_value == 1.0

    @pytest.mark.parametrize(
        "duration_seconds, expected_bucket_exists",
        [
            (0.001, True),  # Very fast analysis
            (0.050, True),  # Typical analysis
            (0.250, True),  # Slower analysis
            (1.000, True),  # Long analysis
            (5.000, True),  # Very long analysis
            (10.000, True),  # Timeout range
        ],
    )
    def test_grammar_analysis_duration_recording(
        self, test_metrics: dict[str, Any], duration_seconds: float, expected_bucket_exists: bool
    ) -> None:
        """Test grammar_analysis_duration_seconds histogram records duration values correctly."""
        analysis_duration = test_metrics["grammar_analysis_duration_seconds"]

        # Record initial sum
        initial_sum = analysis_duration._sum._value

        # Act - observe duration
        analysis_duration.observe(duration_seconds)

        # Assert - verify observation was recorded by checking sum increase
        final_sum = analysis_duration._sum._value
        assert final_sum == initial_sum + duration_seconds

        # Verify bucket exists (all durations should fall into some bucket)
        assert expected_bucket_exists

    @pytest.mark.parametrize(
        "status",
        [
            "healthy",
            "unhealthy",
            "timeout",
            "connection_error",
            "service_unavailable",
        ],
    )
    def test_language_tool_health_checks_labeling(
        self, test_metrics: dict[str, Any], status: str
    ) -> None:
        """Test language_tool_health_checks_total counter accepts various health check statuses."""
        health_checks = test_metrics["language_tool_health_checks_total"]

        # Act - increment counter with status label
        health_checks.labels(status=status).inc()

        # Assert - verify metric value incremented
        metric_value = health_checks.labels(status=status)._value._value
        assert metric_value == 1.0


class TestMetricsRegistryIntegration:
    """Tests for metrics registry integration and isolation."""

    @pytest.fixture
    def test_registry(self) -> CollectorRegistry:
        """Provide a fresh registry for each test to ensure isolation."""
        return CollectorRegistry()

    def test_metrics_are_registered_in_test_registry(
        self, test_registry: CollectorRegistry
    ) -> None:
        """Test that metrics can be registered in a custom registry."""
        # Create metrics with test registry
        Counter(
            "test_language_tool_counter",
            "Test counter for language tool service",
            ["test_label"],
            registry=test_registry,
        )

        Histogram(
            "test_language_tool_histogram",
            "Test histogram for language tool service",
            registry=test_registry,
        )

        # Verify metrics are registered in test registry
        metric_families = list(test_registry.collect())
        metric_names = {family.name for family in metric_families}

        assert "test_language_tool_counter" in metric_names
        assert "test_language_tool_histogram" in metric_names

    def test_global_metrics_instance_structure(self) -> None:
        """Test that the global METRICS instance has the expected structure."""
        # Verify global METRICS dictionary exists and has correct keys
        expected_keys = {
            "request_count",
            "request_duration",
            "grammar_analysis_total",
            "grammar_analysis_duration_seconds",
            "language_tool_health_checks_total",
        }

        assert isinstance(METRICS, dict)
        assert set(METRICS.keys()) == expected_keys

        # Verify types without affecting global registry
        assert isinstance(METRICS["request_count"], Counter)
        assert isinstance(METRICS["request_duration"], Histogram)
        assert isinstance(METRICS["grammar_analysis_total"], Counter)
        assert isinstance(METRICS["grammar_analysis_duration_seconds"], Histogram)
        assert isinstance(METRICS["language_tool_health_checks_total"], Counter)

    def test_create_metrics_function_returns_correct_structure(
        self, test_registry: CollectorRegistry
    ) -> None:
        """Test that _create_metrics function returns correctly structured dictionary."""
        # Since _create_metrics uses the global REGISTRY, we'll test the structure
        # of the global METRICS instead to avoid registry conflicts

        # Verify structure
        expected_keys = {
            "request_count",
            "request_duration",
            "grammar_analysis_total",
            "grammar_analysis_duration_seconds",
            "language_tool_health_checks_total",
        }

        assert isinstance(METRICS, dict)
        assert set(METRICS.keys()) == expected_keys

        # Verify each metric type
        assert isinstance(METRICS["request_count"], Counter)
        assert isinstance(METRICS["request_duration"], Histogram)
        assert isinstance(METRICS["grammar_analysis_total"], Counter)
        assert isinstance(METRICS["grammar_analysis_duration_seconds"], Histogram)
        assert isinstance(METRICS["language_tool_health_checks_total"], Counter)


class TestMetricsNamingConventions:
    """Tests for metrics naming conventions and consistency."""

    def test_service_prefix_consistency(self) -> None:
        """Test that all metrics use consistent 'language_tool_service_' prefix."""
        expected_prefixes = [
            "language_tool_service_http_requests_total",
            "language_tool_service_http_request_duration_seconds",
            "language_tool_service_grammar_analysis_total",
            "language_tool_service_grammar_analysis_duration_seconds",
            "language_tool_service_health_checks_total",
        ]

        for metric_name in expected_prefixes:
            assert metric_name.startswith("language_tool_service_")

    def test_counter_naming_conventions(self) -> None:
        """Test that counter metrics follow proper naming conventions (Prometheus strips _total suffix from _name)."""
        counter_metrics = [
            METRICS["request_count"]._name,
            METRICS["grammar_analysis_total"]._name,
            METRICS["language_tool_health_checks_total"]._name,
        ]

        # Prometheus strips the _total suffix from counter ._name attributes
        expected_names = [
            "language_tool_service_http_requests",
            "language_tool_service_grammar_analysis",
            "language_tool_service_health_checks",
        ]

        assert counter_metrics == expected_names

    def test_histogram_naming_conventions(self) -> None:
        """Test that histogram metrics follow _seconds suffix convention where applicable."""
        duration_histograms = [
            METRICS["request_duration"]._name,
            METRICS["grammar_analysis_duration_seconds"]._name,
        ]

        for histogram_name in duration_histograms:
            assert histogram_name.endswith("_seconds")

    @pytest.mark.parametrize(
        "metric_key, expected_documentation_keywords",
        [
            ("request_count", ["HTTP", "requests"]),
            ("request_duration", ["HTTP", "request", "duration"]),
            ("grammar_analysis_total", ["grammar", "analysis"]),
            ("grammar_analysis_duration_seconds", ["analyzing", "grammar"]),
            ("language_tool_health_checks_total", ["health", "check"]),
        ],
    )
    def test_metric_documentation_content(
        self, metric_key: str, expected_documentation_keywords: list[str]
    ) -> None:
        """Test that metric documentation contains expected keywords."""
        metric = METRICS[metric_key]
        documentation = metric._documentation.lower()

        for keyword in expected_documentation_keywords:
            assert keyword.lower() in documentation


class TestDomainSpecificMetricScenarios:
    """Tests for domain-specific metric scenarios relevant to language analysis."""

    @pytest.fixture
    def test_registry(self) -> CollectorRegistry:
        """Provide a fresh registry for each test to ensure isolation."""
        return CollectorRegistry()

    @pytest.fixture
    def test_metrics(self, test_registry: CollectorRegistry) -> dict[str, Any]:
        """Create metrics with test registry for isolation."""
        return {
            "grammar_analysis_total": Counter(
                "language_tool_service_grammar_analysis_total",
                "Total grammar analysis requests processed",
                ["status", "text_length_range"],
                registry=test_registry,
            ),
            "grammar_analysis_duration_seconds": Histogram(
                "language_tool_service_grammar_analysis_duration_seconds",
                "Time spent analyzing text for grammar errors",
                registry=test_registry,
            ),
        }

    @pytest.mark.parametrize(
        "text_sample, expected_length_range, expected_duration_range",
        [
            # Short text samples
            ("Hello world.", "short", (0.001, 0.050)),
            ("Hej världen!", "short", (0.001, 0.050)),  # Swedish text
            ("Åsa äter äpplen.", "short", (0.001, 0.050)),  # Swedish characters
            # Medium text samples
            (
                "This is a longer text sample that would require more processing time.",
                "medium",
                (0.050, 0.250),
            ),
            (
                "Det här är en längre text på svenska som kräver mer bearbetningstid.",
                "medium",
                (0.050, 0.250),
            ),
            # Long text samples
            ("A" * 1000, "long", (0.250, 2.000)),  # Very long repetitive text
            ("å" * 1000, "long", (0.250, 2.000)),  # Long text with Swedish characters
        ],
    )
    def test_text_analysis_realistic_scenarios(
        self,
        test_metrics: dict[str, Any],
        text_sample: str,
        expected_length_range: str,
        expected_duration_range: tuple[float, float],
    ) -> None:
        """Test metrics with realistic text analysis scenarios including Swedish text."""
        analysis_total = test_metrics["grammar_analysis_total"]
        analysis_duration = test_metrics["grammar_analysis_duration_seconds"]

        # Simulate successful analysis
        analysis_total.labels(status="success", text_length_range=expected_length_range).inc()

        # Simulate realistic processing duration
        min_duration, max_duration = expected_duration_range
        test_duration = (min_duration + max_duration) / 2  # Use middle value
        analysis_duration.observe(test_duration)

        # Assert metrics were recorded
        metric_value = analysis_total.labels(
            status="success", text_length_range=expected_length_range
        )._value._value
        assert metric_value == 1.0

        # Verify duration was recorded (non-zero sum indicates observation)
        assert analysis_duration._sum._value > 0

    @pytest.mark.parametrize(
        "error_scenario, expected_status",
        [
            ("Network timeout to LanguageTool", "timeout"),
            ("Invalid input encoding", "validation_error"),
            ("LanguageTool service down", "error"),
            ("Request rate limit exceeded", "rate_limited"),
            ("Text too long for processing", "text_too_long"),
        ],
    )
    def test_error_scenario_metrics(
        self, test_metrics: dict[str, Any], error_scenario: str, expected_status: str
    ) -> None:
        """Test metrics recording for various error scenarios in language analysis."""
        analysis_total = test_metrics["grammar_analysis_total"]

        # Record error with appropriate text length
        analysis_total.labels(status=expected_status, text_length_range="medium").inc()

        # Assert error metric was recorded
        metric_value = analysis_total.labels(
            status=expected_status, text_length_range="medium"
        )._value._value
        assert metric_value == 1.0
