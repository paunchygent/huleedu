"""
Kafka consumer for Batch Conductor Service.

Consumes processing result events from specialized services to build real-time
batch processing state for intelligent pipeline dependency resolution.

Follows established patterns from spell_checker_service and cj_assessment_service.
"""

from __future__ import annotations

import asyncio
import json

from aiokafka import AIOKafkaConsumer, ConsumerRecord

from common_core.enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import CJAssessmentCompletedV1
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from huleedu_service_libs.idempotency import idempotent_consumer
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol
from services.batch_conductor_service.protocols import BatchStateRepositoryProtocol

logger = create_service_logger("bcs.kafka_consumer")


class BCSKafkaConsumer:
    """
    Kafka consumer for BCS processing result events.

    Consumes completion events from specialized services and updates the
    BatchStateRepository for intelligent pipeline dependency resolution.
    """

    def __init__(
        self,
        kafka_bootstrap_servers: str,
        consumer_group: str,
        batch_state_repo: BatchStateRepositoryProtocol,
        redis_client: RedisClientProtocol,
    ):
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.consumer_group = consumer_group
        self.batch_state_repo = batch_state_repo
        self.redis_client = redis_client
        self._consumer: AIOKafkaConsumer | None = None
        self._consuming = False
        self._stop_event = asyncio.Event()

    async def start_consuming(self) -> None:
        """Start consuming Kafka events with topic subscription."""
        if self._consuming:
            raise RuntimeError("Consumer is already running")

        try:
            # Subscribe to processing result topics
            topics = [
                topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
                topic_name(ProcessingEvent.ESSAY_AIFEEDBACK_COMPLETED),
                topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
                # Add more specialized service result topics as needed
            ]

            self._consumer = AIOKafkaConsumer(
                *topics,
                bootstrap_servers=self.kafka_bootstrap_servers,
                group_id=self.consumer_group,
                enable_auto_commit=False,  # Manual commit for reliability
                auto_offset_reset="latest",  # Only new events
                value_deserializer=lambda m: m.decode("utf-8"),
            )

            await self._consumer.start()
            self._consuming = True
            logger.info(f"BCS Kafka consumer started, subscribed to topics: {topics}")

            # Start consumption loop
            await self._consume_loop()

        except Exception as e:
            logger.error(f"Failed to start BCS Kafka consumer: {e}", exc_info=True)
            if self._consumer:
                await self._consumer.stop()
            raise

    async def stop_consuming(self) -> None:
        """Stop consuming Kafka events gracefully."""
        if not self._consuming:
            return

        self._stop_event.set()
        self._consuming = False

        if self._consumer:
            try:
                await self._consumer.stop()
                logger.info("BCS Kafka consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping BCS Kafka consumer: {e}", exc_info=True)

    async def is_consuming(self) -> bool:
        """Check if consumer is actively consuming events."""
        return self._consuming

    async def _consume_loop(self) -> None:
        """Main consumption loop with signal handling."""
        if self._consumer is None:
            raise RuntimeError("Consumer not initialized")

        try:
            async for msg in self._consumer:
                if self._stop_event.is_set():
                    break

                try:
                    # Apply idempotency decorator
                    idempotent_handler = idempotent_consumer(
                        redis_client=self.redis_client, ttl_seconds=86400
                    )(self._handle_message)

                    await idempotent_handler(msg)
                    await self._consumer.commit()
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    # Continue processing other messages

        except Exception as e:
            logger.error(f"Error in BCS consumption loop: {e}", exc_info=True)

    async def _handle_message(self, msg: ConsumerRecord) -> None:
        """Route messages to appropriate handlers based on topic."""
        try:
            if msg.topic == topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED):
                await self._handle_spellcheck_completed(msg)
            elif msg.topic == topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED):
                await self._handle_cj_assessment_completed(msg)
            else:
                logger.warning(f"Unknown topic: {msg.topic}")

        except Exception as e:
            logger.error(f"Error handling message from topic {msg.topic}: {e}", exc_info=True)
            raise

    async def _handle_spellcheck_completed(self, msg: ConsumerRecord) -> None:
        """Handle spellcheck completion events."""
        try:
            message_data = json.loads(msg.value)
            envelope = EventEnvelope[SpellcheckResultDataV1](**message_data)

            spellcheck_data = envelope.data
            essay_id = spellcheck_data.entity_ref.entity_id

            # Extract batch_id from entity_ref.parent_id or system_metadata
            batch_id = spellcheck_data.entity_ref.parent_id
            if not batch_id:
                # Fallback: try to get batch_id from system_metadata
                batch_id = spellcheck_data.system_metadata.entity.parent_id

            if not batch_id:
                logger.error(
                    f"Cannot determine batch_id for spellcheck result for essay {essay_id}"
                )
                return

            # Determine success based on status
            is_success = spellcheck_data.status.value in ["spellchecked_success"]

            # Record completion in batch state
            success = await self.batch_state_repo.record_essay_step_completion(
                batch_id=batch_id,
                essay_id=essay_id,
                step_name="spellcheck",
                metadata={
                    "completion_status": "success" if is_success else "failed",
                    "status": spellcheck_data.status.value,
                    "event_id": str(envelope.event_id),
                    "timestamp": envelope.event_timestamp.isoformat(),
                },
            )

            if success:
                logger.info(
                    f"Recorded spellcheck completion for essay {essay_id} in batch {batch_id}",
                    extra={"correlation_id": str(envelope.correlation_id)},
                )
            else:
                logger.error(f"Failed to record spellcheck completion for essay {essay_id}")

        except Exception as e:
            logger.error(f"Error processing spellcheck completion: {e}", exc_info=True)
            raise

    async def _handle_cj_assessment_completed(self, msg: ConsumerRecord) -> None:
        """Handle CJ assessment completion events."""
        try:
            message_data = json.loads(msg.value)
            envelope = EventEnvelope[CJAssessmentCompletedV1](**message_data)

            cj_data = envelope.data
            batch_id = cj_data.entity_ref.entity_id  # CJ assessment is batch-level

            # CJ assessment results contain ranking for multiple essays
            for ranking in cj_data.rankings:
                essay_id = ranking.get("els_essay_id")
                if essay_id:
                    # Record completion for each essay in the batch
                    success = await self.batch_state_repo.record_essay_step_completion(
                        batch_id=batch_id,
                        essay_id=essay_id,
                        step_name="cj_assessment",
                        metadata={
                            "completion_status": "success",
                            "cj_job_id": cj_data.cj_assessment_job_id,
                            "rank": ranking.get("rank"),
                            "score": ranking.get("score"),
                            "event_id": str(envelope.event_id),
                            "timestamp": envelope.event_timestamp.isoformat(),
                        },
                    )

                    if success:
                        logger.info(
                            f"Recorded CJ assessment completion for essay {essay_id} "
                            f"in batch {batch_id}",
                            extra={"correlation_id": str(envelope.correlation_id)},
                        )
                    else:
                        logger.error(
                            f"Failed to record CJ assessment completion for essay {essay_id}"
                        )

        except Exception as e:
            logger.error(f"Error processing CJ assessment completion: {e}", exc_info=True)
            raise
