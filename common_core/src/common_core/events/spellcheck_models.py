"""Event data models specific to spell checking processes."""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from ..metadata_models import StorageReferenceMetadata
from .base_event_models import ProcessingUpdate


class SpellcheckRequestedDataV1(ProcessingUpdate):
    """
    Data for requesting a spellcheck.
    'event_name' (from BaseEventData) should be ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value
    'status' (from ProcessingUpdate) should be EssayStatus.AWAITING_SPELLCHECK.value
    'system_metadata' provides context for this request event.
    """

    text_storage_id: str = Field(description="Storage ID of the original text to be spellchecked.")
    # No need to repeat system_metadata, it's inherited.


class SpellcheckResultDataV1(ProcessingUpdate):
    """
    Data representing the result of a spellcheck.
    'event_name' (from BaseEventData) should be
        ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED.value
    'status' (from ProcessingUpdate) indicates outcome
        (e.g., SPELLCHECKED_SUCCESS or _FAILED).
    'system_metadata' provides context for this result event, including error_info if failed.
    """

    original_text_storage_id: str = Field(
        description="Storage ID of the original text that was spellchecked."
    )
    storage_metadata: Optional[StorageReferenceMetadata] = Field(
        default=None, description="Ref to corrected text, logs."
    )
    corrections_made: Optional[int] = Field(default=None, description="Number of corrections made.")
