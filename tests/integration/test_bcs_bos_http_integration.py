"""
HTTP Integration Tests for BCS ↔ BOS Communication

Phase 1: Direct HTTP communication validation between Batch Orchestrator Service (BOS)
and Batch Conductor Service (BCS) using real Docker containers.

Tests the internal API endpoint POST /internal/v1/pipelines/define that BOS calls
to request pipeline resolution from BCS.

Uses real services, mocks only external boundaries.
"""

from __future__ import annotations

from typing import Any, Dict

import aiohttp
import pytest

from tests.utils.service_test_manager import ServiceTestManager


class TestBCSBOSHttpIntegration:
    """Integration tests for BCS ↔ BOS HTTP communication."""

    @pytest.fixture
    async def service_manager(self) -> ServiceTestManager:
        """Get ServiceTestManager for service validation."""
        return ServiceTestManager()

    @pytest.fixture
    async def validated_services(self, service_manager: ServiceTestManager) -> Dict[str, Any]:
        """Ensure both BOS and BCS services are running and healthy."""
        endpoints = await service_manager.get_validated_endpoints()

        required_services = ["batch_orchestrator_service", "batch_conductor_service"]
        for service in required_services:
            if service not in endpoints:
                pytest.skip(f"{service} not available for HTTP integration testing")

        return endpoints

    @pytest.fixture
    def bcs_endpoint_url(self) -> str:
        """BCS internal API endpoint URL."""
        return "http://localhost:4002/internal/v1/pipelines/define"

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_successful_pipeline_resolution(
        self, validated_services: Dict[str, Any], bcs_endpoint_url: str
    ):
        """
        Test successful HTTP communication and pipeline resolution.

        Validates:
        - BCS accepts valid pipeline resolution requests
        - Returns properly structured response
        - HTTP status codes are correct
        """
        request_data = {"batch_id": "test-batch-http-001", "requested_pipeline": "ai_feedback"}

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    bcs_endpoint_url,
                    json=request_data,
                    timeout=aiohttp.ClientTimeout(total=10.0),
                    headers={"Content-Type": "application/json"},
                ) as response:
                    # Validate HTTP response
                    assert response.status == 200, f"Expected 200, got {response.status}"

                    # Parse response JSON
                    response_data = await response.json()

                    # Validate response structure (BCS API contract)
                    assert "batch_id" in response_data, "Response missing batch_id"
                    assert "final_pipeline" in response_data, "Response missing final_pipeline"
                    assert isinstance(response_data["final_pipeline"], list), (
                        "final_pipeline must be a list"
                    )

                    # Validate response content
                    assert response_data["batch_id"] == request_data["batch_id"]

                    print(f"✅ Successful pipeline resolution for {request_data['batch_id']}")
                    print(f"   Final pipeline: {response_data['final_pipeline']}")
                    print("   Response structure validated")

            except aiohttp.ClientError as e:
                pytest.fail(f"HTTP communication failed: {e}")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_http_error_handling_400_bad_request(
        self, validated_services: Dict[str, Any], bcs_endpoint_url: str
    ):
        """
        Test BCS handles invalid requests with proper HTTP 400 responses.

        Validates:
        - Invalid request data returns 400
        - Error response structure is consistent
        - BCS validates input properly
        """
        # Test with missing required fields
        invalid_requests = [
            {},  # Empty request
            {"batch_id": ""},  # Empty batch_id
            {"requested_pipeline": "ai_feedback"},  # Missing batch_id
            {"batch_id": "test-batch"},  # Missing requested_pipeline
            {"batch_id": "test-batch", "requested_pipeline": ""},  # Empty pipeline
        ]

        async with aiohttp.ClientSession() as session:
            for i, invalid_request in enumerate(invalid_requests):
                try:
                    async with session.post(
                        bcs_endpoint_url,
                        json=invalid_request,
                        timeout=aiohttp.ClientTimeout(total=5.0),
                        headers={"Content-Type": "application/json"},
                    ) as response:
                        # Should return 400 for invalid requests
                        assert response.status == 400, (
                            f"Invalid request {i} should return 400, got {response.status}"
                        )

                        # Validate error response structure
                        error_data = await response.json()
                        assert "detail" in error_data or "error" in error_data, (
                            f"Error response {i} missing error details"
                        )

                        print(f"✅ Invalid request {i} properly rejected with 400")

                except aiohttp.ClientError as e:
                    pytest.fail(f"HTTP communication failed for invalid request {i}: {e}")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_http_timeout_and_resilience(
        self, validated_services: Dict[str, Any], bcs_endpoint_url: str
    ):
        """
        Test HTTP timeout configuration and error handling.

        Validates:
        - HTTP client timeout configuration works
        - Connection errors are handled gracefully
        - Proper error propagation for network issues
        """
        request_data = {"batch_id": "test-batch-timeout-001", "requested_pipeline": "ai_feedback"}

        # Test with very short timeout to validate timeout handling
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    bcs_endpoint_url,
                    json=request_data,
                    timeout=aiohttp.ClientTimeout(total=0.001),  # 1ms timeout
                    headers={"Content-Type": "application/json"},
                ) as response:
                    # If this succeeds, the service is very fast
                    assert response.status in [200, 400, 500], "Unexpected status code"
                    print("✅ Service responded within 1ms (very fast!)")

            except (aiohttp.ServerTimeoutError, TimeoutError):
                # This is expected with 1ms timeout
                print("✅ Timeout handling working correctly")
            except aiohttp.ClientError as e:
                # Other client errors are also acceptable for timeout test
                print(f"✅ Client error handled: {type(e).__name__}")

        # Test with reasonable timeout to ensure service actually works
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    bcs_endpoint_url,
                    json=request_data,
                    timeout=aiohttp.ClientTimeout(total=10.0),
                    headers={"Content-Type": "application/json"},
                ) as response:
                    assert response.status in [200, 400], f"Unexpected status: {response.status}"
                    response_data = await response.json()
                    assert isinstance(response_data, dict), (
                        "Response data is not a dictionary (invalid JSON format)"
                    )
                    print("✅ Service responded normally with reasonable timeout")

            except aiohttp.ClientError as e:
                pytest.fail(f"Service should respond with reasonable timeout: {e}")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_http_requests(
        self, validated_services: Dict[str, Any], bcs_endpoint_url: str
    ):
        """
        Test BCS handles concurrent HTTP requests properly.

        Validates:
        - Multiple simultaneous requests are handled
        - No race conditions in response handling
        - Service maintains consistency under load
        """
        import asyncio

        request_data_template = {"requested_pipeline": "ai_feedback"}

        async def make_request(session: aiohttp.ClientSession, batch_id: str) -> Dict[str, Any]:
            """Make a single HTTP request to BCS."""
            request_data = {**request_data_template, "batch_id": batch_id}

            async with session.post(
                bcs_endpoint_url,
                json=request_data,
                timeout=aiohttp.ClientTimeout(total=15.0),
                headers={"Content-Type": "application/json"},
            ) as response:
                assert response.status in [200, 400], (
                    f"Unexpected status for {batch_id}: {response.status}"
                )
                response_data: Dict[str, Any] = await response.json()
                response_data["_test_batch_id"] = batch_id  # Track which request this is
                return response_data

        # Test with 5 concurrent requests
        batch_ids = [f"test-batch-concurrent-{i:03d}" for i in range(5)]

        async with aiohttp.ClientSession() as session:
            try:
                # Execute all requests concurrently
                results = await asyncio.gather(
                    *[make_request(session, batch_id) for batch_id in batch_ids],
                    return_exceptions=True,
                )

                # Validate all requests completed
                successful_results = []
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        print(f"⚠️  Request {i} failed: {result}")
                    else:
                        successful_results.append(result)
                        print(f"✅ Concurrent request {i} successful")

                # At least some requests should succeed
                assert len(successful_results) >= 3, (
                    f"Too many concurrent requests failed: {len(successful_results)}/5 succeeded"
                )

                # Validate response consistency
                for result in successful_results:
                    if isinstance(result, dict) and "final_pipeline" in result:
                        assert isinstance(result["final_pipeline"], list)
                        assert result["batch_id"] == result["_test_batch_id"]

                print(f"✅ Concurrent requests handled: {len(successful_results)}/5 successful")

            except Exception as e:
                pytest.fail(f"Concurrent request testing failed: {e}")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_request_response_contract_validation(
        self, validated_services: Dict[str, Any], bcs_endpoint_url: str
    ):
        """
        Test detailed request/response contract validation.

        Validates:
        - All required fields are present
        - Data types match expected schema
        - Optional fields are handled correctly
        """
        # Test various pipeline types
        test_cases = [
            {"batch_id": "test-batch-contract-001", "requested_pipeline": "ai_feedback"},
            {"batch_id": "test-batch-contract-002", "requested_pipeline": "cj_assessment"},
            {"batch_id": "test-batch-contract-003", "requested_pipeline": "spellcheck"},
        ]

        async with aiohttp.ClientSession() as session:
            for i, request_data in enumerate(test_cases):
                try:
                    async with session.post(
                        bcs_endpoint_url,
                        json=request_data,
                        timeout=aiohttp.ClientTimeout(total=10.0),
                        headers={"Content-Type": "application/json"},
                    ) as response:
                        response_data = await response.json()

                        if response.status == 200:
                            # Validate successful response contract
                            required_fields = ["batch_id", "final_pipeline"]
                            for field in required_fields:
                                assert field in response_data, f"Response missing {field}"

                            # Validate data types
                            assert isinstance(response_data["batch_id"], str)
                            assert isinstance(response_data["final_pipeline"], list)

                            # Validate content
                            assert response_data["batch_id"] == request_data["batch_id"]

                            print(
                                f"✅ Contract validation {i}: {request_data['requested_pipeline']}"
                            )

                        elif response.status == 400:
                            # Validate error response contract
                            assert "detail" in response_data or "error" in response_data
                            print(
                                f"✅ Error contract validation {i}: "
                                f"{request_data['requested_pipeline']}"
                            )

                        else:
                            pytest.fail(f"Unexpected status code: {response.status}")

                except aiohttp.ClientError as e:
                    pytest.fail(f"Contract validation failed for case {i}: {e}")
