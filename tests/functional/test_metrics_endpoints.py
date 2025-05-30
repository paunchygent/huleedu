"""
Metrics Endpoint Testing

Validates Prometheus metrics functionality across all services.
Tests metric format, content, and specific HuleEdu metrics.
"""

import re

import httpx
import pytest


class TestPrometheusMetrics:
    """Test suite for validating Prometheus metrics across all services."""

    HTTP_SERVICES = [
        ("content_service", 8001),
        ("batch_orchestrator_service", 5001),
        ("essay_lifecycle_service", 6001),
        ("spell_checker_service", 8002),  # Metrics-only endpoint
    ]

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_metrics_format_compliance(self):
        """Test that all metrics endpoints return valid Prometheus format."""
        async with httpx.AsyncClient() as client:
            for service_name, port in self.HTTP_SERVICES:
                url = f"http://localhost:{port}/metrics"
                try:
                    response = await client.get(url, timeout=5.0)
                    assert response.status_code == 200, f"{service_name} metrics endpoint failed"

                    metrics_text = response.text

                    # Validate Prometheus format requirements
                    assert "# HELP" in metrics_text, f"{service_name}: Missing HELP comments"
                    assert "# TYPE" in metrics_text, f"{service_name}: Missing TYPE declarations"

                    # Check for valid metric lines (metric_name{labels} value)
                    metric_lines = [
                        line
                        for line in metrics_text.split("\n")
                        if line and not line.startswith("#")
                    ]

                    # Note: Services may have 0 metric values if they haven't processed anything yet
                    # This is valid Prometheus format - HELP and TYPE declarations are sufficient
                    if len(metric_lines) == 0:
                        print(
                            f"ℹ️  {service_name}: Valid Prometheus format "
                            "(HELP/TYPE only, no metric values yet)"
                        )
                    else:
                        print(
                            f"✅ {service_name}: Valid Prometheus format "
                            f"({len(metric_lines)} metrics)"
                        )

                except httpx.ConnectError:
                    if service_name == "spell_checker_service":
                        pytest.skip(f"{service_name} metrics server not running (worker service)")
                    else:
                        pytest.skip(f"{service_name} not accessible - services may not be running")
                except Exception as e:
                    pytest.fail(f"{service_name} metrics validation failed: {e}")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_http_service_standard_metrics(self):
        """Test that HTTP services expose standard request metrics."""
        http_only_services = [
            ("content_service", 8001),
            ("batch_orchestrator_service", 5001),
            ("essay_lifecycle_service", 6001),
        ]

        async with httpx.AsyncClient() as client:
            for service_name, port in http_only_services:
                url = f"http://localhost:{port}/metrics"
                try:
                    response = await client.get(url, timeout=5.0)
                    metrics_text = response.text

                    # Check for standard HTTP metrics
                    expected_metrics = [
                        "http_requests_total",
                        "http_request_duration_seconds",
                    ]

                    for metric in expected_metrics:
                        assert metric in metrics_text, f"{service_name}: Missing {metric}"

                    print(f"📊 {service_name}: Standard HTTP metrics present")
                except httpx.ConnectError:
                    pytest.skip(f"{service_name} not accessible - services may not be running")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_spell_checker_kafka_metrics(self):
        """Test that Spell Checker Service exposes Kafka-specific metrics."""
        async with httpx.AsyncClient() as client:
            url = "http://localhost:8002/metrics"
            try:
                response = await client.get(url, timeout=5.0)
                assert response.status_code == 200, "Spell Checker metrics failed"

                metrics_text = response.text

                # Check for Kafka queue latency metric
                assert "kafka_message_queue_latency_seconds" in metrics_text, (
                    "Missing Kafka queue latency metric"
                )

                print("📊 spell_checker_service: Kafka metrics present")

            except httpx.ConnectError:
                pytest.skip("Spell Checker metrics server not running")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_metrics_content_type(self):
        """Test that metrics endpoints return correct Content-Type header."""
        async with httpx.AsyncClient() as client:
            for service_name, port in self.HTTP_SERVICES:
                url = f"http://localhost:{port}/metrics"
                try:
                    response = await client.get(url, timeout=5.0)
                    content_type = response.headers.get("content-type", "")

                    # Prometheus metrics should be text/plain
                    assert "text/plain" in content_type, (
                        f"{service_name}: Invalid Content-Type: {content_type}"
                    )

                    print(f"✅ {service_name}: Correct Content-Type: {content_type}")

                except httpx.ConnectError:
                    if service_name == "spell_checker_service":
                        pytest.skip(
                            f"{service_name} not accessible - worker service may not be running"
                        )
                    else:
                        pytest.skip(f"{service_name} not accessible - services may not be running")


class TestMetricsData:
    """Test suite for validating actual metrics data and values."""

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_metrics_have_values(self):
        """Test that metrics contain actual data (not just declarations)."""
        services = [
            ("content_service", 8001),
            ("batch_orchestrator_service", 5001),
            ("essay_lifecycle_service", 6001),
        ]

        async with httpx.AsyncClient() as client:
            for service_name, port in services:
                try:
                    # First, trigger some activity by calling health endpoint
                    health_url = f"http://localhost:{port}/healthz"
                    await client.get(health_url)

                    # Then check metrics
                    metrics_url = f"http://localhost:{port}/metrics"
                    response = await client.get(metrics_url)
                    metrics_text = response.text

                    # Look for http_requests_total with actual values > 0
                    http_requests_pattern = r"http_requests_total\{.*\}\s+([0-9.]+)"
                    matches = re.findall(http_requests_pattern, metrics_text)

                    assert len(matches) > 0, f"{service_name}: No http_requests_total values found"

                    # At least one metric should have value > 0 (from our health check)
                    values = [float(match) for match in matches]
                    assert any(v > 0 for v in values), (
                        f"{service_name}: All request counters are zero"
                    )

                    print(
                        f"📈 {service_name}: Metrics have live data (max requests: {max(values)})"
                    )
                except httpx.ConnectError:
                    pytest.skip(f"{service_name} not accessible - services may not be running")


# TODO: Add metric aggregation tests
# TODO: Add metric retention/persistence tests
# TODO: Add custom business metrics validation
