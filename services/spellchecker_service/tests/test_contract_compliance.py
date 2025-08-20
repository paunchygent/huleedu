"""
Unit tests for event contract compliance.

These tests focus on ensuring events conform to the expected schemas and contracts,
validating the structure of messages sent by the spell checker service.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from common_core.domain_enums import ContentType
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.spellcheck_models import (
    SpellcheckPhaseCompletedV1,
    SpellcheckResultDataV1,
    SpellcheckResultV1,
)
from common_core.status_enums import EssayStatus, ProcessingStage

from services.spellchecker_service.event_processor import process_single_message
from services.spellchecker_service.protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
)
from services.spellchecker_service.tests.mocks import MockWhitelist, create_mock_parallel_processor

# Constants for frequently referenced values
ESSAY_RESULT_EVENT = ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED
SPELLCHECK_PHASE_COMPLETED = ProcessingEvent.SPELLCHECK_PHASE_COMPLETED
SPELLCHECK_RESULTS = ProcessingEvent.SPELLCHECK_RESULTS
CORRECTED_TEXT_TYPE = ContentType.CORRECTED_TEXT

if TYPE_CHECKING:
    pass


class TestEventContractCompliance:
    """Test compliance with event contracts and Pydantic models."""

    @pytest.mark.asyncio
    async def test_published_event_structure(
        self,
        kafka_message: Any,
        mock_kafka_bus: Any,  # Updated from mock_producer to mock_kafka_bus
        mock_http_session: Any,
        sample_essay_id: str,
        sample_text: str,
        corrected_text: str,
    ) -> None:
        """Test that published events conform to the expected event contract structure."""

        # 1. Mock Protocol Implementations - only mock external dependencies
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.return_value = sample_text

        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        mock_corrected_storage_id = "corrected_storage_id_xyz"
        mock_result_store.store_content.return_value = mock_corrected_storage_id

        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)

        # Use REAL spell logic implementation
        from services.spellchecker_service.implementations.spell_logic_impl import (
            DefaultSpellLogic,
        )

        real_spell_logic = DefaultSpellLogic(
            result_store=mock_result_store,
            http_session=mock_http_session,
            whitelist=MockWhitelist(),
            parallel_processor=create_mock_parallel_processor(),
        )

        # Act - Process message using real spell checking with NEW signature
        result = await process_single_message(
            kafka_message,
            mock_http_session,
            mock_content_client,
            mock_result_store,
            mock_event_publisher,
            real_spell_logic,  # Use real implementation
            consumer_group_id="test-group",
        )

        # Assert
        assert result is True  # Should commit the message

        # Verify the result was published (with dual events)
        mock_event_publisher.publish_spellcheck_result.assert_called_once()

        # Extract the published result from the real spell checking
        publish_call_args = mock_event_publisher.publish_spellcheck_result.call_args
        published_result: SpellcheckResultDataV1 = publish_call_args[0][0]

        # Verify contract compliance - the event should have all required fields
        assert published_result.event_name == ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED
        assert published_result.entity_id == sample_essay_id
        assert published_result.entity_type == "essay"
        assert published_result.status == EssayStatus.SPELLCHECKED_SUCCESS
        assert published_result.timestamp is not None
        assert published_result.system_metadata is not None
        assert published_result.system_metadata.processing_stage == ProcessingStage.COMPLETED
        assert published_result.corrections_made is not None
        assert published_result.storage_metadata is not None
        assert ContentType.CORRECTED_TEXT in published_result.storage_metadata.references
        assert (
            published_result.storage_metadata.references[ContentType.CORRECTED_TEXT]["default"]
            == mock_corrected_storage_id
        )

    @pytest.mark.asyncio
    async def test_correlation_id_propagation(
        self,
        kafka_message: Any,
        mock_kafka_bus: Any,  # Updated from mock_producer to mock_kafka_bus
        mock_http_session: Any,
        sample_essay_id: str,
        sample_text: str,
        corrected_text: str,
    ) -> None:
        """Test that correlation_id is properly propagated from input to output."""

        # 1. Mock Protocol Implementations - only mock external dependencies
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.return_value = sample_text

        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        mock_corrected_storage_id = "corrected_storage_id_def"
        mock_result_store.store_content.return_value = mock_corrected_storage_id

        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)

        # Use REAL spell logic implementation
        from services.spellchecker_service.implementations.spell_logic_impl import (
            DefaultSpellLogic,
        )

        real_spell_logic = DefaultSpellLogic(
            result_store=mock_result_store,
            http_session=mock_http_session,
            whitelist=MockWhitelist(),
            parallel_processor=create_mock_parallel_processor(),
        )

        # Act - Process message using real spell checking with NEW signature
        result = await process_single_message(
            kafka_message,
            mock_http_session,
            mock_content_client,
            mock_result_store,
            mock_event_publisher,
            real_spell_logic,  # Use real implementation
            consumer_group_id="test-group",
        )

        # Assert
        assert result is True  # Should commit the message

        # Verify the result was published (with dual events)
        mock_event_publisher.publish_spellcheck_result.assert_called_once()

        # Extract the correlation_id passed to publisher
        call_args = mock_event_publisher.publish_spellcheck_result.call_args
        passed_correlation_id: UUID = call_args[0][1]  # Second argument

        # Extract expected correlation_id from the original kafka message
        request_envelope_dict = json.loads(kafka_message.value.decode("utf-8"))
        expected_correlation_id = (
            UUID(request_envelope_dict["correlation_id"])
            if request_envelope_dict.get("correlation_id")
            else None
        )

        # Verify correlation_id propagation
        assert passed_correlation_id == expected_correlation_id

        # Verify the published result has the expected correlation ID context
        published_result: SpellcheckResultDataV1 = call_args[0][0]
        assert (
            published_result.entity_id == sample_essay_id
        )  # Should match the essay from the request

    @pytest.mark.asyncio
    async def test_dual_event_publisher_contract_compliance(
        self,
        kafka_message: Any,
        mock_kafka_bus: Any,
        mock_http_session: Any,
        sample_essay_id: str,
        sample_text: str,
        corrected_text: str,
    ) -> None:
        """Test that event publisher creates both thin and rich events with correct structure."""
        
        # 1. Mock Protocol Implementations - only mock external dependencies
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.return_value = sample_text

        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        mock_corrected_storage_id = "corrected_storage_id_dual"
        mock_result_store.store_content.return_value = mock_corrected_storage_id

        # Use REAL event publisher implementation to test dual event creation
        from services.spellchecker_service.implementations.event_publisher_impl import (
            DefaultSpellcheckEventPublisher,
        )
        from services.spellchecker_service.implementations.outbox_manager import OutboxManager
        
        # Mock the outbox manager
        mock_outbox_manager = AsyncMock(spec=OutboxManager)
        
        real_event_publisher = DefaultSpellcheckEventPublisher(
            source_service_name="test-spellchecker-service",
            outbox_manager=mock_outbox_manager,
        )

        # Use REAL spell logic implementation
        from services.spellchecker_service.implementations.spell_logic_impl import (
            DefaultSpellLogic,
        )

        real_spell_logic = DefaultSpellLogic(
            result_store=mock_result_store,
            http_session=mock_http_session,
            whitelist=MockWhitelist(),
            parallel_processor=create_mock_parallel_processor(),
        )

        # Act - Process message using real implementations
        result = await process_single_message(
            kafka_message,
            mock_http_session,
            mock_content_client,
            mock_result_store,
            real_event_publisher,  # Use real event publisher
            real_spell_logic,      # Use real spell logic
            consumer_group_id="test-group",
        )

        # Assert
        assert result is True  # Should commit the message

        # Verify the event publisher created BOTH events in outbox
        assert mock_outbox_manager.publish_to_outbox.call_count == 2

        # Extract the calls
        thin_call = mock_outbox_manager.publish_to_outbox.call_args_list[0]
        rich_call = mock_outbox_manager.publish_to_outbox.call_args_list[1]

        # Verify thin event (SPELLCHECK_PHASE_COMPLETED)
        assert thin_call.kwargs["event_type"] == "SpellcheckPhaseCompletedV1"
        assert thin_call.kwargs["topic"] == topic_name(SPELLCHECK_PHASE_COMPLETED)
        
        thin_envelope = thin_call.kwargs["event_data"]
        assert thin_envelope.event_type == "SpellcheckPhaseCompletedV1"
        assert thin_envelope.source_service == "test-spellchecker-service"
        
        # Verify thin event data structure compliance
        thin_data = thin_envelope.data
        assert isinstance(thin_data, SpellcheckPhaseCompletedV1)
        assert thin_data.entity_id == sample_essay_id
        assert thin_data.batch_id is not None  # Should have batch ID from parent_id
        assert thin_data.status is not None    # Should have processing status
        assert thin_data.corrected_text_storage_id == mock_corrected_storage_id
        assert thin_data.processing_duration_ms >= 0
        assert thin_data.timestamp is not None
        assert thin_data.correlation_id is not None

        # Verify rich event (SPELLCHECK_RESULTS)
        assert rich_call.kwargs["event_type"] == "SpellcheckResultV1"
        assert rich_call.kwargs["topic"] == topic_name(SPELLCHECK_RESULTS)
        
        rich_envelope = rich_call.kwargs["event_data"]
        assert rich_envelope.event_type == "SpellcheckResultV1"
        assert rich_envelope.source_service == "test-spellchecker-service"
        
        # Verify rich event data structure compliance
        rich_data = rich_envelope.data
        assert isinstance(rich_data, SpellcheckResultV1)
        assert rich_data.entity_id == sample_essay_id
        assert rich_data.entity_type == "essay"
        assert rich_data.corrections_made > 0  # Should have real corrections from spell logic
        assert rich_data.correction_metrics is not None
        assert rich_data.original_text_storage_id is not None
        assert rich_data.corrected_text_storage_id == mock_corrected_storage_id
        assert rich_data.processing_duration_ms >= 0
        assert rich_data.processor_version == "pyspellchecker_1.0_L2_swedish"
        assert rich_data.timestamp is not None
        assert rich_data.correlation_id is not None

        # Verify both events have the same correlation ID
        assert thin_data.correlation_id == rich_data.correlation_id
        
        # Verify both events have the same entity_id
        assert thin_data.entity_id == rich_data.entity_id

        # Verify envelope metadata includes partition key
        assert thin_envelope.metadata["partition_key"] == sample_essay_id
        assert rich_envelope.metadata["partition_key"] == sample_essay_id
