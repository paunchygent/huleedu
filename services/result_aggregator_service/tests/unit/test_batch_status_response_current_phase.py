"""Unit tests for BatchStatusResponse current_phase derivation."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus, ProcessingStage

from services.result_aggregator_service.models_api import BatchStatusResponse


@dataclass(frozen=True)
class _EssayProcessingStages:
    spellcheck_status: ProcessingStage | None = None
    cj_assessment_status: ProcessingStage | None = None


class TestBatchStatusResponseDeriveCurrentPhase:
    """Tests for BatchStatusResponse._derive_current_phase()."""

    @pytest.mark.parametrize(
        "overall_status",
        [
            BatchStatus.AWAITING_CONTENT_VALIDATION,
            BatchStatus.READY_FOR_PIPELINE_EXECUTION,
            BatchStatus.COMPLETED_SUCCESSFULLY,
            BatchStatus.COMPLETED_WITH_FAILURES,
            BatchStatus.CANCELLED,
        ],
    )
    def test_not_processing_pipelines_returns_none(self, overall_status: BatchStatus) -> None:
        result = BatchStatusResponse._derive_current_phase(
            overall_status=overall_status,
            essays=[_EssayProcessingStages(spellcheck_status=None)],
            metadata={"current_phase": "CJ_ASSESSMENT"},
        )

        assert result is None

    def test_processing_pipelines_empty_essays_returns_none(self) -> None:
        result = BatchStatusResponse._derive_current_phase(
            overall_status=BatchStatus.PROCESSING_PIPELINES,
            essays=[],
            metadata={},
        )

        assert result is None

    @pytest.mark.parametrize("spellcheck_status", [None, ProcessingStage.PROCESSING])
    def test_any_spellcheck_incomplete_returns_spellcheck(
        self, spellcheck_status: ProcessingStage | None
    ) -> None:
        result = BatchStatusResponse._derive_current_phase(
            overall_status=BatchStatus.PROCESSING_PIPELINES,
            essays=[
                _EssayProcessingStages(
                    spellcheck_status=ProcessingStage.COMPLETED,
                    cj_assessment_status=ProcessingStage.COMPLETED,
                ),
                _EssayProcessingStages(
                    spellcheck_status=spellcheck_status,
                    cj_assessment_status=None,
                ),
            ],
            metadata={"current_phase": "CJ_ASSESSMENT"},
        )

        assert result == PhaseName.SPELLCHECK

    @pytest.mark.parametrize("cj_status", [None, ProcessingStage.PROCESSING])
    def test_spellcheck_terminal_and_any_cj_incomplete_returns_cj_assessment(
        self, cj_status: ProcessingStage | None
    ) -> None:
        result = BatchStatusResponse._derive_current_phase(
            overall_status=BatchStatus.PROCESSING_PIPELINES,
            essays=[
                _EssayProcessingStages(
                    spellcheck_status=ProcessingStage.COMPLETED,
                    cj_assessment_status=ProcessingStage.COMPLETED,
                ),
                _EssayProcessingStages(
                    spellcheck_status=ProcessingStage.FAILED,
                    cj_assessment_status=cj_status,
                ),
            ],
            metadata={},
        )

        assert result == PhaseName.CJ_ASSESSMENT

    def test_all_terminal_returns_none(self) -> None:
        result = BatchStatusResponse._derive_current_phase(
            overall_status=BatchStatus.PROCESSING_PIPELINES,
            essays=[
                _EssayProcessingStages(
                    spellcheck_status=ProcessingStage.COMPLETED,
                    cj_assessment_status=ProcessingStage.CANCELLED,
                ),
                _EssayProcessingStages(
                    spellcheck_status=ProcessingStage.FAILED,
                    cj_assessment_status=ProcessingStage.COMPLETED,
                ),
            ],
            metadata={"current_phase": "CJ_ASSESSMENT"},
        )

        assert result is None

    def test_processing_pipelines_empty_essays_uses_metadata_fallback(self) -> None:
        result = BatchStatusResponse._derive_current_phase(
            overall_status=BatchStatus.PROCESSING_PIPELINES,
            essays=[],
            metadata={"current_phase": "CJ_ASSESSMENT"},
        )

        assert result == PhaseName.CJ_ASSESSMENT
