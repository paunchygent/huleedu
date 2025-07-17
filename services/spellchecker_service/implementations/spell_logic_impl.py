"""Default implementation of SpellLogicProtocol."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import aiohttp

# OpenTelemetry tracing handled by HuleEduError automatically
from common_core.domain_enums import ContentType
from common_core.event_enums import ProcessingEvent
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.metadata_models import (
    EntityReference,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)
from common_core.status_enums import EssayStatus, ProcessingStage
from huleedu_service_libs.error_handling import (
    raise_content_service_error,
    raise_processing_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.spellchecker_service.core_logic import default_perform_spell_check_algorithm
from services.spellchecker_service.protocols import ResultStoreProtocol, SpellLogicProtocol

logger = create_service_logger("spellchecker_service.spell_logic_impl")


class DefaultSpellLogic(SpellLogicProtocol):
    """Default implementation of SpellLogicProtocol with structured error handling."""

    def __init__(
        self,
        result_store: ResultStoreProtocol,
        http_session: aiohttp.ClientSession,
    ):
        self.result_store = result_store
        self.http_session = http_session

    async def perform_spell_check(
        self,
        text: str,
        essay_id: str | None,
        original_text_storage_id: str,
        initial_system_metadata: SystemProcessingMetadata,
        correlation_id: UUID,
        language: str = "en",
    ) -> SpellcheckResultDataV1:
        """Perform spell check with structured error handling and correlation tracking.

        Args:
            text: Text to spell check
            essay_id: Essay identifier for logging
            original_text_storage_id: Original text storage reference
            initial_system_metadata: System processing metadata
            correlation_id: Request correlation ID for tracing
            language: Language for spell checking

        Returns:
            SpellcheckResultDataV1 with processing results

        Raises:
            HuleEduError: On algorithm or storage failures
        """
        logger.info(
            f"Starting spell check for essay {essay_id} with language {language}",
            extra={
                "correlation_id": str(correlation_id),
                "essay_id": essay_id,
                "language": language,
            },
        )

        # Perform spell check algorithm
        try:
            corrected_text, corrections_count = await default_perform_spell_check_algorithm(
                text,
                essay_id,
                language=language,
                correlation_id=correlation_id,
            )
        except Exception as e:
            logger.error(
                f"Spell check algorithm failed for essay {essay_id}: {e}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id), "essay_id": essay_id},
            )
            raise_processing_error(
                service="spellchecker_service",
                operation="perform_spell_check",
                message=f"Spell check algorithm failed: {str(e)}",
                correlation_id=correlation_id,
                algorithm_stage="spell_checking",
                content_length=len(text),
                language=language,
                essay_id=essay_id,
            )

        new_storage_id: str | None = None
        storage_metadata_for_result: StorageReferenceMetadata | None = None

        # Store corrected text if available
        if corrected_text:
            try:
                new_storage_id = await self.result_store.store_content(
                    original_storage_id=original_text_storage_id,
                    content_type=ContentType.CORRECTED_TEXT,
                    content=corrected_text,
                    http_session=self.http_session,
                    correlation_id=correlation_id,
                    essay_id=essay_id,
                )

                if new_storage_id:
                    storage_metadata_for_result = StorageReferenceMetadata(
                        references={ContentType.CORRECTED_TEXT: {"default": new_storage_id}},
                    )
                    logger.info(
                        f"Successfully stored corrected text for essay {essay_id}, "
                        f"new storage_id: {new_storage_id}",
                        extra={
                            "correlation_id": str(correlation_id),
                            "essay_id": essay_id,
                            "storage_id": new_storage_id,
                        },
                    )
                else:
                    # This should not happen with proper error handling in result_store
                    raise_content_service_error(
                        service="spellchecker_service",
                        operation="perform_spell_check",
                        message="Content storage returned empty storage_id",
                        correlation_id=correlation_id,
                        content_service_url="unknown",  # Will be filled by result_store
                        essay_id=essay_id,
                    )

            except Exception:
                # Re-raise HuleEduError from result_store without modification
                # All other exceptions should have been converted already
                raise
        else:
            # This indicates algorithm failure but algorithm didn't raise exception
            raise_processing_error(
                service="spellchecker_service",
                operation="perform_spell_check",
                message="Spell check algorithm returned empty corrected text",
                correlation_id=correlation_id,
                algorithm_stage="correction_generation",
                content_length=len(text),
                language=language,
                essay_id=essay_id,
                corrections_count=0,
            )

        # Preserve entity reference from incoming request to maintain parent_id (batch_id)
        final_entity_ref = (
            initial_system_metadata.entity.model_copy(update={"entity_id": essay_id or "unknown"})
            if initial_system_metadata.entity
            else EntityReference(entity_id=essay_id or "unknown", entity_type="essay")
        )

        # Update system_metadata for successful completion
        final_system_metadata = initial_system_metadata.model_copy(
            update={
                "processing_stage": ProcessingStage.COMPLETED,
                "event": ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
                "completed_at": datetime.now(UTC),
                "error_info": initial_system_metadata.error_info,  # Keep existing error info
            },
        )
        # Ensure entity in system_metadata is the correct one for this essay
        final_system_metadata.entity = final_entity_ref

        logger.info(
            f"Spell check completed successfully for essay {essay_id} "
            f"with {corrections_count} corrections",
            extra={
                "correlation_id": str(correlation_id),
                "essay_id": essay_id,
                "corrections_count": corrections_count,
            },
        )

        return SpellcheckResultDataV1(
            original_text_storage_id=original_text_storage_id,
            storage_metadata=storage_metadata_for_result,
            corrections_made=corrections_count,
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_ref=final_entity_ref,
            timestamp=datetime.now(UTC),
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=final_system_metadata,
        )
