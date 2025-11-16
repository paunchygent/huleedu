"""CJ assessment request composition helpers."""

from __future__ import annotations

from datetime import timezone
from pathlib import Path
from typing import Sequence

from common_core.domain_enums import ContentType
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import ELS_CJAssessmentRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)
from common_core.status_enums import ProcessingStage

from scripts.cj_experiments_runners.eng5_np.inventory import FileRecord
from scripts.cj_experiments_runners.eng5_np.settings import RunnerSettings


def build_prompt_reference(
    record: FileRecord, storage_id: str | None = None
) -> StorageReferenceMetadata | None:
    """Build a StorageReferenceMetadata entry for the student prompt.

    Args:
        record: File record for the prompt file
        storage_id: Content Service storage ID (required if prompt exists)

    Returns:
        StorageReferenceMetadata with prompt reference, or None if prompt doesn't exist
    """
    if not record.exists:
        return None
    if storage_id is None:
        raise ValueError("storage_id is required when prompt file exists")
    reference = StorageReferenceMetadata()
    reference.add_reference(
        ContentType.STUDENT_PROMPT_TEXT,
        storage_id=storage_id,
        path_hint=str(record.path),
    )
    return reference


def compose_cj_assessment_request(
    *,
    settings: RunnerSettings,
    essay_refs: Sequence[EssayProcessingInputRefV1],
    prompt_reference: StorageReferenceMetadata | None,
) -> EventEnvelope[ELS_CJAssessmentRequestV1]:
    """Build the ELS → CJ request envelope for execute mode."""

    if not essay_refs:
        raise ValueError("At least one essay is required to compose CJ request")

    if not settings.batch_id or settings.batch_id.strip() == "":
        raise ValueError("batch_id cannot be empty - must be provided via --batch-id CLI argument")

    canonical_batch_id = str(settings.batch_uuid)

    system_metadata = SystemProcessingMetadata(
        entity_id=canonical_batch_id,
        entity_type="batch",
        parent_id=str(settings.assignment_id),
        processing_stage=ProcessingStage.PENDING,
        event=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED.value,
    )

    event_data = ELS_CJAssessmentRequestV1(
        event_name=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED,
        entity_id=canonical_batch_id,
        entity_type="batch",
        parent_id=str(settings.assignment_id),
        system_metadata=system_metadata,
        essays_for_cj=list(essay_refs),
        language=settings.language.value,
        course_code=settings.course_code,
        student_prompt_ref=prompt_reference,
        llm_config_overrides=settings.llm_overrides,
        assignment_id=str(settings.assignment_id),
        user_id=settings.user_id,
        org_id=settings.org_id,
    )

    metadata = {
        "runner_mode": settings.mode.value,
        "batch_label": settings.batch_id,
    }
    if settings.max_comparisons is not None:
        metadata["max_comparisons"] = settings.max_comparisons

    envelope = EventEnvelope[ELS_CJAssessmentRequestV1](
        event_type=topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED),
        source_service="eng5_np_batch_runner",
        correlation_id=settings.correlation_id,
        data=event_data,
        metadata=metadata,
    )
    return envelope


def write_cj_request_envelope(
    *,
    envelope: EventEnvelope[ELS_CJAssessmentRequestV1],
    output_dir: Path,
) -> Path:
    """Persist the CJ request envelope for auditing and replay."""

    requests_dir = output_dir / "requests"
    requests_dir.mkdir(parents=True, exist_ok=True)
    timestamp = envelope.event_timestamp.isoformat() if envelope.event_timestamp else None
    if not timestamp:
        from datetime import datetime

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = requests_dir / f"els_cj_assessment_request_{timestamp}.json"
    path.write_text(envelope.model_dump_json(indent=2), encoding="utf-8")
    return path
