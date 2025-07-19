"""Unit tests for BOSDataTransformer."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from services.result_aggregator_service.implementations.bos_data_transformer import (
    BOSDataTransformer,
)


def create_mock_bos_pipeline_state(
    batch_id: str = "test-batch",
    user_id: str = "test-user",
    override_status: str = "COMPLETED_SUCCESSFULLY",
    include_all_pipelines: bool = True,
    essay_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Create realistic BOS ProcessingPipelineState data."""
    if essay_counts is None:
        essay_counts = {"total": 3, "successful": 3, "failed": 0}

    requested_pipelines: list[str] = ["spellcheck"]

    data = {
        "batch_id": batch_id,
        "user_id": user_id,
        "requested_pipelines": requested_pipelines,
        "spellcheck": {
            "status": override_status,
            "essay_counts": essay_counts,
            "started_at": "2024-01-01T10:00:00Z",
            "completed_at": "2024-01-01T10:05:00Z"
            if override_status == "COMPLETED_SUCCESSFULLY"
            else None,
        },
        "last_updated": "2024-01-01T10:06:00Z",
    }

    if include_all_pipelines:
        requested_pipelines.append("cj_assessment")
        data["cj_assessment"] = {
            "status": "IN_PROGRESS",
            "essay_counts": {"total": 3, "successful": 2, "failed": 0},
            "started_at": "2024-01-01T10:05:00Z",
            "completed_at": None,
        }

    return data


class TestBOSDataTransformer:
    """Test cases for BOS data transformation logic."""

    def test_transform_bos_to_batch_result_success(self) -> None:
        """Test successful transformation of complete BOS data."""
        # Arrange
        transformer = BOSDataTransformer()
        bos_data = create_mock_bos_pipeline_state(
            batch_id="test-batch-123",
            user_id="test-user-456",
        )

        # Act
        result = transformer.transform_bos_to_batch_result(bos_data, "test-user-456")

        # Assert
        assert result.batch_id == "test-batch-123"
        assert result.user_id == "test-user-456"
        assert (
            result.overall_status.value == "processing_pipelines"
        )  # One pipeline still in progress
        assert result.essay_count == 3
        assert result.completed_essay_count == 5  # Sum across pipelines (3 + 2)
        assert result.failed_essay_count == 0
        assert result.requested_pipeline == "spellcheck,cj_assessment"
        assert result.batch_metadata is not None
        assert result.batch_metadata["current_phase"] == "CJ_ASSESSMENT"
        assert result.essays == []  # Cannot populate from BOS
        assert result.batch_metadata["source"] == "bos_fallback"

    def test_transform_single_pipeline_spellcheck_only(self) -> None:
        """Test transformation with only spellcheck pipeline."""
        # Arrange
        transformer = BOSDataTransformer()
        bos_data = create_mock_bos_pipeline_state(
            batch_id="spellcheck-only-batch",
            user_id="test-user",
            override_status="COMPLETED_SUCCESSFULLY",
            include_all_pipelines=False,
        )

        # Act
        result = transformer.transform_bos_to_batch_result(bos_data, "test-user")

        # Assert
        assert result.batch_id == "spellcheck-only-batch"
        assert result.overall_status.value == "completed_successfully"  # Completed successfully
        assert result.essay_count == 3
        assert result.completed_essay_count == 3
        assert result.failed_essay_count == 0
        assert result.requested_pipeline == "spellcheck"
        assert result.batch_metadata is not None
        assert result.batch_metadata["current_phase"] is None  # No active pipeline

    def test_transform_failed_pipeline_status(self) -> None:
        """Test transformation with failed pipeline status."""
        # Arrange
        transformer = BOSDataTransformer()
        bos_data = create_mock_bos_pipeline_state(
            override_status="FAILED",
            essay_counts={"total": 3, "successful": 1, "failed": 2},
        )

        # Act
        result = transformer.transform_bos_to_batch_result(bos_data, "test-user")

        # Assert
        assert result.overall_status.value == "completed_with_failures"
        assert result.completed_essay_count == 3  # 1 from spellcheck + 2 from cj_assessment
        assert result.failed_essay_count == 2  # Only from spellcheck pipeline

    def test_transform_missing_pipeline_states(self) -> None:
        """Test error handling for missing pipeline data."""
        # Arrange
        transformer = BOSDataTransformer()
        invalid_bos_data = {"batch_id": "test", "user_id": "test", "requested_pipelines": []}

        # Act & Assert
        with pytest.raises(ValueError, match="No valid pipeline states found"):
            transformer.transform_bos_to_batch_result(invalid_bos_data, "test-user")

    def test_transform_missing_required_fields(self) -> None:
        """Test error handling for missing required BOS fields."""
        # Arrange
        transformer = BOSDataTransformer()
        # Include valid pipeline data but missing batch_id to trigger KeyError->ValueError
        invalid_bos_data = {
            "user_id": "test",
            "spellcheck": {"status": "COMPLETED_SUCCESSFULLY", "essay_counts": {"total": 1}},
        }  # Missing batch_id

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid BOS data structure"):
            transformer.transform_bos_to_batch_result(invalid_bos_data, "test-user")

    def test_transform_datetime_parsing_various_formats(self) -> None:
        """Test datetime parsing with various ISO formats."""
        # Arrange
        transformer = BOSDataTransformer()
        bos_data = create_mock_bos_pipeline_state()

        # Test with Z suffix
        bos_data["spellcheck"]["started_at"] = "2024-01-01T10:00:00Z"
        bos_data["last_updated"] = "2024-01-01T10:06:00.123Z"

        # Act
        result = transformer.transform_bos_to_batch_result(bos_data, "test-user")

        # Assert
        assert result.processing_started_at is not None
        assert isinstance(result.processing_started_at, datetime)
        # Verify that the transformer processed the datetime format correctly
        assert result.batch_metadata is not None
        assert "transformed_at" in result.batch_metadata
        # The transformed_at should be parseable as datetime
        transformed_at = result.batch_metadata["transformed_at"]
        assert datetime.fromisoformat(transformed_at.replace("Z", "+00:00")) is not None

    def test_transform_invalid_datetime_format(self) -> None:
        """Test datetime parsing with invalid format."""
        # Arrange
        transformer = BOSDataTransformer()
        bos_data = create_mock_bos_pipeline_state()
        bos_data["spellcheck"]["started_at"] = "invalid-datetime"

        # Act - Should not raise, but handle gracefully
        result = transformer.transform_bos_to_batch_result(bos_data, "test-user")

        # Assert - Gracefully handled invalid datetime
        assert result is not None

    def test_derive_batch_status_all_in_progress(self) -> None:
        """Test status derivation when all pipelines are in progress."""
        # Arrange
        transformer = BOSDataTransformer()
        pipeline_states = [
            {"status": "IN_PROGRESS"},
            {"status": "DISPATCH_INITIATED"},
        ]

        # Act
        result = transformer._derive_batch_status_from_pipelines(pipeline_states)

        # Assert
        assert result.value == "processing_pipelines"

    def test_derive_batch_status_all_completed(self) -> None:
        """Test status derivation when all pipelines are completed."""
        # Arrange
        transformer = BOSDataTransformer()
        pipeline_states = [
            {"status": "COMPLETED_SUCCESSFULLY"},
            {"status": "COMPLETED_WITH_PARTIAL_SUCCESS"},
        ]

        # Act
        result = transformer._derive_batch_status_from_pipelines(pipeline_states)

        # Assert
        assert result.value == "completed_successfully"

    def test_derive_batch_status_any_failed(self) -> None:
        """Test status derivation when any pipeline has failed."""
        # Arrange
        transformer = BOSDataTransformer()
        pipeline_states = [
            {"status": "COMPLETED_SUCCESSFULLY"},
            {"status": "FAILED"},
        ]

        # Act
        result = transformer._derive_batch_status_from_pipelines(pipeline_states)

        # Assert
        assert result.value == "completed_with_failures"

    def test_derive_batch_status_mixed_states(self) -> None:
        """Test status derivation with mixed pipeline states (in progress takes priority)."""
        # Arrange
        transformer = BOSDataTransformer()
        pipeline_states = [
            {"status": "COMPLETED_SUCCESSFULLY"},
            {"status": "IN_PROGRESS"},
            {"status": "PENDING_DEPENDENCIES"},
        ]

        # Act
        result = transformer._derive_batch_status_from_pipelines(pipeline_states)

        # Assert
        assert result.value == "processing_pipelines"  # In progress takes priority

    def test_derive_current_phase_first_active_pipeline(self) -> None:
        """Test current phase derivation - should return first active pipeline."""
        # Arrange
        transformer = BOSDataTransformer()
        pipeline_states_with_names = [
            ("spellcheck", {"status": "COMPLETED_SUCCESSFULLY"}),
            ("nlp_metrics", {"status": "IN_PROGRESS"}),
            ("ai_feedback", {"status": "PENDING_DEPENDENCIES"}),
        ]

        # Act
        result = transformer._derive_current_phase(pipeline_states_with_names)

        # Assert
        assert result == "NLP_METRICS"  # Should map nlp_metrics to NLP_METRICS

    def test_derive_current_phase_no_active_pipelines(self) -> None:
        """Test current phase derivation when no pipelines are active."""
        # Arrange
        transformer = BOSDataTransformer()
        pipeline_states_with_names = [
            ("spellcheck", {"status": "COMPLETED_SUCCESSFULLY"}),
            ("cj_assessment", {"status": "COMPLETED_SUCCESSFULLY"}),
        ]

        # Act
        result = transformer._derive_current_phase(pipeline_states_with_names)

        # Assert
        assert result is None

    def test_essay_count_calculations(self) -> None:
        """Test essay count aggregation across pipelines."""
        # Arrange
        transformer = BOSDataTransformer()
        pipeline_states: list[dict[str, Any]] = [
            {
                "status": "COMPLETED_SUCCESSFULLY",
                "essay_counts": {"successful": 5, "failed": 1},
            },
            {
                "status": "IN_PROGRESS",
                "essay_counts": {"successful": 3, "failed": 2},
            },
        ]

        # Act
        successful_count = transformer._sum_successful_essays(pipeline_states)
        failed_count = transformer._sum_failed_essays(pipeline_states)

        # Assert
        assert successful_count == 8  # 5 + 3
        assert failed_count == 3  # 1 + 2

    def test_essay_count_missing_counts(self) -> None:
        """Test essay count calculation with missing essay_counts field."""
        # Arrange
        transformer = BOSDataTransformer()
        pipeline_states: list[dict[str, Any]] = [
            {"status": "COMPLETED_SUCCESSFULLY"},  # Missing essay_counts
            {
                "status": "IN_PROGRESS",
                "essay_counts": {"successful": 3, "failed": 2},
            },
        ]

        # Act
        successful_count = transformer._sum_successful_essays(pipeline_states)
        failed_count = transformer._sum_failed_essays(pipeline_states)

        # Assert
        assert successful_count == 3  # Only from second pipeline
        assert failed_count == 2  # Only from second pipeline

    def test_extract_pipeline_states_filters_correctly(self) -> None:
        """Test pipeline state extraction filters out invalid states."""
        # Arrange
        transformer = BOSDataTransformer()
        bos_data = {
            "spellcheck": {"status": "COMPLETED"},  # Valid
            "nlp_metrics": None,  # Invalid - None
            "ai_feedback": {"status": "IN_PROGRESS"},  # Valid
            "cj_assessment": {"status": "PENDING"},  # Valid
            "unknown_pipeline": {"status": "COMPLETED"},  # Not in expected list
        }

        # Act
        result = transformer._extract_pipeline_states(bos_data)

        # Assert
        assert len(result) == 3  # Only valid pipelines
        assert result[0][0] == "spellcheck" and result[0][1]["status"] == "COMPLETED"
        assert result[1][0] == "ai_feedback" and result[1][1]["status"] == "IN_PROGRESS"
        assert result[2][0] == "cj_assessment" and result[2][1]["status"] == "PENDING"

    def test_get_earliest_start_time(self) -> None:
        """Test earliest start time calculation."""
        # Arrange
        transformer = BOSDataTransformer()
        pipeline_states: list[dict[str, Any]] = [
            {"started_at": "2024-01-01T10:05:00Z"},
            {"started_at": "2024-01-01T10:00:00Z"},  # Earliest
            {"started_at": "2024-01-01T10:10:00Z"},
        ]

        # Act
        result = transformer._get_earliest_start_time(pipeline_states)

        # Assert
        assert result is not None
        assert result.isoformat() == "2024-01-01T10:00:00+00:00"

    def test_get_latest_completion_time(self) -> None:
        """Test latest completion time calculation."""
        # Arrange
        transformer = BOSDataTransformer()
        pipeline_states: list[dict[str, Any]] = [
            {"completed_at": "2024-01-01T10:15:00Z"},
            {"completed_at": "2024-01-01T10:20:00Z"},  # Latest
            {"completed_at": None},  # Not completed
        ]

        # Act
        result = transformer._get_latest_completion_time(pipeline_states)

        # Assert
        assert result is not None
        assert result.isoformat() == "2024-01-01T10:20:00+00:00"

    def test_get_completion_time_none_completed(self) -> None:
        """Test completion time when no pipelines are completed."""
        # Arrange
        transformer = BOSDataTransformer()
        pipeline_states: list[dict[str, Any]] = [
            {"completed_at": None},
            {"completed_at": None},
        ]

        # Act
        result = transformer._get_latest_completion_time(pipeline_states)

        # Assert
        assert result is None

    def test_parse_datetime_edge_cases(self) -> None:
        """Test datetime parsing edge cases."""
        # Arrange
        transformer = BOSDataTransformer()

        # Act & Assert
        assert transformer._parse_datetime(None) is None
        assert transformer._parse_datetime("") is None
        assert transformer._parse_datetime("invalid") is None

        # Valid datetime object
        dt = datetime.now()
        assert transformer._parse_datetime(dt) == dt

        # Valid ISO string
        iso_string = "2024-01-01T10:00:00Z"
        result = transformer._parse_datetime(iso_string)
        assert result is not None
        assert isinstance(result, datetime)

    def test_transform_metadata_contains_source_info(self) -> None:
        """Test that transformed result contains proper metadata."""
        # Arrange
        transformer = BOSDataTransformer()
        bos_data = create_mock_bos_pipeline_state()

        # Act
        result = transformer.transform_bos_to_batch_result(bos_data, "test-user")

        # Assert
        assert result.batch_metadata is not None
        assert result.batch_metadata["source"] == "bos_fallback"
        assert "transformed_at" in result.batch_metadata
