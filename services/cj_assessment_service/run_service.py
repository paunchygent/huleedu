"""Main service runner for CJ Assessment Service.

This script runs both the Kafka worker and health API concurrently,
sharing the same application-scoped DI container as required by the
architecture.

Usage:
    python run_service.py
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any

from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)

from services.cj_assessment_service.app import run_health_api
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.worker_main import main as run_kafka_worker

logger = create_service_logger("cj_assessment_service.run_service")


class ServiceManager:
    """Manages concurrent execution of Kafka worker and health API."""

    def __init__(self, settings: Settings) -> None:
        """Initialize service manager with settings."""
        self.settings = settings
        self.tasks: list[asyncio.Task[Any]] = []
        self.shutdown_event = asyncio.Event()

    async def start_services(self) -> None:
        """Start both Kafka worker and health API concurrently."""
        logger.info("Starting CJ Assessment Service components")

        try:
            # Create tasks for both services
            kafka_task = asyncio.create_task(
                self._run_kafka_worker_with_shutdown()
            )
            health_api_task = asyncio.create_task(
                self._run_health_api_with_shutdown()
            )

            self.tasks = [kafka_task, health_api_task]

            # Wait for shutdown signal or any task to complete/fail
            done, pending = await asyncio.wait(
                self.tasks + [asyncio.create_task(self.shutdown_event.wait())],
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel remaining tasks
            for task in pending:
                task.cancel()

            # Wait for clean shutdown
            await asyncio.gather(*pending, return_exceptions=True)

            logger.info("All service components stopped")

        except Exception as e:
            logger.error(f"Service manager error: {e}", exc_info=True)
            raise

    async def _run_kafka_worker_with_shutdown(self) -> None:
        """Run Kafka worker with shutdown monitoring."""
        try:
            logger.info("Starting Kafka worker component")
            await run_kafka_worker()
        except asyncio.CancelledError:
            logger.info("Kafka worker component cancelled")
            raise
        except Exception as e:
            logger.error(f"Kafka worker error: {e}", exc_info=True)
            self.shutdown_event.set()
            raise

    async def _run_health_api_with_shutdown(self) -> None:
        """Run health API with shutdown monitoring."""
        try:
            logger.info("Starting health API component")
            await run_health_api(self.settings)
        except asyncio.CancelledError:
            logger.info("Health API component cancelled")
            raise
        except Exception as e:
            logger.error(f"Health API error: {e}", exc_info=True)
            self.shutdown_event.set()
            raise

    def handle_shutdown_signal(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating shutdown")
        self.shutdown_event.set()


async def main() -> None:
    """Main entry point for the CJ Assessment Service."""
    # Load settings
    settings = Settings()

    # Configure logging
    configure_service_logging(
        "cj_assessment_service", log_level=settings.LOG_LEVEL
    )

    logger.info("CJ Assessment Service starting up")
    logger.info(f"Kafka worker + Health API on port {settings.METRICS_PORT}")

    # Create service manager
    manager = ServiceManager(settings)

    # Set up signal handlers
    for sig in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(sig, manager.handle_shutdown_signal)

    try:
        # Start all services
        await manager.start_services()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
    except Exception as e:
        logger.error(f"Service startup failed: {e}", exc_info=True)
        sys.exit(1)

    logger.info("CJ Assessment Service shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
