"""
Kafka consumer logic for CJ Assessment Service.

Handles CJ assessment request message processing using injected dependencies.
Follows clean architecture with DI pattern.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError
from huleedu_service_libs.idempotency import idempotent_consumer
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.event_processor import process_single_message
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)

logger = create_service_logger("cj_assessment.kafka.consumer")


class CJAssessmentKafkaConsumer:
    """Kafka consumer for handling CJ assessment request events."""

    def __init__(
        self,
        settings: Settings,
        database: CJRepositoryProtocol,
        content_client: ContentClientProtocol,
        event_publisher: CJEventPublisherProtocol,
        llm_interaction: LLMInteractionProtocol,
        redis_client: RedisClientProtocol,
        tracer: "Tracer | None" = None,
    ) -> None:
        """Initialize with injected dependencies."""
        self.settings = settings
        self.database = database
        self.content_client = content_client
        self.event_publisher = event_publisher
        self.llm_interaction = llm_interaction
        self.redis_client = redis_client
        self.tracer = tracer
        self.consumer: AIOKafkaConsumer | None = None
        self.should_stop = False

        # Create idempotent message processor with 24-hour TTL
        @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
        async def process_message_idempotently(msg: Any) -> bool | None:
            return await process_single_message(
                msg=msg,
                database=self.database,
                content_client=self.content_client,
                event_publisher=self.event_publisher,
                llm_interaction=self.llm_interaction,
                settings_obj=self.settings,
                tracer=self.tracer,
            )

        self._process_message_idempotently = process_message_idempotently

    async def start_consumer(self) -> None:
        """Start the Kafka consumer and begin processing messages."""
        # Initialize database schema
        await self.database.initialize_db_schema()
        logger.info("Database schema initialized")

        # Create Kafka consumer
        self.consumer = AIOKafkaConsumer(
            self.settings.CJ_ASSESSMENT_REQUEST_TOPIC,
            bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=self.settings.CONSUMER_GROUP_ID_CJ,
            auto_offset_reset="latest",
            enable_auto_commit=False,
        )

        try:
            await self.consumer.start()
            logger.info(
                "CJ Assessment Kafka consumer started",
                extra={
                    "topic": self.settings.CJ_ASSESSMENT_REQUEST_TOPIC,
                    "group_id": self.settings.CONSUMER_GROUP_ID_CJ,
                },
            )

            # Start message processing loop
            await self._process_messages()

        except asyncio.CancelledError:
            logger.info("Kafka consumer task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in CJ Assessment Kafka consumer: {e}", exc_info=True)
            raise
        finally:
            await self.stop_consumer()

    async def stop_consumer(self) -> None:
        """Stop the Kafka consumer gracefully."""
        self.should_stop = True
        if self.consumer:
            try:
                await self.consumer.stop()
                logger.info("CJ Assessment Kafka consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping CJ Assessment Kafka consumer: {e}")
            finally:
                self.consumer = None

    async def _process_messages(self) -> None:
        """Main message processing loop."""
        if not self.consumer:
            return

        logger.info("Starting CJ Assessment message processing loop")

        while not self.should_stop:
            try:
                async for msg in self.consumer:
                    if self.should_stop:
                        break

                    try:
                        result = await self._process_message_idempotently(msg)

                        if result is not None:
                            # Only commit if not a skipped duplicate
                            if result:
                                await self.consumer.commit()
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

            except KafkaConnectionError as kce:
                logger.error(f"Kafka connection error: {kce}", exc_info=True)
                if self.should_stop:
                    break
                await asyncio.sleep(5)  # Wait before retry
            except asyncio.CancelledError:
                logger.info("Message consumption cancelled")
                break
            except Exception as e:
                logger.error(f"Error in message processing loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying

        logger.info("CJ Assessment message processing loop has finished")
