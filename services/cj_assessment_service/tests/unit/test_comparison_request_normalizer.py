"""Unit tests for ComparisonRequestNormalizer batch config handling."""

from __future__ import annotations

from common_core import CourseCode, LLMBatchingMode

from services.cj_assessment_service.cj_core_logic.comparison_request_normalizer import (
    ComparisonRequestNormalizer,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import CJAssessmentRequestData, EssayToProcess


class TestComparisonRequestNormalizerBatchConfig:
    """Tests for mapping batch_config_overrides into typed overrides."""

    def test_string_batching_mode_override_is_normalized_to_enum(self) -> None:
        """String llm_batching_mode_override should become LLMBatchingMode enum."""

        settings = Settings()
        normalizer = ComparisonRequestNormalizer(settings=settings)

        request_data = CJAssessmentRequestData(
            bos_batch_id="bos-batch-123",
            assignment_id="assignment-123",
            essays_to_process=[
                EssayToProcess(els_essay_id="essay-1", text_storage_id="storage-1"),
            ],
            language="en",
            course_code=CourseCode.ENG5.value,
            cj_source="els",
            cj_request_type="cj_comparison",
            student_prompt_text=None,
            student_prompt_storage_id=None,
            judge_rubric_text=None,
            judge_rubric_storage_id=None,
            llm_config_overrides=None,
            batch_config_overrides={"llm_batching_mode_override": "provider_batch_api"},
            max_comparisons_override=None,
            user_id="user-123",
            org_id="org-123",
        )

        normalized = normalizer.normalize(request_data)

        assert normalized.batch_config_overrides is not None
        assert (
            normalized.batch_config_overrides.llm_batching_mode_override
            is LLMBatchingMode.PROVIDER_BATCH_API
        )
