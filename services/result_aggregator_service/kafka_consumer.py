"""Hardened Kafka consumer for Result Aggregator Service."""
import asyncio
import json
from typing import Any

from aiokafka import ConsumerRecord
from dishka import AsyncContainer

from common_core.enums import ServiceName
from common_core.events import EventEnvelope
from huleedu_service_libs.idempotency import idempotent_consumer
from huleedu_service_libs.logging_utils import create_service_logger

from .metrics import ResultAggregatorMetrics
from .protocols import EventProcessorProtocol, StateStoreProtocol

logger = create_service_logger("result_aggregator.kafka_consumer")


class ResultAggregatorKafkaConsumer:
    """Kafka consumer with production-grade error handling."""

    def __init__(
        self,
        kafka_bus: Any,  # KafkaBus type
        container: AsyncContainer,
        metrics: ResultAggregatorMetrics,
        redis_client: Any,  # RedisClientProtocol
    ):
        """Initialize the consumer."""
        self.kafka_bus = kafka_bus
        # DLQ handling is BOS responsibility
        self.container = container
        self.metrics = metrics
        self.redis_client = redis_client
        self._running = False

        # Topic subscription list - current services only
        self.topics = [
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

        try:
            await self.kafka_bus.start()
            await self.kafka_bus.subscribe(self.topics)

            while self._running:
                try:
                    # Fetch messages with timeout
                    messages = await self.kafka_bus.get_many(
                        timeout_ms=1000, max_records=100
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
            await self.kafka_bus.stop()
            logger.info("Kafka consumer stopped")

    async def stop(self) -> None:
        """Stop the consumer gracefully."""
        logger.info("Stopping Result Aggregator Kafka consumer")
        self._running = False

    async def _process_batch(self, messages: dict[str, list[ConsumerRecord]]) -> None:
        """Process a batch of messages with manual commits."""
        for topic, records in messages.items():
            for record in records:
                try:
                    with self.metrics.message_processing_time.time():
                        result = await self._process_message_idempotently(record)

                    # Handle three states: True (success), False (business failure), None (duplicate)
                    # Commit offset for all cases to avoid reprocessing
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
                    await self.kafka_bus.commit()

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
                    await self.kafka_bus.commit()

    async def _process_message_impl(self, record: ConsumerRecord) -> bool:
        """Process a single message implementation."""
        try:
            # Parse the event envelope
            envelope_data = json.loads(record.value.decode("utf-8"))
            envelope = EventEnvelope.model_validate(envelope_data)

            # Route to appropriate handler based on topic
            async with self.container() as request_container:
                processor = await request_container.get(EventProcessorProtocol)

                if record.topic == "huleedu.els.batch_phase.outcome.v1":
                    # Import here to avoid circular dependency
                    from common_core.events import ELSBatchPhaseOutcomeV1

                    data = ELSBatchPhaseOutcomeV1.model_validate(envelope.data)
                    await processor.process_batch_phase_outcome(envelope, data)

                elif record.topic == "huleedu.essay.spellcheck.completed.v1":
                    # Use the correct event type from common_core
                    from common_core.events import SpellcheckResultDataV1

                    data = SpellcheckResultDataV1.model_validate(envelope.data)
                    await processor.process_spellcheck_completed(envelope, data)

                elif record.topic == "huleedu.cj_assessment.completed.v1":
                    from common_core.events import CJAssessmentCompletedV1

                    data = CJAssessmentCompletedV1.model_validate(envelope.data)
                    await processor.process_cj_assessment_completed(envelope, data)

                else:
                    logger.warning(f"Unhandled topic: {record.topic}")

            return True  # Successfully processed

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Processing failed: {str(e)}")
            raise

    async def _handle_processing_error(
        self, record: ConsumerRecord, error: Exception
    ) -> None:
        """Handle processing errors with DLQ production."""
        retry_count = 0
        if record.headers:
            for key, value in record.headers:
                if key == "retry_count":
                    retry_count = int(value.decode("utf-8"))

        if retry_count >= self.dlq_max_retries:
            # Send to DLQ
            await self.dlq_producer.send_to_dlq(
                original_topic=record.topic,
                original_value=record.value,
                error_message=str(error),
                service_name=ServiceName.RESULT_AGGREGATOR,
                correlation_id=None,  # Extract from envelope if available
            )
            self.metrics.dlq_messages_sent.inc()
            logger.error(
                "Message sent to DLQ after max retries",
                topic=record.topic,
                retry_count=retry_count,
                error=str(error),
            )
        else:
            # Would implement retry logic here in production
            logger.warning(
                "Message processing failed, retry logic not implemented",
                topic=record.topic,
                retry_count=retry_count,
                error=str(error),
            )