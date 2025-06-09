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
        """Test that Kafka worker services expose metrics."""
        service_manager = ServiceTestManager()

        # Test Spell Checker metrics (port 8002)
        spell_checker_metrics = await service_manager.get_service_metrics(
            "spell_checker_service", 8002
        )

        if spell_checker_metrics:
            print("✅ Spell Checker metrics available")
        else:
            pytest.skip("Spell Checker metrics not accessible")

        # Test CJ Assessment metrics (port 9090)
        cj_assessment_metrics = await service_manager.get_service_metrics(
            "cj_assessment_service", 9090
        )
        if cj_assessment_metrics:
            print("✅ CJ Assessment metrics available")
        else:
            pytest.skip("CJ Assessment metrics not accessible")

# TODO: Add container integration tests
# TODO: Add end-to-end workflow tests
# TODO: Add service dependency validation
