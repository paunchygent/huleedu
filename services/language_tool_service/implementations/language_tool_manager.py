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
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiohttp
from huleedu_service_libs.error_handling import raise_service_unavailable
from huleedu_service_libs.logging_utils import create_service_logger

from services.language_tool_service.config import Settings

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
            self.process = await asyncio.create_subprocess_exec(
                *java_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # Set environment to ensure UTF-8 encoding
                env={**os.environ, "JAVA_TOOL_OPTIONS": "-Dfile.encoding=UTF-8"},
            )

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
        if not self.process or self.process.returncode is not None:
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
            return False

    async def restart_if_needed(self) -> None:
        """
        Restart the server if it's not healthy.

        Implements exponential backoff to prevent restart loops.
        """
        if self.is_shutting_down:
            return

        current_time = time.time()
        time_since_last_restart = current_time - self.last_restart_time

        # Exponential backoff: wait 2^restart_count seconds, max 60 seconds
        min_wait_time = min(2**self.restart_count, 60)

        if time_since_last_restart < min_wait_time:
            logger.debug(
                f"Skipping restart, waiting {min_wait_time - time_since_last_restart:.1f}s more"
            )
            return

        logger.warning(f"Restarting LanguageTool server (attempt {self.restart_count + 1})")

        # Stop the current process
        await self._cleanup_process()

        # Start a new process
        try:
            await self.start()
            self.restart_count = 0  # Reset on successful restart
        except Exception as e:
            logger.error(f"Failed to restart LanguageTool server: {e}")
            self.restart_count += 1
            self.last_restart_time = current_time
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
                _, stderr = await self.process.communicate()
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise RuntimeError(f"LanguageTool process died during startup: {error_msg}")

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
            # Try graceful shutdown first
            try:
                self.process.send_signal(signal.SIGTERM)
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                # Force kill if graceful shutdown fails
                logger.warning("Graceful shutdown timed out, forcing kill")
                self.process.send_signal(signal.SIGKILL)
                await self.process.wait()
            except ProcessLookupError:
                # Process already dead
                pass

        self.process = None

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
            "port": self.settings.LANGUAGE_TOOL_PORT,
            "heap_size": self.settings.LANGUAGE_TOOL_HEAP_SIZE,
        }

    async def get_jvm_heap_usage(self) -> int | None:
        """
        Get current JVM heap usage in MB.
        
        Returns:
            Heap usage in MB, or None if unable to retrieve
        """
        if not self.process or self.process.returncode is not None:
            return None
            
        try:
            # Use jstat to get heap information
            result = await asyncio.create_subprocess_exec(
                "jstat", "-gc", str(self.process.pid),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            
            if result.returncode != 0:
                return None
                
            # Parse jstat output
            # Format: S0C S1C S0U S1U EC EU OC OU MC MU CCSC CCSU YGC YGCT FGC FGCT GCT
            lines = stdout.decode().strip().split('\n')
            if len(lines) < 2:
                return None
                
            data = lines[1].split()
            if len(data) < 8:
                return None
                
            # Calculate total heap usage: Eden Used + Old Used + Survivor Used
            eden_used = float(data[5])  # EU - Eden space used (KB)
            old_used = float(data[7])   # OU - Old space used (KB) 
            survivor_used = float(data[2]) + float(data[3])  # S0U + S1U (KB)
            
            # Convert KB to MB
            heap_used_mb = int((eden_used + old_used + survivor_used) / 1024)
            return heap_used_mb
            
        except Exception as e:
            logger.debug(f"Failed to get JVM heap usage: {e}")
            return None
