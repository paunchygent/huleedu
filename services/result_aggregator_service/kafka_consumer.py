"""Hardened Kafka consumer for Result Aggregator Service."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Awaitable, Callable, Dict, List

from aiokafka import AIOKafkaConsumer, ConsumerRecord
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events import (
    BatchEssaysRegistered,
    CJAssessmentCompletedV1,
    ELSBatchPhaseOutcomeV1,
    EventEnvelope,
    SpellcheckResultDataV1,
)
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol
from pydantic import ValidationError

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.metrics import ResultAggregatorMetrics
from services.result_aggregator_service.protocols import EventProcessorProtocol

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
            topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED),  # Add slot assignment for traceability
            topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME),
            topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
            topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
            # Future topics to add when services are implemented:
            # "huleedu.essay.nlp.completed.v1",
            # "huleedu.essay.aifeedback.completed.v1",
        ]

        # Create idempotency configuration for Result Aggregator Service
        # Aggregation operations need longer retention for batch completion workflows
        idempotency_config = IdempotencyConfig(
            service_name="result-aggregator-service",
            # Override specific TTLs for result aggregator events by Pydantic class name
            event_type_ttls={
                # Batch registration and coordination events (12 hours)
                "BatchEssaysRegistered": 43200,
                "EssaySlotAssignedV1": 43200,  # Slot assignment for traceability
                "ELSBatchPhaseOutcomeV1": 43200,
                # Processing completion events (24 hours)
                "SpellcheckResultDataV1": 86400,
                "CJAssessmentCompletedV1": 86400,
                # Aggregation completion events (72 hours for batch lifecycle)
                "ResultAggregatorBatchCompletedV1": 259200,
                "ResultAggregatorClassSummaryUpdatedV1": 259200,
            },
            default_ttl=86400,  # 24 hours for unknown events
            enable_debug_logging=True,  # Enhanced observability for aggregation workflows
        )

        # Create idempotent message processor with v2 configuration
        @idempotent_consumer(redis_client=redis_client, config=idempotency_config)
        async def process_message_idempotently(
            msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Awaitable[None]]
        ) -> bool:
            result = await self._process_message_impl(msg)
            await confirm_idempotency()  # Confirm after successful processing
            return result

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
        """Process a single message implementation with specific deserialization."""
        try:
            # Decode the message value once
            message_value_str = record.value.decode("utf-8")

            # Route to appropriate handler based on topic
            if record.topic == topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED):
                # Deserialize with the specific, expected Pydantic model
                batch_envelope = EventEnvelope[BatchEssaysRegistered].model_validate_json(
                    message_value_str
                )
                await self.event_processor.process_batch_registered(
                    batch_envelope, BatchEssaysRegistered.model_validate(batch_envelope.data)
                )

            elif record.topic == topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME):
                phase_envelope = EventEnvelope[ELSBatchPhaseOutcomeV1].model_validate_json(
                    message_value_str
                )
                await self.event_processor.process_batch_phase_outcome(
                    phase_envelope, ELSBatchPhaseOutcomeV1.model_validate(phase_envelope.data)
                )

            elif record.topic == topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED):
                spell_envelope = EventEnvelope[SpellcheckResultDataV1].model_validate_json(
                    message_value_str
                )
                await self.event_processor.process_spellcheck_completed(
                    spell_envelope, SpellcheckResultDataV1.model_validate(spell_envelope.data)
                )

            elif record.topic == topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED):
                cj_envelope = EventEnvelope[CJAssessmentCompletedV1].model_validate_json(
                    message_value_str
                )
                await self.event_processor.process_cj_assessment_completed(
                    cj_envelope, CJAssessmentCompletedV1.model_validate(cj_envelope.data)
                )

            elif record.topic == topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED):
                # Import here to avoid circular imports
                from common_core.events.essay_lifecycle_events import EssaySlotAssignedV1

                slot_envelope = EventEnvelope[EssaySlotAssignedV1].model_validate_json(
                    message_value_str
                )
                await self.event_processor.process_essay_slot_assigned(
                    slot_envelope, EssaySlotAssignedV1.model_validate(slot_envelope.data)
                )

            else:
                logger.warning(f"Unhandled topic: {record.topic}")

            return True  # Successfully processed

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(
                "Failed to deserialize or validate message",
                topic=record.topic,
                error=str(e),
                exc_info=True,
            )
            # Increment the invalid messages metric
            self.metrics.invalid_messages_total.labels(
                topic=record.topic, error_type=e.__class__.__name__
            ).inc()

            # Store poison pill for inspection if enabled
            if self.settings.STORE_POISON_PILLS:
                try:
                    poison_pill_key = (
                        f"poison_pill:{record.topic}:{record.partition}:{record.offset}"
                    )
                    poison_pill_data = json.dumps(
                        {
                            "raw_value": record.value.decode("utf-8", errors="replace"),
                            "error": str(e),
                            "error_type": e.__class__.__name__,
                            "timestamp": datetime.now(UTC).isoformat(),
                            "topic": record.topic,
                            "partition": record.partition,
                            "offset": record.offset,
                        }
                    )
                    await self.redis_client.setex(
                        poison_pill_key,
                        self.settings.POISON_PILL_TTL_SECONDS,
                        poison_pill_data,
                    )
                    logger.info(
                        "Stored poison pill for inspection",
                        key=poison_pill_key,
                        ttl=self.settings.POISON_PILL_TTL_SECONDS,
                    )
                except Exception as storage_error:
                    logger.warning(
                        "Failed to store poison pill",
                        error=str(storage_error),
                        topic=record.topic,
                        offset=record.offset,
                    )

            # Check if we should raise the error (for testing)
            if self.settings.RAISE_ON_DESERIALIZATION_ERROR:
                raise

            # We will not re-raise the error, allowing the consumer to commit the offset
            # and avoid getting stuck on a poison pill message.
            # Failures should be monitored via logs and DLQ in a production environment.
            return True  # Acknowledge message to prevent reprocessing
        except Exception as e:
            logger.error(
                "Processing failed with an unexpected error",
                topic=record.topic,
                error=str(e),
                exc_info=True,
            )
            raise  # Re-raise to allow the idempotency v2 decorator to handle it
