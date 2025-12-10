"""
Functional Tests for BFF Teacher Dashboard Endpoint

Tests the BFF Teacher Service dashboard endpoint with real backend services
(RAS, CMS) running via docker-compose.

Requires:
- `pdm run dev-start` to start the full service stack
- BFF Teacher Service running on port 4101
- RAS running on port 4003
- CMS running on port 5002

Validates:
- End-to-end data aggregation from RAS and CMS
- Authentication header requirements (X-User-ID)
- Correlation ID propagation
- Error handling for unauthenticated requests
"""

from __future__ import annotations

import uuid
from typing import Any

import aiohttp
import pytest

from tests.utils.service_test_manager import ServiceTestManager


class TestBFFTeacherDashboardFunctional:
    """Functional tests for BFF Teacher dashboard endpoint.

    These tests require the full docker-compose stack to be running.
    They validate HTTP communication across BFF → RAS and BFF → CMS.
    """

    BFF_BASE_URL = "http://localhost:4101"
    DASHBOARD_ENDPOINT = "/bff/v1/teacher/dashboard"

    @pytest.fixture
    async def service_manager(self) -> ServiceTestManager:
        """Get ServiceTestManager for service validation."""
        return ServiceTestManager()

    @pytest.fixture
    async def _validated_services(self, service_manager: ServiceTestManager) -> dict[str, Any]:
        """Ensure BFF, RAS, and CMS services are running and healthy.

        This fixture validates that all required backend services are available
        before running tests. Tests are skipped if services are not running.
        """
        endpoints = await service_manager.get_validated_endpoints()

        # BFF depends on RAS and CMS
        required_services = ["result_aggregator_service", "class_management_service"]
        for service in required_services:
            if service not in endpoints:
                pytest.skip(f"{service} not available - run 'pdm run dev-start'")

        # Check BFF health directly since it may not be in standard service list
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self.BFF_BASE_URL}/healthz",
                    timeout=aiohttp.ClientTimeout(total=5.0),
                ) as response:
                    if response.status != 200:
                        pytest.skip("BFF Teacher Service not healthy - run 'pdm run dev-start'")
            except aiohttp.ClientError:
                pytest.skip("BFF Teacher Service not available - run 'pdm run dev-start'")

        return endpoints

    @pytest.mark.functional
    @pytest.mark.asyncio
    async def test_dashboard_requires_authentication(
        self,
        _validated_services: dict[str, Any],
    ) -> None:
        """Test that dashboard endpoint rejects requests without X-User-ID header.

        Validates:
        - Returns 401 Unauthorized without authentication header
        - Error response contains proper HuleEdu error structure
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.BFF_BASE_URL}{self.DASHBOARD_ENDPOINT}",
                timeout=aiohttp.ClientTimeout(total=10.0),
                headers={
                    "X-Correlation-ID": str(uuid.uuid4()),
                },
            ) as response:
                assert response.status == 401, f"Expected 401, got {response.status}"
                data = await response.json()
                assert "error" in data
                assert data["error"]["code"] == "AUTHENTICATION_ERROR"

    @pytest.mark.functional
    @pytest.mark.asyncio
    async def test_dashboard_with_valid_user_id(
        self,
        _validated_services: dict[str, Any],
    ) -> None:
        """Test dashboard endpoint returns valid response with X-User-ID header.

        Validates:
        - Returns 200 OK with valid authentication
        - Response contains expected dashboard structure (batches, total_count)
        - New/unknown user gets empty batches list (not error)
        """
        test_user_id = f"functional-test-user-{uuid.uuid4()}"

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.BFF_BASE_URL}{self.DASHBOARD_ENDPOINT}",
                timeout=aiohttp.ClientTimeout(total=10.0),
                headers={
                    "X-User-ID": test_user_id,
                    "X-Correlation-ID": str(uuid.uuid4()),
                },
            ) as response:
                assert response.status == 200, f"Expected 200, got {response.status}"
                data = await response.json()

                # Validate response structure
                assert "batches" in data
                assert "total_count" in data
                assert isinstance(data["batches"], list)
                assert isinstance(data["total_count"], int)

                # New user should have no batches
                assert data["total_count"] == 0
                assert len(data["batches"]) == 0

    @pytest.mark.functional
    @pytest.mark.asyncio
    async def test_dashboard_returns_correlation_id(
        self,
        _validated_services: dict[str, Any],
    ) -> None:
        """Test that dashboard response includes correlation ID header.

        Validates:
        - Response includes X-Correlation-ID header
        - Correlation ID matches the one sent in request
        """
        test_user_id = f"functional-test-user-{uuid.uuid4()}"
        request_correlation_id = str(uuid.uuid4())

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.BFF_BASE_URL}{self.DASHBOARD_ENDPOINT}",
                timeout=aiohttp.ClientTimeout(total=10.0),
                headers={
                    "X-User-ID": test_user_id,
                    "X-Correlation-ID": request_correlation_id,
                },
            ) as response:
                assert response.status == 200

                # Check correlation ID is returned and matches
                response_correlation_id = response.headers.get("X-Correlation-ID")
                assert response_correlation_id is not None
                assert response_correlation_id == request_correlation_id

    @pytest.mark.functional
    @pytest.mark.asyncio
    async def test_health_endpoint(
        self,
        _validated_services: dict[str, Any],
    ) -> None:
        """Test BFF health endpoint returns proper status.

        Validates:
        - Health endpoint returns 200
        - Response includes service name and status fields
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.BFF_BASE_URL}/healthz",
                timeout=aiohttp.ClientTimeout(total=5.0),
            ) as response:
                assert response.status == 200
                data = await response.json()

                assert data["service"] == "bff_teacher_service"
                assert data["status"] in ["healthy", "degraded"]
