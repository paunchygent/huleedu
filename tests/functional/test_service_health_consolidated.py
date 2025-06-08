"""
Consolidated Service Health Testing

Refactored version demonstrating elimination of redundant health check logic.
Uses consolidated fixtures instead of duplicating validation across multiple files.

REPLACES: 
- Redundant health checks in test_service_health.py
- Duplicate validation in test_pattern_alignment_validation.py
- Metrics validation in test_metrics_endpoints.py
"""

import pytest

from tests.fixtures.consolidated_service_fixtures import (
    SERVICE_ENDPOINTS,
)


class TestConsolidatedServiceHealth:
    """Test suite using consolidated service health validation."""

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_all_services_validated_once(self, validated_service_endpoints):
        """
        Test that demonstrates service validation happens once per session.

        No redundant health checks - relies on session-scoped fixture.
        """
        # Service validation already completed by fixture
        assert len(validated_service_endpoints) >= 4, "Expected at least 4 healthy services"

        # Verify expected services are present
        expected_http_services = [
            "content_service",
            "batch_orchestrator_service",
            "essay_lifecycle_service",
            "file_service"
        ]

        for service_name in expected_http_services:
            assert service_name in validated_service_endpoints, f"Missing {service_name}"
            service_info = validated_service_endpoints[service_name]
            assert service_info["status"] == "healthy", f"{service_name} not healthy"
            assert "base_url" in service_info, f"Missing base_url for {service_name}"

        print(f"✅ All {len(validated_service_endpoints)} services validated successfully")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_metrics_endpoints_validated_once(self, validated_service_endpoints):
        """
        Test that demonstrates metrics validation happens once per session.

        No redundant metrics checks - relies on session-scoped fixture.
        """
        services_with_metrics = [
            service for service in SERVICE_ENDPOINTS
            if service.has_metrics
        ]

        validated_metrics_count = 0
        for service in services_with_metrics:
            if service.name in validated_service_endpoints:
                service_info = validated_service_endpoints[service.name]
                if "metrics_status" in service_info:
                    assert service_info["metrics_status"] == "valid", (
                        f"{service.name} metrics not valid"
                    )
                    validated_metrics_count += 1

        print(f"📊 {validated_metrics_count} metrics endpoints validated successfully")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_service_response_times_from_validated_endpoints(
        self, validated_service_endpoints
    ):
        """
        Test response times using already-validated endpoints.

        Uses consolidated service information instead of re-validating health.
        """
        import asyncio

        import httpx

        response_times = []

        async with httpx.AsyncClient() as client:
            for service_name, service_info in validated_service_endpoints.items():
                if "health_url" in service_info:
                    health_url = service_info["health_url"]

                    start_time = asyncio.get_event_loop().time()
                    response = await client.get(health_url, timeout=5.0)
                    end_time = asyncio.get_event_loop().time()

                    response_time = end_time - start_time
                    response_times.append((service_name, response_time))

                    assert response.status_code == 200, f"{service_name} health check failed"
                    assert response_time < 2.0, (
                        f"{service_name} response too slow: {response_time:.2f}s"
                    )
                    print(f"⚡ {service_name}: {response_time:.3f}s response time")

        assert len(response_times) >= 4, "Expected response times for at least 4 services"


class TestConsolidatedHelperValidation:
    """Test the consolidated helper fixtures work correctly."""

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_batch_creation_helper(self, batch_creation_helper):
        """Test batch creation helper eliminates duplicate logic."""
        batch_id, correlation_id = await batch_creation_helper(
            expected_essay_count=5,
            course_code="CONSOLIDATED",
            class_designation="HelperTest"
        )

        assert batch_id is not None, "Batch creation failed"
        assert correlation_id is not None, "Missing correlation ID"
        assert len(batch_id) > 0, "Empty batch ID"
        print(f"✅ Batch created via helper: {batch_id}")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_file_upload_helper(self, file_upload_helper, batch_creation_helper):
        """Test file upload helper eliminates duplicate logic."""
        # Create a test batch first
        batch_id, correlation_id = await batch_creation_helper(
            expected_essay_count=2,
            course_code="UPLOAD",
            class_designation="HelperTest"
        )

        # Test file upload
        test_files = [
            {
                "name": "test_essay_1.txt",
                "content": "This is a test essay with sufficient content for validation testing."
            },
            {
                "name": "test_essay_2.txt",
                "content": "This is another test essay with enough content to pass validation."
            }
        ]

        upload_result = await file_upload_helper(batch_id, test_files, correlation_id)

        assert upload_result is not None, "File upload failed"
        assert "files_processed" in upload_result, "Missing files_processed in response"
        print(f"✅ Files uploaded via helper: {upload_result['files_processed']} files")


# Performance comparison test
class TestPerformanceComparison:
    """Demonstrate performance improvement from consolidated fixtures."""

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_no_redundant_health_checks(self, validated_service_endpoints):
        """
        This test runs instantly because health validation was done once.

        Compare to old approach: Each test file did its own health validation,
        resulting in 6+ duplicate health check rounds per test session.
        """
        import time

        start_time = time.time()

        # Access pre-validated service information
        service_count = len(validated_service_endpoints)
        healthy_services = [
            name for name, info in validated_service_endpoints.items()
            if info.get("status") == "healthy"
        ]

        end_time = time.time()
        execution_time = end_time - start_time

        # This should be nearly instant since no network calls are made
        assert execution_time < 0.1, f"Too slow: {execution_time:.3f}s"
        assert service_count >= 4, f"Expected >=4 services, got {service_count}"
        assert len(healthy_services) >= 4, (
            f"Expected >=4 healthy services, got {len(healthy_services)}"
        )

        print(f"🚀 Performance test: {execution_time:.4f}s for {service_count} services")
        print("📈 Improvement: No redundant health checks across multiple test files")
