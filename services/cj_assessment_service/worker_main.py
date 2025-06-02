"""Main entry point for CJ Assessment Service worker."""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any

from aiokafka import AIOKafkaConsumer
from dishka import make_async_container
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger

from .config import settings
from .di import CJAssessmentServiceProvider
from .event_processor import process_single_message
from .protocols import (
    CJDatabaseProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)

# Configure logging
configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)
logger = create_service_logger("worker_main")

# Global shutdown flag
shutdown_event = asyncio.Event()


async def main() -> None:
    """Main entry point for CJ Assessment Service worker."""
    logger.info("CJ Assessment Service worker starting...")

    # Initialize Dishka container
    container = make_async_container(CJAssessmentServiceProvider())

    try:
        # Initialize database schema
        database = await container.get(CJDatabaseProtocol)
        await database.initialize_db_schema()
        logger.info("Database schema initialized")

        # Set up Kafka consumer
        consumer = AIOKafkaConsumer(
            settings.CJ_ASSESSMENT_REQUEST_TOPIC,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=settings.CONSUMER_GROUP_ID_CJ,
            auto_offset_reset="latest",
            enable_auto_commit=False,
        )

        await consumer.start()
        logger.info(f"Kafka consumer started for topic: {settings.CJ_ASSESSMENT_REQUEST_TOPIC}")

        # Get dependencies from container
        content_client = await container.get(ContentClientProtocol)
        event_publisher = await container.get(CJEventPublisherProtocol)
        llm_interaction = await container.get(LLMInteractionProtocol)

        logger.info("CJ Assessment Service worker ready")

        # Message consumption loop
        try:
            async for msg in consumer:
                if shutdown_event.is_set():
                    break

                try:
                    success = await process_single_message(
                        msg=msg,
                        database=database,
                        content_client=content_client,
                        event_publisher=event_publisher,
                        llm_interaction=llm_interaction,
                        settings_obj=settings,
                    )

                    if success:
                        await consumer.commit()
                        logger.debug(f"Message committed: {msg.topic}:{msg.partition}:{msg.offset}")
                    else:
                        logger.warning(
                            f"Message processing failed, not committing: "
                            f"{msg.topic}:{msg.partition}:{msg.offset}"
                        )

                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("Message consumption cancelled")
        finally:
            await consumer.stop()
            logger.info("Kafka consumer stopped")

    except Exception as e:
        logger.error(f"Worker initialization failed: {e}", exc_info=True)
        raise
    finally:
        await container.close()
        logger.info("CJ Assessment Service worker shutdown complete")


def signal_handler(signum: int, frame: Any) -> None:
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    shutdown_event.set()


if __name__ == "__main__":
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"CJ Assessment Service worker failed: {e}", exc_info=True)
        sys.exit(1)
