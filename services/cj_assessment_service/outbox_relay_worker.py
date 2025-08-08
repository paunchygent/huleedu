"""
Outbox relay worker for CJ Assessment Service.

This worker processes events from the transactional outbox table and publishes
them to Kafka, implementing the relay component of the TRUE OUTBOX PATTERN.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol

from dishka import make_async_container
from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.outbox import EventRelayWorker, OutboxRepositoryProtocol, OutboxSettings
from sqlalchemy.ext.asyncio import create_async_engine

from services.cj_assessment_service.config import settings
from services.cj_assessment_service.di import CJAssessmentServiceProvider

# Configure logging
configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)
logger = create_service_logger("outbox_relay_worker")

# Global shutdown event
shutdown_event = asyncio.Event()


async def main() -> None:
    """Main entry point for the outbox relay worker."""
    logger.info(
        "CJ Assessment Service outbox relay worker starting...",
        extra={
            "service": settings.SERVICE_NAME,
            "poll_interval": settings.OUTBOX_POLL_INTERVAL_SECONDS,
            "batch_size": settings.OUTBOX_BATCH_SIZE,
            "max_retries": settings.OUTBOX_MAX_RETRIES,
        },
    )

    # Initialize tracing
    init_tracing(f"{settings.SERVICE_NAME}_outbox_relay")
    logger.info("OpenTelemetry tracing initialized for outbox relay")

    # Initialize database engine
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        future=True,
        pool_size=5,  # Smaller pool for relay worker
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

    # Initialize Dishka container
    container = make_async_container(CJAssessmentServiceProvider(engine=engine))

    relay_worker = None

    try:
        async with container() as request_container:
            # Get dependencies from container
            outbox_repository = await request_container.get(OutboxRepositoryProtocol)
            kafka_publisher = await request_container.get(KafkaPublisherProtocol)
            redis_client = await request_container.get(AtomicRedisClientProtocol)

            # Configure outbox settings
            outbox_settings = OutboxSettings(
                poll_interval_seconds=settings.OUTBOX_POLL_INTERVAL_SECONDS,
                batch_size=settings.OUTBOX_BATCH_SIZE,
                max_retries=settings.OUTBOX_MAX_RETRIES,
                error_retry_interval_seconds=settings.OUTBOX_ERROR_RETRY_INTERVAL_SECONDS,
                enable_metrics=settings.OUTBOX_ENABLE_METRICS,
                enable_wake_notifications=settings.OUTBOX_ENABLE_WAKE_NOTIFICATIONS,
            )

            # Create and start the relay worker
            relay_worker = EventRelayWorker(
                outbox_repository=outbox_repository,
                kafka_bus=kafka_publisher,
                settings=outbox_settings,
                service_name=settings.SERVICE_NAME,
                redis_client=redis_client,
            )

            logger.info(
                "Starting outbox relay worker",
                extra={
                    "service": settings.SERVICE_NAME,
                    "wake_key": f"outbox:wake:{settings.SERVICE_NAME}",
                    "batch_size": outbox_settings.batch_size,
                    "poll_interval": outbox_settings.poll_interval_seconds,
                },
            )

            # Start the worker
            await relay_worker.start()

            # Wait for shutdown signal
            await shutdown_event.wait()

            logger.info("Shutdown signal received, stopping outbox relay worker...")

            # Stop the worker gracefully
            if relay_worker:
                await relay_worker.stop()

    except Exception as e:
        logger.error(
            "Outbox relay worker failed",
            extra={"error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
        raise
    finally:
        # Clean up resources
        logger.info("Cleaning up resources...")

        # Close the container
        await container.close()

        # Dispose of the database engine
        await engine.dispose()
        logger.info("Database connections closed")

        logger.info("CJ Assessment Service outbox relay worker shutdown complete")


def signal_handler(signum: int, frame: Any) -> None:
    """Handle shutdown signals."""
    _ = frame  # Unused but required by signal handler signature
    logger.info(f"Received signal {signum}, initiating shutdown...")
    shutdown_event.set()


if __name__ == "__main__":
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        asyncio.run(main())
        logger.info("Outbox relay worker exited normally")
    except KeyboardInterrupt:
        logger.info("Outbox relay worker interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Outbox relay worker failed: {e}", exc_info=True)
        sys.exit(1)
