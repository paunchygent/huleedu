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
from common_core.domain_enums import ContentType
from common_core.event_enums import ProcessingEvent
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.status_enums import EssayStatus, ProcessingStage

from services.spellchecker_service.event_processor import process_single_message
from services.spellchecker_service.protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
    SpellLogicProtocol,
)
from services.spellchecker_service.tests.mocks import MockWhitelist, create_mock_parallel_processor

# Constants for frequently referenced values
ESSAY_RESULT_EVENT = ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED
CORRECTED_TEXT_TYPE = ContentType.CORRECTED_TEXT


class TestProcessSingleMessage:
    """Test the core message processing function with dependency injection."""

    @pytest.mark.asyncio
    async def test_successful_processing(
        self,
        kafka_message: Any,
        mock_kafka_bus: Any,
        mock_http_session: Any,
        sample_essay_id: str,
        sample_text: str,
        corrected_text: str,
    ) -> None:
        """Test successful processing of a spell check message."""

        # 1. Mock Protocol Implementations - only mock external dependencies
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.return_value = sample_text

        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        mock_corrected_storage_id = "corrected_storage_id_xyz"
        mock_result_store.store_content.return_value = mock_corrected_storage_id

        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)

        # Use REAL spell logic implementation, not a mock
        from services.spellchecker_service.implementations.spell_logic_impl import (
            DefaultSpellLogic,
        )

        real_spell_logic = DefaultSpellLogic(
            result_store=mock_result_store,
            http_session=mock_http_session,
            whitelist=MockWhitelist(),
            parallel_processor=create_mock_parallel_processor(),
        )

        # Act - The real algorithm will run, which is the correct behavior
        result = await process_single_message(
            kafka_message,
            mock_http_session,
            mock_content_client,
            mock_result_store,
            mock_event_publisher,
            real_spell_logic,  # Use real implementation
            mock_kafka_bus,
            consumer_group_id="test-group",
        )

        # Assert
        assert result is True  # Should commit the message

        # Verify protocol calls - modernized signature includes correlation_id
        from uuid import UUID

        kafka_data = json.loads(kafka_message.value.decode("utf-8"))
        mock_content_client.fetch_content.assert_called_once_with(
            storage_id=kafka_data["data"]["text_storage_id"],
            http_session=mock_http_session,
            correlation_id=UUID(kafka_data["correlation_id"]),
        )

        # Verify that the real spell logic called the result store to save corrected content
        mock_result_store.store_content.assert_called_once()
        store_call_args = mock_result_store.store_content.call_args
        stored_content = store_call_args.kwargs["content"]
        assert stored_content != sample_text  # Should be corrected text, not original
        assert store_call_args.kwargs["content_type"] == ContentType.CORRECTED_TEXT

        # Verify that the result was published
        mock_event_publisher.publish_spellcheck_result.assert_called_once()

        # Verify the published result contains real spell check results
        publish_call_args = mock_event_publisher.publish_spellcheck_result.call_args
        published_result: SpellcheckResultDataV1 = publish_call_args[0][1]
        assert published_result.status == EssayStatus.SPELLCHECKED_SUCCESS
        assert published_result.corrections_made is not None
        assert published_result.storage_metadata is not None
        assert (
            published_result.storage_metadata.references[ContentType.CORRECTED_TEXT]["default"]
            == mock_corrected_storage_id
        )

    @pytest.mark.asyncio
    async def test_fetch_content_failure(
        self,
        kafka_message: Any,
        mock_kafka_bus: Any,
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
        mock_spell_logic = AsyncMock(spec=SpellLogicProtocol)

        # 2. Patch the core algorithm function (should not be called)
        with patch(
            "services.spellchecker_service.core_logic.default_perform_spell_check_algorithm",
            new_callable=AsyncMock,
        ) as mock_spell_check_algo:
            # Act
            result = await process_single_message(
                kafka_message,
                mock_http_session,
                mock_content_client,
                mock_result_store,
                mock_event_publisher,
                mock_spell_logic,
                mock_kafka_bus,
                consumer_group_id="test-group",
            )

            # Assert
            assert result is True  # Should still commit to avoid reprocessing

            # Verify fetch was attempted - modernized signature includes correlation_id
            from uuid import UUID

            kafka_data = json.loads(kafka_message.value.decode("utf-8"))
            mock_content_client.fetch_content.assert_called_once_with(
                storage_id=kafka_data["data"]["text_storage_id"],
                http_session=mock_http_session,
                correlation_id=UUID(kafka_data["correlation_id"]),
            )

            # Verify other main operations were NOT called
            mock_spell_check_algo.assert_not_called()
            mock_result_store.store_content.assert_not_called()

            # Verify a failure event was published
            mock_event_publisher.publish_spellcheck_result.assert_called_once()

            call_args = mock_event_publisher.publish_spellcheck_result.call_args
            published_event_data: SpellcheckResultDataV1 = call_args[0][1]

            assert published_event_data.status == EssayStatus.SPELLCHECK_FAILED
            assert published_event_data.entity_id == sample_essay_id
            assert published_event_data.event_name == ESSAY_RESULT_EVENT
            assert published_event_data.system_metadata.processing_stage == ProcessingStage.FAILED
            # Verify modernized structured error information
            assert "error_code" in published_event_data.system_metadata.error_info
            assert (
                published_event_data.system_metadata.error_info["error_code"]
                == "CONTENT_SERVICE_ERROR"
            )
            assert "error_message" in published_event_data.system_metadata.error_info
            assert (
                "Failed to fetch content"
                in published_event_data.system_metadata.error_info["error_message"]
            )

    @pytest.mark.asyncio
    async def test_store_content_failure(
        self,
        kafka_message: Any,
        mock_kafka_bus: Any,
        mock_http_session: Any,
        sample_essay_id: str,
        sample_text: str,
        corrected_text: str,
    ) -> None:
        """Test handling of storage failure."""

        # 1. Mock Protocol Implementations - mock storage failure
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.return_value = sample_text

        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        mock_result_store.store_content.side_effect = Exception("Storage failed during spell check")

        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)

        # Use REAL spell logic implementation that will encounter the storage error
        from services.spellchecker_service.implementations.spell_logic_impl import (
            DefaultSpellLogic,
        )

        real_spell_logic = DefaultSpellLogic(
            result_store=mock_result_store,  # This will fail
            http_session=mock_http_session,
            whitelist=MockWhitelist(),
            parallel_processor=create_mock_parallel_processor(),
        )

        # Act - Process message, expecting spell logic to fail during storage
        result = await process_single_message(
            kafka_message,
            mock_http_session,
            mock_content_client,
            mock_result_store,
            mock_event_publisher,
            real_spell_logic,
            mock_kafka_bus,
            consumer_group_id="test-group",
        )

        # Assert
        assert result is True  # Should ALWAYS commit to avoid reprocessing loops

        # Verify content was fetched
        mock_content_client.fetch_content.assert_called_once()

        # Verify storage was attempted (and failed) inside the real spell logic
        mock_result_store.store_content.assert_called_once()

        # Verify failure event was published
        mock_event_publisher.publish_spellcheck_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_spell_check_failure(
        self,
        kafka_message: Any,
        mock_kafka_bus: Any,
        mock_http_session: Any,
        sample_essay_id: str,
        sample_text: str,
        corrected_text: str,
    ) -> None:
        """Test handling when spell checking logic fails."""

        # 1. Mock Protocol Implementations - simulate internal failure
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.return_value = sample_text

        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        mock_corrected_storage_id = "corrected_storage_id_abc"
        mock_result_store.store_content.return_value = mock_corrected_storage_id

        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)

        # Use a mock that fails during perform_spell_check (not real implementation)
        mock_spell_logic = AsyncMock(spec=SpellLogicProtocol)
        mock_spell_logic.perform_spell_check.side_effect = Exception("Spell check failed")

        # Act - Process message, expecting spell logic to fail
        result = await process_single_message(
            kafka_message,
            mock_http_session,
            mock_content_client,
            mock_result_store,
            mock_event_publisher,
            mock_spell_logic,  # Use mock that fails
            mock_kafka_bus,
            consumer_group_id="test-group",
        )

        # Assert
        assert result is True  # Should ALWAYS commit to avoid reprocessing loops

        # Verify content was fetched successfully
        mock_content_client.fetch_content.assert_called_once()

        # Verify spell check was attempted and failed
        mock_spell_logic.perform_spell_check.assert_called_once()

        # Since spell check failed, storage should not be called
        # (because the real implementation handles storage internally)

        # Verify failure event was published
        mock_event_publisher.publish_spellcheck_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_message_validation_error(
        self,
        invalid_kafka_message: Any,  # Fixture providing malformed message
        mock_kafka_bus: Any,
        mock_http_session: Any,
    ) -> None:
        """Test handling of invalid message that causes validation error."""

        # 1. Mock Protocol Implementations (their methods should not be called)
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)
        mock_spell_logic = AsyncMock(spec=SpellLogicProtocol)

        # 2. Import HuleEduError for expected exception
        from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

        # 3. Patch the core algorithm function (should not be called)
        with patch(
            "services.spellchecker_service.core_logic.default_perform_spell_check_algorithm",
            new_callable=AsyncMock,
        ) as mock_spell_check_algo:
            # Act & Assert - Modernized code raises HuleEduError instead of returning False
            with pytest.raises(HuleEduError) as exc_info:
                await process_single_message(
                    invalid_kafka_message,
                    mock_http_session,
                    mock_content_client,
                    mock_result_store,
                    mock_event_publisher,
                    mock_spell_logic,
                    mock_kafka_bus,
                    consumer_group_id="test-group",
                )

            # Verify the error is a parsing error with structured details
            assert "PARSING_ERROR" in str(exc_info.value)
            assert "Failed to parse Kafka message" in str(exc_info.value)

            # Verify no processing functions/protocol methods were called
            mock_content_client.fetch_content.assert_not_called()
            mock_spell_check_algo.assert_not_called()
            mock_result_store.store_content.assert_not_called()
            mock_event_publisher.publish_spellcheck_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_producer_failure(
        self,
        kafka_message: Any,
        mock_kafka_bus: Any,
        mock_http_session: Any,
        sample_essay_id: str,
        sample_text: str,
        corrected_text: str,
    ) -> None:
        """Test handling when Kafka producer fails."""

        # 1. Mock Protocol Implementations
        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        mock_content_client.fetch_content.return_value = sample_text

        mock_result_store = AsyncMock(spec=ResultStoreProtocol)
        mock_corrected_storage_id = "corrected_storage_id_def"
        mock_result_store.store_content.return_value = mock_corrected_storage_id

        mock_event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)
        # Make the publisher fail every time
        mock_event_publisher.publish_spellcheck_result.side_effect = Exception(
            "Kafka producer error",
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

        # Act - Process message, expecting publisher to fail
        result = await process_single_message(
            kafka_message,
            mock_http_session,
            mock_content_client,
            mock_result_store,
            mock_event_publisher,
            real_spell_logic,
            mock_kafka_bus,
            consumer_group_id="test-group",
        )

        # Assert
        assert (
            result is True
        )  # Should ALWAYS commit even when publisher fails to avoid reprocessing loops

        # Verify all processing steps were completed
        mock_content_client.fetch_content.assert_called_once()
        mock_result_store.store_content.assert_called_once()

        # Verify publisher was called twice:
        # 1. First call for successful spell check result
        # 2. Second call for failure event (which also fails)
        assert mock_event_publisher.publish_spellcheck_result.call_count == 2
