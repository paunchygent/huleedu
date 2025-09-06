"""Unit tests for health endpoints following Rule 075 behavioral testing methodology.

This module tests health endpoint behavior including:
- Health check endpoint (/healthz) returns with proper status codes
- Database health component validation and response formatting
- Kafka consumer health component validation and response formatting
- Combined health status calculation and HTTP response codes
- Metrics endpoint (/metrics) Prometheus format responses
- Error handling scenarios and structured response formats
- Swedish error message formatting where applicable

Tests focus on actual endpoint behavior and response validation,
using protocol-based mocking with AsyncMock for comprehensive coverage.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from huleedu_service_libs.quart_app import HuleEduApp
from prometheus_client import CONTENT_TYPE_LATEST
from quart.typing import TestClientProtocol as QuartTestClient

from services.entitlements_service.api.health_routes import health_bp
from services.entitlements_service.kafka_consumer import EntitlementsKafkaConsumer


class TestHealthEndpoints:
    """Tests for health endpoint behavioral responses."""

    @pytest.fixture
    def mock_health_checker(self) -> AsyncMock:
        """Create mock health checker for database health validation."""
        mock_checker = AsyncMock()
        mock_checker.get_health_summary.return_value = {"status": "healthy"}
        return mock_checker

    @pytest.fixture
    def mock_kafka_consumer(self) -> AsyncMock:
        """Create mock Kafka consumer following protocol patterns."""
        mock_consumer = AsyncMock(spec=EntitlementsKafkaConsumer)
        return mock_consumer

    @pytest.fixture
    def mock_consumer_task(self) -> MagicMock:
        """Create mock consumer task for health status validation."""
        mock_task = MagicMock()
        mock_task.done.return_value = False  # Task is running
        return mock_task

    @pytest.fixture
    async def test_app(
        self,
        mock_health_checker: AsyncMock,
        mock_kafka_consumer: AsyncMock,
        mock_consumer_task: MagicMock,
    ) -> AsyncGenerator[HuleEduApp, None]:
        """Create test application with mocked health components."""
        app = HuleEduApp(__name__)
        app.config["TESTING"] = True

        # Register health blueprint
        app.register_blueprint(health_bp)

        # Mock health checker in extensions
        app.extensions = {"health_checker": mock_health_checker}

        # Mock Kafka consumer and task
        app.kafka_consumer = mock_kafka_consumer
        app.consumer_task = mock_consumer_task

        yield app

    @pytest.fixture
    async def test_client(self, test_app: HuleEduApp) -> AsyncGenerator[QuartTestClient, None]:
        """Create test client for endpoint testing."""
        async with test_app.test_client() as client:
            yield client

    @pytest.mark.parametrize(
        "db_status, kafka_task_done, expected_status, expected_code",
        [
            # All components healthy -> 200 OK
            ("healthy", False, "healthy", 200),
            # Database healthy, Kafka running -> 200 OK
            ("warning", False, "healthy", 200),  # Warning still counts as healthy
            # Database unhealthy, Kafka running -> 503 Service Unavailable
            ("unhealthy", False, "unhealthy", 503),
            # Database healthy, Kafka task completed/failed -> 503 Service Unavailable
            ("healthy", True, "unhealthy", 503),
            # Both components unhealthy -> 503 Service Unavailable
            ("unhealthy", True, "unhealthy", 503),
        ],
    )
    async def test_health_check_component_status_combinations(
        self,
        test_client: QuartTestClient,
        test_app: HuleEduApp,
        mock_health_checker: AsyncMock,
        mock_consumer_task: MagicMock,
        db_status: str,
        kafka_task_done: bool,
        expected_status: str,
        expected_code: int,
    ) -> None:
        """Test health check endpoint with different component status combinations."""
        # Configure mock responses
        mock_health_checker.get_health_summary.return_value = {"status": db_status}
        mock_consumer_task.done.return_value = kafka_task_done

        response = await test_client.get("/healthz")

        assert response.status_code == expected_code

        data = await response.get_json()
        assert data["status"] == expected_status
        assert data["service"] == "entitlements_service"
        assert "checks" in data
        assert "database" in data["checks"]
        assert "kafka_consumer" in data["checks"]

    async def test_health_check_database_healthy_response_format(
        self, test_client: QuartTestClient, mock_health_checker: AsyncMock
    ) -> None:
        """Test health check returns properly formatted database health information."""
        mock_health_checker.get_health_summary.return_value = {"status": "healthy"}

        response = await test_client.get("/healthz")
        data = await response.get_json()

        db_check = data["checks"]["database"]
        assert db_check["status"] == "healthy"
        assert db_check["message"] == "Database connection healthy"

    async def test_health_check_database_unhealthy_response_format(
        self, test_client: QuartTestClient, mock_health_checker: AsyncMock
    ) -> None:
        """Test health check returns properly formatted database unhealthy information."""
        mock_health_checker.get_health_summary.return_value = {"status": "error"}

        response = await test_client.get("/healthz")
        data = await response.get_json()

        db_check = data["checks"]["database"]
        assert db_check["status"] == "unhealthy"
        assert db_check["message"] == "Database connection unhealthy"

    async def test_health_check_kafka_consumer_healthy_response_format(
        self, test_client: QuartTestClient, mock_consumer_task: MagicMock
    ) -> None:
        """Test health check returns properly formatted Kafka consumer health information."""
        mock_consumer_task.done.return_value = False

        response = await test_client.get("/healthz")
        data = await response.get_json()

        kafka_check = data["checks"]["kafka_consumer"]
        assert kafka_check["status"] == "healthy"
        assert kafka_check["message"] == "Kafka consumer running"

    async def test_health_check_kafka_consumer_unhealthy_response_format(
        self, test_client: QuartTestClient, mock_consumer_task: MagicMock
    ) -> None:
        """Test health check returns properly formatted Kafka consumer unhealthy information."""
        mock_consumer_task.done.return_value = True

        response = await test_client.get("/healthz")
        data = await response.get_json()

        kafka_check = data["checks"]["kafka_consumer"]
        assert kafka_check["status"] == "unhealthy"
        assert kafka_check["message"] == "Kafka consumer task completed or failed"

    async def test_health_check_missing_health_checker_extension(
        self, test_client: QuartTestClient, test_app: HuleEduApp
    ) -> None:
        """Test health check behavior when health checker extension is missing."""
        # Remove health checker from extensions
        test_app.extensions = {}

        response = await test_client.get("/healthz")
        data = await response.get_json()

        assert response.status_code == 503  # Should be unhealthy
        db_check = data["checks"]["database"]
        assert db_check["status"] == "unhealthy"
        assert db_check["message"] == "Health checker not initialized"

    async def test_health_check_missing_kafka_consumer(
        self, test_client: QuartTestClient, test_app: HuleEduApp
    ) -> None:
        """Test health check behavior when Kafka consumer is not initialized."""
        # Remove kafka consumer
        test_app.kafka_consumer = None

        response = await test_client.get("/healthz")
        data = await response.get_json()

        assert response.status_code == 503  # Should be unhealthy
        kafka_check = data["checks"]["kafka_consumer"]
        assert kafka_check["status"] == "unhealthy"
        assert kafka_check["message"] == "Kafka consumer not initialized"

    async def test_health_check_health_checker_exception_handling(
        self, test_client: QuartTestClient, mock_health_checker: AsyncMock
    ) -> None:
        """Test health check handles health checker exceptions appropriately."""
        error_message = "Database connection failed"
        mock_health_checker.get_health_summary.side_effect = Exception(error_message)

        response = await test_client.get("/healthz")
        data = await response.get_json()

        assert response.status_code == 503
        db_check = data["checks"]["database"]
        assert db_check["status"] == "unhealthy"
        assert f"Health check failed: {error_message}" in db_check["message"]

    async def test_health_check_kafka_consumer_exception_handling(
        self, test_client: QuartTestClient, test_app: HuleEduApp
    ) -> None:
        """Test health check handles Kafka consumer attribute access exceptions."""
        # Mock hasattr to raise exception
        original_hasattr = hasattr

        def mock_hasattr(obj: Any, name: str) -> bool:
            if name == "kafka_consumer":
                raise Exception("Kafka consumer access failed")
            return original_hasattr(obj, name)

        import builtins

        builtins.hasattr = mock_hasattr  # type: ignore[assignment]

        try:
            response = await test_client.get("/healthz")
            data = await response.get_json()

            assert response.status_code == 503
            kafka_check = data["checks"]["kafka_consumer"]
            assert kafka_check["status"] == "unhealthy"
            assert "Kafka consumer health check failed" in kafka_check["message"]
        finally:
            builtins.hasattr = original_hasattr  # type: ignore[assignment]

    @pytest.mark.parametrize(
        "db_healthy, kafka_healthy, expected_overall",
        [
            (True, True, "healthy"),
            (True, False, "unhealthy"),
            (False, True, "unhealthy"),
            (False, False, "unhealthy"),
        ],
    )
    async def test_health_check_overall_status_calculation(
        self,
        test_client: QuartTestClient,
        mock_health_checker: AsyncMock,
        mock_consumer_task: MagicMock,
        db_healthy: bool,
        kafka_healthy: bool,
        expected_overall: str,
    ) -> None:
        """Test overall health status calculation logic."""
        # Configure database health
        db_status = "healthy" if db_healthy else "error"
        mock_health_checker.get_health_summary.return_value = {"status": db_status}

        # Configure Kafka health (task done means unhealthy)
        mock_consumer_task.done.return_value = not kafka_healthy

        response = await test_client.get("/healthz")
        data = await response.get_json()

        assert data["status"] == expected_overall

    async def test_metrics_endpoint_successful_response(self, test_client: QuartTestClient) -> None:
        """Test metrics endpoint returns Prometheus formatted metrics successfully."""
        response = await test_client.get("/metrics")

        assert response.status_code == 200
        # Check that it starts with the expected Prometheus content type
        assert response.content_type.startswith(CONTENT_TYPE_LATEST.split(";")[0])

        # Response should contain Prometheus metrics data
        data = await response.get_data()
        assert data is not None
        assert len(data) > 0

    async def test_metrics_endpoint_error_handling(
        self, test_client: QuartTestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test metrics endpoint handles generation errors appropriately."""

        # Mock generate_latest to raise exception
        def mock_generate_latest() -> bytes:
            raise Exception("Prometheus metrics generation failed")

        monkeypatch.setattr(
            "services.entitlements_service.api.health_routes.generate_latest", mock_generate_latest
        )

        response = await test_client.get("/metrics")

        assert response.status_code == 500
        assert response.content_type.startswith("text/plain")

        data = await response.get_data()
        assert b"Error generating metrics" in data

    async def test_health_check_response_structure_validation(
        self, test_client: QuartTestClient
    ) -> None:
        """Test health check response contains all required fields and structure."""
        response = await test_client.get("/healthz")
        data = await response.get_json()

        # Validate top-level structure
        required_fields = ["status", "service", "checks"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate service name
        assert data["service"] == "entitlements_service"

        # Validate checks structure
        checks = data["checks"]
        required_check_components = ["database", "kafka_consumer"]
        for component in required_check_components:
            assert component in checks, f"Missing health check component: {component}"

            # Each component should have status and message
            component_check = checks[component]
            assert "status" in component_check
            assert "message" in component_check
            assert component_check["status"] in ["healthy", "unhealthy"]
            assert isinstance(component_check["message"], str)

    async def test_health_check_database_warning_state_as_healthy(
        self,
        test_client: QuartTestClient,
        mock_health_checker: AsyncMock,
    ) -> None:
        """Test database warning state is treated as healthy for overall status."""
        mock_health_checker.get_health_summary.return_value = {"status": "warning"}

        response = await test_client.get("/healthz")
        data = await response.get_json()

        # Warning state should be treated as healthy for overall calculation
        assert data["checks"]["database"]["status"] == "healthy"
        assert response.status_code == 200
        assert data["status"] == "healthy"

    @pytest.mark.parametrize(
        "unhealthy_status",
        ["degraded", "partial", "error", "critical"],
    )
    async def test_health_check_database_unhealthy_states(
        self,
        test_client: QuartTestClient,
        mock_health_checker: AsyncMock,
        unhealthy_status: str,
    ) -> None:
        """Test database non-healthy/non-warning states are treated as unhealthy."""
        mock_health_checker.get_health_summary.return_value = {"status": unhealthy_status}

        response = await test_client.get("/healthz")
        data = await response.get_json()

        # Non-healthy/non-warning states should be unhealthy
        assert data["checks"]["database"]["status"] == "unhealthy"
        assert response.status_code == 503
        assert data["status"] == "unhealthy"

    async def test_health_check_content_type_json(self, test_client: QuartTestClient) -> None:
        """Test health check endpoint returns proper JSON content type."""
        response = await test_client.get("/healthz")

        assert response.content_type == "application/json"
        # Verify the response is valid JSON
        data = await response.get_json()
        assert isinstance(data, dict)
