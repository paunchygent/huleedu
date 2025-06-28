"""Hardened Kafka consumer for Result Aggregator Service."""

import asyncio
import json
from typing import Any, Dict, List

from aiokafka import AIOKafkaConsumer, ConsumerRecord
from huleedu_service_libs.idempotency import idempotent_consumer
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events import (
    BatchEssaysRegistered,
    CJAssessmentCompletedV1,
    ELSBatchPhaseOutcomeV1,
    EventEnvelope,
    SpellcheckResultDataV1,
)

from .config import Settings
from .metrics import ResultAggregatorMetrics
from .protocols import EventProcessorProtocol

logger = create_service_logger("result_aggregator.kafka_consumer")


class ResultAggregatorKafkaConsumer:
    """Kafka consumer with production-grade error handling."""

    def __init__(
        self,
        settings: Settings,
        event_processor: EventProcessorProtocol,
        metrics: ResultAggregatorMetrics,
        redis_client: RedisClientProtocol,
    ):
        """Initialize the consumer."""
        self.settings = settings
        self.event_processor = event_processor
        self.metrics = metrics
        self.redis_client = redis_client
        self._running = False
        self.consumer: AIOKafkaConsumer | None = None

        # Topic subscription list - current services only
        self.topics = [
            topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),  # Add batch registration
            "huleedu.els.batch_phase.outcome.v1",
            "huleedu.essay.spellcheck.completed.v1",
            "huleedu.cj_assessment.completed.v1",
            # Future topics to add when services are implemented:
            # "huleedu.essay.nlp.completed.v1",
            # "huleedu.essay.aifeedback.completed.v1",
        ]

        # Create idempotent message processor with 24-hour TTL
        @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
        async def process_message_idempotently(msg: ConsumerRecord) -> bool:
            return await self._process_message_impl(msg)

        self._process_message_idempotently = process_message_idempotently

    async def start(self) -> None:
        """Start the consumer loop."""
        logger.info("Starting Result Aggregator Kafka consumer", topics=self.topics)
        self._running = True

        # Create consumer
        self.consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=self.settings.KAFKA_CONSUMER_GROUP_ID,
            client_id="result-aggregator-consumer",
            auto_offset_reset=self.settings.KAFKA_AUTO_OFFSET_RESET,
            enable_auto_commit=False,  # Manual commits for reliability
            session_timeout_ms=self.settings.KAFKA_SESSION_TIMEOUT_MS,
            max_poll_records=self.settings.KAFKA_MAX_POLL_RECORDS,
        )

        try:
            await self.consumer.start()
            logger.info("Kafka consumer started successfully")

            while self._running:
                try:
                    # Fetch messages with timeout
                    messages = await self.consumer.getmany(
                        timeout_ms=1000, max_records=self.settings.KAFKA_MAX_POLL_RECORDS
                    )

                    if messages:
                        await self._process_batch(messages)

                except asyncio.CancelledError:
                    logger.info("Consumer cancelled, shutting down")
                    break
                except Exception as e:
                    logger.error("Error in consumer loop", error=str(e), exc_info=True)
                    self.metrics.consumer_errors.inc()
                    await asyncio.sleep(1)  # Brief pause before retry

        finally:
            if self.consumer:
                await self.consumer.stop()
            logger.info("Kafka consumer stopped")

    async def stop(self) -> None:
        """Stop the consumer gracefully."""
        logger.info("Stopping Result Aggregator Kafka consumer")
        self._running = False

    async def _process_batch(self, messages: Dict[str, List[ConsumerRecord]]) -> None:
        """Process a batch of messages with manual commits."""
        for topic, records in messages.items():
            for record in records:
                try:
                    with self.metrics.message_processing_time.time():
                        result = await self._process_message_idempotently(record)

                    # Handle three states: True (success), False (business failure),
                    # None (duplicate). Commit offset for all cases to avoid reprocessing
                    if result is not None:  # Successfully processed
                        self.metrics.messages_processed.inc()
                    else:  # Duplicate message
                        logger.debug(
                            "Duplicate message skipped",
                            topic=topic,
                            partition=record.partition,
                            offset=record.offset,
                        )

                    # Always commit to avoid reprocessing
                    if self.consumer:
                        await self.consumer.commit()

                except Exception as e:
                    logger.error(
                        "Failed to process message",
                        topic=topic,
                        partition=record.partition,
                        offset=record.offset,
                        error=str(e),
                        exc_info=True,
                    )

                    # Log error - DLQ handling is BOS responsibility
                    self.metrics.consumer_errors.inc()

                    # Still commit to avoid reprocessing
                    if self.consumer:
                        await self.consumer.commit()

    async def _process_message_impl(self, record: ConsumerRecord) -> bool:
        """Process a single message implementation."""
        try:
            # Parse the event envelope
            envelope_data = json.loads(record.value.decode("utf-8"))
            envelope: EventEnvelope[Any] = EventEnvelope.model_validate(envelope_data)

            # Route to appropriate handler based on topic
            if record.topic == topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED):
                batch_registered_data = BatchEssaysRegistered.model_validate(envelope.data)
                await self.event_processor.process_batch_registered(envelope, batch_registered_data)

            elif record.topic == "huleedu.els.batch_phase.outcome.v1":
                batch_phase_data = ELSBatchPhaseOutcomeV1.model_validate(envelope.data)
                await self.event_processor.process_batch_phase_outcome(envelope, batch_phase_data)

            elif record.topic == "huleedu.essay.spellcheck.completed.v1":
                spellcheck_data = SpellcheckResultDataV1.model_validate(envelope.data)
                await self.event_processor.process_spellcheck_completed(envelope, spellcheck_data)

            elif record.topic == "huleedu.cj_assessment.completed.v1":
                cj_assessment_data = CJAssessmentCompletedV1.model_validate(envelope.data)
                await self.event_processor.process_cj_assessment_completed(
                    envelope, cj_assessment_data
                )

            else:
                logger.warning(f"Unhandled topic: {record.topic}")

            return True  # Successfully processed

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Processing failed: {str(e)}")
            raise
