"""Default implementation of SpellcheckEventPublisherProtocol using TRUE OUTBOX PATTERN."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import (
    SpellcheckMetricsV1,
    SpellcheckPhaseCompletedV1,
    SpellcheckResultDataV1,
    SpellcheckResultV1,
)
from common_core.status_enums import ProcessingStatus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context

from services.spellchecker_service.implementations.outbox_manager import OutboxManager
from services.spellchecker_service.protocols import SpellcheckEventPublisherProtocol

logger = create_service_logger("spellchecker_service.event_publisher_impl")


class DefaultSpellcheckEventPublisher(SpellcheckEventPublisherProtocol):
    """Default implementation using TRUE OUTBOX PATTERN for transactional safety."""

    def __init__(
        self,
        source_service_name: str,
        outbox_manager: OutboxManager,
    ) -> None:
        self.source_service_name = source_service_name
        self.outbox_manager = outbox_manager

    def _create_thin_event(
        self,
        event_data: SpellcheckResultDataV1,
        correlation_id: UUID,
        processing_start_time: datetime,
    ) -> SpellcheckPhaseCompletedV1:
        """Create thin event for state management."""
        processing_duration_ms = int(
            (datetime.now(UTC) - processing_start_time).total_seconds() * 1000
        )

        # Determine status from the result data
        status = (
            ProcessingStatus.COMPLETED
            if "success" in event_data.status.lower()
            else ProcessingStatus.FAILED
        )

        # Extract corrected text storage ID from storage metadata
        corrected_text_storage_id = None
        if event_data.storage_metadata and hasattr(event_data.storage_metadata, "references"):
            from common_core.domain_enums import ContentType

            corrected_refs = event_data.storage_metadata.references.get(
                ContentType.CORRECTED_TEXT, {}
            )
            if corrected_refs:
                corrected_text_storage_id = next(iter(corrected_refs.values()), None)

        # Extract error code if failed
        error_code = None
        if (
            status == ProcessingStatus.FAILED
            and event_data.system_metadata
            and event_data.system_metadata.error_info
        ):
            error_code = str(event_data.system_metadata.error_info)[:100]  # Limit error code length

        return SpellcheckPhaseCompletedV1(
            entity_id=event_data.entity_id,
            batch_id=event_data.parent_id or "",
            correlation_id=str(correlation_id),
            status=status,
            corrected_text_storage_id=corrected_text_storage_id,
            error_code=error_code,
            processing_duration_ms=processing_duration_ms,
            timestamp=datetime.now(UTC),
        )

    def _create_rich_event(
        self,
        event_data: SpellcheckResultDataV1,
        correlation_id: UUID,
        processing_start_time: datetime,
    ) -> SpellcheckResultV1:
        """Create rich event for business data aggregation."""
        processing_duration_ms = int(
            (datetime.now(UTC) - processing_start_time).total_seconds() * 1000
        )

        # Extract metrics if available
        metrics = getattr(event_data, "_spellcheck_metrics", None)
        if metrics:
            correction_metrics = SpellcheckMetricsV1(
                total_corrections=metrics.total_corrections,
                l2_dictionary_corrections=metrics.l2_dictionary_corrections,
                spellchecker_corrections=metrics.spellchecker_corrections,
                word_count=metrics.word_count,
                correction_density=metrics.correction_density,
            )
        else:
            # Fallback to basic metrics
            correction_metrics = SpellcheckMetricsV1(
                total_corrections=event_data.corrections_made or 0,
                l2_dictionary_corrections=0,
                spellchecker_corrections=event_data.corrections_made or 0,
                word_count=0,
                correction_density=0.0,
            )

        # Extract corrected text storage ID
        corrected_text_storage_id = None
        if event_data.storage_metadata and hasattr(event_data.storage_metadata, "references"):
            from common_core.domain_enums import ContentType

            corrected_refs = event_data.storage_metadata.references.get(
                ContentType.CORRECTED_TEXT, {}
            )
            if corrected_refs:
                corrected_text_storage_id = next(iter(corrected_refs.values()), None)

        return SpellcheckResultV1(
            entity_id=event_data.entity_id,
            entity_type=event_data.entity_type,
            parent_id=event_data.parent_id,
            timestamp=datetime.now(UTC),
            status=event_data.status,
            system_metadata=event_data.system_metadata,
            event_name=event_data.event_name,
            correlation_id=str(correlation_id),
            user_id=None,  # Would need to be passed through if available
            corrections_made=event_data.corrections_made or 0,
            correction_metrics=correction_metrics,
            original_text_storage_id=event_data.original_text_storage_id,
            corrected_text_storage_id=corrected_text_storage_id,
            processing_duration_ms=processing_duration_ms,
            processor_version="pyspellchecker_1.0_L2_swedish",
        )

    async def publish_spellcheck_result(
        self,
        event_data: SpellcheckResultDataV1,
        correlation_id: UUID,
    ) -> None:
        """Publish DUAL spellcheck events via outbox pattern for transactional safety.

        Args:
            event_data: Spellcheck result data to publish
            correlation_id: Request correlation ID for tracing

        Raises:
            HuleEduError: On any failure to store event in outbox
        """
        entity_id = event_data.entity_id
        processing_start_time = event_data.timestamp or datetime.now(UTC)

        logger.debug(
            f"Publishing DUAL spellcheck events for essay {entity_id} via outbox pattern",
            extra={
                "correlation_id": str(correlation_id),
                "entity_id": entity_id,
            },
        )

        # 1. Create and publish THIN event for state management (ELS/BCS)
        thin_event = self._create_thin_event(event_data, correlation_id, processing_start_time)
        thin_topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)

        thin_envelope = EventEnvelope[SpellcheckPhaseCompletedV1](
            event_type=thin_topic,
            source_service=self.source_service_name,
            correlation_id=correlation_id,
            data=thin_event,
            metadata={},
        )

        # Inject trace context
        if thin_envelope.metadata is None:
            thin_envelope.metadata = {}
        inject_trace_context(thin_envelope.metadata)
        thin_envelope.metadata["partition_key"] = str(entity_id)

        # Store thin event in outbox - USE TOPIC NAME AS EVENT_TYPE
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="spellcheck_job",
            aggregate_id=str(entity_id),
            event_type=thin_topic,  # Use topic name, not class name!
            event_data=thin_envelope,
            topic=thin_topic,
        )

        logger.info(
            f"Thin spellcheck event stored in outbox for essay {entity_id}",
            extra={
                "correlation_id": str(correlation_id),
                "entity_id": entity_id,
                "event_type": thin_topic,  # Log the actual topic name
                "topic": thin_topic,
            },
        )

        # 2. Create and publish RICH event for business data (RAS)
        rich_event = self._create_rich_event(event_data, correlation_id, processing_start_time)
        rich_topic = topic_name(ProcessingEvent.SPELLCHECK_RESULTS)

        rich_envelope = EventEnvelope[SpellcheckResultV1](
            event_type=rich_topic,
            source_service=self.source_service_name,
            correlation_id=correlation_id,
            data=rich_event,
            metadata={},
        )

        # Inject trace context
        if rich_envelope.metadata is None:
            rich_envelope.metadata = {}
        inject_trace_context(rich_envelope.metadata)
        rich_envelope.metadata["partition_key"] = str(entity_id)

        # Store rich event in outbox - USE TOPIC NAME AS EVENT_TYPE
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="spellcheck_job",
            aggregate_id=str(entity_id),
            event_type=rich_topic,  # Use topic name, not class name!
            event_data=rich_envelope,
            topic=rich_topic,
        )

        logger.info(
            f"Rich spellcheck event stored in outbox for essay {entity_id}",
            extra={
                "correlation_id": str(correlation_id),
                "entity_id": entity_id,
                "event_type": rich_topic,  # Log the actual topic name
                "topic": rich_topic,
            },
        )
