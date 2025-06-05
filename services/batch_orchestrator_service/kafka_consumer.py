"""
Kafka consumer logic for Batch Orchestrator Service.

Handles message routing to specialized handlers for BatchEssaysReady and ELSBatchPhaseOutcomeV1.
Refactored to follow clean architecture with extracted message handlers.
"""

from __future__ import annotations

from typing import Any

from aiokafka import AIOKafkaConsumer
from huleedu_service_libs.logging_utils import create_service_logger
from implementations.batch_essays_ready_handler import BatchEssaysReadyHandler
from implementations.els_batch_phase_outcome_handler import ELSBatchPhaseOutcomeHandler

from common_core.enums import ProcessingEvent, topic_name

logger = create_service_logger("bos.kafka.consumer")


class BatchKafkaConsumer:
    """Kafka consumer for handling BatchEssaysReady events and phase transitions."""

    def __init__(
        self,
        kafka_bootstrap_servers: str,
        consumer_group: str,
        batch_essays_ready_handler: BatchEssaysReadyHandler,
        els_batch_phase_outcome_handler: ELSBatchPhaseOutcomeHandler,
    ) -> None:
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.consumer_group = consumer_group
        self.batch_essays_ready_handler = batch_essays_ready_handler
        self.els_batch_phase_outcome_handler = els_batch_phase_outcome_handler
        self.consumer: AIOKafkaConsumer | None = None
        self.should_stop = False

    async def start_consumer(self) -> None:
        """Start the Kafka consumer and begin processing messages."""
        # Subscribe to BatchEssaysReady topic and ELS batch phase outcome topic (Phase 3)
        topics = [
            topic_name(ProcessingEvent.BATCH_ESSAYS_READY),
            "huleedu.els.batch_phase.outcome.v1",  # ELSBatchPhaseOutcomeV1 events from ELS
        ]

        # TODO: Add subscription to ExcessContentProvisionedV1 topic for handling
        # excess content that couldn't be assigned to essay slots. Handler should
        # log the event and potentially update batch metadata or alert administrators.
        # topics.append(topic_name(ProcessingEvent.EXCESS_CONTENT_PROVISIONED))

        self.consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self.kafka_bootstrap_servers,
            group_id=self.consumer_group,
            client_id="bos-pipeline-initiator",
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            auto_commit_interval_ms=1000,
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
        """Main message processing loop."""
        if not self.consumer:
            return

        logger.info("Starting BOS message processing loop")

        try:
            async for msg in self.consumer:
                if self.should_stop:
                    logger.info("Shutdown requested, stopping BOS message processing")
                    break

                try:
                    await self._handle_message(msg)
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
            else:
                logger.warning(f"Received message from unknown topic: {msg.topic}")

        except Exception as e:
            logger.error(f"Error handling message from topic {msg.topic}: {e}", exc_info=True)
            raise
