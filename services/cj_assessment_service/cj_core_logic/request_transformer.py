"""Request transformation for CJ Assessment Service.

This module transforms incoming event data into internal request models
for CJ assessment workflows.
"""

from __future__ import annotations

from common_core.events.cj_assessment_events import ELS_CJAssessmentRequestV1

from services.cj_assessment_service.models_api import (
    CJAssessmentRequestData,
    EssayToProcess,
)


def transform_cj_assessment_request(
    request_event_data: ELS_CJAssessmentRequestV1,
    *,
    prompt_text: str | None,
    prompt_storage_id: str | None,
    judge_rubric_text: str | None,
    judge_rubric_storage_id: str | None,
    metadata_payload: dict | None = None,
) -> CJAssessmentRequestData:
    """Transform ELS CJ assessment request event into internal request model.

    Args:
        request_event_data: The incoming event data from ELS
        prompt_text: Hydrated student prompt text (optional)
        prompt_storage_id: Storage ID for the prompt (optional)
        judge_rubric_text: Hydrated judge rubric text (optional)
        judge_rubric_storage_id: Storage ID for the rubric (optional)
        metadata_payload: Event envelope metadata for overrides (optional)

    Returns:
        CJAssessmentRequestData ready for workflow processing
    """
    # Convert event data to Pydantic model for type safety
    essays_to_process = [
        EssayToProcess(
            els_essay_id=essay_ref.essay_id,
            text_storage_id=essay_ref.text_storage_id,
        )
        for essay_ref in request_event_data.essays_for_cj
    ]

    # Extract max_comparisons override from metadata if provided
    max_comparisons_override = None
    if metadata_payload:
        raw_max = metadata_payload.get("max_comparisons")
        if isinstance(raw_max, int) and raw_max > 0:
            max_comparisons_override = raw_max

    # Build internal request data model
    return CJAssessmentRequestData(
        bos_batch_id=str(request_event_data.entity_id),
        assignment_id=request_event_data.assignment_id,
        essays_to_process=essays_to_process,
        language=request_event_data.language,
        course_code=request_event_data.course_code,
        cj_source="els",
        cj_request_type="cj_comparison",
        student_prompt_text=prompt_text,
        student_prompt_storage_id=prompt_storage_id,
        judge_rubric_text=judge_rubric_text,
        judge_rubric_storage_id=judge_rubric_storage_id,
        llm_config_overrides=request_event_data.llm_config_overrides,
        user_id=request_event_data.user_id,
        org_id=request_event_data.org_id,
        max_comparisons_override=max_comparisons_override,
    )
