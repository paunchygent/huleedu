"""
Unit tests for ACL transformation functions.

Tests the Anti-Corruption Layer transformers following Rule 070 (Testing Standards)
with protocol-based mocking and contract validation.
"""

from __future__ import annotations

from typing import Any

import pytest

from common_core.pipeline_models import PipelineExecutionStatus
from common_core.status_enums import BatchClientStatus
from services.api_gateway_service.acl_transformers import (
    _derive_batch_status_from_pipelines,
    _derive_current_phase,
    _extract_pipeline_states,
    _sum_failed_essays,
    _sum_successful_essays,
    transform_bos_state_to_ras_response,
)


class TestTransformBosStateToRasResponse:
    """Test suite for BOS to RAS transformation function."""

    def test_valid_transformation_with_single_pipeline(self):
        """Test successful transformation with valid BOS data."""
        # Arrange
        bos_data = {
            "batch_id": "test-batch-123",
            "requested_pipelines": ["spellcheck"],
            "last_updated": "2024-01-15T10:30:00Z",
            "spellcheck": {
                "status": "in_progress",
                "essay_counts": {
                    "total": 10,
                    "successful": 3,
                    "failed": 1,
                    "pending_dispatch_or_processing": 6,
                },
                "started_at": "2024-01-15T10:00:00Z",
                "completed_at": None,
            },
        }
        user_id = "user-456"

        # Act
        result = transform_bos_state_to_ras_response(bos_data, user_id)

        # Assert - Verify contract compliance
        assert result["batch_id"] == "test-batch-123"
        assert result["user_id"] == "user-456"
        assert result["overall_status"] == BatchClientStatus.PROCESSING.value
        assert result["essay_count"] == 10
        assert result["completed_essay_count"] == 3
        assert result["failed_essay_count"] == 1
        assert result["requested_pipeline"] == "spellcheck"
        assert result["current_phase"] == "SPELLCHECK"
        assert not result["essays"]  # Cannot populate from BOS
        assert result["created_at"] is None  # Not available in BOS
        assert result["last_updated"] == "2024-01-15T10:30:00Z"

    def test_transformation_with_multiple_pipelines(self):
        """Test transformation with multiple active pipelines."""
        # Arrange
        bos_data = {
            "batch_id": "multi-batch-789",
            "requested_pipelines": ["spellcheck", "cj_assessment"],
            "last_updated": "2024-01-15T12:00:00Z",
            "spellcheck": {
                "status": "completed_successfully",
                "essay_counts": {"total": 5, "successful": 5, "failed": 0},
                "started_at": "2024-01-15T10:00:00Z",
                "completed_at": "2024-01-15T11:00:00Z",
            },
            "cj_assessment": {
                "status": "in_progress",
                "essay_counts": {"total": 5, "successful": 2, "failed": 1},
                "started_at": "2024-01-15T11:30:00Z",
                "completed_at": None,
            },
        }
        user_id = "user-multi"

        # Act
        result = transform_bos_state_to_ras_response(bos_data, user_id)

        # Assert
        assert (
            result["overall_status"] == BatchClientStatus.PROCESSING.value
        )  # CJ still in progress
        assert result["completed_essay_count"] == 7  # 5 + 2
        assert result["failed_essay_count"] == 1
        assert result["requested_pipeline"] == "spellcheck,cj_assessment"
        assert result["current_phase"] == "NLP_METRICS"  # Second pipeline in extraction order

    def test_transformation_with_missing_batch_id_raises_error(self):
        """Test that missing batch_id raises appropriate error."""
        # Arrange
        bos_data = {
            "requested_pipelines": ["spellcheck"],
            "spellcheck": {"status": "in_progress", "essay_counts": {"total": 1}},
        }
        user_id = "user-error"

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid BOS data structure"):
            transform_bos_state_to_ras_response(bos_data, user_id)

    def test_transformation_with_no_pipeline_states_raises_error(self):
        """Test that BOS data without pipeline states raises error."""
        # Arrange
        bos_data = {
            "batch_id": "empty-batch",
            "requested_pipelines": ["spellcheck"],
            "last_updated": "2024-01-15T10:30:00Z",
        }
        user_id = "user-empty"

        # Act & Assert
        with pytest.raises(ValueError, match="No valid pipeline states found"):
            transform_bos_state_to_ras_response(bos_data, user_id)


class TestDeriveBatchStatusFromPipelines:
    """Test suite for batch status derivation logic."""

    def test_processing_status_when_pipeline_in_progress(self):
        """Test PROCESSING status for in-progress pipelines."""
        # Arrange
        pipeline_states = [
            {"status": PipelineExecutionStatus.IN_PROGRESS.value},
            {"status": PipelineExecutionStatus.COMPLETED_SUCCESSFULLY.value},
        ]

        # Act
        result = _derive_batch_status_from_pipelines(pipeline_states)

        # Assert
        assert result == BatchClientStatus.PROCESSING.value

    def test_failed_status_when_pipeline_failed(self):
        """Test FAILED status for failed pipelines."""
        # Arrange
        pipeline_states = [
            {"status": PipelineExecutionStatus.FAILED.value},
            {"status": PipelineExecutionStatus.COMPLETED_SUCCESSFULLY.value},
        ]

        # Act
        result = _derive_batch_status_from_pipelines(pipeline_states)

        # Assert
        assert result == "FAILED"  # Note: BatchClientStatus doesn't have FAILED enum

    def test_available_status_when_all_completed(self):
        """Test AVAILABLE status when all pipelines completed."""
        # Arrange
        pipeline_states = [
            {"status": PipelineExecutionStatus.COMPLETED_SUCCESSFULLY.value},
            {"status": PipelineExecutionStatus.COMPLETED_WITH_PARTIAL_SUCCESS.value},
        ]

        # Act
        result = _derive_batch_status_from_pipelines(pipeline_states)

        # Assert
        assert result == BatchClientStatus.AVAILABLE.value

    def test_processing_default_for_unknown_status(self):
        """Test default PROCESSING status for unknown statuses."""
        # Arrange
        pipeline_states = [{"status": "unknown_status"}]

        # Act
        result = _derive_batch_status_from_pipelines(pipeline_states)

        # Assert
        assert result == BatchClientStatus.PROCESSING.value


class TestDeriveCurrentPhase:
    """Test suite for current phase derivation."""

    def test_current_phase_identification(self):
        """Test identification of current active phase."""
        # Arrange
        pipeline_states = [
            {"status": PipelineExecutionStatus.COMPLETED_SUCCESSFULLY.value},  # spellcheck done
            {"status": PipelineExecutionStatus.IN_PROGRESS.value},  # second pipeline active
        ]

        # Act
        result = _derive_current_phase(pipeline_states)

        # Assert - Returns the second pipeline (nlp_metrics) which is in_progress
        assert result == "NLP_METRICS"

    def test_no_current_phase_when_all_completed(self):
        """Test no current phase when all pipelines completed."""
        # Arrange
        pipeline_states = [
            {"status": PipelineExecutionStatus.COMPLETED_SUCCESSFULLY.value},
            {"status": PipelineExecutionStatus.COMPLETED_SUCCESSFULLY.value},
        ]

        # Act
        result = _derive_current_phase(pipeline_states)

        # Assert
        assert result is None


class TestExtractPipelineStates:
    """Test suite for pipeline state extraction."""

    def test_extract_valid_pipeline_states(self):
        """Test extraction of valid pipeline states."""
        # Arrange
        bos_data = {
            "spellcheck": {"status": "in_progress"},
            "cj_assessment": {"status": "completed"},
            "ai_feedback": None,  # Should be filtered out
            "other_field": "ignored",
        }

        # Act
        result = _extract_pipeline_states(bos_data)

        # Assert
        assert len(result) == 2
        assert result[0]["status"] == "in_progress"
        assert result[1]["status"] == "completed"

    def test_extract_empty_when_no_valid_states(self):
        """Test empty extraction when no valid pipeline states exist."""
        # Arrange
        bos_data = {"spellcheck": None, "ai_feedback": None, "other_field": "value"}

        # Act
        result = _extract_pipeline_states(bos_data)

        # Assert
        assert not result


class TestEssayCountAggregation:
    """Test suite for essay count aggregation functions."""

    def test_sum_successful_essays(self):
        """Test successful essay count aggregation."""
        # Arrange
        pipeline_states: list[dict[str, Any]] = [
            {"essay_counts": {"successful": 3}},
            {"essay_counts": {"successful": 2}},
            {"essay_counts": {}},  # Missing successful count
        ]

        # Act
        result = _sum_successful_essays(pipeline_states)

        # Assert
        assert result == 5

    def test_sum_failed_essays(self):
        """Test failed essay count aggregation."""
        # Arrange
        pipeline_states: list[dict[str, Any]] = [
            {"essay_counts": {"failed": 1}},
            {"essay_counts": {"failed": 2}},
            {},  # Missing essay_counts
        ]

        # Act
        result = _sum_failed_essays(pipeline_states)

        # Assert
        assert result == 3
