"""
Unit tests for event contract compliance.

These tests focus on ensuring events conform to the expected schemas and contracts,
validating the structure of messages sent by the spell checker service.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from common_core.enums import (
    ContentType,
    EssayStatus,
    ProcessingEvent,
    ProcessingStage,
)
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckResultDataV1

from ..event_processor import process_single_message
from ..protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
)
from ..worker_main import (
    KAFKA_EVENT_TYPE_SPELLCHECK_COMPLETED,
    SOURCE_SERVICE_NAME_CONFIG,
)

# Constants for frequently referenced values
ESSAY_RESULT_EVENT = ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED
CORRECTED_TEXT_TYPE = ContentType.CORRECTED_TEXT


class TestEventContractCompliance:
    """Test compliance with event contracts and Pydantic models."""

    @pytest.mark.asyncio
    async def test_published_event_structure(
        self,
        kafka_message: Any,
        mock_producer: Any,  # AIOKafkaProducer mock
        mock_http_session: Any,
        sample_essay_id: str,  # Keep for assertions
        sample_text: str,  # Added: needed for mock_content_client and spell_check_algo
        corrected_text: str,  # Added: needed for mock_spell_check_algo
    ) -> None:
        """Test that published events conform to the expected Pydantic schema."""

        # 1. Mock Protocol Implementations
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.return_value = sample_text

        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        mock_corrected_storage_id = "corrected_storage_id_def"
        mock_result_store.store_content.return_value = mock_corrected_storage_id

        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)
        # We will inspect the arguments passed to this mock

        # Act - Let the real algorithm run since it's working correctly
        await process_single_message(
            kafka_message,
            mock_producer,  # Passed to event_publisher
            mock_http_session,
            mock_content_client,
            mock_result_store,
            mock_event_publisher,
            consumer_group_id="test-group",
            kafka_queue_latency_metric=None,
        )

        # Assert
        mock_event_publisher.publish_spellcheck_result.assert_called_once()

        # Extract the published message data from the event_publisher mock
        call_args = mock_event_publisher.publish_spellcheck_result.call_args
        # call_args[0] is a tuple of positional args: (producer, event_data, correlation_id)
        published_event_data: SpellcheckResultDataV1 = call_args[0][1]
        published_correlation_id: UUID | None = call_args[0][2]

        # Build an EventEnvelope with the captured data to validate the whole structure
        # The actual EventEnvelope is created inside publish_spellcheck_result,
        # but its 'data' field is what we have as published_event_data.
        # We need the original request envelope to get correlation_id for a full check,
        # or assume kafka_message fixture provides a request_envelope with a correlation_id.

        request_envelope_dict = json.loads(kafka_message.value.decode("utf-8"))
        expected_correlation_id = (
            UUID(request_envelope_dict["correlation_id"])
            if request_envelope_dict.get("correlation_id")
            else None
        )

        # Construct a representative EventEnvelope for validation
        # based on what event_publisher received
        # The actual event_type for the *envelope* comes from the publisher's config,
        # so we assume KAFKA_EVENT_TYPE_SPELLCHECK_COMPLETED from event_router.py
        expected_event_type_str = KAFKA_EVENT_TYPE_SPELLCHECK_COMPLETED
        expected_source_service = SOURCE_SERVICE_NAME_CONFIG

        temp_envelope_for_validation = EventEnvelope[SpellcheckResultDataV1](
            event_type=expected_event_type_str,
            source_service=expected_source_service,
            correlation_id=published_correlation_id,  # Use what was passed to publisher
            data=published_event_data,
        )
        # Validate the constructed envelope can be dumped and re-parsed (basic Pydantic check)
        # This validates the *structure* of the data that would form the envelope
        validated_envelope = EventEnvelope[SpellcheckResultDataV1].model_validate(
            json.loads(temp_envelope_for_validation.model_dump_json())
        )

        # Verify envelope structure (using validated_envelope)
        assert validated_envelope.event_type == expected_event_type_str
        assert validated_envelope.source_service == expected_source_service
        # Check against original request
        assert validated_envelope.correlation_id == expected_correlation_id

        # Verify data structure (using published_event_data directly, as it IS the data part)
        assert published_event_data.event_name == ESSAY_RESULT_EVENT
        assert published_event_data.status == EssayStatus.SPELLCHECKED_SUCCESS
        assert published_event_data.entity_ref.entity_id == sample_essay_id
        # Real algorithm produces actual corrections - verify it's > 0
        assert published_event_data.corrections_made is not None
        assert published_event_data.corrections_made > 0
        assert published_event_data.storage_metadata is not None
        assert (
            published_event_data.storage_metadata.references[CORRECTED_TEXT_TYPE]["default"]
            == mock_corrected_storage_id
        )
        assert published_event_data.system_metadata.processing_stage == ProcessingStage.COMPLETED

    @pytest.mark.asyncio
    async def test_correlation_id_propagation(
        self,
        kafka_message: Any,  # Using general kafka_message fixture with correlation_id
        mock_producer: Any,
        mock_http_session: Any,
        sample_essay_id: str,  # Keep for assertions and mocking
        sample_text: str,  # Added: needed for mock_content_client and spell_check_algo
        corrected_text: str,  # Added: needed for mock_spell_check_algo
    ) -> None:
        """Test that correlation ID is properly propagated from request to response."""

        # 1. Extract original correlation_id from the incoming kafka_message
        request_envelope_dict = json.loads(kafka_message.value.decode("utf-8"))
        original_correlation_id_str = request_envelope_dict.get("correlation_id")
        assert original_correlation_id_str is not None, (
            "Test setup error: kafka_message fixture must have a correlation_id"
        )
        original_correlation_id = UUID(original_correlation_id_str)

        # 2. Mock Protocol Implementations
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.return_value = sample_text

        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        mock_corrected_storage_id = "corrected_storage_id_efg"
        mock_result_store.store_content.return_value = mock_corrected_storage_id

        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)

        # Act - Let the real algorithm run since it's working correctly
        await process_single_message(
            # This is the ConsumerRecord containing the request envelope string
            kafka_message,
            mock_producer,
            mock_http_session,
            mock_content_client,
            mock_result_store,
            mock_event_publisher,
            consumer_group_id="test-group",
            kafka_queue_latency_metric=None,
        )

        # Assert
        mock_event_publisher.publish_spellcheck_result.assert_called_once()

        # Extract correlation ID from the arguments passed to the event publisher
        call_args = mock_event_publisher.publish_spellcheck_result.call_args
        # args[0] is producer, args[1] is event_data, args[2] is correlation_id
        published_correlation_id: UUID | None = call_args[0][2]

        assert published_correlation_id == original_correlation_id
