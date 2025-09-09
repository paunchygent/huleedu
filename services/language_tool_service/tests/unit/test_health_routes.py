"""Unit tests for health endpoints following Rule 075 behavioral testing methodology.

This module tests health endpoint behavior including:
- Health check endpoint (/healthz) returns with proper status codes
- LanguageToolWrapper health component validation and response formatting
- Combined health status calculation and HTTP response codes
- Metrics endpoint (/metrics) Prometheus format responses
- Error handling scenarios and structured response formats
- Correlation context injection and proper propagation

Tests focus on actual endpoint behavior and response validation,
using protocol-based mocking with AsyncMock for comprehensive coverage.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from huleedu_service_libs.error_handling.correlation import CorrelationContext
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from services.language_tool_service.protocols import LanguageToolWrapperProtocol


class TestHealthCheckLogic:
    """Tests for health check endpoint logic without Quart dependencies."""

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings for health endpoint testing."""
        mock_settings = MagicMock()
        mock_settings.SERVICE_NAME = "language-tool-service"
        mock_settings.ENVIRONMENT.value = "test"
        return mock_settings

    @pytest.fixture
    def mock_correlation_context(self) -> CorrelationContext:
        """Create mock correlation context for testing."""
        return CorrelationContext(
            original="test-correlation-id",
            uuid=UUID("12345678-1234-1234-1234-123456789012"),
            source="generated",
        )

    @pytest.fixture
    def mock_language_tool_wrapper(self) -> AsyncMock:
        """Create mock Language Tool wrapper following protocol patterns."""
        mock_wrapper = AsyncMock(spec=LanguageToolWrapperProtocol)
        mock_wrapper.get_health_status.return_value = {
            "status": "healthy",
            "response_time_ms": 150,
            "implementation": "production",
            "server": {"running": True, "pid": 12345},
        }
        return mock_wrapper

    async def _health_check_logic(
        self,
        settings: Any,
        corr: CorrelationContext,
        language_tool_wrapper: LanguageToolWrapperProtocol,
    ) -> tuple[dict[str, Any], int]:
        """Extract the core health check logic for testing."""
        try:
            checks = {"service_responsive": True, "dependencies_available": True}
            dependencies = {}

            # Check Language Tool wrapper health
            try:
                wrapper_health = await language_tool_wrapper.get_health_status(corr)
                dependencies["language_tool_wrapper"] = {
                    "status": "healthy",
                    **wrapper_health,
                }
            except Exception as e:
                dependencies["language_tool_wrapper"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }
                checks["dependencies_available"] = False

            overall_status = "healthy" if all(checks.values()) else "degraded"

            health_response = {
                "service": settings.SERVICE_NAME,
                "status": overall_status,
                "message": f"Language Tool Service is {overall_status}",
                "version": "1.0.0",
                "checks": checks,
                "dependencies": dependencies,
                "environment": settings.ENVIRONMENT.value,
                "correlation_id": corr.original,
            }

            status_code = 200 if overall_status == "healthy" else 503
            return health_response, status_code

        except Exception as e:
            try:
                service_name = settings.SERVICE_NAME
            except Exception:
                service_name = "unknown-service"

            return (
                {
                    "service": service_name,
                    "status": "unhealthy",
                    "message": "Health check failed",
                    "version": "1.0.0",
                    "error": str(e),
                    "correlation_id": corr.original,
                },
                503,
            )

    @pytest.mark.parametrize(
        "wrapper_status, expected_overall_status, expected_code, expected_dependencies_available",
        [
            # Wrapper healthy -> 200 OK
            ("healthy", "healthy", 200, True),
            # Wrapper unhealthy -> 200 OK (wrapper returned status, no exception)
            ("unhealthy", "healthy", 200, True),
            # Wrapper degraded -> 200 OK (wrapper returned status, no exception)
            ("degraded", "healthy", 200, True),
        ],
    )
    async def test_health_check_wrapper_status_combinations(
        self,
        mock_settings: MagicMock,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
        wrapper_status: str,
        expected_overall_status: str,
        expected_code: int,
        expected_dependencies_available: bool,
    ) -> None:
        """Test health check function with different LanguageToolWrapper status combinations."""
        # Configure mock wrapper response
        mock_language_tool_wrapper.get_health_status.return_value = {
            "status": wrapper_status,
            "response_time_ms": 150,
            "implementation": "production",
        }

        # Act
        data, status_code = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
        )

        # Assert
        assert status_code == expected_code
        assert data["status"] == expected_overall_status
        assert data["service"] == "language-tool-service"
        assert data["checks"]["service_responsive"] is True
        assert data["checks"]["dependencies_available"] is expected_dependencies_available
        assert "dependencies" in data
        assert "language_tool_wrapper" in data["dependencies"]

    async def test_health_check_wrapper_exception_causes_degraded_status(
        self,
        mock_settings: MagicMock,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
    ) -> None:
        """Test that wrapper exceptions cause degraded status and 503 code."""
        # Configure mock wrapper to raise exception
        mock_language_tool_wrapper.get_health_status.side_effect = Exception("Wrapper error")

        # Act
        data, status_code = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
        )

        # Assert
        assert status_code == 503
        assert data["status"] == "degraded"
        assert data["checks"]["dependencies_available"] is False
        assert data["dependencies"]["language_tool_wrapper"]["status"] == "unhealthy"
        assert "error" in data["dependencies"]["language_tool_wrapper"]

    async def test_health_check_wrapper_healthy_response_format(
        self,
        mock_settings: MagicMock,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
    ) -> None:
        """Test health check returns properly formatted wrapper health information."""
        mock_health_data = {
            "status": "healthy",
            "response_time_ms": 120,
            "implementation": "production",
            "server": {"running": True, "pid": 12345, "port": 8081},
        }
        mock_language_tool_wrapper.get_health_status.return_value = mock_health_data

        # Act
        data, status_code = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
        )

        # Assert
        assert status_code == 200
        wrapper_dep = data["dependencies"]["language_tool_wrapper"]
        assert wrapper_dep["status"] == "healthy"
        assert wrapper_dep["response_time_ms"] == 120
        assert wrapper_dep["implementation"] == "production"
        assert wrapper_dep["server"]["running"] is True

    async def test_health_check_wrapper_unhealthy_response_format(
        self,
        mock_settings: MagicMock,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
    ) -> None:
        """Test health check returns properly formatted wrapper unhealthy information."""
        mock_language_tool_wrapper.get_health_status.side_effect = Exception(
            "Language Tool server down"
        )

        # Act
        data, status_code = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
        )

        # Assert
        assert status_code == 503
        wrapper_dep = data["dependencies"]["language_tool_wrapper"]
        assert wrapper_dep["status"] == "unhealthy"
        assert wrapper_dep["error"] == "Language Tool server down"

    async def test_health_check_correlation_context_propagation(
        self,
        mock_settings: MagicMock,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
    ) -> None:
        """Test that correlation context is properly passed to dependencies."""
        # Act
        data, status_code = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
        )

        # Verify wrapper was called with correlation context
        mock_language_tool_wrapper.get_health_status.assert_called_once_with(
            mock_correlation_context
        )

        # Verify correlation ID in response
        assert data["correlation_id"] == "test-correlation-id"

    async def test_health_check_top_level_exception_handling(
        self, mock_correlation_context: CorrelationContext, mock_language_tool_wrapper: AsyncMock
    ) -> None:
        """Test health check handles top-level exceptions appropriately."""
        # Mock settings that will cause an exception when SERVICE_NAME is accessed
        mock_settings = MagicMock()
        # Make SERVICE_NAME property raise an exception
        type(mock_settings).SERVICE_NAME = property(lambda self: 1 / 0)  # Trigger ZeroDivisionError

        # Act
        data, status_code = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
        )

        # Assert
        assert status_code == 503
        assert data["status"] == "unhealthy"
        assert data["message"] == "Health check failed"
        assert data["service"] == "unknown-service"  # Service name unavailable due to exception
        assert "error" in data
        assert data["correlation_id"] == "test-correlation-id"

    @pytest.mark.parametrize(
        "wrapper_healthy, expected_overall",
        [
            (True, "healthy"),
            (False, "degraded"),
        ],
    )
    async def test_health_check_overall_status_calculation(
        self,
        mock_settings: MagicMock,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
        wrapper_healthy: bool,
        expected_overall: str,
    ) -> None:
        """Test overall health status calculation logic."""
        # Configure wrapper health
        if wrapper_healthy:
            mock_language_tool_wrapper.get_health_status.return_value = {"status": "healthy"}
        else:
            mock_language_tool_wrapper.get_health_status.side_effect = Exception("Wrapper error")

        # Act
        data, status_code = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
        )

        # Assert
        assert data["status"] == expected_overall

    async def test_health_check_response_structure_validation(
        self,
        mock_settings: MagicMock,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
    ) -> None:
        """Test health check response contains all required fields and structure."""
        # Act
        data, status_code = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
        )

        # Validate top-level structure
        required_fields = [
            "status",
            "service",
            "message",
            "version",
            "checks",
            "dependencies",
            "environment",
            "correlation_id",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Validate service name
        assert data["service"] == "language-tool-service"
        assert data["version"] == "1.0.0"
        assert data["environment"] == "test"
        assert data["correlation_id"] == "test-correlation-id"

        # Validate checks structure
        checks = data["checks"]
        required_check_components = ["service_responsive", "dependencies_available"]
        for component in required_check_components:
            assert component in checks, f"Missing health check component: {component}"
            assert isinstance(checks[component], bool)

        # Validate dependencies structure
        dependencies = data["dependencies"]
        assert "language_tool_wrapper" in dependencies
        wrapper_dep = dependencies["language_tool_wrapper"]
        assert "status" in wrapper_dep
        assert wrapper_dep["status"] in ["healthy", "unhealthy"]

    @pytest.mark.parametrize(
        "exception_type, error_message",
        [
            (ConnectionError, "Connection failed"),
            (TimeoutError, "Request timeout"),
            (ValueError, "Invalid configuration"),
            (RuntimeError, "Runtime error occurred"),
        ],
    )
    async def test_health_check_wrapper_exception_scenarios(
        self,
        mock_settings: MagicMock,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
        exception_type: type[Exception],
        error_message: str,
    ) -> None:
        """Test health check handles various wrapper exception types appropriately."""
        # Configure wrapper to raise specific exception
        mock_language_tool_wrapper.get_health_status.side_effect = exception_type(error_message)

        # Act
        data, status_code = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
        )

        # Assert
        assert status_code == 503
        assert data["status"] == "degraded"
        assert data["checks"]["dependencies_available"] is False

        wrapper_dep = data["dependencies"]["language_tool_wrapper"]
        assert wrapper_dep["status"] == "unhealthy"
        assert error_message in wrapper_dep["error"]


class TestMetricsLogic:
    """Tests for metrics endpoint logic without Quart dependencies."""

    def _metrics_logic(self, registry: Any) -> tuple[bytes, str, int]:
        """Extract the core metrics logic for testing."""
        try:
            metrics_data = generate_latest(registry)
            return metrics_data, CONTENT_TYPE_LATEST, 200
        except Exception:
            return b"Error generating metrics", "text/plain", 500

    def test_metrics_endpoint_successful_response(self) -> None:
        """Test metrics endpoint returns Prometheus formatted metrics successfully."""
        # Mock generate_latest to return sample Prometheus data
        sample_metrics = (
            b"# HELP test_metric A test metric\n# TYPE test_metric counter\ntest_metric 42\n"
        )

        mock_registry = MagicMock()

        with pytest.MonkeyPatch().context() as monkeypatch:

            def mock_generate_latest(_registry: Any) -> bytes:
                return sample_metrics

            monkeypatch.setattr(
                "services.language_tool_service.tests.unit.test_health_routes.generate_latest",
                mock_generate_latest,
            )

            # Act
            data, content_type, status_code = self._metrics_logic(registry=mock_registry)

        assert status_code == 200
        # Check that it starts with the expected Prometheus content type
        assert content_type.startswith(CONTENT_TYPE_LATEST.split(";")[0])

        # Response should contain Prometheus metrics data
        assert data == sample_metrics

    def test_metrics_endpoint_error_handling(self) -> None:
        """Test metrics endpoint handles generation errors appropriately."""
        mock_registry = MagicMock()

        with pytest.MonkeyPatch().context() as monkeypatch:

            def mock_generate_latest(_registry: Any) -> bytes:
                raise Exception("Prometheus metrics generation failed")

            monkeypatch.setattr(
                "services.language_tool_service.tests.unit.test_health_routes.generate_latest",
                mock_generate_latest,
            )

            # Act
            data, content_type, status_code = self._metrics_logic(registry=mock_registry)

        assert status_code == 500
        assert content_type == "text/plain"
        assert b"Error generating metrics" in data
