"""
LanguageTool Java process lifecycle manager.

This module manages the LanguageTool server process, including starting,
stopping, health checking, and automatic restart on failure.
"""

from __future__ import annotations

import asyncio
import os
import signal
import time
from collections import deque
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiofiles
import aiohttp
from huleedu_service_libs.error_handling import raise_service_unavailable
from huleedu_service_libs.logging_utils import create_service_logger

from services.language_tool_service.config import Settings
from services.language_tool_service.metrics import METRICS

logger = create_service_logger("language_tool_service.implementations.language_tool_manager")


class LanguageToolManager:
    """
    Manages the LanguageTool Java server process lifecycle.

    This class handles starting, stopping, and monitoring the LanguageTool
    server process, including automatic restart on failure and health checks.
    """

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the LanguageTool manager.

        Args:
            settings: Service configuration settings
        """
        self.settings = settings
        self.process: asyncio.subprocess.Process | None = None
        self.http_session: aiohttp.ClientSession | None = None
        self.health_check_task: asyncio.Task[None] | None = None
        self.restart_count = 0
        self.last_restart_time = 0.0
        self.is_shutting_down = False
        self._restart_lock = asyncio.Lock()
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stdout_buffer: deque[str] = deque(maxlen=50)
        self._stderr_buffer: deque[str] = deque(maxlen=50)

        # Build server URL for health checks
        self.server_url = f"http://localhost:{settings.LANGUAGE_TOOL_PORT}"

        logger.info(
            "LanguageToolManager initialized",
            extra={
                "port": settings.LANGUAGE_TOOL_PORT,
                "heap_size": settings.LANGUAGE_TOOL_HEAP_SIZE,
                "jar_path": settings.LANGUAGE_TOOL_JAR_PATH,
            },
        )

    async def start(self) -> None:
        """
        Start the LanguageTool server process.

        Raises:
            HuleEduError: If the server fails to start
        """
        # Reset shutdown flag when (re)starting the server
        # Without this, restart_if_needed() will early-return
        # if stop() was called earlier in the lifecycle.
        self.is_shutting_down = False
        if self.process and self.process.returncode is None:
            logger.warning("LanguageTool server already running")
            return

        logger.info("Starting LanguageTool server...")

        # Check if JAR exists
        jar_path = Path(self.settings.LANGUAGE_TOOL_JAR_PATH)
        if not jar_path.exists():
            logger.error(f"LanguageTool JAR not found at {jar_path}")
            raise_service_unavailable(
                service="language_tool_service",
                operation="start_server",
                unavailable_service="languagetool_jar",
                message=f"LanguageTool JAR not found at {jar_path}",
                correlation_id=uuid4(),
            )

        # Build Java command with JVM options
        java_cmd = [
            "java",
            f"-Xmx{self.settings.LANGUAGE_TOOL_HEAP_SIZE}",
            f"-Xms{self.settings.LANGUAGE_TOOL_HEAP_SIZE}",
            "-XX:+UseG1GC",
            "-XX:MaxGCPauseMillis=200",
            "-XX:+HeapDumpOnOutOfMemoryError",
            "-XX:HeapDumpPath=/tmp/languagetool_heapdump.hprof",
            "-jar",
            str(jar_path),
            "--port",
            str(self.settings.LANGUAGE_TOOL_PORT),
            "--allow-origin",
            "*",
            "--public",
        ]

        try:
            # Start the subprocess
            await self._cancel_process_log_consumers()
            self._reset_process_logs()
            self.process = await asyncio.create_subprocess_exec(
                *java_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # Set environment to ensure UTF-8 encoding
                env={**os.environ, "JAVA_TOOL_OPTIONS": "-Dfile.encoding=UTF-8"},
            )

            self._start_process_log_consumers()

            # Initialize HTTP session for health checks
            if not self.http_session:
                self.http_session = aiohttp.ClientSession()

            # Wait for server to be ready (with timeout)
            await self._wait_for_server_ready()

            # Start health check monitoring
            if not self.health_check_task or self.health_check_task.done():
                self.health_check_task = asyncio.create_task(self._health_check_loop())

            logger.info(
                "LanguageTool server started successfully",
                extra={"pid": self.process.pid, "port": self.settings.LANGUAGE_TOOL_PORT},
            )

        except asyncio.TimeoutError:
            logger.error("LanguageTool server failed to start within timeout")
            await self._cleanup_process()
            raise_service_unavailable(
                service="language_tool_service",
                operation="start_server",
                unavailable_service="languagetool_server",
                message="LanguageTool server failed to start within timeout",
                correlation_id=uuid4(),
            )
        except Exception as e:
            logger.error(f"Failed to start LanguageTool server: {e}", exc_info=True)
            await self._cleanup_process()
            raise

    async def stop(self) -> None:
        """Gracefully stop the LanguageTool server process."""
        self.is_shutting_down = True

        # Cancel health check task
        if self.health_check_task and not self.health_check_task.done():
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass

        # Close HTTP session
        if self.http_session:
            await self.http_session.close()
            self.http_session = None

        # Stop the process
        await self._cleanup_process()

        logger.info("LanguageTool server stopped")

    async def health_check(self) -> bool:
        """
        Check if the LanguageTool server is healthy.

        Returns:
            True if the server is responsive, False otherwise
        """
        if not self.process:
            return False

        # Check if process has terminated
        if self.process.returncode is not None:
            return False

        if not self.http_session:
            return False

        try:
            # Check the languages endpoint as a health check
            async with self.http_session.get(
                f"{self.server_url}/v2/languages",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                return response.status == 200
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            # If we can't connect, the process might be dead
            # Check if it's still running
            if self.process and self.process.returncode is None:
                # Try to see if process is actually dead
                try:
                    # Send signal 0 to check if process exists
                    os.kill(self.process.pid, 0)
                except ProcessLookupError:
                    # Process is dead but we haven't waited on it
                    # Update returncode by waiting with a short timeout
                    try:
                        await asyncio.wait_for(self.process.wait(), timeout=0.1)
                    except asyncio.TimeoutError:
                        pass
            return False

    async def restart_if_needed(self) -> None:
        """
        Restart the server if it's not healthy.

        Implements exponential backoff to prevent restart loops.
        """
        if self.is_shutting_down:
            return

        async with self._restart_lock:
            if self.is_shutting_down:
                return

            # Check if restart is actually needed
            needs_restart = False

            # First, check if process exists and is alive
            if not self.process:
                needs_restart = True
                logger.debug("restart_if_needed: No process exists, restart needed")
            elif self.process.returncode is not None:
                # Process has terminated - no need for health check
                needs_restart = True
                logger.debug(
                    f"restart_if_needed: Process terminated with returncode "
                    f"{self.process.returncode}, restart needed"
                )
            else:
                # Process exists and hasn't terminated, check health
                is_healthy = await self.health_check()
                logger.debug(f"restart_if_needed: health_check returned {is_healthy}")
                if is_healthy:
                    # Server is healthy, no restart needed
                    return
                needs_restart = True

            if not needs_restart:
                return

            current_time = time.time()
            time_since_last_restart = current_time - self.last_restart_time

            # Exponential backoff: wait 2^restart_count seconds, max 60 seconds
            min_wait_time = min(2**self.restart_count, 60)

            if time_since_last_restart < min_wait_time:
                logger.debug(
                    f"Skipping restart, waiting {min_wait_time - time_since_last_restart:.1f}s more"
                )
                # Record skipped restart due to backoff
                METRICS["manager_restart_skipped_total"].inc()
                return

            # Record the time at which we attempt a restart (regardless of outcome)
            self.last_restart_time = current_time

            logger.warning(
                f"Restarting LanguageTool server (attempt {self.restart_count + 1}), "
                f"process state: PID={self.process.pid if self.process else None}, "
                f"returncode={self.process.returncode if self.process else None}"
            )

            # Stop the current process
            await self._cleanup_process()

            # Start a new process
            try:
                await self.start()
                self.restart_count = 0  # Reset on successful restart
                METRICS["manager_restarts_total"].labels(outcome="success").inc()
                # Record last successful restart timestamp
                METRICS["manager_last_restart_timestamp_seconds"].set(time.time())
            except Exception as e:
                logger.error(f"Failed to restart LanguageTool server: {e}")
                self.restart_count += 1
                # last_restart_time already set at attempt
                METRICS["manager_restarts_total"].labels(outcome="failure").inc()
                raise

    async def _wait_for_server_ready(self, timeout: float = 30.0) -> None:
        """
        Wait for the LanguageTool server to be ready.

        Args:
            timeout: Maximum time to wait in seconds

        Raises:
            asyncio.TimeoutError: If server doesn't become ready within timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            if await self.health_check():
                return

            # Check if process has died
            if self.process and self.process.returncode is not None:
                recent_logs = self.get_recent_output()
                error_lines = recent_logs["stderr"] or recent_logs["stdout"]
                error_msg = "\n".join(error_lines) if error_lines else "Unknown error"
                raise RuntimeError(
                    f"LanguageTool process died during startup (code={self.process.returncode}): {error_msg}"
                )

            await asyncio.sleep(0.5)

        raise asyncio.TimeoutError("LanguageTool server did not become ready in time")

    async def _health_check_loop(self) -> None:
        """
        Continuously monitor server health and restart if needed.

        This runs as a background task during the server's lifetime.
        """
        while not self.is_shutting_down:
            try:
                await asyncio.sleep(self.settings.LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL)

                if not await self.health_check():
                    logger.warning("LanguageTool server health check failed")
                    await self.restart_if_needed()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}", exc_info=True)

    async def _cleanup_process(self) -> None:
        """Clean up the LanguageTool process."""
        if not self.process:
            return

        if self.process.returncode is None:
            # Check if process is actually still alive
            try:
                os.kill(self.process.pid, 0)  # Signal 0 = check if process exists
                # Process is alive, try graceful shutdown
                self.process.send_signal(signal.SIGTERM)
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except ProcessLookupError:
                # Process is already dead, just wait to update returncode
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=0.1)
                except asyncio.TimeoutError:
                    pass  # Process was already waited on
            except asyncio.TimeoutError:
                # Graceful shutdown timed out, force kill
                logger.warning("Graceful shutdown timed out, forcing kill")
                try:
                    self.process.send_signal(signal.SIGKILL)
                    await self.process.wait()
                except ProcessLookupError:
                    # Process died between SIGTERM and SIGKILL
                    pass

        self.process = None
        await self._cancel_process_log_consumers()

    def get_status(self) -> dict[str, Any]:
        """
        Get the current status of the LanguageTool server.

        Returns:
            Dictionary with server status information
        """
        return {
            "running": self.process is not None and self.process.returncode is None,
            "pid": self.process.pid if self.process else None,
            "restart_count": self.restart_count,
            "returncode": self.process.returncode if self.process else None,
            "port": self.settings.LANGUAGE_TOOL_PORT,
            "heap_size": self.settings.LANGUAGE_TOOL_HEAP_SIZE,
            "last_restart_time": self.last_restart_time,
        }

    async def get_jvm_heap_usage(self) -> int | None:
        """
        Get current JVM heap usage in MB using /proc filesystem.

        Returns:
            Heap usage in MB, or None if unable to retrieve
        """
        if not self.process or self.process.returncode is not None:
            return None

        try:
            # Read memory usage from /proc/{pid}/status
            status_path = f"/proc/{self.process.pid}/status"

            async with aiofiles.open(status_path, "r") as f:
                content = await f.read()

            # Extract VmRSS (Resident Set Size in KB)
            for line in content.splitlines():
                if line.startswith("VmRSS:"):
                    # Format: "VmRSS:    219612 kB"
                    parts = line.split()
                    if len(parts) >= 2:
                        kb_value = int(parts[1])
                        return kb_value // 1024  # Convert KB to MB

            return None  # VmRSS not found

        except (OSError, ValueError) as e:
            logger.debug(f"Failed to get JVM heap usage: {e}")
            return None

    def get_recent_output(self, max_lines: int = 10) -> dict[str, list[str]]:
        """Return recent stdout/stderr lines from the LanguageTool process."""
        stdout_tail = list(self._stdout_buffer)[-max_lines:]
        stderr_tail = list(self._stderr_buffer)[-max_lines:]
        return {
            "stdout": stdout_tail,
            "stderr": stderr_tail,
        }

    def _reset_process_logs(self) -> None:
        """Clear cached process log buffers."""
        self._stdout_buffer.clear()
        self._stderr_buffer.clear()

    def _start_process_log_consumers(self) -> None:
        """Begin streaming stdout/stderr from the managed process."""
        if not self.process:
            return

        if self.process.stdout:
            self._stdout_task = asyncio.create_task(
                self._stream_process_output(self.process.stdout, self._stdout_buffer, "stdout")
            )

        if self.process.stderr:
            self._stderr_task = asyncio.create_task(
                self._stream_process_output(self.process.stderr, self._stderr_buffer, "stderr")
            )

    async def _cancel_process_log_consumers(self) -> None:
        """Cancel log streaming tasks if they are active."""
        tasks = [self._stdout_task, self._stderr_task]
        self._stdout_task = None
        self._stderr_task = None

        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _stream_process_output(
        self,
        stream: asyncio.StreamReader,
        buffer: deque[str],
        stream_name: str,
    ) -> None:
        """Stream output from the process and retain recent lines for diagnostics."""
        log_method = logger.debug if stream_name == "stdout" else logger.warning

        try:
            while True:
                line = await stream.readline()
                if not line:
                    break

                text = line.decode("utf-8", errors="replace").rstrip()
                if not text:
                    continue

                buffer.append(text)
                log_method("LanguageTool %s: %s", stream_name, text)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - diagnostic safeguard
            logger.error(
                "Failed while reading LanguageTool %s stream: %s",
                stream_name,
                exc,
                exc_info=True,
            )
