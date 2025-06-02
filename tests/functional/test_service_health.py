"""
Service Health Testing

Validates that all microservices are responding correctly to health check requests.
Tests both /healthz and /metrics endpoints across all HTTP services.
"""

import asyncio

import httpx
import pytest


class TestServiceHealth:
    """Test suite for validating service health endpoints across all services."""

    # Service configuration: (service_name, port, base_path)
    HTTP_SERVICES = [
        ("content_service", 8001, ""),
        ("batch_orchestrator_service", 5001, ""),
        ("essay_lifecycle_service", 6001, ""),
        ("file_service", 7001, ""),
    ]

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_all_services_health_endpoints(self):
        """Test that all services respond to /healthz with HTTP 200."""
        async with httpx.AsyncClient() as client:
            health_results = []

            for service_name, port, base_path in self.HTTP_SERVICES:
                url = f"http://localhost:{port}{base_path}/healthz"
                try:
                    response = await client.get(url, timeout=5.0)
                    health_results.append((service_name, response.status_code, response.json()))
                    assert response.status_code == 200, f"{service_name} health check failed"
                except httpx.ConnectError:
                    pytest.skip(f"{service_name} not accessible - services may not be running")
                except Exception as e:
                    pytest.fail(f"{service_name} health check failed with exception: {e}")

            # Log all results for visibility
            for service_name, status_code, response_data in health_results:
                print(f"✅ {service_name}: {status_code} - {response_data}")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_all_services_metrics_endpoints(self):
        """Test that all services respond to /metrics with HTTP 200 and Prometheus format."""
        async with httpx.AsyncClient() as client:
            metrics_results = []

            for service_name, port, base_path in self.HTTP_SERVICES:
                url = f"http://localhost:{port}{base_path}/metrics"
                try:
                    response = await client.get(url, timeout=5.0)
                    metrics_results.append((service_name, response.status_code, len(response.text)))
                    assert response.status_code == 200, f"{service_name} metrics endpoint failed"

                    # Verify Prometheus format
                    metrics_text = response.text
                    # Allow empty metrics (valid for services with no metrics registered yet)
                    if metrics_text.strip():
                        assert "# HELP" in metrics_text, (
                            f"{service_name} metrics not in Prometheus format"
                        )
                        assert "# TYPE" in metrics_text, (
                            f"{service_name} metrics missing TYPE declarations"
                        )
                    else:
                        # Empty metrics registry is acceptable for walking skeleton
                        print(
                            f"ℹ️  {service_name}: Empty metrics registry (acceptable for walking skeleton)"
                        )

                except httpx.ConnectError:
                    pytest.skip(f"{service_name} not accessible - services may not be running")
                except Exception as e:
                    pytest.fail(f"{service_name} metrics endpoint failed with exception: {e}")

            # Log all results for visibility
            for service_name, status_code, metrics_size in metrics_results:
                print(f"📊 {service_name}: {status_code} - {metrics_size} chars of metrics data")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_service_response_times(self):
        """Test that all services respond within acceptable time limits."""
        async with httpx.AsyncClient() as client:
            for service_name, port, base_path in self.HTTP_SERVICES:
                url = f"http://localhost:{port}{base_path}/healthz"

                try:
                    start_time = asyncio.get_event_loop().time()
                    await client.get(url, timeout=5.0)
                    end_time = asyncio.get_event_loop().time()

                    response_time = end_time - start_time
                    assert response_time < 2.0, (
                        f"{service_name} responded too slowly: {response_time:.2f}s"
                    )
                    print(f"⚡ {service_name}: {response_time:.3f}s response time")
                except httpx.ConnectError:
                    pytest.skip(f"{service_name} not accessible - services may not be running")


class TestSpellCheckerServiceHealth:
    """Test suite for validating Kafka-based Spell Checker Service health."""

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_spell_checker_metrics_endpoint(self):
        """Test that Spell Checker Service metrics endpoint is accessible."""
        async with httpx.AsyncClient() as client:
            # Spell Checker runs metrics on port 8002
            url = "http://localhost:8002/metrics"
            try:
                response = await client.get(url, timeout=5.0)
                assert response.status_code == 200, "Spell Checker metrics endpoint failed"

                metrics_text = response.text
                assert "kafka_message_queue_latency_seconds" in metrics_text, (
                    "Missing Kafka queue latency metric"
                )
                print(f"📊 spell_checker_service: {response.status_code} - Kafka metrics available")

            except httpx.ConnectError:
                pytest.skip(
                    "Spell Checker Service metrics server not running (worker-only service)"
                )
            except Exception as e:
                pytest.fail(f"Spell Checker metrics test failed: {e}")


# TODO: Add container integration tests
# TODO: Add end-to-end workflow tests
# TODO: Add service dependency validation
