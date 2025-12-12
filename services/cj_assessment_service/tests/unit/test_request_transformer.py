"""Unit tests for CJ request transformer metadata handling."""

from __future__ import annotations

from common_core.events.cj_assessment_events import ELS_CJAssessmentRequestV1

from services.cj_assessment_service.cj_core_logic.request_transformer import (
    transform_cj_assessment_request,
)


class TestTransformCJAssessmentRequestBatchingModeHint:
    """Tests for llm_batching_mode_hint → batch_config_overrides plumbing."""

    def test_valid_provider_batch_api_hint_populates_batch_config_overrides(
        self,
        cj_assessment_request_data_no_overrides: ELS_CJAssessmentRequestV1,
    ) -> None:
        """A valid provider_batch_api hint should create overrides dict."""

        result = transform_cj_assessment_request(
            cj_assessment_request_data_no_overrides,
            prompt_text="prompt",
            prompt_storage_id="prompt-storage-id",
            judge_rubric_text=None,
            judge_rubric_storage_id=None,
            metadata_payload={"llm_batching_mode_hint": "provider_batch_api"},
        )

        assert result.batch_config_overrides is not None
        assert (
            result.batch_config_overrides.get("llm_batching_mode_override") == "provider_batch_api"
        )

    def test_invalid_hint_is_ignored(
        self,
        cj_assessment_request_data_no_overrides: ELS_CJAssessmentRequestV1,
    ) -> None:
        """An unknown hint value must not create overrides."""

        result = transform_cj_assessment_request(
            cj_assessment_request_data_no_overrides,
            prompt_text="prompt",
            prompt_storage_id="prompt-storage-id",
            judge_rubric_text=None,
            judge_rubric_storage_id=None,
            metadata_payload={"llm_batching_mode_hint": "unknown_mode"},
        )

        assert result.batch_config_overrides is None
