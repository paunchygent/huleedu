"""
Unit tests for the spell checker event router.

These tests focus on testing the event routing and message processing logic
with dependency injection, ensuring correct handling of various scenarios.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from common_core.enums import (
    ContentType,
    EssayStatus,
    ProcessingEvent,
    ProcessingStage,
)
from common_core.events.spellcheck_models import SpellcheckResultDataV1

from ..event_router import process_single_message
from ..protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
)

# Constants for frequently referenced values
ESSAY_RESULT_EVENT = ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED
CORRECTED_TEXT_TYPE = ContentType.CORRECTED_TEXT


class TestProcessSingleMessage:
    """Test the core message processing function with dependency injection."""

    @pytest.mark.asyncio
    async def test_successful_processing(
        self,
        kafka_message: Any,
        mock_producer: Any,
        mock_http_session: Any,
        sample_essay_id: str,
        sample_text: str,
        corrected_text: str,
    ) -> None:
        """Test successful processing of a spell check message."""

        # 1. Mock Protocol Implementations
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.return_value = sample_text

        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        # Assume store_content is called for the corrected text and returns a new ID
        mock_corrected_storage_id = "corrected_storage_id_xyz"
        mock_result_store.store_content.return_value = mock_corrected_storage_id

        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)

        # 2. Patch the core algorithm function from core_logic.py
        # This is because DefaultSpellLogic (instantiated inside process_single_message)
        # will call this algorithm.
        corrections_count = 1  # Example
        with patch(
            "spell_checker_service.event_router.default_perform_spell_check_algorithm",
            new_callable=AsyncMock,
            return_value=(corrected_text, corrections_count),
        ) as mock_spell_check_algo:
            # Act
            result = await process_single_message(
                kafka_message,
                mock_producer,
                mock_http_session,
                mock_content_client,
                mock_result_store,
                mock_event_publisher,
            )

            # Assert
            assert result is True  # Should commit the message

            # Verify protocol calls
            mock_content_client.fetch_content.assert_called_once_with(
                storage_id=json.loads(
                    kafka_message.value.decode('utf-8')
                )["data"]["text_storage_id"],
                http_session=mock_http_session,
            )

            # Verify the core algorithm was called by DefaultSpellLogic
            mock_spell_check_algo.assert_called_once_with(sample_text, sample_essay_id)

            # Verify that DefaultSpellLogic (via result_store mock) stored the corrected text
            mock_result_store.store_content.assert_called_once_with(
                original_storage_id=json.loads(
                    kafka_message.value.decode('utf-8')
                )["data"]["text_storage_id"],
                content_type=ContentType.CORRECTED_TEXT,
                content=corrected_text,
                http_session=mock_http_session,
            )

            # Verify event publisher was called
            mock_event_publisher.publish_spellcheck_result.assert_called_once()

            # Detailed assertions on the published event data
            call_args = mock_event_publisher.publish_spellcheck_result.call_args
            # args[0] is producer, args[1] is event_data, args[2] is correlation_id
            published_event_data: SpellcheckResultDataV1 = call_args[0][1]

            assert published_event_data.status == EssayStatus.SPELLCHECKED_SUCCESS
            assert published_event_data.corrections_made == corrections_count
            assert (
                published_event_data.original_text_storage_id ==
                json.loads(kafka_message.value.decode('utf-8'))["data"]["text_storage_id"]
            )
            assert published_event_data.storage_metadata is not None
            assert (
                published_event_data.storage_metadata.references[CORRECTED_TEXT_TYPE]["default"] ==
                mock_corrected_storage_id
            )
            assert published_event_data.entity_ref.entity_id == sample_essay_id
            assert published_event_data.event_name == ESSAY_RESULT_EVENT
            assert (
                published_event_data.system_metadata.processing_stage ==
                ProcessingStage.COMPLETED
            )

    @pytest.mark.asyncio
    async def test_fetch_content_failure(
        self,
        kafka_message: Any,
        mock_producer: Any,
        mock_http_session: Any,
        sample_essay_id: str,
    ) -> None:
        """Test handling when content fetching fails."""

        # 1. Mock Protocol Implementations
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.side_effect = Exception("Failed to fetch content")

        # These will be passed but their main methods shouldn't be called
        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)

        # 2. Patch the core algorithm function (should not be called)
        with patch(
            "spell_checker_service.event_router.default_perform_spell_check_algorithm",
            new_callable=AsyncMock,
        ) as mock_spell_check_algo:
            # Act
            result = await process_single_message(
                kafka_message,
                mock_producer,
                mock_http_session,
                mock_content_client,
                mock_result_store,
                mock_event_publisher
            )

            # Assert
            assert result is True  # Should still commit to avoid reprocessing

            # Verify fetch was attempted
            mock_content_client.fetch_content.assert_called_once_with(
                storage_id=json.loads(kafka_message.value.decode('utf-8'))["data"]["text_storage_id"],
                http_session=mock_http_session,
            )

            # Verify other main operations were NOT called
            mock_spell_check_algo.assert_not_called()
            mock_result_store.store_content.assert_not_called()

            # Verify a failure event was published
            mock_event_publisher.publish_spellcheck_result.assert_called_once()

            call_args = mock_event_publisher.publish_spellcheck_result.call_args
            published_event_data: SpellcheckResultDataV1 = call_args[0][1]

            assert published_event_data.status == EssayStatus.SPELLCHECK_FAILED
            assert published_event_data.entity_ref.entity_id == sample_essay_id
            assert published_event_data.event_name == ESSAY_RESULT_EVENT
            assert published_event_data.system_metadata.processing_stage == ProcessingStage.FAILED
            assert "fetch_error" in published_event_data.system_metadata.error_info
            assert (
                "Failed to fetch original content"
                in published_event_data.system_metadata.error_info["fetch_error"]
            )

    @pytest.mark.asyncio
    async def test_store_content_failure(
        self,
        kafka_message: Any,
        mock_producer: Any,
        mock_http_session: Any,
        sample_text: str,
        sample_essay_id: str,
        corrected_text: str,
    ) -> None:
        """Test handling when content storing fails."""

        # 1. Mock Protocol Implementations
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.return_value = sample_text  # Success

        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        # Set side effect to simulate failure
        mock_result_store.store_content.side_effect = Exception("Failed to store content")
        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)

        # 2. Patch the core algorithm function (should be called and succeed)
        corrections_count = 1
        with patch(
            "spell_checker_service.event_router.default_perform_spell_check_algorithm",
            new_callable=AsyncMock,
            return_value=(corrected_text, corrections_count),
        ) as mock_spell_check_algo:
            # Act
            result = await process_single_message(
                kafka_message,
                mock_producer,
                mock_http_session,
                mock_content_client,
                mock_result_store,
                mock_event_publisher,
            )

            # Assert
            assert result is True  # Should still commit to avoid reprocessing

            # Verify fetch and spell check algorithm were called
            mock_content_client.fetch_content.assert_called_once()
            mock_spell_check_algo.assert_called_once_with(sample_text, sample_essay_id)

            # Verify store_content was attempted
            mock_result_store.store_content.assert_called_once_with(
                original_storage_id=json.loads(
                    kafka_message.value.decode('utf-8')
                )["data"]["text_storage_id"],
                content_type=ContentType.CORRECTED_TEXT,
                content=corrected_text,
                http_session=mock_http_session,
            )

            # Verify a failure event was published
            mock_event_publisher.publish_spellcheck_result.assert_called_once()
            call_args = mock_event_publisher.publish_spellcheck_result.call_args
            published_event_data: SpellcheckResultDataV1 = call_args[0][1]

            assert published_event_data.status == EssayStatus.SPELLCHECK_FAILED
            assert published_event_data.entity_ref.entity_id == sample_essay_id
            assert published_event_data.event_name == ESSAY_RESULT_EVENT
            assert published_event_data.system_metadata.processing_stage == ProcessingStage.FAILED
            assert "spellcheck_error" in published_event_data.system_metadata.error_info
            # Check that the error message contains key parts rather than exact match
            error_message = published_event_data.system_metadata.error_info["spellcheck_error"]
            assert "Exception storing corrected text" in error_message
            assert "Failed to store content" in error_message or "validation error" in error_message
            # Original text ID should still be there
            json_data = json.loads(kafka_message.value.decode('utf-8'))
            assert (
                published_event_data.original_text_storage_id ==
                json_data["data"]["text_storage_id"]
            )
            # Storage metadata for corrected text should be None because storing failed
            assert published_event_data.storage_metadata is None
            # Corrections count might still be reported as the algo ran
            assert published_event_data.corrections_made == corrections_count

    @pytest.mark.asyncio
    async def test_spell_check_failure(
        self,
        kafka_message: Any,
        mock_producer: Any,
        mock_http_session: Any,
        sample_text: str,
        sample_essay_id: str,
    ) -> None:
        """Test handling when spell checking fails."""

        # 1. Mock Protocol Implementations
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.return_value = sample_text  # Success

        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)

        # 2. Patch the core algorithm function to simulate failure
        # Option B: Return values indicating failure (e.g., None for corrected_text)
        with patch(
            "spell_checker_service.event_router.default_perform_spell_check_algorithm",
            new_callable=AsyncMock,
            return_value=(None, 0),  # Simulate algorithm returning no corrected text
        ) as mock_spell_check_algo:
            # Act
            result = await process_single_message(
                kafka_message,
                mock_producer,
                mock_http_session,
                mock_content_client,
                mock_result_store,
                mock_event_publisher,
            )

            # Assert
            assert result is True  # Should commit to avoid reprocessing

            # Verify fetch and spell check algorithm were called
            mock_content_client.fetch_content.assert_called_once()
            mock_spell_check_algo.assert_called_once_with(sample_text, sample_essay_id)

            # Verify store_content was NOT called
            mock_result_store.store_content.assert_not_called()

            # Verify a failure event was published
            mock_event_publisher.publish_spellcheck_result.assert_called_once()
            call_args = mock_event_publisher.publish_spellcheck_result.call_args
            published_event_data: SpellcheckResultDataV1 = call_args[0][1]

            assert published_event_data.status == EssayStatus.SPELLCHECK_FAILED
            assert published_event_data.entity_ref.entity_id == sample_essay_id
            assert published_event_data.event_name == ESSAY_RESULT_EVENT
            assert published_event_data.system_metadata.processing_stage == ProcessingStage.FAILED
            assert "spellcheck_error" in published_event_data.system_metadata.error_info
            assert (
                "Spell check algorithm did not return corrected text"
                in published_event_data.system_metadata.error_info["spellcheck_error"]
            )
            assert published_event_data.storage_metadata is None
            assert published_event_data.corrections_made == 0  # Since algo returned 0

    @pytest.mark.asyncio
    async def test_invalid_message_validation_error(
        self,
        invalid_kafka_message: Any,  # Fixture providing malformed message
        mock_producer: Any,
        mock_http_session: Any,
    ) -> None:
        """Test handling of invalid message that causes validation error."""

        # 1. Mock Protocol Implementations (their methods should not be called)
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)

        # 2. Patch the core algorithm function (should not be called)
        with patch(
            "spell_checker_service.event_router.default_perform_spell_check_algorithm",
            new_callable=AsyncMock,
        ) as mock_spell_check_algo:
            # Act
            result = await process_single_message(
                invalid_kafka_message,
                mock_producer,
                mock_http_session,
                mock_content_client,
                mock_result_store,
                mock_event_publisher,
            )

            # Assert
            assert result is True  # Should commit invalid message to avoid reprocessing

            # Verify no processing functions/protocol methods were called
            mock_content_client.fetch_content.assert_not_called()
            mock_spell_check_algo.assert_not_called()
            mock_result_store.store_content.assert_not_called()
            mock_event_publisher.publish_spellcheck_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_producer_failure(
        self,
        kafka_message: Any,
        # This is the AIOKafkaProducer used by the event_publisher
        mock_producer: Any,
        mock_http_session: Any,
        sample_essay_id: str,
        sample_text: str,
        corrected_text: str,
    ) -> None:
        """Test handling when Kafka producer (via event publisher) fails."""

        # 1. Mock Protocol Implementations
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.return_value = sample_text  # Success

        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        mock_corrected_storage_id = "corrected_storage_id_abc"
        mock_result_store.store_content.return_value = mock_corrected_storage_id  # Success

        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)
        # Simulate failure when event_publisher tries to publish
        mock_event_publisher.publish_spellcheck_result.side_effect = Exception(
            "Kafka producer error"
        )

        # 2. Patch the core algorithm function (should be called and succeed)
        corrections_count = 1
        with patch(
            "spell_checker_service.event_router.default_perform_spell_check_algorithm",
            new_callable=AsyncMock,
            return_value=(corrected_text, corrections_count),
        ) as mock_spell_check_algo:
            # Act
            result = await process_single_message(
                kafka_message,
                mock_producer,  # This mock_producer is passed to the event_publisher
                mock_http_session,
                mock_content_client,
                mock_result_store,
                mock_event_publisher,
            )

            # Assert
            assert result is True  # Should still commit to avoid reprocessing

            # Verify all processing steps were attempted up to publishing
            mock_content_client.fetch_content.assert_called_once()
            mock_spell_check_algo.assert_called_once_with(sample_text, sample_essay_id)
            mock_result_store.store_content.assert_called_once()

            # Assert that publish_spellcheck_result was attempted with the successful data
            assert mock_event_publisher.publish_spellcheck_result.call_count > 0
            first_call_args = mock_event_publisher.publish_spellcheck_result.call_args_list[0]
            # first_call_args is a unittest.mock.call object, args is a tuple:
            # (producer, event_data, correlation_id)
            published_event_data_attempt: SpellcheckResultDataV1 = first_call_args[0][1]

            assert published_event_data_attempt.status == EssayStatus.SPELLCHECKED_SUCCESS
            assert published_event_data_attempt.entity_ref.entity_id == sample_essay_id
            assert published_event_data_attempt.corrections_made == corrections_count
            assert published_event_data_attempt.storage_metadata is not None
            assert (
                published_event_data_attempt.storage_metadata.references[CORRECTED_TEXT_TYPE]["default"]
                == mock_corrected_storage_id
            )
