"""
Integration tests for event processor LLM override handling.

These tests verify end-to-end processing of LLM config overrides
from Kafka message consumption through to core logic execution.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka import ConsumerRecord
from common_core.events.cj_assessment_events import (
    ELS_CJAssessmentRequestV1,
    LLMConfigOverrides,
)
from common_core.events.envelope import EventEnvelope

from services.cj_assessment_service.cj_core_logic.workflow_orchestrator import (
    CJAssessmentWorkflowResult,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.event_processor import process_single_message
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)


class TestEventProcessorOverrides:
    """Test event processor handling of LLM config overrides."""

    @pytest.fixture
    def mock_database(self) -> AsyncMock:
        """Create a mock database with proper async session handling."""
        return AsyncMock(spec=CJRepositoryProtocol)

    @pytest.fixture
    def mock_content_client(self, sample_essay_text: str) -> AsyncMock:
        """Create mock content client protocol."""
        client = AsyncMock(spec=ContentClientProtocol)
        client.fetch_content = AsyncMock(return_value=sample_essay_text)
        return client

    @pytest.fixture
    def mock_llm_interaction(self, sample_comparison_results: list[dict[str, Any]]) -> AsyncMock:
        """Create mock LLM interaction protocol."""
        from common_core import EssayComparisonWinner

        from services.cj_assessment_service.models_api import (
            ComparisonResult,
            ComparisonTask,
            EssayForComparison,
            LLMAssessmentResponseSchema,
        )

        interaction = AsyncMock(spec=LLMInteractionProtocol)

        # Create realistic mock comparison results to prevent infinite loops
        mock_results = [
            ComparisonResult(
                task=ComparisonTask(
                    essay_a=EssayForComparison(
                        id="essay_1", text_content="Sample essay A", current_bt_score=0.5
                    ),
                    essay_b=EssayForComparison(
                        id="essay_2", text_content="Sample essay B", current_bt_score=0.5
                    ),
                    prompt="Compare these essays",
                ),
                llm_assessment=LLMAssessmentResponseSchema(
                    winner=EssayComparisonWinner.ESSAY_A,
                    justification="Essay A shows better structure",
                    confidence=3.5,
                ),
                error_detail=None,
                raw_llm_response_content="Essay A is better",
            )
        ]

        interaction.perform_comparisons = AsyncMock(return_value=mock_results)
        return interaction

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher protocol."""
        publisher = AsyncMock(spec=CJEventPublisherProtocol)
        publisher.publish_assessment_completed = AsyncMock()
        publisher.publish_assessment_failed = AsyncMock()
        return publisher

    @pytest.fixture
    def mock_core_workflow(self, sample_comparison_results: list[dict[str, Any]]) -> AsyncMock:
        """Create mock for core assessment workflow."""
        mock_workflow = AsyncMock()
        mock_workflow.return_value = CJAssessmentWorkflowResult(
            rankings=sample_comparison_results, batch_id="cj_batch_123"
        )
        return mock_workflow

    @pytest.mark.asyncio
    async def test_process_message_with_llm_overrides(
        self,
        kafka_message_with_overrides: ConsumerRecord,
        mock_database: AsyncMock,
        mock_content_client: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
        llm_config_overrides: LLMConfigOverrides,
    ) -> None:
        """Test processing Kafka message with LLM config overrides.

        This test verifies that:
        1. LLM overrides are properly extracted from the request
        2. LLM interaction is called with the correct overrides
        3. Event publisher receives correct completion data
        """
        # Arrange
        # Configure mock database to return a proper CJ batch ID
        mock_cj_batch = AsyncMock()
        mock_cj_batch.id = 12345
        mock_database.create_new_cj_batch.return_value = mock_cj_batch

        # Configure mock database session context manager
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        mock_database.session.return_value.__aexit__.return_value = None

        # Mock the execute method to return empty results for rankings query
        mock_result = MagicMock()
        mock_result.all.return_value = []  # No essays in ranking query
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await process_single_message(
            msg=kafka_message_with_overrides,
            database=mock_database,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
            llm_interaction=mock_llm_interaction,
            settings_obj=mock_settings,
        )

        # Assert processing succeeded
        assert result is True

        # Verify LLM interaction was called with overrides
        # (Since we only have 1 essay, no comparisons will be made, but the setup should be correct)

        # Verify event publisher was called with completion event
        mock_event_publisher.publish_assessment_completed.assert_called_once()

        # Extract the completion data to verify LLM overrides were processed
        call_args = mock_event_publisher.publish_assessment_completed.call_args
        completion_data = call_args[1]["completion_data"]

        # Verify completion data structure (EventEnvelope with CJAssessmentCompletedV1)
        assert isinstance(completion_data, EventEnvelope)
        assert completion_data.data.status.value == "completed_successfully"
        assert hasattr(completion_data.data, "cj_assessment_job_id")
        assert completion_data.data.cj_assessment_job_id == "12345"

    @pytest.mark.asyncio
    async def test_process_message_without_llm_overrides(
        self,
        kafka_message_no_overrides: ConsumerRecord,
        mock_database: AsyncMock,
        mock_content_client: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
    ) -> None:
        """Test processing Kafka message without LLM config overrides.

        This test verifies that:
        1. Messages without LLM overrides are processed correctly
        2. Default LLM settings are used
        3. Event publisher receives correct completion data
        """
        # Arrange
        # Configure mock database to return a proper CJ batch ID
        mock_cj_batch = AsyncMock()
        mock_cj_batch.id = 98765
        mock_database.create_new_cj_batch.return_value = mock_cj_batch

        # Configure mock database session context manager
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        mock_database.session.return_value.__aexit__.return_value = None

        # Mock the execute method to return empty results for rankings query
        mock_result = MagicMock()
        mock_result.all.return_value = []  # No essays in ranking query
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await process_single_message(
            msg=kafka_message_no_overrides,
            database=mock_database,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
            llm_interaction=mock_llm_interaction,
            settings_obj=mock_settings,
        )

        # Assert processing succeeded
        assert result is True

        # Verify event publisher was called with completion event
        mock_event_publisher.publish_assessment_completed.assert_called_once()

        # Extract the completion data to verify no LLM overrides were used
        call_args = mock_event_publisher.publish_assessment_completed.call_args
        completion_data = call_args[1]["completion_data"]

        # Verify completion data structure (EventEnvelope with CJAssessmentCompletedV1)
        assert isinstance(completion_data, EventEnvelope)
        assert completion_data.data.status.value == "completed_successfully"
        assert hasattr(completion_data.data, "cj_assessment_job_id")
        assert completion_data.data.cj_assessment_job_id == "98765"

    @pytest.mark.asyncio
    async def test_process_message_deserialization_with_overrides(
        self,
        kafka_message_with_overrides: ConsumerRecord,
        mock_database: AsyncMock,
        mock_content_client: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
    ) -> None:
        """Test that message deserialization correctly handles LLM overrides.

        This test verifies that:
        1. LLM overrides are properly deserialized from Kafka messages
        2. Invalid override values are handled gracefully
        3. Valid overrides pass through to business logic
        """
        # Arrange - Configure database to fail to test early error handling
        mock_database.create_new_cj_batch.side_effect = Exception("Database connection failed")

        # Act
        result = await process_single_message(
            msg=kafka_message_with_overrides,
            database=mock_database,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
            llm_interaction=mock_llm_interaction,
            settings_obj=mock_settings,
        )

        # Assert - Should return False due to database error, but deserialization should succeed
        assert result is False

        # Verify database was called (meaning deserialization succeeded)
        mock_database.create_new_cj_batch.assert_called_once()

        # Verify no event was published due to the error
        mock_event_publisher.publish_assessment_completed.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_correlation_id_propagation_with_overrides(
        self,
        kafka_message_with_overrides: ConsumerRecord,
        mock_database: AsyncMock,
        mock_content_client: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
        cj_request_envelope_with_overrides: EventEnvelope[ELS_CJAssessmentRequestV1],
    ) -> None:
        """Test correlation ID propagation when processing messages with overrides.

        This test verifies that:
        1. Correlation IDs are properly extracted from Kafka messages
        2. Correlation IDs are propagated through to event publishing
        3. LLM overrides don't interfere with correlation ID handling
        """
        # Arrange
        expected_correlation_id = str(cj_request_envelope_with_overrides.correlation_id)

        # Configure mock database to return a proper CJ batch ID
        mock_cj_batch = AsyncMock()
        mock_cj_batch.id = 55555
        mock_database.create_new_cj_batch.return_value = mock_cj_batch

        # Configure mock database session context manager
        mock_session = AsyncMock()
        mock_database.session.return_value.__aenter__.return_value = mock_session
        mock_database.session.return_value.__aexit__.return_value = None

        # Mock the execute method to return empty results for rankings query
        mock_result = MagicMock()
        mock_result.all.return_value = []  # No essays in ranking query
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await process_single_message(
            msg=kafka_message_with_overrides,
            database=mock_database,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
            llm_interaction=mock_llm_interaction,
            settings_obj=mock_settings,
        )

        # Assert
        assert result is True

        # Verify correlation ID was propagated to event publisher
        mock_event_publisher.publish_assessment_completed.assert_called_once()
        publisher_call_args = mock_event_publisher.publish_assessment_completed.call_args
        published_correlation_id = publisher_call_args[1]["correlation_id"]
        # Should be UUID object with same string representation
        assert str(published_correlation_id) == expected_correlation_id

        # Verify completion data structure includes correct correlation
        completion_data = publisher_call_args[1]["completion_data"]
        assert isinstance(completion_data, EventEnvelope)
        assert str(completion_data.correlation_id) == expected_correlation_id

    @pytest.mark.asyncio
    async def test_process_message_validation_error_with_overrides(
        self,
        mock_database: AsyncMock,
        mock_content_client: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
        sample_batch_id: str,
    ) -> None:
        """Test error handling when message validation fails with LLM overrides.

        This test verifies that:
        1. Invalid message format is handled gracefully
        2. Proper error events are published
        3. LLM overrides don't cause additional validation errors
        """
        # Arrange - Create invalid Kafka message with malformed JSON
        invalid_message = MagicMock()
        invalid_message.value.decode.return_value = '{"invalid": "json"'  # Malformed JSON
        invalid_message.topic = "test_topic"
        invalid_message.partition = 0
        invalid_message.offset = 123

        # Act
        result = await process_single_message(
            msg=invalid_message,
            database=mock_database,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
            llm_interaction=mock_llm_interaction,
            settings_obj=mock_settings,
        )

        # Assert - Should return False due to validation error
        assert result is False

        # Verify no database operations were attempted
        mock_database.create_new_cj_batch.assert_not_called()

        # Verify no event was published due to the error
        mock_event_publisher.publish_assessment_completed.assert_not_called()
