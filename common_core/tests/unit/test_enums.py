"""Unit tests for common_core.enums module.

This module tests the enums and functions defined in common_core.enums,
with particular focus on the topic_name() function as required by
HULEEDU_PIPELINE_IMPLEMENT_002 Phase 1 Task 1.2.
"""

from __future__ import annotations

import pytest

from common_core.enums import (
    _TOPIC_MAPPING,
    BatchStatus,
    ContentType,
    ErrorCode,
    EssayStatus,
    ProcessingEvent,
    ProcessingStage,
    topic_name,
)


class TestProcessingStage:
    """Test ProcessingStage enum functionality."""

    def test_terminal_states(self) -> None:
        """Test that terminal() returns correct terminal states."""
        terminal_states = ProcessingStage.terminal()
        expected = {
            ProcessingStage.COMPLETED,
            ProcessingStage.FAILED,
            ProcessingStage.CANCELLED,
        }
        assert terminal_states == expected

    def test_active_states(self) -> None:
        """Test that active() returns correct active states."""
        active_states = ProcessingStage.active()
        expected = {
            ProcessingStage.COMPLETED,
            ProcessingStage.INITIALIZED,
            ProcessingStage.PROCESSING,
        }
        assert active_states == expected

    def test_all_enum_values_are_strings(self) -> None:
        """Test that all ProcessingStage values are strings."""
        for stage in ProcessingStage:
            assert isinstance(stage.value, str)
            assert len(stage.value) > 0


class TestEssayStatus:
    """Test EssayStatus enum completeness and correctness."""

    def test_awaiting_cj_assessment_exists(self) -> None:
        """Test that AWAITING_CJ_ASSESSMENT status exists (Task 1.1 requirement)."""
        assert hasattr(EssayStatus, "AWAITING_CJ_ASSESSMENT")
        assert EssayStatus.AWAITING_CJ_ASSESSMENT == "awaiting_cj_assessment"

    def test_cj_assessment_statuses_complete(self) -> None:
        """Test that all CJ Assessment related statuses exist."""
        cj_statuses = [
            "AWAITING_CJ_ASSESSMENT",
            "CJ_ASSESSMENT_IN_PROGRESS",
            "CJ_ASSESSMENT_SUCCESS",
            "CJ_ASSESSMENT_FAILED",
        ]
        for status in cj_statuses:
            assert hasattr(EssayStatus, status), f"Missing {status} in EssayStatus"

    def test_all_essay_statuses_are_strings(self) -> None:
        """Test that all EssayStatus values are strings."""
        for status in EssayStatus:
            assert isinstance(status.value, str)
            assert len(status.value) > 0


class TestTopicNameFunction:
    """Test the topic_name() function comprehensively."""

    def test_topic_name_els_batch_phase_outcome(self) -> None:
        """Test specific mapping for ELS_BATCH_PHASE_OUTCOME (Task 1.2 requirement)."""
        result = topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME)
        assert result == "huleedu.els.batch_phase.outcome.v1"

    def test_all_mapped_events(self) -> None:
        """Test topic_name() for all currently mapped events."""
        # Test all events that have explicit mappings in _TOPIC_MAPPING
        for event, expected_topic in _TOPIC_MAPPING.items():
            result = topic_name(event)
            assert result == expected_topic, f"Event {event} mapped incorrectly"

    def test_spellcheck_events_mapping(self) -> None:
        """Test spellcheck-related event mappings."""
        assert (
            topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
            == "huleedu.essay.spellcheck.requested.v1"
        )
        assert (
            topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED)
            == "huleedu.essay.spellcheck.completed.v1"
        )

    def test_batch_coordination_events_mapping(self) -> None:
        """Test batch coordination event mappings."""
        assert (
            topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED)
            == "huleedu.batch.essays.registered.v1"
        )
        assert (
            topic_name(ProcessingEvent.BATCH_ESSAYS_READY)
            == "huleedu.els.batch.essays.ready.v1"
        )

    def test_content_provisioning_events_mapping(self) -> None:
        """Test content provisioning event mappings."""
        assert (
            topic_name(ProcessingEvent.ESSAY_CONTENT_PROVISIONED)
            == "huleedu.file.essay.content.provisioned.v1"
        )
        assert (
            topic_name(ProcessingEvent.EXCESS_CONTENT_PROVISIONED)
            == "huleedu.els.excess.content.provisioned.v1"
        )

    def test_command_events_mapping(self) -> None:
        """Test command event mappings."""
        assert (
            topic_name(ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND)
            == "huleedu.els.spellcheck.initiate.command.v1"
        )
        assert (
            topic_name(ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND)
            == "huleedu.batch.cj_assessment.initiate.command.v1"
        )

    def test_cj_assessment_events_mapping(self) -> None:
        """Test CJ Assessment event mappings."""
        assert (
            topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)
            == "huleedu.els.cj_assessment.requested.v1"
        )
        assert (
            topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)
            == "huleedu.cj_assessment.completed.v1"
        )
        assert (
            topic_name(ProcessingEvent.CJ_ASSESSMENT_FAILED)
            == "huleedu.cj_assessment.failed.v1"
        )

    def test_unmapped_event_raises_error(self) -> None:
        """Test that unmapped events raise ValueError with helpful message."""
        # Use an event that should not have a mapping
        unmapped_event = ProcessingEvent.PROCESSING_STARTED

        with pytest.raises(ValueError) as exc_info:
            topic_name(unmapped_event)

        error_message = str(exc_info.value)
        assert "does not have an explicit topic mapping" in error_message
        assert unmapped_event.name in error_message
        assert unmapped_event.value in error_message
        assert "Currently mapped events:" in error_message

    def test_topic_name_returns_string(self) -> None:
        """Test that topic_name() always returns a string for mapped events."""
        for event in _TOPIC_MAPPING.keys():
            result = topic_name(event)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_topic_name_format_consistency(self) -> None:
        """Test that all topic names follow the expected format pattern."""
        for event in _TOPIC_MAPPING.keys():
            topic = topic_name(event)
            parts = topic.split(".")

            # Should start with 'huleedu'
            assert parts[0] == "huleedu", f"Topic {topic} should start with 'huleedu'"

            # Should end with 'v1'
            assert parts[-1] == "v1", f"Topic {topic} should end with 'v1'"

            # Should have at least 4 parts (huleedu.domain.entity.action.v1)
            assert len(parts) >= 4, f"Topic {topic} should have at least 4 parts"

    def test_topic_mapping_completeness(self) -> None:
        """Test that _TOPIC_MAPPING includes all intended events."""
        # This test ensures we don't accidentally miss mapping new events
        # that should be mapped to Kafka topics

        # Events that should definitely have mappings
        required_mapped_events = [
            ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            ProcessingEvent.BATCH_ESSAYS_REGISTERED,
            ProcessingEvent.BATCH_ESSAYS_READY,
            ProcessingEvent.ESSAY_CONTENT_PROVISIONED,
            ProcessingEvent.EXCESS_CONTENT_PROVISIONED,
            ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
            ProcessingEvent.ELS_BATCH_PHASE_OUTCOME,
        ]

        for event in required_mapped_events:
            assert event in _TOPIC_MAPPING, f"Event {event} should be mapped but is missing"


class TestOtherEnums:
    """Test other enum classes for basic functionality."""

    def test_batch_status_values(self) -> None:
        """Test that BatchStatus enum has expected values."""
        # Test a few key statuses exist
        assert hasattr(BatchStatus, "AWAITING_CONTENT_VALIDATION")
        assert hasattr(BatchStatus, "READY_FOR_PIPELINE_EXECUTION")
        assert hasattr(BatchStatus, "PROCESSING_PIPELINES")
        assert hasattr(BatchStatus, "COMPLETED_SUCCESSFULLY")

    def test_content_type_values(self) -> None:
        """Test that ContentType enum has expected values."""
        assert hasattr(ContentType, "ORIGINAL_ESSAY")
        assert hasattr(ContentType, "CORRECTED_TEXT")
        assert hasattr(ContentType, "CJ_RESULTS_JSON")

    def test_error_code_values(self) -> None:
        """Test that ErrorCode enum has expected values."""
        assert hasattr(ErrorCode, "UNKNOWN_ERROR")
        assert hasattr(ErrorCode, "VALIDATION_ERROR")
        assert hasattr(ErrorCode, "CJ_ASSESSMENT_SERVICE_ERROR")

    def test_enum_values_are_strings(self) -> None:
        """Test that all enum values are strings."""
        # Test BatchStatus
        for status in BatchStatus:
            assert isinstance(status.value, str)
            assert len(status.value) > 0

        # Test ContentType
        for content_type in ContentType:
            assert isinstance(content_type.value, str)
            assert len(content_type.value) > 0

        # Test ErrorCode
        for error_code in ErrorCode:
            assert isinstance(error_code.value, str)
            assert len(error_code.value) > 0

        # Test ProcessingEvent
        for event in ProcessingEvent:
            assert isinstance(event.value, str)
            assert len(event.value) > 0


class TestTopicMappingPrivateDict:
    """Test the _TOPIC_MAPPING private dictionary."""

    def test_topic_mapping_is_dict(self) -> None:
        """Test that _TOPIC_MAPPING is a dictionary."""
        assert isinstance(_TOPIC_MAPPING, dict)
        assert len(_TOPIC_MAPPING) > 0

    def test_topic_mapping_keys_are_processing_events(self) -> None:
        """Test that all keys in _TOPIC_MAPPING are ProcessingEvent instances."""
        for key in _TOPIC_MAPPING.keys():
            assert isinstance(key, ProcessingEvent)

    def test_topic_mapping_values_are_strings(self) -> None:
        """Test that all values in _TOPIC_MAPPING are strings."""
        for value in _TOPIC_MAPPING.values():
            assert isinstance(value, str)
            assert len(value) > 0

    def test_no_duplicate_topic_names(self) -> None:
        """Test that there are no duplicate topic names in the mapping."""
        topic_names = list(_TOPIC_MAPPING.values())
        unique_topic_names = set(topic_names)
        assert len(topic_names) == len(unique_topic_names), "Duplicate topic names found"
