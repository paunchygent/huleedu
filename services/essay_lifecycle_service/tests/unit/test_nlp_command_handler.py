from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.batch_service_models import BatchServiceNLPInitiateCommandDataV2
from common_core.event_enums import ProcessingEvent
from common_core.events.nlp_events import BatchNlpProcessingRequestedV2
from common_core.events.spellcheck_models import SpellcheckMetricsV1
from common_core.metadata_models import EssayProcessingInputRefV1, StorageReferenceMetadata
from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus
from services.essay_lifecycle_service.constants import MetadataKey
from services.essay_lifecycle_service.implementations.nlp_command_handler import (
    NlpCommandHandler,
)
from services.essay_lifecycle_service.protocols import (
    BatchEssayTracker,
    EssayRepositoryProtocol,
    SpecializedServiceRequestDispatcher,
)


def test_batch_nlp_processing_requested_allows_optional_prompt_ref() -> None:
    event = BatchNlpProcessingRequestedV2(
        event_name=ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED_V2,
        entity_id="batch-1",
        entity_type="batch",
        essays_to_process=[],
        language="en",
        batch_id="batch-1",
        student_prompt_ref=None,
    )
    assert event.student_prompt_ref is None


@pytest.mark.asyncio
async def test_process_initiate_nlp_command_includes_spellcheck_metrics(
    mock_session_factory: AsyncMock,
) -> None:
    repo = AsyncMock(spec=EssayRepositoryProtocol)
    dispatcher = AsyncMock(spec=SpecializedServiceRequestDispatcher)
    batch_tracker = AsyncMock(spec=BatchEssayTracker)

    # Mock batch_tracker to return None for student_prompt_ref (backward compat)
    batch_tracker.get_batch_status.return_value = {
        "batch_id": "batch-1",
        "user_id": "user-1",
        "student_prompt_ref": None,
    }

    handler = NlpCommandHandler(repo, dispatcher, batch_tracker, mock_session_factory)

    metrics = SpellcheckMetricsV1(
        total_corrections=3,
        l2_dictionary_corrections=1,
        spellchecker_corrections=2,
        word_count=150,
        correction_density=2.0,
    )

    essay_state = MagicMock()
    essay_state.current_status = EssayStatus.SPELLCHECKED_SUCCESS
    essay_state.processing_metadata = {
        "spellcheck_result": {"metrics": metrics.model_dump()},
        MetadataKey.COMMANDED_PHASES: [],
    }

    repo.get_essay_state.return_value = essay_state
    repo.update_essay_status_via_machine.return_value = None

    student_prompt_ref = StorageReferenceMetadata(
        references={
            ContentType.STUDENT_PROMPT_TEXT: {"storage_id": "prompt-123", "path": ""}
        }
    )

    command = BatchServiceNLPInitiateCommandDataV2(
        event_name=ProcessingEvent.BATCH_NLP_INITIATE_COMMAND_V2,
        entity_id="batch-1",
        entity_type="batch",
        parent_id=None,
        essays_to_process=[
            EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-1")
        ],
        language="en",
        student_prompt_ref=student_prompt_ref,
    )

    await handler.process_initiate_nlp_command(command, uuid4())

    dispatcher.dispatch_nlp_requests.assert_awaited_once()
    dispatched_args = dispatcher.dispatch_nlp_requests.await_args.kwargs
    essays = dispatched_args["essays_to_process"]
    assert len(essays) == 1
    assert essays[0].spellcheck_metrics is not None
    assert essays[0].spellcheck_metrics.total_corrections == metrics.total_corrections
    assert dispatched_args["student_prompt_ref"] == student_prompt_ref
