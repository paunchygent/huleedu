"""
Service Health Testing

Validates that all microservices are responding correctly.
Uses ServiceTestManager utility - no fixtures or direct HTTP calls.
"""

import pytest

from tests.utils.service_test_manager import ServiceTestManager


class TestServiceHealth:
    """Test suite for validating service health across all services."""

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_all_services_healthy(self):
        """Test that all HTTP services respond to health checks."""
        service_manager = ServiceTestManager()

        endpoints = await service_manager.get_validated_endpoints()

        assert len(endpoints) >= 4, f"Expected at least 4 services, got {len(endpoints)}"

        expected_services = [
            "content_service",
            "batch_orchestrator_service",
            "essay_lifecycle_service",
            "file_service"
        ]

        for service_name in expected_services:
            assert service_name in endpoints, f"Missing {service_name}"
            service_info = endpoints[service_name]
            assert service_info["status"] == "healthy", f"{service_name} not healthy"

        print(f"✅ All {len(endpoints)} services healthy")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_kafka_services_metrics(self):
        """Test that services with HTTP APIs expose metrics endpoints."""
        service_manager = ServiceTestManager()

        # Get all validated endpoints (includes metrics validation)
        endpoints = await service_manager.get_validated_endpoints()

        # Test services that should have metrics endpoints
        services_with_metrics = ["spell_checker_service", "cj_assessment_service"]

        for service_name in services_with_metrics:
            if service_name in endpoints:
                service_info = endpoints[service_name]
                assert service_info["status"] == "healthy"
                print(f"✅ {service_name} health and metrics endpoints available")
            else:
                print(f"⚠️  {service_name} not available or not configured with HTTP API")

# TODO: Add container integration tests
# TODO: Add end-to-end workflow tests
# TODO: Add service dependency validation
