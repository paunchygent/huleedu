"""
Integration tests for event processor LLM override handling.

These tests verify end-to-end processing of LLM config overrides
from Kafka message consumption through to core logic execution.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from common_core.events.cj_assessment_events import LLMConfigOverrides

from ..config import Settings
from ..event_processor import process_single_message
from ..protocols import (
    CJDatabaseProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)


class TestEventProcessorOverrides:
    """Test event processor handling of LLM config overrides."""

    @pytest.fixture
    def mock_database(self) -> AsyncMock:
        """Create mock database protocol."""
        return AsyncMock(spec=CJDatabaseProtocol)

    @pytest.fixture
    def mock_content_client(self, sample_essay_text: str) -> AsyncMock:
        """Create mock content client protocol."""
        client = AsyncMock(spec=ContentClientProtocol)
        client.fetch_content = AsyncMock(return_value=sample_essay_text)
        return client

    @pytest.fixture
    def mock_llm_interaction(self, sample_comparison_results: list[Dict[str, Any]]) -> AsyncMock:
        """Create mock LLM interaction protocol."""
        interaction = AsyncMock(spec=LLMInteractionProtocol)
        interaction.perform_comparisons = AsyncMock(return_value=[])
        return interaction

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher protocol."""
        publisher = AsyncMock(spec=CJEventPublisherProtocol)
        publisher.publish_assessment_completed = AsyncMock()
        publisher.publish_assessment_failed = AsyncMock()
        return publisher

    @pytest.fixture
    def mock_core_workflow(self, sample_comparison_results: list[Dict[str, Any]]) -> AsyncMock:
        """Create mock for core assessment workflow."""
        mock_workflow = AsyncMock()
        mock_workflow.return_value = (sample_comparison_results, "cj_batch_123")
        return mock_workflow

    @pytest.mark.asyncio
    async def test_process_message_with_llm_overrides(
        self,
        kafka_message_with_overrides,
        mock_database: AsyncMock,
        mock_content_client: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
        llm_config_overrides: LLMConfigOverrides,
    ) -> None:
        """Test processing Kafka message with LLM config overrides."""
        # Arrange
        with pytest.importorskip("core_logic.core_assessment_logic") as core_logic:
            # Mock the core workflow function
            original_workflow = core_logic.run_cj_assessment_workflow
            mock_workflow_result = (
                [{"els_essay_id": "essay1", "rank": 1, "score": 0.85}],
                "cj_batch_456"
            )
            core_logic.run_cj_assessment_workflow = AsyncMock(
                return_value=mock_workflow_result
            )

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

            # Verify core workflow was called with override data
            core_logic.run_cj_assessment_workflow.assert_called_once()
            call_args = core_logic.run_cj_assessment_workflow.call_args
            request_data = call_args[1]['request_data']  # Keyword argument

            # Verify LLM config overrides were included in request data
            assert 'llm_config_overrides' in request_data
            overrides = request_data['llm_config_overrides']
            assert overrides is not None
            assert overrides.model_override == "gpt-4o"
            assert overrides.temperature_override == 0.3
            assert overrides.max_tokens_override == 2000
            assert overrides.provider_override == "openai"

            # Verify completion event was published
            mock_event_publisher.publish_assessment_completed.assert_called_once()

            # Restore original function
            core_logic.run_cj_assessment_workflow = original_workflow

    @pytest.mark.asyncio
    async def test_process_message_without_llm_overrides(
        self,
        kafka_message_no_overrides,
        mock_database: AsyncMock,
        mock_content_client: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
    ) -> None:
        """Test processing Kafka message without LLM config overrides."""
        # Arrange
        with pytest.importorskip("core_logic.core_assessment_logic") as core_logic:
            original_workflow = core_logic.run_cj_assessment_workflow
            mock_workflow_result = (
                [{"els_essay_id": "essay1", "rank": 1, "score": 0.85}],
                "cj_batch_789"
            )
            core_logic.run_cj_assessment_workflow = AsyncMock(
                return_value=mock_workflow_result
            )

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

            # Verify core workflow was called without override data
            core_logic.run_cj_assessment_workflow.assert_called_once()
            call_args = core_logic.run_cj_assessment_workflow.call_args
            request_data = call_args[1]['request_data']

            # Verify LLM config overrides field is None
            assert 'llm_config_overrides' in request_data
            assert request_data['llm_config_overrides'] is None

            # Verify completion event was published
            mock_event_publisher.publish_assessment_completed.assert_called_once()

            # Restore original function
            core_logic.run_cj_assessment_workflow = original_workflow

    @pytest.mark.asyncio
    async def test_process_message_deserialization_with_overrides(
        self,
        kafka_message_with_overrides,
        mock_database: AsyncMock,
        mock_content_client: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
    ) -> None:
        """Test that message deserialization correctly handles LLM overrides."""
        # Arrange
        with pytest.importorskip("core_logic.core_assessment_logic") as core_logic:
            original_workflow = core_logic.run_cj_assessment_workflow
            # Mock workflow to fail early so we can focus on deserialization
            core_logic.run_cj_assessment_workflow = AsyncMock(
                side_effect=Exception("Test early exit")
            )

            # Act & Assert - Should not fail during deserialization
            try:
                result = await process_single_message(
                    msg=kafka_message_with_overrides,
                    database=mock_database,
                    content_client=mock_content_client,
                    event_publisher=mock_event_publisher,
                    llm_interaction=mock_llm_interaction,
                    settings_obj=mock_settings,
                )
                # Expect False due to our exception, but deserialization should succeed
                assert result is False

                # Verify workflow was called (meaning deserialization succeeded)
                core_logic.run_cj_assessment_workflow.assert_called_once()

            finally:
                # Restore original function
                core_logic.run_cj_assessment_workflow = original_workflow

    @pytest.mark.asyncio
    async def test_process_message_correlation_id_propagation_with_overrides(
        self,
        kafka_message_with_overrides,
        mock_database: AsyncMock,
        mock_content_client: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
        cj_request_envelope_with_overrides,
    ) -> None:
        """Test correlation ID propagation when processing messages with overrides."""
        # Arrange
        expected_correlation_id = str(cj_request_envelope_with_overrides.correlation_id)

        with pytest.importorskip("core_logic.core_assessment_logic") as core_logic:
            original_workflow = core_logic.run_cj_assessment_workflow
            mock_workflow_result = (
                [{"els_essay_id": "essay1", "rank": 1, "score": 0.85}],
                "cj_batch_999"
            )
            core_logic.run_cj_assessment_workflow = AsyncMock(
                return_value=mock_workflow_result
            )

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

            # Verify correlation ID was propagated to core workflow
            core_logic.run_cj_assessment_workflow.assert_called_once()
            call_args = core_logic.run_cj_assessment_workflow.call_args
            correlation_id = call_args[1]['correlation_id']
            assert correlation_id == expected_correlation_id

            # Verify correlation ID was propagated to event publisher
            mock_event_publisher.publish_assessment_completed.assert_called_once()
            publisher_call_args = mock_event_publisher.publish_assessment_completed.call_args
            published_correlation_id = publisher_call_args[1]['correlation_id']
            # Should be UUID object with same string representation
            assert str(published_correlation_id) == expected_correlation_id

            # Restore original function
            core_logic.run_cj_assessment_workflow = original_workflow

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
        """Test handling of validation errors in messages with LLM overrides."""
        # Arrange - Create message with invalid LLM overrides
        import json

        from aiokafka import ConsumerRecord

        invalid_message_data = {
            "event_type": "els.cj_assessment.requested.v1",
            "source_service": "essay-lifecycle-service",
            "data": {
                "llm_config_overrides": {
                    "temperature_override": 3.0,  # Invalid: > 2.0
                    "max_tokens_override": -100,   # Invalid: < 0
                },
                # ... other required fields would be here but we expect validation to fail
            }
        }

        invalid_kafka_message = MagicMock(spec=ConsumerRecord)
        invalid_kafka_message.topic = "test-topic"
        invalid_kafka_message.partition = 0
        invalid_kafka_message.offset = 456
        invalid_kafka_message.key = sample_batch_id.encode("utf-8")
        invalid_kafka_message.value = json.dumps(invalid_message_data).encode("utf-8")

        # Act
        result = await process_single_message(
            msg=invalid_kafka_message,
            database=mock_database,
            content_client=mock_content_client,
            event_publisher=mock_event_publisher,
            llm_interaction=mock_llm_interaction,
            settings_obj=mock_settings,
        )

        # Assert - Should return False for unparseable message
        assert result is False

        # Verify no downstream calls were made due to validation failure
        mock_content_client.fetch_content.assert_not_called()
        mock_llm_interaction.perform_comparisons.assert_not_called()
        mock_event_publisher.publish_assessment_completed.assert_not_called()
