"""
Pattern Alignment Validation Tests

Validates that all 6 services follow consistent patterns after alignment and that
business functionality is preserved while gaining the benefits of architectural consistency.
"""

import asyncio
import time

import httpx
import pytest


class TestPatternAlignmentValidation:
    """
    Comprehensive test suite validating that service pattern alignment maintains
    functionality while improving consistency and reliability.
    """

    # All HTTP services with their pattern compliance status
    ALIGNED_SERVICES = [
        ("content_service", 8001, "BOS Pattern"),
        ("batch_orchestrator_service", 5001, "BOS Reference"),
        ("essay_lifecycle_service", 6001, "BOS Pattern"),
        ("file_service", 7001, "BOS Pattern"),
    ]

    WORKER_SERVICES = [
        ("spell_checker_service", 8002, "Worker Pattern"),
        ("cj_assessment_service", None, "Worker Pattern"),  # No metrics endpoint
    ]

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_consistent_health_check_patterns(self):
        """
        Validate that all HTTP services follow consistent health check patterns
        after pattern alignment.
        """
        async with httpx.AsyncClient() as client:
            health_responses = []

            for service_name, port, pattern_type in self.ALIGNED_SERVICES:
                url = f"http://localhost:{port}/healthz"
                try:
                    response = await client.get(url, timeout=10.0)
                    response_data = response.json()

                    # Pattern validation
                    assert response.status_code == 200, (
                        f"{service_name} health check failed after pattern alignment"
                    )

                    # Consistent response structure validation
                    assert "status" in response_data, (
                        f"{service_name} missing 'status' field in health response"
                    )
                    assert "message" in response_data, (
                        f"{service_name} missing 'message' field in health response"
                    )

                    health_responses.append((service_name, pattern_type, response.status_code))
                    print(f"✅ {service_name} ({pattern_type}): {response_data}")

                except httpx.ConnectError:
                    pytest.skip(f"{service_name} not running - start with docker compose up -d")
                except Exception as e:
                    pytest.fail(f"{service_name} health check failed: {e}")

            # Verify all services responded
            assert len(health_responses) >= 4, "Not all aligned services are responding"

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_metrics_consistency_after_alignment(self):
        """
        Validate that the new app context metrics pattern works consistently
        across all services and prevents Prometheus registry collisions.
        """
        async with httpx.AsyncClient() as client:
            metrics_results = []

            # Test HTTP services
            for service_name, port, pattern_type in self.ALIGNED_SERVICES:
                url = f"http://localhost:{port}/metrics"
                try:
                    response = await client.get(url, timeout=10.0)
                    assert response.status_code == 200, (
                        f"{service_name} metrics endpoint failed after alignment"
                    )

                    metrics_text = response.text

                    # Validate no registry collision indicators
                    assert "Duplicated timeseries" not in metrics_text, (
                        f"{service_name} has Prometheus registry collisions"
                    )

                    # Check for expected metric patterns (if any metrics exist)
                    if metrics_text.strip():
                        assert "# HELP" in metrics_text, (
                            f"{service_name} metrics not in Prometheus format"
                        )
                        assert "# TYPE" in metrics_text, f"{service_name} missing TYPE declarations"

                    metrics_results.append((service_name, len(metrics_text)))
                    print(f"📊 {service_name}: {len(metrics_text)} chars of metrics data")

                except httpx.ConnectError:
                    pytest.skip(f"{service_name} not accessible")
                except Exception as e:
                    pytest.fail(f"{service_name} metrics test failed: {e}")

            # Test worker service with metrics (spell checker)
            try:
                response = await client.get("http://localhost:8002/metrics", timeout=10.0)
                assert response.status_code == 200, "Spell Checker metrics failed"
                print(f"📊 spell_checker_service: {len(response.text)} chars of metrics data")
            except httpx.ConnectError:
                print("ℹ️  Spell Checker metrics server not running (optional)")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_service_startup_reliability(self):
        """
        Test that pattern alignment improves service startup reliability.
        This test validates the PYTHONPATH=/app and startup_setup.py patterns.
        """
        startup_times = []

        async with httpx.AsyncClient() as client:
            for service_name, port, pattern_type in self.ALIGNED_SERVICES:
                start_time = time.time()

                # Retry health check with timeout
                max_retries = 30  # 30 seconds max wait
                success = False

                for retry in range(max_retries):
                    try:
                        url = f"http://localhost:{port}/healthz"
                        response = await client.get(url, timeout=1.0)
                        if response.status_code == 200:
                            success = True
                            break
                    except (httpx.ConnectError, httpx.TimeoutException):
                        if retry < max_retries - 1:
                            await asyncio.sleep(1)
                        continue

                end_time = time.time()
                startup_time = end_time - start_time

                if success:
                    startup_times.append((service_name, startup_time))
                    print(f"⚡ {service_name}: Started in {startup_time:.2f}s")

                    # Pattern alignment should improve startup reliability
                    assert startup_time < 30.0, (
                        f"{service_name} startup took too long: {startup_time:.2f}s"
                    )
                else:
                    pytest.fail(f"{service_name} failed to start within 30 seconds")

            # Validate we tested all services
            assert len(startup_times) >= 4, "Not all services started successfully"

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cross_service_integration_preserved(self):
        """
        Validate that cross-service integration still works correctly
        after pattern alignment.
        """
        async with httpx.AsyncClient() as client:
            # Test Content Service storage functionality
            try:
                # Upload content
                upload_url = "http://localhost:8001/v1/content"
                test_content = "This is test content for pattern alignment validation."

                upload_response = await client.post(
                    upload_url, json={"content": test_content}, timeout=10.0
                )

                assert upload_response.status_code == 201, (
                    "Content Service upload failed after pattern alignment"
                )

                upload_data = upload_response.json()
                assert "storage_id" in upload_data, "Missing storage_id in upload response"
                storage_id = upload_data["storage_id"]

                print(f"✅ Content upload successful: {storage_id}")

                # Download content to verify
                download_url = f"http://localhost:8001/v1/content/{storage_id}"
                download_response = await client.get(download_url, timeout=10.0)

                assert download_response.status_code == 200, (
                    "Content Service download failed after pattern alignment"
                )

                downloaded_data = download_response.json()
                actual_content = downloaded_data.get("content", download_response.text)
                assert actual_content == test_content, (
                    "Downloaded content doesn't match uploaded content"
                )

                print(f"✅ Content download successful: {len(actual_content)} chars")

            except httpx.ConnectError:
                pytest.skip("Content Service not running")
            except Exception as e:
                pytest.fail(f"Content Service integration test failed: {e}")

            # Test File Service if available
            try:
                file_health_response = await client.get(
                    "http://localhost:7001/healthz", timeout=5.0
                )
                if file_health_response.status_code == 200:
                    print("✅ File Service integration endpoint accessible")
            except httpx.ConnectError:
                print("ℹ️  File Service not running for integration test")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_development_experience_improvements(self):
        """
        Test that pattern alignment provides measurable development experience improvements.
        """
        consistency_checks: list[tuple[str, int | float]] = []

        async with httpx.AsyncClient() as client:
            # Test 1: Consistent error response formats
            error_responses = []
            for service_name, port, pattern_type in self.ALIGNED_SERVICES:
                try:
                    # Request non-existent endpoint to trigger error
                    url = f"http://localhost:{port}/nonexistent"
                    response = await client.get(url, timeout=5.0)

                    # Record error response structure
                    error_responses.append((service_name, response.status_code))

                    # Services should have consistent error behavior
                    assert response.status_code in [404, 405, 500], (
                        f"{service_name} unexpected error response: {response.status_code}"
                    )

                except httpx.ConnectError:
                    continue

            consistency_checks.append(("Error Response Consistency", len(error_responses)))
            print(f"✅ Consistent error handling across {len(error_responses)} services")

            # Test 2: Consistent health check response times
            response_times = []
            for service_name, port, pattern_type in self.ALIGNED_SERVICES:
                try:
                    start_time = asyncio.get_event_loop().time()
                    await client.get(f"http://localhost:{port}/healthz", timeout=5.0)
                    end_time = asyncio.get_event_loop().time()

                    response_time = end_time - start_time
                    response_times.append(response_time)

                except httpx.ConnectError:
                    continue

            if response_times:
                avg_response_time = sum(response_times) / len(response_times)
                consistency_checks.append(("Average Response Time", avg_response_time))
                print(f"✅ Average health check response time: {avg_response_time:.3f}s")

                # Pattern alignment should provide consistent, fast responses
                assert avg_response_time < 1.0, (
                    f"Average response time too slow: {avg_response_time:.3f}s"
                )

        # Validate we have consistency data
        assert len(consistency_checks) >= 2, "Insufficient consistency validation"

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_pattern_alignment_success_summary(self):
        """
        Summary test that validates overall pattern alignment success.
        """
        success_metrics = {
            "services_aligned": 0,
            "health_checks_passing": 0,
            "metrics_endpoints_working": 0,
            "consistent_responses": 0,
        }

        async with httpx.AsyncClient() as client:
            # Count aligned services responding
            for service_name, port, pattern_type in self.ALIGNED_SERVICES:
                try:
                    health_response = await client.get(
                        f"http://localhost:{port}/healthz", timeout=5.0
                    )
                    if health_response.status_code == 200:
                        success_metrics["services_aligned"] += 1
                        success_metrics["health_checks_passing"] += 1
                        success_metrics["consistent_responses"] += 1

                    metrics_response = await client.get(
                        f"http://localhost:{port}/metrics", timeout=5.0
                    )
                    if metrics_response.status_code == 200:
                        success_metrics["metrics_endpoints_working"] += 1

                except httpx.ConnectError:
                    continue

        # Pattern alignment success criteria
        total_services = len(self.ALIGNED_SERVICES)
        success_rate = success_metrics["services_aligned"] / total_services

        print("\n🎯 Pattern Alignment Success Summary:")
        print(f"   • Services Aligned: {success_metrics['services_aligned']}/{total_services}")
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


# Additional focused tests for specific pattern benefits


class TestStartupSetupPatternBenefits:
    """Test specific benefits of the startup_setup.py pattern."""

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_no_prometheus_registry_collisions(self):
        """
        Validate that the app context metrics pattern prevents
        Prometheus registry collisions that occurred with DI-based metrics.
        """
        async with httpx.AsyncClient() as client:
            # Make multiple requests to trigger metrics creation
            services_to_test = [
                ("content_service", 8001),
                ("file_service", 7001),
            ]

            for service_name, port in services_to_test:
                try:
                    # Multiple requests to same endpoint
                    for i in range(5):
                        await client.get(f"http://localhost:{port}/healthz", timeout=5.0)

                    # Check metrics endpoint for collision indicators
                    metrics_response = await client.get(
                        f"http://localhost:{port}/metrics", timeout=5.0
                    )

                    if metrics_response.status_code == 200:
                        metrics_text = metrics_response.text

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

                except httpx.ConnectError:
                    print(f"ℹ️  {service_name} not running - skipping collision test")


# Test execution helper
if __name__ == "__main__":
    print("Run with: pdm run pytest tests/functional/test_pattern_alignment_validation.py -v -s")
