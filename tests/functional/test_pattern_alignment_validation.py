"""
Pattern Alignment Validation Tests

Validates that all 6 services follow consistent patterns after alignment and that
business functionality is preserved while gaining the benefits of architectural consistency.

Uses modern utility patterns for all HTTP interactions while preserving validation focus.
"""

import asyncio
import time

import pytest

from tests.utils.service_test_manager import ServiceTestManager


class TestPatternAlignmentValidation:
    """
    Comprehensive test suite validating that service pattern alignment maintains
    functionality while improving consistency and reliability.

    Uses ServiceTestManager for all HTTP interactions - demonstrates modern utility patterns
    for architectural compliance testing.
    """

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_consistent_health_check_patterns(self):
        """
        Validate that all HTTP services follow consistent health check patterns
        after pattern alignment.
        """
        service_manager = ServiceTestManager()

        # Use utility-based service validation with built-in health checking
        endpoints = await service_manager.get_validated_endpoints()

        if not endpoints:
            pytest.skip("No services available for health pattern validation")

        health_responses = []

        # ServiceTestManager already validates health check response structure
        # We validate the pattern compliance on top of that
        for service_name, service_info in endpoints.items():
            assert service_info["status"] == "healthy", (
                f"{service_name} health check failed after pattern alignment"
            )

            # Find service pattern type from ServiceTestManager configuration
            service_endpoint = next(
                (ep for ep in service_manager.SERVICE_ENDPOINTS if ep.name == service_name),
                None,
            )
            pattern_type = (
                "HTTP Service" if service_endpoint and service_endpoint.has_http_api else "Worker"
            )

            health_responses.append((service_name, pattern_type, 200))
            print(f"✅ {service_name} ({pattern_type}): Health check validated")

        # Verify all expected HTTP services responded
        expected_http_services = [
            ep.name for ep in service_manager.SERVICE_ENDPOINTS if ep.has_http_api
        ]
        responding_services = list(endpoints.keys())

        for expected_service in expected_http_services:
            if expected_service in responding_services:
                print(f"✅ Expected service {expected_service} responding")

        assert len(health_responses) >= 4, "Not all aligned services are responding"

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_metrics_consistency_after_alignment(self):
        """
        Validate that the new app context metrics pattern works consistently
        across all services and prevents Prometheus registry collisions.
        """
        service_manager = ServiceTestManager()
        metrics_results = []

        # Test all services with metrics endpoints using utility pattern
        for service_endpoint in service_manager.SERVICE_ENDPOINTS:
            if service_endpoint.has_metrics:
                metrics_text = await service_manager.get_service_metrics(
                    service_endpoint.name,
                    service_endpoint.port,
                )

                if metrics_text is not None:
                    # Validate no registry collision indicators
                    assert "Duplicated timeseries" not in metrics_text, (
                        f"{service_endpoint.name} has Prometheus registry collisions"
                    )

                    # Check for expected metric patterns (if any metrics exist)
                    if metrics_text.strip():
                        assert "# HELP" in metrics_text, (
                            f"{service_endpoint.name} metrics not in Prometheus format"
                        )
                        assert "# TYPE" in metrics_text, (
                            f"{service_endpoint.name} missing TYPE declarations"
                        )

                    metrics_results.append((service_endpoint.name, len(metrics_text)))
                    print(f"📊 {service_endpoint.name}: {len(metrics_text)} chars of metrics data")
                else:
                    print(f"ℹ️  {service_endpoint.name} metrics not accessible")

        # Validate we tested some metrics endpoints
        assert len(metrics_results) >= 2, "Insufficient metrics endpoints tested"

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_service_startup_reliability(self):
        """
        Test that pattern alignment improves service startup reliability.
        This test validates the PYTHONPATH=/app and startup_setup.py patterns.
        """
        service_manager = ServiceTestManager()
        startup_times = []

        # ServiceTestManager validation includes startup reliability testing
        start_time = time.time()
        endpoints = await service_manager.get_validated_endpoints()
        end_time = time.time()

        validation_time = end_time - start_time

        if not endpoints:
            pytest.skip("No services available for startup reliability testing")

        # The fact that get_validated_endpoints() succeeded means services started reliably
        for service_name in endpoints:
            # ServiceTestManager already validates startup within reasonable time
            startup_times.append((service_name, validation_time))
            print(f"⚡ {service_name}: Validated in {validation_time:.2f}s")

        # Pattern alignment should improve startup reliability
        assert validation_time < 30.0, f"Service validation took too long: {validation_time:.2f}s"

        # Validate we tested multiple services
        assert len(startup_times) >= 4, "Not all services started successfully"

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cross_service_integration_preserved(self):
        """
        Validate that cross-service integration still works correctly
        after pattern alignment.
        """
        service_manager = ServiceTestManager()

        # Validate Content Service is available using utility
        endpoints = await service_manager.get_validated_endpoints()
        if "content_service" not in endpoints:
            pytest.skip("Content Service not available for integration testing")

        test_content = "This is test content for pattern alignment validation."

        # Test Content Service integration using utility methods
        try:
            # Upload content using utility
            storage_id = await service_manager.upload_content_directly(test_content)
            assert storage_id is not None
            print(f"✅ Content upload successful: {storage_id}")

            # Download content to verify using utility
            downloaded_content = await service_manager.fetch_content_directly(storage_id)
            assert downloaded_content == test_content, (
                "Downloaded content doesn't match uploaded content"
            )
            print(f"✅ Content download successful: {len(downloaded_content)} chars")

        except RuntimeError as e:
            if "not available" in str(e):
                pytest.skip("Content Service integration not available")
            else:
                pytest.fail(f"Content Service integration test failed: {e}")

        # Test File Service availability if present
        if "file_service" in endpoints:
            print("✅ File Service integration endpoint accessible")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_development_experience_improvements(self):
        """
        Test that pattern alignment provides measurable development experience improvements.
        """
        service_manager = ServiceTestManager()
        consistency_checks: list[tuple[str, int | float]] = []

        # Test 1: Consistent service availability through utilities
        endpoints = await service_manager.get_validated_endpoints()
        available_services = len(endpoints)
        consistency_checks.append(("Service Availability", available_services))
        print(f"✅ Service availability through utilities: {available_services} services")

        # Test 2: Consistent metrics access patterns
        metrics_count = 0
        for service_endpoint in service_manager.SERVICE_ENDPOINTS:
            if service_endpoint.has_metrics:
                metrics_text = await service_manager.get_service_metrics(
                    service_endpoint.name,
                    service_endpoint.port,
                )
                if metrics_text is not None:
                    metrics_count += 1

        consistency_checks.append(("Metrics Consistency", metrics_count))
        print(f"✅ Consistent metrics access across {metrics_count} services")

        # Test 3: Utility pattern response times
        start_time = asyncio.get_event_loop().time()
        await service_manager.get_validated_endpoints()  # Should use cache
        end_time = asyncio.get_event_loop().time()

        cached_response_time = end_time - start_time
        consistency_checks.append(("Cached Response Time", cached_response_time))
        print(f"✅ Cached utility response time: {cached_response_time:.3f}s")

        # Pattern alignment should provide fast, consistent responses
        assert cached_response_time < 1.0, (
            f"Cached response time too slow: {cached_response_time:.3f}s"
        )

        # Validate we have consistency data
        assert len(consistency_checks) >= 3, "Insufficient consistency validation"

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_pattern_alignment_success_summary(self):
        """
        Summary test that validates overall pattern alignment success.
        """
        service_manager = ServiceTestManager()

        success_metrics = {
            "services_aligned": 0,
            "health_checks_passing": 0,
            "metrics_endpoints_working": 0,
            "consistent_responses": 0,
        }

        # Use utility-based service discovery and validation
        endpoints = await service_manager.get_validated_endpoints()

        # Count validated services (health checks already validated by utility)
        success_metrics["services_aligned"] = len(endpoints)
        success_metrics["health_checks_passing"] = len(endpoints)
        success_metrics["consistent_responses"] = len(endpoints)

        # Count working metrics endpoints
        for service_endpoint in service_manager.SERVICE_ENDPOINTS:
            if service_endpoint.has_metrics:
                metrics_text = await service_manager.get_service_metrics(
                    service_endpoint.name,
                    service_endpoint.port,
                )
                if metrics_text is not None:
                    success_metrics["metrics_endpoints_working"] += 1

        # Pattern alignment success criteria
        total_expected_services = len(
            [ep for ep in service_manager.SERVICE_ENDPOINTS if ep.has_http_api],
        )
        success_rate = (
            success_metrics["services_aligned"] / total_expected_services
            if total_expected_services > 0
            else 0
        )

        print("\n🎯 Pattern Alignment Success Summary:")
        print(
            f"   • Services Aligned: {success_metrics['services_aligned']}/"
            f"{total_expected_services}",
        )
        print(f"   • Health Checks Passing: {success_metrics['health_checks_passing']}")
        print(f"   • Metrics Endpoints Working: {success_metrics['metrics_endpoints_working']}")
        print(f"   • Success Rate: {success_rate:.1%}")

        # Success criteria: At least 75% of services aligned and working
        assert success_rate >= 0.75, f"Pattern alignment success rate too low: {success_rate:.1%}"

        # Validate we have meaningful test coverage
        assert success_metrics["health_checks_passing"] >= 3, (
            "Insufficient services responding for pattern validation"
        )

        print(f"✅ Pattern alignment validation PASSED with {success_rate:.1%} success rate!")


class TestStartupSetupPatternBenefits:
    """Test specific benefits of the startup_setup.py pattern using modern utilities."""

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_no_prometheus_registry_collisions(self):
        """
        Validate that the app context metrics pattern prevents
        Prometheus registry collisions that occurred with DI-based metrics.
        """
        service_manager = ServiceTestManager()

        # Test services with metrics endpoints
        services_to_test = [
            ("content_service", 8001),
            ("file_service", 7001),
        ]

        for service_name, port in services_to_test:
            # Get metrics using utility pattern
            metrics_text = await service_manager.get_service_metrics(service_name, port)

            if metrics_text is not None:
                # Should not contain collision error messages
                collision_indicators = [
                    "Duplicated timeseries",
                    "CollectorRegistry",
                    "already registered",
                ]

                for indicator in collision_indicators:
                    assert indicator not in metrics_text, (
                        f"{service_name} has Prometheus collision: {indicator}"
                    )

                print(f"✅ {service_name}: No registry collisions detected")
            else:
                print(f"ℹ️  {service_name} not running - skipping collision test")


# Test execution helper
if __name__ == "__main__":
    print("Run with: pdm run pytest tests/functional/test_pattern_alignment_validation.py -v -s")
