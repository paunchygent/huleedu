"""Integration tests for Prometheus metrics emission in Language Tool Service.

These tests validate real metrics emission by parsing actual /metrics endpoint output.
No mocking of metrics infrastructure - tests real Prometheus format compliance.

Tests follow Rule 070: behavioral testing of actual metrics collection, parsing, and validation.
All tests use real Quart application with actual DI container and Prometheus collectors.
"""

from __future__ import annotations

from typing import Any

import pytest
from prometheus_client.parser import text_string_to_metric_families

# MetricsAwareStubWrapper is now defined in conftest.py to be shared across all integration tests


# Registry clearing functionality is handled by the shared fixture in conftest.py


# The MetricsAwareStubWrapper is now in conftest.py for use by all integration tests


# Registry cleanup is now handled by the shared clear_prometheus_registry fixture in conftest.py


# Use the shared integration_app fixture from conftest.py to avoid conflicts


# Use the shared client fixture from conftest.py to avoid conflicts


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
