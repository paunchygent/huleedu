"""Centralized dual event publishing logic for CJ Assessment Service.

This module extracts the common dual event publishing pattern used across
multiple locations to follow DRY principle and ensure consistency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

if TYPE_CHECKING:
    from services.cj_assessment_service.config import Settings
    from services.cj_assessment_service.protocols import CJEventPublisherProtocol

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import (
    AssessmentResultV1,
    CJAssessmentCompletedV1,
    EssayResultV1,
)
from common_core.events.envelope import EventEnvelope
from common_core.events.resource_consumption_events import ResourceConsumptionV1
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus, ProcessingStage
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context

from services.cj_assessment_service.cj_core_logic.grade_utils import _grade_to_normalized

logger = create_service_logger("dual_event_publisher")


@dataclass
class DualEventPublishingData:
    """Data contract for dual event publishing.

    This DTO provides all necessary data for publishing both thin (ELS)
    and rich (RAS) assessment events, decoupling the publishing logic
    from database models.
    """

    bos_batch_id: str  # Original BOS batch identifier
    cj_batch_id: str  # Internal CJ batch identifier
    assignment_id: Optional[str]
    course_code: str
    user_id: str  # Required for resource consumption tracking
    org_id: Optional[str]
    created_at: datetime


async def publish_dual_assessment_events(
    rankings: list[dict[str, Any]],
    grade_projections: Any,  # GradeProjectionSummary
    publishing_data: DualEventPublishingData,
    event_publisher: CJEventPublisherProtocol,
    settings: Settings,
    correlation_id: UUID,
    processing_started_at: datetime | None = None,
) -> None:
    """Publish dual events: thin to ELS, rich to RAS.

    This centralized function ensures consistency across all three publishing locations:
    - event_processor.py
    - batch_callback_handler.py
    - batch_monitor.py

    Args:
        rankings: Complete rankings including both students and anchors
        grade_projections: Grade projection summary with confidence scores
        publishing_data: Data contract containing all required publishing information
        event_publisher: Event publisher protocol implementation
        settings: Application settings
        correlation_id: Correlation ID for event tracing
        processing_started_at: When processing started (for duration calculation)
    """
    if processing_started_at is None:
        processing_started_at = publishing_data.created_at.replace(tzinfo=UTC)

    # Separate student essays from anchors using the correct field name
    student_rankings = [r for r in rankings if not r["els_essay_id"].startswith("ANCHOR_")]
    anchor_rankings = [r for r in rankings if r["els_essay_id"].startswith("ANCHOR_")]

    # Determine successful/failed essays (bradley_terry_score field contains BT score)
    successful_essay_ids = [
        r["els_essay_id"] for r in student_rankings if r.get("bradley_terry_score") is not None
    ]
    failed_essay_ids = [
        r["els_essay_id"] for r in student_rankings if r.get("bradley_terry_score") is None
    ]

    # Extract batch metadata from publishing data
    bos_batch_id = publishing_data.bos_batch_id
    cj_batch_id = publishing_data.cj_batch_id
    assignment_id = publishing_data.assignment_id
    course_code = publishing_data.course_code

    # Convert course_code enum to string if needed
    if hasattr(course_code, "value"):
        course_code = course_code.value

    # Calculate processing time (ensure processing_started_at is timezone-aware)
    if processing_started_at.tzinfo is None:
        processing_started_at = processing_started_at.replace(tzinfo=UTC)
    processing_time = (datetime.now(UTC) - processing_started_at).total_seconds()

    # 1. THIN EVENT TO ELS (Phase tracking with essay IDs only - NO business data)
    els_event = CJAssessmentCompletedV1(
        event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
        entity_id=bos_batch_id,
        entity_type="batch",
        parent_id=None,
        status=BatchStatus.COMPLETED_SUCCESSFULLY
        if successful_essay_ids
        else BatchStatus.FAILED_CRITICALLY,
        system_metadata=SystemProcessingMetadata(
            entity_id=bos_batch_id,
            entity_type="batch",
            parent_id=None,
            timestamp=datetime.now(UTC),
            processing_stage=ProcessingStage.COMPLETED,
            started_at=processing_started_at,
            completed_at=datetime.now(UTC),
            event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
        ),
        cj_assessment_job_id=cj_batch_id,
        # Clean state tracking - NO business data (rankings, grades, scores)
        processing_summary={
            "total_essays": len(student_rankings),
            "successful": len(successful_essay_ids),
            "failed": len(failed_essay_ids),
            "successful_essay_ids": successful_essay_ids,
            "failed_essay_ids": failed_essay_ids,
            "processing_time_seconds": round(processing_time, 2),
        },
    )

    els_envelope = EventEnvelope[CJAssessmentCompletedV1](
        event_type=settings.CJ_ASSESSMENT_COMPLETED_TOPIC,
        event_timestamp=datetime.now(UTC),
        source_service=settings.SERVICE_NAME,
        correlation_id=correlation_id,
        data=els_event,
        metadata={},
    )

    # Add trace context to metadata
    if els_envelope.metadata is not None:
        inject_trace_context(els_envelope.metadata)

    # Publish thin event to ELS using existing method
    await event_publisher.publish_assessment_completed(
        completion_data=els_envelope,
        correlation_id=correlation_id,
    )

    logger.info(
        "Published thin completion event to ELS",
        extra={
            "correlation_id": str(correlation_id),
            "batch_id": cj_batch_id,
            "successful_essays": len(successful_essay_ids),
            "failed_essays": len(failed_essay_ids),
            "anchors_filtered": len(anchor_rankings),
        },
    )

    # 2. RICH EVENT TO RAS (Full assessment results INCLUDING anchors for score bands)
    essay_results = []
    for ranking in rankings:  # Include ALL rankings (students + anchors)
        essay_id = ranking["els_essay_id"]
        is_anchor = essay_id.startswith("ANCHOR_")
        grade = grade_projections.primary_grades.get(essay_id, "U")

        essay_results.append(
            EssayResultV1(
                essay_id=essay_id,
                normalized_score=_grade_to_normalized(grade),
                letter_grade=grade,
                confidence_score=grade_projections.confidence_scores.get(essay_id, 0.0),
                confidence_label=grade_projections.confidence_labels.get(essay_id, "LOW"),
                bt_score=ranking.get("bradley_terry_score") or 0.0,  # Handle None values
                rank=ranking.get("rank", 999),
                is_anchor=is_anchor,
                # Display name for anchors to help with score band visualization
                display_name=f"ANCHOR GRADE {grade}" if is_anchor else None,
            )
        )

    # Calculate anchor grade distribution (CRITICAL - was missing in some locations)
    anchor_grade_distribution = {}
    if anchor_rankings:
        for grade in ["A", "B", "C", "D", "E", "F", "U"]:
            anchor_grade_distribution[grade] = sum(
                1
                for r in anchor_rankings
                if grade_projections.primary_grades.get(r["els_essay_id"]) == grade
            )

    ras_event = AssessmentResultV1(
        event_name=ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED,
        entity_id=bos_batch_id,
        entity_type="batch",
        batch_id=bos_batch_id,
        cj_assessment_job_id=cj_batch_id,
        assessment_method="cj_assessment",
        model_used=settings.DEFAULT_LLM_MODEL,
        model_provider=settings.DEFAULT_LLM_PROVIDER.value,
        model_version=getattr(settings, "DEFAULT_LLM_MODEL_VERSION", None),
        essay_results=essay_results,
        assessment_metadata={
            "anchor_essays_used": len(anchor_rankings),
            "calibration_method": "anchor" if anchor_rankings else "default",
            "anchor_grade_distribution": anchor_grade_distribution,  # CRITICAL FIELD
            "comparison_count": len(rankings) * (len(rankings) - 1) // 2,  # Estimated
            "processing_duration_seconds": (
                datetime.now(UTC) - processing_started_at
            ).total_seconds(),
            "llm_temperature": settings.DEFAULT_LLM_TEMPERATURE,
            "assignment_id": assignment_id,
            "course_code": course_code,
        },
        assessed_at=datetime.now(UTC),
    )

    ras_envelope = EventEnvelope[AssessmentResultV1](
        event_type=settings.ASSESSMENT_RESULT_TOPIC,
        event_timestamp=datetime.now(UTC),
        source_service=settings.SERVICE_NAME,
        correlation_id=correlation_id,
        data=ras_event,
        metadata={},
    )

    # Add trace context to metadata
    if ras_envelope.metadata is not None:
        inject_trace_context(ras_envelope.metadata)

    # Publish rich event to RAS using new method
    await event_publisher.publish_assessment_result(
        result_data=ras_envelope,
        correlation_id=correlation_id,
    )

    logger.info(
        f"Published dual events: ELS (thin) and RAS (rich) for batch {cj_batch_id}",
        extra={
            "correlation_id": str(correlation_id),
            "batch_id": cj_batch_id,
            "essay_results_count": len(essay_results),
            "anchor_essays_used": len(anchor_rankings),
            "anchor_grade_distribution": anchor_grade_distribution,
        },
    )

    # 3. RESOURCE CONSUMPTION EVENT (for Entitlements credit tracking)
    try:
        # Compute estimated comparisons (includes student-only to avoid anchors inflating counts)
        comparisons_estimated = len(student_rankings) * (len(student_rankings) - 1) // 2

        # Extract identities from publishing data
        user_id = publishing_data.user_id
        org_id = publishing_data.org_id

        if not user_id:
            raise ValueError(
                f"user_id not available for batch {cj_batch_id} - identity threading failed"
            )

        resource_event = ResourceConsumptionV1(
            entity_id=bos_batch_id,
            entity_type="batch",
            user_id=str(user_id),
            org_id=str(org_id) if org_id else None,
            resource_type="cj_comparison",
            quantity=comparisons_estimated,
            service_name=settings.SERVICE_NAME,
            processing_id=cj_batch_id,
            consumed_at=datetime.now(UTC),
        )

        resource_envelope = EventEnvelope[ResourceConsumptionV1](
            event_type=topic_name(ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED),
            event_timestamp=datetime.now(UTC),
            source_service=settings.SERVICE_NAME,
            correlation_id=correlation_id,
            data=resource_event,
            metadata={},
        )

        if resource_envelope.metadata is not None:
            inject_trace_context(resource_envelope.metadata)

        await event_publisher.publish_resource_consumption(
            resource_event=resource_envelope, correlation_id=correlation_id
        )

        logger.info(
            "Published resource consumption event for CJ comparisons",
            extra={
                "correlation_id": str(correlation_id),
                "batch_id": cj_batch_id,
                "quantity": comparisons_estimated,
                "user_id": user_id,
                "org_id": org_id,
            },
        )
    except Exception as e:
        logger.warning(
            f"Failed to publish ResourceConsumptionV1: {e}",
            extra={"batch_id": cj_batch_id, "correlation_id": str(correlation_id)},
        )
