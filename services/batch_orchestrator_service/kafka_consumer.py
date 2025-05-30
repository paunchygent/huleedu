"""
Kafka consumer logic for Batch Orchestrator Service.

Handles BatchEssaysReady events from ELS and initiates pipeline processing.

TODO: Evaluate moving this Kafka consumer to a separate worker process
if event volume or processing complexity increases, or for better resource isolation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from aiokafka import AIOKafkaConsumer
from huleedu_service_libs.logging_utils import create_service_logger
from protocols import BatchEventPublisherProtocol, BatchRepositoryProtocol

from common_core.batch_service_models import BatchServiceSpellcheckInitiateCommandDataV1
from common_core.enums import ProcessingEvent, topic_name
from common_core.events.batch_coordination_events import BatchEssaysReady
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import (
    EntityReference,
    EssayProcessingInputRefV1,
)

logger = create_service_logger("bos.kafka.consumer")


def _infer_language_from_course_code(course_code: str) -> str:
    """
    Infer language from course code for pipeline processing.

    Args:
        course_code: Course code (e.g., "SV1", "ENG5")

    Returns:
        Language code (e.g., "sv", "en")
    """
    # Simple mapping logic - can be enhanced as needed
    course_code_upper = course_code.upper()

    if course_code_upper.startswith("SV"):
        return "sv"  # Swedish
    elif course_code_upper.startswith("ENG"):
        return "en"  # English
    elif course_code_upper.startswith("NO"):
        return "no"  # Norwegian
    elif course_code_upper.startswith("DA"):
        return "da"  # Danish
    else:
        # Default to English if course code is unrecognized
        logger.warning(f"Unknown course code '{course_code}', defaulting to English")
        return "en"


class BatchKafkaConsumer:
    """Kafka consumer for handling BatchEssaysReady events."""

    def __init__(
        self,
        kafka_bootstrap_servers: str,
        consumer_group: str,
        event_publisher: BatchEventPublisherProtocol,
        batch_repo: BatchRepositoryProtocol,
    ) -> None:
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.consumer_group = consumer_group
        self.event_publisher = event_publisher
        self.batch_repo = batch_repo
        self.consumer: AIOKafkaConsumer | None = None
        self.should_stop = False

    async def start_consumer(self) -> None:
        """Start the Kafka consumer and begin processing messages."""
        # Subscribe to BatchEssaysReady topic
        topics = [topic_name(ProcessingEvent.BATCH_ESSAYS_READY)]

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
        """
        Handle a single Kafka message containing BatchEssaysReady event.

        WALKING SKELETON IMPLEMENTATION NOTE:
        ====================================
        This implementation uses mock text_storage_id values because the File Service
        has not yet been implemented. In the complete architecture:

        1. File Service processes uploaded files and stores content via Content Service
        2. File Service emits EssayContentReady events containing real text_storage_id values
        3. ELS receives and stores these storage references per essay
        4. ELS emits BatchEssaysReady when all essays are ready (contains essay_ids only)
        5. BOS needs the text_storage_id values to create
           BatchServiceSpellcheckInitiateCommandDataV1

        ARCHITECTURAL CHALLENGE:
        BatchEssaysReady follows the "thin event" principle and only contains essay_ids,
        not the text_storage_id values. The real implementation will need either:
        - ELS to provide storage references via query mechanism, OR
        - Expanded coordination event structure

        CURRENT APPROACH:
        Using consistent mock pattern "mock-storage-id-{essay_id}" following the
        established codebase style (see: spell_checker_service/di.py).
        This maintains architectural integrity while enabling end-to-end testing.
        """
        try:
            # Deserialize the message
            message_data = json.loads(msg.value.decode("utf-8"))
            envelope = EventEnvelope[BatchEssaysReady](**message_data)

            batch_essays_ready_data = envelope.data
            batch_id = batch_essays_ready_data.batch_id

            logger.info(
                f"Received BatchEssaysReady for batch {batch_id}",
                extra={"correlation_id": str(envelope.correlation_id)},
            )

            # 1. Idempotency Check
            current_pipeline_state = await self.batch_repo.get_processing_pipeline_state(batch_id)
            if current_pipeline_state and current_pipeline_state.get("spellcheck_status") in [
                "DISPATCH_INITIATED", "IN_PROGRESS", "COMPLETED", "FAILED"
            ]:
                logger.info(
                    f"Spellcheck already initiated for batch {batch_id}, skipping",
                    extra={"current_status": current_pipeline_state.get("spellcheck_status")},
                )
                return

            # 2. Retrieve stored batch context
            batch_context = await self.batch_repo.get_batch_context(batch_id)
            if not batch_context:
                logger.error(f"No batch context found for batch {batch_id}")
                return

            # 3. Infer language from course code
            language = _infer_language_from_course_code(batch_context.course_code)
            logger.info(
                f"Inferred language '{language}' from course code '{batch_context.course_code}'"
            )

            # 4. Construct spellcheck initiate command
            batch_entity_ref = EntityReference(
                entity_id=batch_id,
                entity_type="batch"
            )

            # Create EssayProcessingInputRefV1 objects for each essay
            # NOTE: Walking skeleton implementation - using mock storage IDs
            # In production: File Service → ELS coordination will provide real
            # text_storage_id values. The BatchEssaysReady event only contains essay_ids,
            # not storage references. Real flow: ELS stores storage_id from EssayContentReady
            # events and would need to provide this data to BOS (either via expanded event
            # or query mechanism)
            essays_to_process = [
                EssayProcessingInputRefV1(
                    essay_id=essay_id,
                    text_storage_id=f"mock-storage-id-{essay_id}",  # Walking skeleton pattern
                    student_name=None  # Will be populated by File Service coordination
                )
                for essay_id in batch_context.essay_ids
            ]

            spellcheck_command = BatchServiceSpellcheckInitiateCommandDataV1(
                event_name=ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
                entity_ref=batch_entity_ref,
                essays_to_process=essays_to_process,
                language=language,
            )

            # 5. Create EventEnvelope for command
            command_envelope = EventEnvelope[BatchServiceSpellcheckInitiateCommandDataV1](
                event_type=topic_name(ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND),
                source_service="batch-orchestrator-service",
                correlation_id=envelope.correlation_id,  # Maintain correlation
                data=spellcheck_command,
            )

            # 6. Publish command
            await self.event_publisher.publish_batch_event(command_envelope)
            logger.info(
                f"Published spellcheck initiate command for batch {batch_id}, "
                f"event_id {command_envelope.event_id}",
                extra={"correlation_id": str(envelope.correlation_id)},
            )

            # 7. Update pipeline state
            updated_pipeline_state = current_pipeline_state or {}
            updated_pipeline_state.update({
                "spellcheck_status": "DISPATCH_INITIATED",
                "spellcheck_initiated_at": datetime.now(timezone.utc).isoformat(),
                "language": language,
            })
            await self.batch_repo.save_processing_pipeline_state(batch_id, updated_pipeline_state)

            logger.info(f"Successfully initiated spellcheck pipeline for batch {batch_id}")

        except Exception as e:
            logger.error(f"Error handling BatchEssaysReady message: {e}", exc_info=True)
            raise
