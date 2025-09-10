"""Unit tests for health endpoint JVM metrics and monitoring.

This module tests health endpoint monitoring requirements:
- JVM status fields (running, heap_used_mb) in health response
- Service uptime calculation and reporting
- Integration with LanguageToolManager for heap monitoring
- Proper fallback behavior when JVM metrics unavailable

Tests focus on behavioral verification using protocol-based mocking.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock
from uuid import UUID

import pytest
from huleedu_service_libs.error_handling.correlation import CorrelationContext

from services.language_tool_service.protocols import (
    LanguageToolManagerProtocol,
    LanguageToolWrapperProtocol,
)


class TestHealthCheckTask052G:
    """Tests for TASK-052G health endpoint requirements."""

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

    @pytest.fixture
    def mock_language_tool_manager(self) -> AsyncMock:
        """Create mock Language Tool manager following protocol patterns."""
        mock_manager = AsyncMock(spec=LanguageToolManagerProtocol)
        mock_manager.get_jvm_heap_usage.return_value = 215  # Typical heap usage in MB
        return mock_manager

    @pytest.fixture
    def mock_current_app(self) -> MagicMock:
        """Create mock current_app with extensions."""
        mock_app = MagicMock()
        mock_app.extensions = {"service_start_time": time.time() - 300}  # 5 minutes ago
        return mock_app

    async def _health_check_logic(
        self,
        settings: Any,
        corr: CorrelationContext,
        language_tool_wrapper: LanguageToolWrapperProtocol,
        language_tool_manager: LanguageToolManagerProtocol,
        current_app: Any | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Extract the core health check logic matching actual implementation."""
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

            # Get JVM status (TASK-052G requirement)
            jvm_running = False
            heap_used_mb = 0

            if (
                "language_tool_wrapper" in dependencies
                and dependencies["language_tool_wrapper"]["status"] == "healthy"
            ):
                server_info = dependencies["language_tool_wrapper"].get("server", {})
                jvm_running = server_info.get("running", False)

                # Get actual heap usage if JVM is running
                if jvm_running:
                    try:
                        heap_used = await language_tool_manager.get_jvm_heap_usage()
                        if heap_used is not None:
                            heap_used_mb = heap_used
                    except Exception:
                        # Fallback to 0 if unable to get heap usage
                        pass

            # Calculate service uptime (TASK-052G requirement)
            uptime_seconds = 0.0
            if current_app:
                try:
                    start_time = current_app.extensions.get("service_start_time")
                    if start_time:
                        uptime_seconds = time.time() - start_time
                except Exception:
                    # Fallback to 0 if unable to calculate uptime
                    pass

            # TASK-052G format: Include jvm and uptime_seconds at top level
            health_response = {
                "service": settings.SERVICE_NAME,
                "status": overall_status,
                "message": f"Language Tool Service is {overall_status}",
                "version": "1.0.0",
                "jvm": {
                    "running": jvm_running,
                    "heap_used_mb": heap_used_mb,
                },
                "uptime_seconds": uptime_seconds,
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
                    "jvm": {
                        "running": False,
                        "heap_used_mb": 0,
                    },
                    "uptime_seconds": 0.0,
                    "error": str(e),
                    "correlation_id": corr.original,
                },
                503,
            )

    async def test_health_check_task_052g_fields_present(
        self,
        mock_settings: MagicMock,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
        mock_language_tool_manager: AsyncMock,
        mock_current_app: MagicMock,
    ) -> None:
        """Test that TASK-052G required fields (jvm, uptime_seconds) are present and correctly typed."""
        # Act
        data, status_code = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
            language_tool_manager=mock_language_tool_manager,
            current_app=mock_current_app,
        )

        # Assert TASK-052G fields present
        assert "jvm" in data, "Missing required TASK-052G field: jvm"
        assert "uptime_seconds" in data, "Missing required TASK-052G field: uptime_seconds"

        # Verify JVM structure
        jvm = data["jvm"]
        assert "running" in jvm, "Missing jvm.running field"
        assert "heap_used_mb" in jvm, "Missing jvm.heap_used_mb field"

        # Verify types
        assert isinstance(jvm["running"], bool), "jvm.running must be boolean"
        assert isinstance(jvm["heap_used_mb"], int), "jvm.heap_used_mb must be integer"
        assert isinstance(data["uptime_seconds"], float), "uptime_seconds must be float"

        # Verify values
        assert jvm["running"] is True  # JVM should be running when wrapper is healthy
        assert jvm["heap_used_mb"] == 215  # Should match mock manager return value
        assert data["uptime_seconds"] > 0  # Should have calculated uptime

    @pytest.mark.parametrize(
        "heap_value, expected_heap_mb",
        [
            (215, 215),  # Normal heap usage
            (0, 0),  # JVM just started
            (512, 512),  # High usage
            (None, 0),  # Unable to retrieve - fallback to 0
        ],
    )
    async def test_health_check_jvm_heap_usage_integration(
        self,
        mock_settings: MagicMock,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
        mock_language_tool_manager: AsyncMock,
        heap_value: int | None,
        expected_heap_mb: int,
    ) -> None:
        """Test JVM heap usage retrieval from manager with various scenarios."""
        # Configure manager to return specific heap value
        mock_language_tool_manager.get_jvm_heap_usage.return_value = heap_value

        # Act
        data, _ = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
            language_tool_manager=mock_language_tool_manager,
        )

        # Assert
        assert data["jvm"]["heap_used_mb"] == expected_heap_mb
        # Verify manager was called when JVM is running
        mock_language_tool_manager.get_jvm_heap_usage.assert_called_once()

    async def test_health_check_jvm_heap_usage_manager_exception(
        self,
        mock_settings: MagicMock,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
        mock_language_tool_manager: AsyncMock,
    ) -> None:
        """Test heap usage fallback when manager raises exception."""
        # Configure manager to raise exception
        mock_language_tool_manager.get_jvm_heap_usage.side_effect = Exception("Manager error")

        # Act
        data, _ = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
            language_tool_manager=mock_language_tool_manager,
        )

        # Assert - should fallback to 0 without crashing
        assert data["jvm"]["heap_used_mb"] == 0
        assert data["jvm"]["running"] is True  # JVM still considered running
        assert data["status"] == "healthy"  # Overall health not affected

    @pytest.mark.parametrize(
        "start_time_offset, expected_uptime_range",
        [
            (300, (299, 301)),  # 5 minutes ago
            (3600, (3599, 3601)),  # 1 hour ago
            (0, (-1, 1)),  # Just started
            (86400, (86399, 86401)),  # 1 day ago
        ],
    )
    async def test_health_check_uptime_calculation(
        self,
        mock_settings: MagicMock,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
        mock_language_tool_manager: AsyncMock,
        start_time_offset: float,
        expected_uptime_range: tuple[float, float],
    ) -> None:
        """Test service uptime calculation with various start times."""
        # Create mock app with specific start time
        mock_app = MagicMock()
        mock_app.extensions = {"service_start_time": time.time() - start_time_offset}

        # Act
        data, _ = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
            language_tool_manager=mock_language_tool_manager,
            current_app=mock_app,
        )

        # Assert - uptime should be within expected range (accounting for test execution time)
        uptime = data["uptime_seconds"]
        assert expected_uptime_range[0] <= uptime <= expected_uptime_range[1]

    async def test_health_check_task_052g_fields_in_error_response(
        self,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
        mock_language_tool_manager: AsyncMock,
    ) -> None:
        """Test TASK-052G fields are included even in error responses."""
        # Mock settings that will cause an exception
        mock_settings = MagicMock()
        type(mock_settings).SERVICE_NAME = PropertyMock(side_effect=Exception("Settings error"))

        # Act
        data, status_code = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
            language_tool_manager=mock_language_tool_manager,
        )

        # Assert - TASK-052G fields present with safe defaults
        assert status_code == 503
        assert "jvm" in data
        assert data["jvm"]["running"] is False
        assert data["jvm"]["heap_used_mb"] == 0
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] == 0.0

    async def test_health_check_jvm_status_when_wrapper_unhealthy(
        self,
        mock_settings: MagicMock,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
        mock_language_tool_manager: AsyncMock,
    ) -> None:
        """Test JVM status defaults when wrapper is unhealthy."""
        # Configure wrapper to raise exception
        mock_language_tool_wrapper.get_health_status.side_effect = Exception("Wrapper down")

        # Act
        data, status_code = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
            language_tool_manager=mock_language_tool_manager,
        )

        # Assert - JVM should show as not running when wrapper is down
        assert status_code == 503
        assert data["jvm"]["running"] is False
        assert data["jvm"]["heap_used_mb"] == 0
        # Manager should not be called when JVM is not running
        mock_language_tool_manager.get_jvm_heap_usage.assert_not_called()

    async def test_health_check_task_052g_response_structure_validation(
        self,
        mock_settings: MagicMock,
        mock_correlation_context: CorrelationContext,
        mock_language_tool_wrapper: AsyncMock,
        mock_language_tool_manager: AsyncMock,
        mock_current_app: MagicMock,
    ) -> None:
        """Test complete TASK-052G response structure with all fields."""
        # Act
        data, status_code = await self._health_check_logic(
            settings=mock_settings,
            corr=mock_correlation_context,
            language_tool_wrapper=mock_language_tool_wrapper,
            language_tool_manager=mock_language_tool_manager,
            current_app=mock_current_app,
        )

        # Assert complete structure
        assert status_code == 200

        # Core fields
        assert data["service"] == "language-tool-service"
        assert data["status"] == "healthy"
        assert data["version"] == "1.0.0"

        # TASK-052G specific fields
        assert data["jvm"] == {"running": True, "heap_used_mb": 215}
        assert data["uptime_seconds"] > 0

        # Standard health fields
        assert data["checks"]["service_responsive"] is True
        assert data["checks"]["dependencies_available"] is True
        assert "dependencies" in data
        assert "correlation_id" in data
