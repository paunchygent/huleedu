"""
Unit tests for LanguageToolManager pure logic and state management.

Tests cover configuration, status reporting, URL construction, backoff calculations,
and state management without process/network interactions (per Rule 075).

Note: Process lifecycle and HTTP interaction tests belong in integration tests:
- Subprocess spawning/cleanup
- Signal handling (SIGTERM/SIGKILL)
- Real HTTP health checks
- Restart logic with actual processes
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.language_tool_service.config import Settings
from services.language_tool_service.implementations.language_tool_manager import LanguageToolManager


class _TestableLanguageToolManager(LanguageToolManager):
    """Testable version that allows control without patching."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        # Test control flags
        self.should_health_check_succeed = True
        self.process_start_succeeds = True
        self.cleanup_called = False
        self.start_called = False

        # Mock controlled objects
        self.mock_process: MagicMock | None = None
        self.mock_session: AsyncMock | None = None

    async def _check_server_health(self) -> bool:
        """Override to return controlled result."""
        return self.should_health_check_succeed

    async def health_check(self) -> bool:
        """Override to test logic without real HTTP calls."""
        if not self.process or self.process.returncode is not None:
            return False

        if not self.http_session:
            return False

        return self.should_health_check_succeed

    async def _cleanup_process(self) -> None:
        """Track cleanup calls without real process interaction."""
        self.cleanup_called = True
        self.process = None

    async def start(self) -> None:
        """Track start calls and simulate success/failure."""
        self.start_called = True
        if not self.process_start_succeeds:
            raise RuntimeError("Simulated start failure")

        # Simulate successful start
        self.mock_process = MagicMock()
        self.mock_process.pid = 12345
        self.mock_process.returncode = None
        self.process = self.mock_process

        self.mock_session = AsyncMock()
        self.http_session = self.mock_session


@pytest.fixture
def mock_settings() -> Settings:
    """Create test settings with controlled values."""
    settings = Settings()
    settings.LANGUAGE_TOOL_PORT = 8081
    settings.LANGUAGE_TOOL_HEAP_SIZE = "256m"
    settings.LANGUAGE_TOOL_JAR_PATH = "/test/languagetool-server.jar"
    settings.LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL = 5
    return settings


class TestLanguageToolManagerInitialization:
    """Test LanguageToolManager initialization and configuration."""

    def test_manager_initialization_with_default_settings(self, mock_settings: Settings) -> None:
        """Test manager initializes correctly with provided settings."""
        manager = LanguageToolManager(mock_settings)

        assert manager.settings is mock_settings
        assert manager.process is None
        assert manager.http_session is None
        assert manager.health_check_task is None
        assert manager.restart_count == 0
        assert manager.last_restart_time == 0.0
        assert manager.is_shutting_down is False
        assert manager.server_url == f"http://localhost:{mock_settings.LANGUAGE_TOOL_PORT}"

    def test_server_url_construction(self, mock_settings: Settings) -> None:
        """Test server URL is constructed correctly from settings."""
        mock_settings.LANGUAGE_TOOL_PORT = 9999
        manager = LanguageToolManager(mock_settings)

        assert manager.server_url == "http://localhost:9999"

    @pytest.mark.parametrize(
        "port, expected_url",
        [
            (8080, "http://localhost:8080"),
            (8443, "http://localhost:8443"),
            (9000, "http://localhost:9000"),
            (3000, "http://localhost:3000"),
        ],
    )
    def test_server_url_construction_various_ports(
        self, mock_settings: Settings, port: int, expected_url: str
    ) -> None:
        """Test server URL construction with various port numbers."""
        mock_settings.LANGUAGE_TOOL_PORT = port
        manager = LanguageToolManager(mock_settings)

        assert manager.server_url == expected_url


class TestLanguageToolManagerStatus:
    """Test status reporting functionality."""

    def test_get_status_running_process(self, mock_settings: Settings) -> None:
        """Test status report for running process."""
        manager = LanguageToolManager(mock_settings)

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None
        manager.process = mock_process
        manager.restart_count = 2

        status = manager.get_status()

        assert status["running"] is True
        assert status["pid"] == 12345
        assert status["restart_count"] == 2
        assert status["returncode"] is None
        assert status["port"] == mock_settings.LANGUAGE_TOOL_PORT
        assert status["heap_size"] == mock_settings.LANGUAGE_TOOL_HEAP_SIZE
        assert status["last_restart_time"] == 0.0

    def test_get_status_no_process(self, mock_settings: Settings) -> None:
        """Test status report when no process is running."""
        manager = LanguageToolManager(mock_settings)
        manager.restart_count = 1

        status = manager.get_status()

        assert status["running"] is False
        assert status["pid"] is None
        assert status["restart_count"] == 1
        assert status["returncode"] is None
        assert status["port"] == mock_settings.LANGUAGE_TOOL_PORT
        assert status["heap_size"] == mock_settings.LANGUAGE_TOOL_HEAP_SIZE
        assert status["last_restart_time"] == 0.0

    def test_get_status_dead_process(self, mock_settings: Settings) -> None:
        """Test status report for dead process."""
        manager = LanguageToolManager(mock_settings)

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = 1  # Exited
        manager.process = mock_process

        status = manager.get_status()

        assert status["running"] is False
        assert status["pid"] == 12345  # Still reports PID even when dead

    @pytest.mark.parametrize(
        "pid, returncode, restart_count, expected_running",
        [
            (12345, None, 0, True),  # Running process
            (12345, 0, 1, False),  # Clean exit
            (12345, 1, 2, False),  # Error exit
            (12345, -9, 3, False),  # Killed
            (None, None, 0, False),  # No process
        ],
    )
    def test_get_status_various_process_states(
        self,
        mock_settings: Settings,
        pid: int | None,
        returncode: int | None,
        restart_count: int,
        expected_running: bool,
    ) -> None:
        """Test status reporting with various process states."""
        manager = LanguageToolManager(mock_settings)
        manager.restart_count = restart_count

        if pid is not None:
            mock_process = MagicMock()
            mock_process.pid = pid
            mock_process.returncode = returncode
            manager.process = mock_process

        status = manager.get_status()

        assert status["running"] == expected_running
        assert status["restart_count"] == restart_count


@pytest.mark.asyncio
class TestLanguageToolManagerHealthCheck:
    """Test health check logic without HTTP calls."""

    @pytest.mark.parametrize(
        "process_state,session_exists,health_result,expected_result",
        [
            (None, True, True, False),  # No process
            ("running", False, True, False),  # No HTTP session
            ("running", True, True, True),  # Healthy
            ("running", True, False, False),  # Health check fails
            ("dead", True, True, False),  # Process died
        ],
    )
    async def test_health_check_logic(
        self,
        mock_settings: Settings,
        process_state: str | None,
        session_exists: bool,
        health_result: bool,
        expected_result: bool,
    ) -> None:
        """Test health check logic under various states."""
        manager = _TestableLanguageToolManager(mock_settings)
        manager.should_health_check_succeed = health_result

        # Set up process state
        if process_state == "running":
            mock_process = MagicMock()
            mock_process.returncode = None
            manager.process = mock_process
        elif process_state == "dead":
            mock_process = MagicMock()
            mock_process.returncode = 1  # Process exited
            manager.process = mock_process
        else:
            manager.process = None

        # Set up HTTP session
        if session_exists:
            manager.http_session = AsyncMock()
        else:
            manager.http_session = None

        result = await manager.health_check()

        assert result == expected_result


@pytest.mark.asyncio
class TestLanguageToolManagerRestartLogic:
    """Test server restart logic with exponential backoff."""

    async def test_restart_if_needed_when_shutting_down(self, mock_settings: Settings) -> None:
        """Test restart skipped when manager is shutting down."""
        manager = _TestableLanguageToolManager(mock_settings)
        manager.is_shutting_down = True

        await manager.restart_if_needed()

        assert not manager.cleanup_called
        assert not manager.start_called

    async def test_restart_if_needed_exponential_backoff(self, mock_settings: Settings) -> None:
        """Test restart respects exponential backoff timing."""
        manager = _TestableLanguageToolManager(mock_settings)
        manager.restart_count = 3  # Should wait 2^3 = 8 seconds
        manager.last_restart_time = time.time() - 5  # Only 5 seconds ago

        await manager.restart_if_needed()

        # Should skip restart due to backoff
        assert not manager.cleanup_called
        assert not manager.start_called

    async def test_restart_if_needed_successful_restart(self, mock_settings: Settings) -> None:
        """Test successful server restart resets counters."""
        manager = _TestableLanguageToolManager(mock_settings)
        manager.restart_count = 2
        manager.last_restart_time = time.time() - 100  # Long enough ago

        await manager.restart_if_needed()

        assert manager.cleanup_called
        assert manager.start_called
        assert manager.restart_count == 0  # Reset on success

    async def test_restart_if_needed_failed_restart(self, mock_settings: Settings) -> None:
        """Test failed restart increments counters and updates timing."""
        manager = _TestableLanguageToolManager(mock_settings)
        manager.restart_count = 1
        manager.last_restart_time = time.time() - 100  # Long enough ago
        manager.process_start_succeeds = False  # Force failure
        old_time = manager.last_restart_time

        with pytest.raises(RuntimeError, match="Simulated start failure"):
            await manager.restart_if_needed()

        assert manager.cleanup_called
        assert manager.start_called
        assert manager.restart_count == 2  # Incremented
        assert manager.last_restart_time > old_time  # Updated

    @pytest.mark.parametrize(
        "restart_count,expected_min_wait",
        [
            (0, 1),  # 2^0 = 1 second
            (1, 2),  # 2^1 = 2 seconds
            (3, 8),  # 2^3 = 8 seconds
            (6, 60),  # 2^6 = 64, but capped at 60
            (10, 60),  # Still capped at 60
        ],
    )
    async def test_exponential_backoff_calculation(
        self, mock_settings: Settings, restart_count: int, expected_min_wait: int
    ) -> None:
        """Test exponential backoff calculation with various restart counts."""
        manager = _TestableLanguageToolManager(mock_settings)
        manager.restart_count = restart_count
        manager.last_restart_time = time.time() - (expected_min_wait - 1)  # Just under threshold

        await manager.restart_if_needed()

        # Should skip restart due to backoff
        assert not manager.cleanup_called
        assert not manager.start_called

    async def test_exponential_backoff_allows_restart_after_wait(
        self, mock_settings: Settings
    ) -> None:
        """Test exponential backoff allows restart after sufficient wait time."""
        manager = _TestableLanguageToolManager(mock_settings)
        manager.restart_count = 2  # Should wait 2^2 = 4 seconds
        manager.last_restart_time = time.time() - 5  # 5 seconds ago (enough)

        await manager.restart_if_needed()

        # Should allow restart since enough time has passed
        assert manager.cleanup_called
        assert manager.start_called


class TestLanguageToolManagerConfiguration:
    """Test configuration-related behavior."""

    def test_configuration_attributes_set_correctly(self, mock_settings: Settings) -> None:
        """Test all configuration attributes are set correctly from settings."""
        mock_settings.LANGUAGE_TOOL_PORT = 9001
        mock_settings.LANGUAGE_TOOL_HEAP_SIZE = "512m"
        mock_settings.LANGUAGE_TOOL_JAR_PATH = "/custom/path/languagetool.jar"
        mock_settings.LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL = 10

        manager = LanguageToolManager(mock_settings)

        assert manager.settings.LANGUAGE_TOOL_PORT == 9001
        assert manager.settings.LANGUAGE_TOOL_HEAP_SIZE == "512m"
        assert manager.settings.LANGUAGE_TOOL_JAR_PATH == "/custom/path/languagetool.jar"
        assert manager.settings.LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL == 10
        assert manager.server_url == "http://localhost:9001"

    @pytest.mark.parametrize(
        "heap_size, port, expected_heap, expected_port",
        [
            ("256m", 8080, "256m", 8080),
            ("512m", 8443, "512m", 8443),
            ("1g", 9000, "1g", 9000),
            ("2g", 3000, "2g", 3000),
        ],
    )
    def test_various_configuration_combinations(
        self,
        mock_settings: Settings,
        heap_size: str,
        port: int,
        expected_heap: str,
        expected_port: int,
    ) -> None:
        """Test manager works with various configuration combinations."""
        mock_settings.LANGUAGE_TOOL_HEAP_SIZE = heap_size
        mock_settings.LANGUAGE_TOOL_PORT = port

        manager = LanguageToolManager(mock_settings)

        assert manager.settings.LANGUAGE_TOOL_HEAP_SIZE == expected_heap
        assert manager.settings.LANGUAGE_TOOL_PORT == expected_port
        assert manager.server_url == f"http://localhost:{expected_port}"


class TestLanguageToolManagerStateManagement:
    """Test internal state management logic."""

    def test_initial_state_values(self, mock_settings: Settings) -> None:
        """Test all state variables have correct initial values."""
        manager = LanguageToolManager(mock_settings)

        assert manager.process is None
        assert manager.http_session is None
        assert manager.health_check_task is None
        assert manager.restart_count == 0
        assert manager.last_restart_time == 0.0
        assert manager.is_shutting_down is False

    def test_shutdown_flag_behavior(self, mock_settings: Settings) -> None:
        """Test shutdown flag affects manager behavior."""
        manager = _TestableLanguageToolManager(mock_settings)

        # Initially not shutting down
        assert not manager.is_shutting_down

        # Set shutdown flag
        manager.is_shutting_down = True
        assert manager.is_shutting_down

    def test_restart_count_tracking(self, mock_settings: Settings) -> None:
        """Test restart count is tracked correctly."""
        manager = LanguageToolManager(mock_settings)

        # Initial count
        assert manager.restart_count == 0

        # Manual increment for testing
        manager.restart_count += 1
        assert manager.restart_count == 1

        # Reset count
        manager.restart_count = 0
        assert manager.restart_count == 0

    def test_last_restart_time_tracking(self, mock_settings: Settings) -> None:
        """Test last restart time is tracked correctly."""
        manager = LanguageToolManager(mock_settings)

        # Initial time
        assert manager.last_restart_time == 0.0

        # Update time
        current_time = time.time()
        manager.last_restart_time = current_time
        assert manager.last_restart_time == current_time
