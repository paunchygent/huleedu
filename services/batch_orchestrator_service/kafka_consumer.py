"""
Kafka consumer logic for Batch Orchestrator Service.

Handles message routing to specialized handlers for BatchEssaysReady, ELSBatchPhaseOutcomeV1,
and ClientBatchPipelineRequestV1 events.
Refactored to follow clean architecture with extracted message handlers.
"""

from __future__ import annotations

from typing import Any

from aiokafka import AIOKafkaConsumer
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol
from implementations.batch_essays_ready_handler import BatchEssaysReadyHandler
from implementations.client_pipeline_request_handler import ClientPipelineRequestHandler
from implementations.els_batch_phase_outcome_handler import ELSBatchPhaseOutcomeHandler

from common_core.enums import ProcessingEvent, topic_name

logger = create_service_logger("bos.kafka.consumer")


class BatchKafkaConsumer:
    """Kafka consumer for handling BatchEssaysReady events,
    phase transitions, and client pipeline requests."""

    def __init__(
        self,
        kafka_bootstrap_servers: str,
        consumer_group: str,
        batch_essays_ready_handler: BatchEssaysReadyHandler,
        els_batch_phase_outcome_handler: ELSBatchPhaseOutcomeHandler,
        client_pipeline_request_handler: ClientPipelineRequestHandler,
        redis_client: RedisClientProtocol,
    ) -> None:
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.consumer_group = consumer_group
        self.batch_essays_ready_handler = batch_essays_ready_handler
        self.els_batch_phase_outcome_handler = els_batch_phase_outcome_handler
        self.client_pipeline_request_handler = client_pipeline_request_handler
        self.redis_client = redis_client
        self.consumer: AIOKafkaConsumer | None = None
        self.should_stop = False

    async def start_consumer(self) -> None:
        """Start the Kafka consumer and begin processing messages."""
        # Subscribe to all relevant topics
        topics = [
            topic_name(ProcessingEvent.BATCH_ESSAYS_READY),
            "huleedu.els.batch_phase.outcome.v1",  # ELSBatchPhaseOutcomeV1 events from ELS
            "huleedu.commands.batch.pipeline.v1",  # ClientBatchPipelineRequestV1 from API Gateway
        ]

        # TODO: Add subscription to ExcessContentProvisionedV1 topic for handling
        # excess content that couldn't be assigned to essay slots. Handler should
        # log the event and potentially update batch metadata or alert administrators.
        # topics.append(topic_name(ProcessingEvent.EXCESS_CONTENT_PROVISIONED))

        self.consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self.kafka_bootstrap_servers,
            group_id=self.consumer_group,
            client_id="bos-pipeline-orchestrator",
            auto_offset_reset="earliest",
            enable_auto_commit=False,  # Manual commit for reliable message processing
        )

        try:
            await self.consumer.start()
            logger.info(
                "BOS Kafka consumer started",
                extra={
                    "group_id": self.consumer_group,
                    "topics": list(self.consumer.subscription()),
                },
            )

            # Start message processing loop
            await self._process_messages()

        except Exception as e:
            logger.error(f"Error starting BOS Kafka consumer: {e}")
            raise
        finally:
            await self.stop_consumer()

    async def stop_consumer(self) -> None:
        """Stop the Kafka consumer gracefully."""
        self.should_stop = True
        if self.consumer:
            try:
                await self.consumer.stop()
                logger.info("BOS Kafka consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping BOS Kafka consumer: {e}")
            finally:
                self.consumer = None

    async def _process_messages(self) -> None:
        """Main message processing loop with idempotency support."""
        if not self.consumer:
            return

        logger.info("Starting BOS message processing loop with idempotency")

        # Import decorator locally to avoid circular imports
        from huleedu_service_libs.idempotency import idempotent_consumer

        # Apply idempotency decorator (following ELS pattern exactly)
        @idempotent_consumer(redis_client=self.redis_client, ttl_seconds=86400)
        async def handle_message_idempotently(msg: Any) -> bool:
            await self._handle_message(msg)
            return True  # Success - existing _handle_message raises on failure

        try:
            async for msg in self.consumer:
                if self.should_stop:
                    logger.info("Shutdown requested, stopping BOS message processing")
                    break

                try:
                    result = await handle_message_idempotently(msg)

                    if result is not None:
                        # Only commit if not a skipped duplicate
                        if result:
                            # Commit offset only after successful processing (manual commit pattern)
                            await self.consumer.commit()
                            logger.debug(
                                "Successfully processed and committed BOS message",
                                extra={
                                    "topic": msg.topic,
                                    "partition": msg.partition,
                                    "offset": msg.offset,
                                },
                            )
                        else:
                            logger.warning(
                                "Failed to process message, not committing offset",
                                extra={
                                    "topic": msg.topic,
                                    "partition": msg.partition,
                                    "offset": msg.offset,
                                },
                            )
                    else:
                        # Message was a duplicate and skipped
                        logger.info(
                            "Duplicate message skipped, not committing offset",
                            extra={
                                "topic": msg.topic,
                                "partition": msg.partition,
                                "offset": msg.offset,
                            },
                        )

                except Exception as e:
                    logger.error(
                        "Error processing message in BOS",
                        extra={
                            "error": str(e),
                            "topic": msg.topic,
                            "partition": msg.partition,
                            "offset": msg.offset,
                        },
                    )
        except Exception as e:
            logger.error(f"Error in BOS message processing loop: {e}")
            raise

    async def _handle_message(self, msg: Any) -> None:
        """Handle a single Kafka message based on topic type."""
        try:
            if msg.topic == topic_name(ProcessingEvent.BATCH_ESSAYS_READY):
                await self.batch_essays_ready_handler.handle_batch_essays_ready(msg)
            elif msg.topic == "huleedu.els.batch_phase.outcome.v1":
                await self.els_batch_phase_outcome_handler.handle_els_batch_phase_outcome(msg)
            elif msg.topic == "huleedu.commands.batch.pipeline.v1":
                await self.client_pipeline_request_handler.handle_client_pipeline_request(msg)
            else:
                logger.warning(f"Received message from unknown topic: {msg.topic}")

        except Exception as e:
            logger.error(f"Error handling message from topic {msg.topic}: {e}", exc_info=True)
            raise
