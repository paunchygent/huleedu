"""
Integration tests for Language Tool Java process lifecycle management.

Tests validate real-world interactions with LanguageTool Java processes,
focusing on behavioral outcomes without mocking implementation details (Rule 070).

These tests verify:
- Real Java subprocess management and lifecycle
- Actual HTTP health check interactions
- Process restart behavior on failure
- Graceful shutdown and cleanup
- Fallback to stub mode when resources unavailable

Note: These tests interact with actual Java processes and HTTP servers,
requiring proper resource cleanup and timeout handling.
"""

from __future__ import annotations

import asyncio
import os
import signal
import tempfile
import time
from collections.abc import AsyncIterator, Generator
from pathlib import Path
from typing import Any

import aiohttp
import psutil
import pytest
from dishka import make_async_container
from quart import Quart
from quart_dishka import QuartDishka

from services.language_tool_service.config import Settings
from services.language_tool_service.di import (
    CoreInfrastructureProvider,
    ServiceImplementationsProvider,
)
from services.language_tool_service.implementations.language_tool_manager import (
    LanguageToolManager,
)

# Test configuration constants
INTEGRATION_TEST_TIMEOUT = 30.0  # 30 second default timeout
JAVA_PROCESS_STARTUP_TIMEOUT = 15.0  # Allow reasonable time for Java startup
HEALTH_CHECK_TIMEOUT = 5.0  # Quick health check timeout


@pytest.fixture
def integration_settings() -> Settings:
    """Create settings configured for integration testing with real components."""
    settings = Settings()

    # Use test-specific ports to avoid conflicts
    settings.LANGUAGE_TOOL_PORT = 8091  # Different from default 8081
    settings.HTTP_PORT = 8095  # Different from default 8085

    # Configure for testing environment
    settings.LANGUAGE_TOOL_HEAP_SIZE = "256m"  # Smaller heap for testing
    settings.LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL = 5  # Faster health checks
    settings.LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS = 10  # Shorter timeout

    # Use actual JAR path if available, will test fallback scenarios separately
    settings.LANGUAGE_TOOL_JAR_PATH = "/app/languagetool/languagetool-server.jar"

    return settings


@pytest.fixture
async def real_app(integration_settings: Settings) -> Quart:
    """
    Create real Quart application with full DI container for integration testing.

    This fixture provides a complete application instance with real dependencies,
    not mocked ones, enabling true integration test validation.
    """
    app = Quart(__name__)

    # Initialize DI container with real providers
    container = make_async_container(
        CoreInfrastructureProvider(),
        ServiceImplementationsProvider(),
    )
    QuartDishka(app=app, container=container)

    # Store settings for test access
    app.config["TEST_SETTINGS"] = integration_settings

    return app


@pytest.fixture
async def client(real_app: Quart) -> Any:
    """Create test client for real HTTP requests to the application."""
    return real_app.test_client()


@pytest.fixture
async def real_language_tool_manager(
    integration_settings: Settings,
) -> AsyncIterator[LanguageToolManager]:
    """
    Create real LanguageToolManager instance for direct testing.

    This manager uses actual subprocess management and HTTP clients,
    not test doubles or mocks.
    """
    manager = LanguageToolManager(integration_settings)

    # Ensure clean state
    await manager.stop()

    yield manager

    # Cleanup after test
    await manager.stop()


@pytest.fixture
def temporary_jar_path() -> Generator[Path, None, None]:
    """Create temporary JAR file path for testing missing JAR scenarios."""
    with tempfile.NamedTemporaryFile(suffix=".jar", delete=False) as tmp:
        jar_path = Path(tmp.name)

    # Remove the file so we can test missing JAR behavior
    jar_path.unlink()

    yield jar_path

    # Cleanup if file was created during test
    if jar_path.exists():
        jar_path.unlink()


def create_minimal_jar_file(jar_path: Path) -> None:
    """
    Create minimal JAR file for testing.

    Creates a basic JAR structure that Java can attempt to execute,
    though it won't be a functional LanguageTool server.
    """
    jar_path.parent.mkdir(parents=True, exist_ok=True)

    # Create minimal JAR content (just a ZIP with manifest)
    import zipfile

    with zipfile.ZipFile(jar_path, "w") as jar:
        jar.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")


def find_java_processes_by_port(port: int) -> list[psutil.Process]:
    """
    Find Java processes listening on specific port.

    Args:
        port: Port number to search for

    Returns:
        List of psutil.Process objects for Java processes on the port
    """
    java_processes = []

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["name"] and "java" in proc.info["name"].lower():
                # Check if process has connections on the target port
                try:
                    connections = proc.connections()
                    for conn in connections:
                        if conn.laddr.port == port:
                            java_processes.append(proc)
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return java_processes


async def wait_for_process_startup(
    manager: LanguageToolManager, timeout: float = JAVA_PROCESS_STARTUP_TIMEOUT
) -> bool:
    """
    Wait for Java process to start and become responsive.

    Args:
        manager: LanguageToolManager instance to monitor
        timeout: Maximum time to wait in seconds

    Returns:
        True if process started successfully, False if timeout
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        if manager.process and manager.process.returncode is None:
            # Process exists, check if it's healthy
            if await manager.health_check():
                return True

        await asyncio.sleep(0.5)

    return False


async def wait_for_process_shutdown(manager: LanguageToolManager, timeout: float = 10.0) -> bool:
    """
    Wait for Java process to shut down completely.

    Args:
        manager: LanguageToolManager instance to monitor
        timeout: Maximum time to wait in seconds

    Returns:
        True if process shut down, False if timeout
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        if not manager.process or manager.process.returncode is not None:
            return True
        await asyncio.sleep(0.2)

    return False


class TestProcessLifecycle:
    """Integration tests for Language Tool Java process management."""

    @pytest.mark.integration
    @pytest.mark.timeout(INTEGRATION_TEST_TIMEOUT)
    async def test_java_process_starts_successfully(
        self, real_language_tool_manager: LanguageToolManager
    ) -> None:
        """
        Verify real JAR launches actual Java process.

        Tests that the LanguageToolManager can start a real Java subprocess
        and that the process becomes responsive to health checks.
        """
        manager = real_language_tool_manager

        # Check if JAR exists before attempting test
        jar_path = Path(manager.settings.LANGUAGE_TOOL_JAR_PATH)
        if not jar_path.exists():
            pytest.skip(f"LanguageTool JAR not found at {jar_path}, skipping real process test")

        # Start the server
        await manager.start()

        # Verify process was created
        assert manager.process is not None, "Java process should be created"
        assert manager.process.returncode is None, "Java process should be running"

        # Verify process is actually a Java process
        process_pid = manager.process.pid
        java_processes = find_java_processes_by_port(manager.settings.LANGUAGE_TOOL_PORT)

        process_found = any(proc.pid == process_pid for proc in java_processes)
        assert process_found, (
            f"Java process with PID {process_pid} should be listening on port {manager.settings.LANGUAGE_TOOL_PORT}"
        )

        # Verify health check passes (real HTTP interaction)
        health_check_passed = await manager.health_check()
        assert health_check_passed, "Health check should pass for running Java process"

        # Verify status reflects running state
        status = manager.get_status()
        assert status["running"] is True, "Manager status should indicate running"
        assert status["pid"] == process_pid, "Status should report correct PID"

    @pytest.mark.integration
    @pytest.mark.timeout(INTEGRATION_TEST_TIMEOUT)
    async def test_health_check_reports_jvm_status(
        self, real_language_tool_manager: LanguageToolManager
    ) -> None:
        """
        Validate JVM running state and heap usage reporting.

        Tests that health checks accurately report JVM status including
        process running state and actual heap usage from /proc filesystem.
        """
        manager = real_language_tool_manager

        # Check if JAR exists
        jar_path = Path(manager.settings.LANGUAGE_TOOL_JAR_PATH)
        if not jar_path.exists():
            pytest.skip(f"LanguageTool JAR not found at {jar_path}, skipping JVM status test")

        # Start process
        await manager.start()

        # Wait for process to be fully ready
        process_ready = await wait_for_process_startup(manager)
        assert process_ready, "Java process should start and become responsive"

        # Test health check returns True for healthy process
        is_healthy = await manager.health_check()
        assert is_healthy, "Health check should return True for running process"

        # Test JVM heap usage reporting
        heap_usage = await manager.get_jvm_heap_usage()

        if heap_usage is not None:
            # If we can read heap usage, validate it's reasonable
            assert isinstance(heap_usage, int), "Heap usage should be integer MB value"
            assert heap_usage > 0, "Heap usage should be positive for running JVM"
            assert heap_usage < 1024, f"Heap usage {heap_usage}MB seems unreasonably high for test"

        # Verify process status accuracy
        status = manager.get_status()
        assert status["running"] is True, "Status should indicate process is running"
        assert isinstance(status["pid"], int), "Status should include valid PID"

        # Verify the process is actually responsive via HTTP
        # This tests real network interaction, not mocked responses
        http_session = manager.http_session
        assert http_session is not None, "HTTP session should be available"

        try:
            async with http_session.get(
                f"{manager.server_url}/v2/languages", timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                assert response.status == 200, "LanguageTool server should respond to HTTP requests"
        except Exception as e:
            pytest.fail(f"Real HTTP health check failed: {e}")

    @pytest.mark.integration
    @pytest.mark.timeout(INTEGRATION_TEST_TIMEOUT * 2)  # Allow more time for restart scenarios
    async def test_process_restart_on_failure(
        self, real_language_tool_manager: LanguageToolManager
    ) -> None:
        """
        Test automatic restart when process dies.

        Tests the restart mechanism by killing the Java process and
        verifying the manager detects the failure and restarts automatically.
        """
        manager = real_language_tool_manager

        # Check if JAR exists
        jar_path = Path(manager.settings.LANGUAGE_TOOL_JAR_PATH)
        if not jar_path.exists():
            pytest.skip(f"LanguageTool JAR not found at {jar_path}, skipping restart test")

        # Start initial process
        await manager.start()

        # Wait for initial startup
        initial_ready = await wait_for_process_startup(manager)
        assert initial_ready, "Initial Java process should start successfully"

        assert manager.process is not None, "Process should exist after startup"
        original_pid = manager.process.pid
        assert original_pid is not None, "Original process should have valid PID"

        # Kill the process externally (simulate crash)
        try:
            os.kill(original_pid, signal.SIGKILL)
        except ProcessLookupError:
            # Process might have already died, that's okay for this test
            pass

        # Wait a moment for process death to be detected
        await asyncio.sleep(2)

        # Verify health check now fails
        health_after_kill = await manager.health_check()
        assert health_after_kill is False, "Health check should fail after process is killed"

        # Trigger restart manually (in real scenarios this happens automatically via health check loop)
        # Reset restart timing to allow immediate restart
        manager.last_restart_time = 0.0
        manager.restart_count = 0

        # Attempt restart
        await manager.restart_if_needed()

        # Wait for restart to complete
        restart_ready = await wait_for_process_startup(
            manager, timeout=JAVA_PROCESS_STARTUP_TIMEOUT
        )
        assert restart_ready, "Process should restart successfully after failure"

        # Verify new process has different PID
        assert manager.process is not None, "New process should exist after restart"
        new_pid = manager.process.pid
        assert new_pid != original_pid, (
            f"New process PID {new_pid} should differ from original {original_pid}"
        )

        # Verify new process is healthy
        health_after_restart = await manager.health_check()
        assert health_after_restart, "Health check should pass after successful restart"

    @pytest.mark.integration
    @pytest.mark.timeout(INTEGRATION_TEST_TIMEOUT)
    async def test_graceful_shutdown_cleanup(
        self, real_language_tool_manager: LanguageToolManager
    ) -> None:
        """
        Ensure clean process termination.

        Tests that the shutdown process properly terminates Java processes
        and cleans up resources without leaving zombie processes.
        """
        manager = real_language_tool_manager

        # Check if JAR exists
        jar_path = Path(manager.settings.LANGUAGE_TOOL_JAR_PATH)
        if not jar_path.exists():
            pytest.skip(f"LanguageTool JAR not found at {jar_path}, skipping shutdown test")

        # Start process
        await manager.start()

        # Wait for startup
        startup_successful = await wait_for_process_startup(manager)
        assert startup_successful, "Process should start before testing shutdown"

        assert manager.process is not None, "Process should exist before shutdown"
        process_pid = manager.process.pid
        assert process_pid is not None, "Process should have valid PID before shutdown"

        # Verify process exists in system
        try:
            proc = psutil.Process(process_pid)
            assert proc.is_running(), "Process should be running before shutdown"
        except psutil.NoSuchProcess:
            pytest.fail(f"Process {process_pid} should exist before shutdown")

        # Perform graceful shutdown
        await manager.stop()

        # Wait for shutdown to complete
        shutdown_complete = await wait_for_process_shutdown(manager)
        assert shutdown_complete, "Process should shut down within timeout"

        # Verify manager state after shutdown
        assert manager.process is None, "Manager should clear process reference after shutdown"
        assert manager.http_session is None, "HTTP session should be cleaned up"
        assert manager.is_shutting_down, "Shutdown flag should be set"

        # Verify process is actually gone from system
        try:
            proc = psutil.Process(process_pid)
            # If process still exists, it should not be running
            assert not proc.is_running(), (
                f"Process {process_pid} should not be running after shutdown"
            )
        except psutil.NoSuchProcess:
            # This is the expected case - process should be completely gone
            pass

        # Verify no Java processes remain on the test port
        remaining_processes = find_java_processes_by_port(manager.settings.LANGUAGE_TOOL_PORT)
        assert len(remaining_processes) == 0, (
            f"No Java processes should remain on port {manager.settings.LANGUAGE_TOOL_PORT}"
        )

    @pytest.mark.integration
    @pytest.mark.timeout(INTEGRATION_TEST_TIMEOUT)
    async def test_fallback_to_stub_when_jar_missing(
        self, integration_settings: Settings, temporary_jar_path: Path
    ) -> None:
        """
        Verify stub mode activation when JAR file is missing.

        Tests that the service gracefully falls back to stub implementation
        when the LanguageTool JAR file is not available, without crashing.
        """
        # Configure settings to use non-existent JAR path
        integration_settings.LANGUAGE_TOOL_JAR_PATH = str(temporary_jar_path)

        # Ensure JAR file does not exist
        assert not temporary_jar_path.exists(), "JAR file should not exist for this test"

        # Create manager with missing JAR
        manager = LanguageToolManager(integration_settings)

        try:
            # Attempt to start should fail gracefully
            with pytest.raises(Exception):  # Expect some form of error due to missing JAR
                await manager.start()

            # Verify manager state reflects failure appropriately
            assert manager.process is None, "No process should be created with missing JAR"

            # Health check should return False for non-existent process
            health_result = await manager.health_check()
            assert health_result is False, "Health check should fail when no process exists"

            # Status should reflect non-running state
            status = manager.get_status()
            assert status["running"] is False, "Status should indicate not running"
            assert status["pid"] is None, "No PID should be reported when process doesn't exist"

        finally:
            # Cleanup attempt (should be safe even if start failed)
            await manager.stop()

        # Test that DI container properly detects missing JAR and uses stub
        # This tests the actual fallback mechanism in the DI provider
        container = make_async_container(
            CoreInfrastructureProvider(),
            ServiceImplementationsProvider(),
        )

        async with container() as request_container:
            # The DI system should provide a working implementation despite missing JAR
            from services.language_tool_service.protocols import LanguageToolWrapperProtocol

            wrapper = await request_container.get(LanguageToolWrapperProtocol)
            assert wrapper is not None, "DI container should provide wrapper implementation"

            # The wrapper should be functional (stub mode)
            from uuid import uuid4

            from huleedu_service_libs.error_handling.correlation import CorrelationContext

            correlation_context = CorrelationContext(
                original="test-integration-correlation-id", uuid=uuid4(), source="generated"
            )

            # This should work with stub implementation
            health_status = await wrapper.get_health_status(correlation_context)
            assert isinstance(health_status, dict), "Stub wrapper should return health status"

            # Stub should handle text checking gracefully
            result = await wrapper.check_text("Test text", correlation_context)
            assert isinstance(result, list), "Stub wrapper should return results list"
