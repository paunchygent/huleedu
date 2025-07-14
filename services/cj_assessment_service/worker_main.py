"""Kafka consumer worker main for CJ Assessment Service."""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

from aiokafka import AIOKafkaConsumer
from dishka import make_async_container
from huleedu_service_libs import init_tracing
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer_v2
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol
from sqlalchemy.ext.asyncio import create_async_engine

from services.cj_assessment_service.config import settings
from services.cj_assessment_service.di import CJAssessmentServiceProvider
from services.cj_assessment_service.event_processor import process_single_message
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
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

    # Initialize tracing (this sets up the global tracer provider)
    tracer = init_tracing("cj_assessment_service")
    logger.info("OpenTelemetry tracing initialized")

    # Initialize database engine for DI container
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        future=True,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
        pool_recycle=settings.DATABASE_POOL_RECYCLE,
    )

    # Initialize Dishka container with engine
    container = make_async_container(CJAssessmentServiceProvider(engine=engine))

    try:
        async with container() as request_container:
            # Initialize database schema
            database = await request_container.get(CJRepositoryProtocol)
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
            content_client = await request_container.get(ContentClientProtocol)
            event_publisher = await request_container.get(CJEventPublisherProtocol)
            llm_interaction = await request_container.get(LLMInteractionProtocol)
            redis_client = await request_container.get(RedisClientProtocol)
            tracer = await request_container.get(Tracer)

            logger.info("CJ Assessment Service worker ready with idempotency support")

            # Apply idempotency decorator to message processing with v2 configuration
            config = IdempotencyConfig(
                service_name="cj-assessment-service",
                default_ttl=86400,  # 24 hours for complex AI processing
                enable_debug_logging=True,  # Enable for AI workflow monitoring
            )
            
            @idempotent_consumer_v2(redis_client=redis_client, config=config)
            async def handle_message_idempotently(msg: Any) -> bool:
                return await process_single_message(
                    msg=msg,
                    database=database,
                    content_client=content_client,
                    event_publisher=event_publisher,
                    llm_interaction=llm_interaction,
                    settings_obj=settings,
                    tracer=tracer,
                )

            # Message consumption loop with idempotency support
            try:
                async for msg in consumer:
                    if shutdown_event.is_set():
                        break

                    try:
                        result = await handle_message_idempotently(msg)

                        if result is not None:
                            # Only commit if not a skipped duplicate
                            if result:
                                await consumer.commit()
                                logger.debug(
                                    "Message committed: %s:%s:%s",
                                    msg.topic,
                                    msg.partition,
                                    msg.offset,
                                )
                            else:
                                logger.warning(
                                    f"Message processing failed, not committing: "
                                    f"{msg.topic}:{msg.partition}:{msg.offset}",
                                )
                        else:
                            # Message was a duplicate and skipped
                            logger.info(
                                f"Duplicate message skipped, not committing offset: "
                                f"{msg.topic}:{msg.partition}:{msg.offset}",
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
