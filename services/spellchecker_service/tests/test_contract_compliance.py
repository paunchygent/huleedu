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
from common_core.event_enums import ProcessingEvent
from common_core.events.spellcheck_models import SpellcheckResultDataV1
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
            mock_kafka_bus,  # Updated parameter order and name
            consumer_group_id="test-group",
        )

        # Assert
        assert result is True  # Should commit the message

        # Verify the result was published
        mock_event_publisher.publish_spellcheck_result.assert_called_once()

        # Extract the published result from the real spell checking
        publish_call_args = mock_event_publisher.publish_spellcheck_result.call_args
        published_result: SpellcheckResultDataV1 = publish_call_args[0][1]

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
            mock_kafka_bus,  # Updated parameter order and name
            consumer_group_id="test-group",
        )

        # Assert
        assert result is True  # Should commit the message

        # Verify the result was published
        mock_event_publisher.publish_spellcheck_result.assert_called_once()

        # Extract the correlation_id passed to publisher
        call_args = mock_event_publisher.publish_spellcheck_result.call_args
        passed_correlation_id: UUID = call_args[0][2]  # Third argument

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
        published_result: SpellcheckResultDataV1 = call_args[0][1]
        assert (
            published_result.entity_id == sample_essay_id
        )  # Should match the essay from the request
