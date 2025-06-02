"""
Unit tests for the spell checker event processor.

These tests focus on testing the event processing and message processing logic
with dependency injection, ensuring correct handling of various scenarios.
"""

# TODO: ARCHITECTURAL REFACTOR - This test file (455 lines) will be split to align
# TODO: with 'event_router.py' refactoring. Per HULEDU-ARCH-001, tests will be reorganized into:
# TODO: - test_event_processor.py (for message processing logic)
# TODO: - test_protocol_implementations/ (for individual protocol implementation tests)

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

from ..event_processor import process_single_message
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

        # Act - The real algorithm will run, which is the correct behavior
        result = await process_single_message(
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
        assert result is True  # Should commit the message

        # Verify protocol calls
        mock_content_client.fetch_content.assert_called_once_with(
            storage_id=json.loads(kafka_message.value.decode("utf-8"))["data"]["text_storage_id"],
            http_session=mock_http_session,
        )

        # Verify that content was stored (the real algorithm ran and produced results)
        mock_result_store.store_content.assert_called_once()

        # Verify that the result was published
        mock_event_publisher.publish_spellcheck_result.assert_called_once()

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
            "services.spell_checker_service.core_logic.default_perform_spell_check_algorithm",
            new_callable=AsyncMock,
        ) as mock_spell_check_algo:
            # Act
            result = await process_single_message(
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
            assert result is True  # Should still commit to avoid reprocessing

            # Verify fetch was attempted
            mock_content_client.fetch_content.assert_called_once_with(
                storage_id=json.loads(kafka_message.value.decode("utf-8"))["data"][
                    "text_storage_id"
                ],
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

        # Act - The real algorithm will run and then fail when trying to store
        result = await process_single_message(
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
        assert result is True  # Should still commit to avoid reprocessing

        # Verify fetch was called
        mock_content_client.fetch_content.assert_called_once()

        # Verify store was attempted (and failed)
        mock_result_store.store_content.assert_called_once()

        # Verify that a failure event was published
        mock_event_publisher.publish_spellcheck_result.assert_called_once()

        # Verify the published event indicates failure
        call_args = mock_event_publisher.publish_spellcheck_result.call_args
        published_event_data: SpellcheckResultDataV1 = call_args[0][1]
        assert published_event_data.status == EssayStatus.SPELLCHECK_FAILED

    @pytest.mark.asyncio
    async def test_spell_check_failure(
        self,
        kafka_message: Any,
        mock_producer: Any,
        mock_http_session: Any,
        sample_text: str,
        sample_essay_id: str,
    ) -> None:
        """Test handling when spell checking fails during storage."""

        # 1. Mock Protocol Implementations
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.return_value = sample_text  # Success

        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        # Simulate failure at storage step - this will cause spell check to fail
        mock_result_store.store_content.side_effect = Exception("Storage failed")
        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)

        # Act - The real algorithm will run and succeed, but fail when trying to store
        result = await process_single_message(
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
        assert result is True  # Should commit to avoid reprocessing

        # Verify fetch and storage were attempted
        mock_content_client.fetch_content.assert_called_once()
        mock_result_store.store_content.assert_called_once()

        # Verify that a failure event was published
        mock_event_publisher.publish_spellcheck_result.assert_called_once()

        # Verify the published event indicates failure
        call_args = mock_event_publisher.publish_spellcheck_result.call_args
        published_event_data: SpellcheckResultDataV1 = call_args[0][1]
        assert published_event_data.status == EssayStatus.SPELLCHECK_FAILED

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
            "services.spell_checker_service.core_logic.default_perform_spell_check_algorithm",
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
                consumer_group_id="test-group",
                kafka_queue_latency_metric=None,
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

        # Act - The real algorithm will run, succeed, but fail when publishing
        result = await process_single_message(
            kafka_message,
            mock_producer,  # This mock_producer is passed to the event_publisher
            mock_http_session,
            mock_content_client,
            mock_result_store,
            mock_event_publisher,
            consumer_group_id="test-group",
            kafka_queue_latency_metric=None,
        )

        # Assert
        assert result is True  # Should still commit to avoid reprocessing

        # Verify all processing steps were attempted up to publishing
        mock_content_client.fetch_content.assert_called_once()
        mock_result_store.store_content.assert_called_once()

        # Verify that publishing was attempted (and failed)
        mock_event_publisher.publish_spellcheck_result.assert_called()
