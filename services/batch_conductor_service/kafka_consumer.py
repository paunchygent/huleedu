"""
Kafka consumer for Batch Conductor Service.

Consumes processing result events from specialized services to build real-time
batch processing state for intelligent pipeline dependency resolution.

Follows established patterns from spellchecker_service and cj_assessment_service.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiokafka import AIOKafkaConsumer, ConsumerRecord

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import CJAssessmentCompletedV1
from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.status_enums import EssayStatus, OperationStatus
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol
from services.batch_conductor_service.metrics import get_kafka_consumer_metrics
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
        self._metrics: dict[str, Any] | None = get_kafka_consumer_metrics()

        # Create idempotency configuration for Batch Conductor Service
        # Coordination events require longer retention for batch workflow coordination
        idempotency_config = IdempotencyConfig(
            service_name="batch-conductor-service",
            # Override specific TTLs for coordination events
            event_type_ttls={
                # SpellCheck completion events (24 hours - coordination requirements)
                "SpellcheckPhaseCompletedV1": 86400,  # New thin event for state transitions
                # CJ Assessment completion events (24 hours - coordination requirements)
                "CJAssessmentCompletedV1": 86400,
                topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED): 86400,
                # AI Feedback completion events (24 hours - coordination requirements)
                "huleedu.essay.aifeedback.completed.v1": 86400,
            },
            default_ttl=86400,  # 24 hours for coordination events
            enable_debug_logging=True,  # Enhanced observability for coordination workflows
        )

        # Create idempotent message processor with v2 configuration
        @idempotent_consumer(redis_client=redis_client, config=idempotency_config)
        async def handle_message_idempotently(msg: ConsumerRecord, *, confirm_idempotency) -> None:
            await self._handle_message(msg)
            await confirm_idempotency()  # Confirm after successful processing

        self._handle_message_idempotently = handle_message_idempotently

    async def start_consuming(self) -> None:
        """Start consuming Kafka events with topic subscription and retry on failure."""
        if self._consuming:
            raise RuntimeError("Consumer is already running")

        # Retry configuration
        max_retries = 10
        retry_delay = 1.0  # Start with 1 second
        max_delay = 60.0  # Max 60 seconds between retries

        for attempt in range(max_retries + 1):
            try:
                await self._attempt_start_consuming()
                # If we get here, connection was successful
                logger.info(f"BCS Kafka consumer connected successfully on attempt {attempt + 1}")
                break

            except Exception as e:
                if attempt < max_retries:
                    logger.warning(
                        f"BCS Kafka consumer connection attempt {attempt + 1}/{max_retries + 1} "
                        f"failed: {e}. Retrying in {retry_delay:.1f}s..."
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, max_delay)  # Exponential backoff with cap
                else:
                    logger.error(
                        f"Failed to start BCS Kafka consumer after {max_retries + 1} attempts: {e}",
                        exc_info=True,
                    )
                    if self._consumer:
                        try:
                            await self._consumer.stop()
                        except Exception:
                            pass  # Best effort cleanup
                    raise

    async def _attempt_start_consuming(self) -> None:
        """Single attempt to start consuming with proper cleanup on failure."""
        # Subscribe to processing result topics
        topics = [
            topic_name(
                ProcessingEvent.SPELLCHECK_PHASE_COMPLETED
            ),  # New thin event for batch coordination
            # topic_name(ProcessingEvent.ESSAY_AIFEEDBACK_COMPLETED),  # Not implemented yet
            topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
            topic_name(
                ProcessingEvent.ELS_BATCH_PHASE_OUTCOME
            ),  # ELS phase completions for dependency resolution
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

        try:
            await self._consumer.start()
            self._consuming = True
            logger.info(f"BCS Kafka consumer started, subscribed to topics: {topics}")

            # Start consumption loop
            await self._consume_loop()

        except Exception:
            # Cleanup on any failure
            self._consuming = False
            if self._consumer:
                try:
                    await self._consumer.stop()
                except Exception:
                    pass  # Best effort cleanup
            self._consumer = None
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

    async def is_healthy(self) -> bool:
        """Check if consumer is healthy and connected."""
        return self._consuming and self._consumer is not None

    async def _consume_loop(self) -> None:
        """Main consumption loop with signal handling and reconnection on failure."""
        if self._consumer is None:
            raise RuntimeError("Consumer not initialized")

        logger.info("BCS Kafka consumer entering consumption loop")

        try:
            async for msg in self._consumer:
                if self._stop_event.is_set():
                    logger.info("BCS Kafka consumer stopping due to stop event")
                    break

                try:
                    # Process message with idempotency v2
                    await self._handle_message_idempotently(msg)
                    await self._consumer.commit()
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    # Continue processing other messages

        except Exception as e:
            logger.error(f"Error in BCS consumption loop: {e}", exc_info=True)
            self._consuming = False
            raise  # Let the caller handle reconnection

        logger.info("BCS Kafka consumer exited consumption loop")

    async def _handle_message(self, msg: ConsumerRecord) -> None:
        """Route messages to appropriate handlers based on topic."""
        event_type = self._extract_event_type_from_topic(msg.topic)

        try:
            if msg.topic == topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED):
                await self._handle_spellcheck_phase_completed(msg)
                await self._track_event_success("spellcheck_phase_completed")
            elif msg.topic == topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED):
                await self._handle_cj_assessment_completed(msg)
                await self._track_event_success(event_type)
            elif msg.topic == topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME):
                await self._handle_els_batch_phase_outcome(msg)
                await self._track_event_success("els_batch_phase_outcome")
            else:
                logger.warning(f"Unknown topic: {msg.topic}")
                await self._track_event_failure(event_type, "unknown_topic")

        except Exception as e:
            logger.error(f"Error handling message from topic {msg.topic}: {e}", exc_info=True)
            await self._track_event_failure(event_type, "processing_error")
            raise

    def _extract_event_type_from_topic(self, topic: str) -> str:
        """Extract event type from Kafka topic name for metrics labeling."""
        # Convert topic name to event type for metrics
        # e.g., "huleedu.essay.spellcheck.completed.v1" -> "spellcheck_completed"
        # e.g., "huleedu.cj_assessment.completed.v1" -> "cj_assessment_completed"
        # e.g., "huleedu.ai.feedback.completed.v1" -> "ai_feedback_completed"
        parts = topic.split(".")
        if len(parts) >= 4:
            # Special handling for essay topics: skip "huleedu.essay"
            if len(parts) >= 5 and parts[0] == "huleedu" and parts[1] == "essay":
                # Skip first two parts (huleedu.essay) and last two parts (completed.v1)
                service_parts = parts[2:-2]
            else:
                # Skip first part (huleedu) and last two parts (completed.v1)
                service_parts = parts[1:-2]

            return f"{'_'.join(service_parts)}_completed"
        return "unknown_event"

    async def _track_event_success(self, event_type: str) -> None:
        """Track successful event processing in metrics."""
        if self._metrics and "events_processed_total" in self._metrics:
            self._metrics["events_processed_total"].labels(
                event_type=event_type, outcome=OperationStatus.SUCCESS.value
            ).inc()

    async def _track_event_failure(self, event_type: str, failure_reason: str) -> None:
        """Track failed event processing in metrics."""
        if self._metrics and "events_processed_total" in self._metrics:
            self._metrics["events_processed_total"].labels(
                event_type=event_type, outcome=failure_reason
            ).inc()

    async def _handle_spellcheck_completed(self, msg: ConsumerRecord) -> None:
        """Handle spellcheck completion events."""
        try:
            raw_message = msg.value  # Already decoded by deserializer
            envelope = EventEnvelope[SpellcheckResultDataV1].model_validate_json(raw_message)

            spellcheck_data = SpellcheckResultDataV1.model_validate(envelope.data)
            essay_id = spellcheck_data.entity_id
            if essay_id is None:
                logger.error("Cannot process spellcheck result: entity_id (essay_id) is None")
                return

            # Extract batch_id from parent_id or system_metadata
            batch_id = spellcheck_data.parent_id
            if not batch_id:
                # Fallback: try to get batch_id from system_metadata
                batch_id = spellcheck_data.system_metadata.parent_id

            if not batch_id:
                logger.error(
                    f"Cannot determine batch_id for spellcheck result for essay {essay_id}"
                )
                return

            # Determine success based on status
            is_success = spellcheck_data.status == EssayStatus.SPELLCHECKED_SUCCESS

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

    async def _handle_spellcheck_phase_completed(self, msg: ConsumerRecord) -> None:
        """Handle thin spellcheck phase completion events from dual event pattern."""
        try:
            from common_core.events.spellcheck_models import SpellcheckPhaseCompletedV1
            from common_core.status_enums import ProcessingStatus

            raw_message = msg.value  # Already decoded by deserializer
            envelope = EventEnvelope[SpellcheckPhaseCompletedV1].model_validate_json(raw_message)

            thin_event = SpellcheckPhaseCompletedV1.model_validate(envelope.data)
            essay_id = thin_event.entity_id
            batch_id = thin_event.batch_id

            if not essay_id:
                logger.error("Cannot process spellcheck phase result: entity_id (essay_id) is None")
                return

            if not batch_id:
                logger.error(
                    f"Cannot determine batch_id for spellcheck phase result for essay {essay_id}"
                )
                return

            # Determine success based on status
            is_success = thin_event.status == ProcessingStatus.COMPLETED

            # Record completion in batch state
            success = await self.batch_state_repo.record_essay_step_completion(
                batch_id=batch_id,
                essay_id=essay_id,
                step_name="spellcheck",
                metadata={
                    "completion_status": "success" if is_success else "failed",
                    "status": thin_event.status.value,
                    "event_id": str(envelope.event_id),
                    "timestamp": envelope.event_timestamp.isoformat(),
                    "processing_duration_ms": thin_event.processing_duration_ms,
                },
            )

            if success:
                logger.info(
                    f"Recorded spellcheck phase completion for essay {essay_id} in batch {batch_id}"
                )
            else:
                logger.warning(
                    f"Failed to record spellcheck phase completion for essay {essay_id} "
                    f"in batch {batch_id} (might already be recorded)"
                )

        except Exception as e:
            logger.error(f"Error handling spellcheck phase completed: {e}", exc_info=True)
            raise

    async def _handle_cj_assessment_completed(self, msg: ConsumerRecord) -> None:
        """Handle CJ assessment completion events."""
        try:
            raw_message = msg.value  # Already decoded by deserializer
            envelope = EventEnvelope[CJAssessmentCompletedV1].model_validate_json(raw_message)

            cj_data = CJAssessmentCompletedV1.model_validate(envelope.data)
            batch_id = cj_data.entity_id  # CJ assessment is batch-level
            if batch_id is None:
                logger.error("Cannot process CJ assessment result: entity_id (batch_id) is None")
                return

            # Use processing_summary for state tracking only (NO business data)
            processing_summary = cj_data.processing_summary

            # Record successful essay completions
            for essay_id in processing_summary.get("successful_essay_ids", []):
                if essay_id is None:
                    logger.warning("Skipping None essay_id in successful_essay_ids")
                    continue
                # Record completion for each essay (state tracking only)
                success = await self.batch_state_repo.record_essay_step_completion(
                    batch_id=batch_id,
                    essay_id=essay_id,
                    step_name="cj_assessment",
                    metadata={
                        "completion_status": "success",
                        "cj_job_id": cj_data.cj_assessment_job_id,
                        # NO business data (rank, score) - just state tracking
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
                    logger.error(f"Failed to record CJ assessment completion for essay {essay_id}")

            # Record failed essay completions
            for essay_id in processing_summary.get("failed_essay_ids", []):
                success = await self.batch_state_repo.record_essay_step_completion(
                    batch_id=batch_id,
                    essay_id=essay_id,
                    step_name="cj_assessment",
                    metadata={
                        "completion_status": "failed",
                        "cj_job_id": cj_data.cj_assessment_job_id,
                        "event_id": str(envelope.event_id),
                        "timestamp": envelope.event_timestamp.isoformat(),
                    },
                )

                if success:
                    logger.info(
                        f"Recorded CJ assessment failure for essay {essay_id} in batch {batch_id}",
                        extra={"correlation_id": str(envelope.correlation_id)},
                    )
                else:
                    logger.error(f"Failed to record CJ assessment failure for essay {essay_id}")

        except Exception as e:
            logger.error(f"Error processing CJ assessment completion: {e}", exc_info=True)
            raise

    async def _handle_els_batch_phase_outcome(self, msg: ConsumerRecord) -> None:
        """
        Handle ELS batch phase outcome events for dependency resolution.

        Track phase completions from ELS to enable multi-pipeline support
        and intelligent dependency resolution.
        """
        try:
            # Parse the event envelope
            envelope: EventEnvelope = EventEnvelope.model_validate_json(msg.value)
            event: ELSBatchPhaseOutcomeV1 = ELSBatchPhaseOutcomeV1.model_validate(envelope.data)

            # Determine if phase completed successfully
            # Use string comparison since BatchStatus enum might not be imported
            success = str(event.phase_status).endswith("COMPLETED_SUCCESSFULLY")

            # Record phase completion for dependency resolution
            result = await self.batch_state_repo.record_batch_phase_completion(
                batch_id=event.batch_id,
                phase_name=event.phase_name.value,
                completed=success,
            )

            if result:
                successful_count = len(event.processed_essays)
                failed_count = len(event.failed_essay_ids)
                logger.info(
                    f"Recorded phase {event.phase_name.value} completion for batch {event.batch_id}"
                    f" (success={success}, successful_essays={successful_count})",
                    extra={
                        "batch_id": event.batch_id,
                        "phase_name": event.phase_name.value,
                        "success": success,
                        "successful_essay_count": successful_count,
                        "failed_essay_count": failed_count,
                        "correlation_id": str(envelope.correlation_id),
                    },
                )
            else:
                logger.error(
                    f"Failed to record phase completion for batch {event.batch_id}",
                    extra={"batch_id": event.batch_id, "phase_name": event.phase_name.value},
                )

        except Exception as e:
            logger.error(f"Error processing ELS batch phase outcome: {e}", exc_info=True)
            raise
