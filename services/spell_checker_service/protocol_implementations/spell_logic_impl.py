"""Default implementation of SpellLogicProtocol."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import aiohttp
from core_logic import default_perform_spell_check_algorithm
from protocols import ResultStoreProtocol, SpellLogicProtocol

from common_core.enums import ContentType, EssayStatus, ProcessingEvent, ProcessingStage
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.metadata_models import (
    EntityReference,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)


class DefaultSpellLogic(SpellLogicProtocol):
    """Default implementation of SpellLogicProtocol."""

    def __init__(
        self,
        result_store: ResultStoreProtocol,
        http_session: aiohttp.ClientSession,
        original_text_storage_id: str,
        initial_system_metadata: SystemProcessingMetadata,
    ):
        self.result_store = result_store
        self.http_session = http_session
        self.original_text_storage_id = original_text_storage_id
        self.initial_system_metadata = initial_system_metadata

    async def perform_spell_check(
        self, text: str, essay_id: Optional[str]
    ) -> SpellcheckResultDataV1:
        """Perform spell check using the core logic implementation."""
        corrected_text, corrections_count = await default_perform_spell_check_algorithm(
            text, essay_id
        )

        new_storage_id: Optional[str] = None
        storage_metadata_for_result: Optional[StorageReferenceMetadata] = None
        current_status = EssayStatus.SPELLCHECKED_SUCCESS
        error_detail = None

        if corrected_text:
            try:
                new_storage_id = await self.result_store.store_content(
                    original_storage_id=self.original_text_storage_id,
                    content_type=ContentType.CORRECTED_TEXT,
                    content=corrected_text,
                    http_session=self.http_session,
                )
                if new_storage_id:
                    storage_metadata_for_result = StorageReferenceMetadata(
                        references={ContentType.CORRECTED_TEXT: {"default": new_storage_id}}
                    )
                else:
                    current_status = EssayStatus.SPELLCHECK_FAILED
                    error_detail = "Failed to store corrected text (no storage_id returned)."
            except Exception as e:
                from huleedu_service_libs.logging_utils import create_service_logger
                logger = create_service_logger("spell_checker_service.spell_logic_impl")
                logger.error(
                    f"Essay {essay_id}: Failed to store corrected text: {e}", exc_info=True
                )
                current_status = EssayStatus.SPELLCHECK_FAILED
                error_detail = f"Exception storing corrected text: {str(e)[:100]}"
        else:
            current_status = EssayStatus.SPELLCHECK_FAILED
            error_detail = "Spell check algorithm did not return corrected text."
            corrections_count = 0  # Ensure corrections_count is not None if no text

        # Create entity reference for this essay
        final_entity_ref = EntityReference(entity_id=essay_id or "unknown", entity_type="essay")

        # Update system_metadata based on this step's outcome
        updated_error_info = self.initial_system_metadata.error_info.copy()
        if error_detail and not updated_error_info.get("spellcheck_error"):
            updated_error_info["spellcheck_error"] = error_detail

        final_system_metadata = self.initial_system_metadata.model_copy(
            update={
                "processing_stage": (
                    ProcessingStage.COMPLETED
                    if current_status == EssayStatus.SPELLCHECKED_SUCCESS
                    else ProcessingStage.FAILED
                ),
                "event": ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED.value,
                "completed_at": datetime.now(timezone.utc),
                "error_info": updated_error_info,
            }
        )
        # Ensure entity in system_metadata is the correct one for this essay
        final_system_metadata.entity = final_entity_ref

        return SpellcheckResultDataV1(
            original_text_storage_id=self.original_text_storage_id,
            storage_metadata=storage_metadata_for_result,
            corrections_made=corrections_count,
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED,
            entity_ref=final_entity_ref,
            timestamp=datetime.now(timezone.utc),
            status=current_status,
            system_metadata=final_system_metadata,
        )
