"""
Unit tests for the spell checker worker.

These tests focus on testing the core processing logic with dependency injection,
ensuring the worker handles various scenarios correctly without requiring
actual Kafka or HTTP services.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common_core.enums import EssayStatus, ProcessingEvent, ProcessingStage
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckResultDataV1

# Import the functions we're testing
from ..worker import (
    default_fetch_content,
    default_perform_spell_check,
    default_store_content,
    process_single_message,
)


@asynccontextmanager
async def mock_http_context_manager(mock_response: AsyncMock) -> Any:
    """A mock async context manager that yields the provided mock_response."""
    yield mock_response


class TestProcessSingleMessage:
    """Test the core message processing function with dependency injection."""

    @pytest.mark.asyncio
    async def test_successful_processing(
        self,
        kafka_message: Any,
        mock_producer: Any,
        mock_http_session: Any,
        mock_fetch_content_success: Any,
        mock_store_content_success: Any,
        mock_spell_check_success: Any,
        sample_essay_id: str,
        sample_text: str,
        corrected_text: str,
    ) -> None:
        """Test successful processing of a spell check message."""
        # Act
        result = await process_single_message(
            kafka_message,
            mock_producer,
            mock_http_session,
            mock_fetch_content_success,
            mock_store_content_success,
            mock_spell_check_success,
        )

        # Assert
        assert result is True  # Should commit the message

        # Verify all dependencies were called
        mock_fetch_content_success.assert_called_once()
        mock_spell_check_success.assert_called_once_with(sample_text, sample_essay_id)
        mock_store_content_success.assert_called_once_with(
            mock_http_session, corrected_text, sample_essay_id
        )

        # Verify result was published
        mock_producer.send_and_wait.assert_called_once()

        # Verify the published message structure
        call_args = mock_producer.send_and_wait.call_args
        topic, message_bytes = call_args[0]  # positional args
        key = call_args[1]["key"]  # keyword args

        assert topic == "huleedu.essay.spellcheck.completed.v1"  # Expected output topic
        assert key == sample_essay_id.encode("utf-8")

        # Parse and verify the published message
        published_data = json.loads(message_bytes.decode("utf-8"))
        assert published_data["event_type"] == "huleedu.essay.spellcheck.completed.v1"
        assert published_data["source_service"] == "spell-checker-service"
        assert published_data["data"]["status"] == EssayStatus.SPELLCHECKED_SUCCESS.value

    @pytest.mark.asyncio
    async def test_fetch_content_failure(
        self,
        kafka_message: Any,
        mock_producer: Any,
        mock_http_session: Any,
        mock_fetch_content_failure: Any,
        mock_store_content_success: Any,
        mock_spell_check_success: Any,
    ) -> None:
        """Test handling when content fetching fails."""
        # Act
        result = await process_single_message(
            kafka_message,
            mock_producer,
            mock_http_session,
            mock_fetch_content_failure,
            mock_store_content_success,
            mock_spell_check_success,
        )

        # Assert
        assert result is True  # Should still commit to avoid reprocessing

        # Verify fetch was attempted but spell check and store were not called
        mock_fetch_content_failure.assert_called_once()
        mock_spell_check_success.assert_not_called()
        mock_store_content_success.assert_not_called()
        mock_producer.send_and_wait.assert_not_called()

    @pytest.mark.asyncio
    async def test_store_content_failure(
        self,
        kafka_message: Any,
        mock_producer: Any,
        mock_http_session: Any,
        mock_fetch_content_success: Any,
        mock_store_content_failure: Any,
        mock_spell_check_success: Any,
        sample_text: str,
        sample_essay_id: str,
        corrected_text: str,
    ) -> None:
        """Test handling when content storing fails."""
        # Act
        result = await process_single_message(
            kafka_message,
            mock_producer,
            mock_http_session,
            mock_fetch_content_success,
            mock_store_content_failure,
            mock_spell_check_success,
        )

        # Assert
        assert result is True  # Should still commit to avoid reprocessing

        # Verify fetch and spell check were called but result was not published
        mock_fetch_content_success.assert_called_once()
        mock_spell_check_success.assert_called_once_with(sample_text, sample_essay_id)
        mock_store_content_failure.assert_called_once_with(
            mock_http_session, corrected_text, sample_essay_id
        )
        mock_producer.send_and_wait.assert_not_called()

    @pytest.mark.asyncio
    async def test_spell_check_failure(
        self,
        kafka_message: Any,
        mock_producer: Any,
        mock_http_session: Any,
        mock_fetch_content_success: Any,
        mock_store_content_success: Any,
        mock_spell_check_failure: Any,
        sample_text: str,
        sample_essay_id: str,
    ) -> None:
        """Test handling when spell checking fails."""
        # Act
        result = await process_single_message(
            kafka_message,
            mock_producer,
            mock_http_session,
            mock_fetch_content_success,
            mock_store_content_success,
            mock_spell_check_failure,
        )

        # Assert
        assert result is True  # Should commit to avoid reprocessing

        # Verify fetch and spell check were called but store and publish were not
        mock_fetch_content_success.assert_called_once()
        mock_spell_check_failure.assert_called_once_with(sample_text, sample_essay_id)
        mock_store_content_success.assert_not_called()
        mock_producer.send_and_wait.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_message_validation_error(
        self,
        invalid_kafka_message: Any,
        mock_producer: Any,
        mock_http_session: Any,
        mock_fetch_content_success: Any,
        mock_store_content_success: Any,
        mock_spell_check_success: Any,
    ) -> None:
        """Test handling of invalid message that causes validation error."""
        # Act
        result = await process_single_message(
            invalid_kafka_message,
            mock_producer,
            mock_http_session,
            mock_fetch_content_success,
            mock_store_content_success,
            mock_spell_check_success,
        )

        # Assert
        assert result is True  # Should commit invalid message to avoid reprocessing

        # Verify no processing functions were called
        mock_fetch_content_success.assert_not_called()
        mock_spell_check_success.assert_not_called()
        mock_store_content_success.assert_not_called()
        mock_producer.send_and_wait.assert_not_called()

    @pytest.mark.asyncio
    async def test_producer_failure(
        self,
        kafka_message: Any,
        mock_producer: Any,
        mock_http_session: Any,
        mock_fetch_content_success: Any,
        mock_store_content_success: Any,
        mock_spell_check_success: Any,
        sample_essay_id: str,
        sample_text: str,
        corrected_text: str,
    ) -> None:
        """Test handling when Kafka producer fails."""
        # Setup producer to fail
        mock_producer.send_and_wait.side_effect = Exception("Kafka producer error")

        # Act
        result = await process_single_message(
            kafka_message,
            mock_producer,
            mock_http_session,
            mock_fetch_content_success,
            mock_store_content_success,
            mock_spell_check_success,
        )

        # Assert
        assert result is True  # Should still commit to avoid reprocessing

        # Verify all processing was attempted
        mock_fetch_content_success.assert_called_once()
        mock_spell_check_success.assert_called_once_with(sample_text, sample_essay_id)
        mock_store_content_success.assert_called_once_with(
            mock_http_session, corrected_text, sample_essay_id
        )
        mock_producer.send_and_wait.assert_called_once()


class TestDefaultImplementations:
    """Test the default implementation functions."""

    @pytest.mark.asyncio
    async def test_default_perform_spell_check(self, sample_essay_id: str) -> None:
        """Test the default spell check implementation."""
        # Arrange
        text_with_errors = "This is a tset with teh word recieve."

        # Act
        corrected_text, corrections_count = await default_perform_spell_check(
            text_with_errors, sample_essay_id
        )

        # Assert - The dummy implementation only fixes "teh" -> "the" and "recieve" -> "receive"
        assert "the" in corrected_text  # "teh" should be corrected to "the"
        assert "receive" in corrected_text  # "recieve" should be corrected to "receive"
        assert (
            corrections_count == 2
        )  # Should count the two corrections made by dummy implementation

    @pytest.mark.asyncio
    async def test_default_fetch_content_success(
        self, sample_essay_id: str, sample_storage_id: str
    ) -> None:
        """Test successful content fetching."""
        # Arrange - Mock the actual HTTP response properly using custom async context manager
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.text = AsyncMock(return_value="Sample content")

        mock_session = AsyncMock()
        # Use MagicMock for get() since it's not async, but returns an async context manager
        mock_session.get = MagicMock(return_value=mock_http_context_manager(mock_response))

        # Act
        with patch("spell_checker_service.worker.CONTENT_SERVICE_URL", "http://test-service"):
            result = await default_fetch_content(mock_session, sample_storage_id, sample_essay_id)

        # Assert
        assert result == "Sample content"
        mock_session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_fetch_content_http_error(
        self, sample_essay_id: str, sample_storage_id: str
    ) -> None:
        """Test content fetching with HTTP error."""
        # Arrange
        mock_response = AsyncMock()
        # Make raise_for_status a regular MagicMock that raises an exception when called
        mock_response.raise_for_status = MagicMock(side_effect=Exception("HTTP 404"))

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_http_context_manager(mock_response))

        # Act
        with patch("spell_checker_service.worker.CONTENT_SERVICE_URL", "http://test-service"):
            result = await default_fetch_content(mock_session, sample_storage_id, sample_essay_id)

        # Assert
        assert result is None
        mock_session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_store_content_success(self, sample_essay_id: str) -> None:
        """Test successful content storing."""
        # Arrange
        content_to_store = "Corrected content"
        expected_storage_id = "new-storage-id"

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(return_value={"storage_id": expected_storage_id})

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_http_context_manager(mock_response))

        # Act
        with patch("spell_checker_service.worker.CONTENT_SERVICE_URL", "http://test-service"):
            result = await default_store_content(mock_session, content_to_store, sample_essay_id)

        # Assert
        assert result == expected_storage_id
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_store_content_http_error(self, sample_essay_id: str) -> None:
        """Test content storing with HTTP error."""
        # Arrange
        content_to_store = "Corrected content"

        mock_response = AsyncMock()
        # Make raise_for_status a regular MagicMock that raises an exception when called
        mock_response.raise_for_status = MagicMock(side_effect=Exception("HTTP 500"))

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_http_context_manager(mock_response))

        # Act
        with patch("spell_checker_service.worker.CONTENT_SERVICE_URL", "http://test-service"):
            result = await default_store_content(mock_session, content_to_store, sample_essay_id)

        # Assert
        assert result is None
        mock_session.post.assert_called_once()


class TestEventContractCompliance:
    """Test compliance with event contracts and Pydantic models."""

    @pytest.mark.asyncio
    async def test_published_event_structure(
        self,
        kafka_message: Any,
        mock_producer: Any,
        mock_http_session: Any,
        mock_fetch_content_success: Any,
        mock_store_content_success: Any,
        mock_spell_check_success: Any,
        sample_essay_id: str,
    ) -> None:
        """Test that published events conform to the expected Pydantic schema."""
        # Act
        await process_single_message(
            kafka_message,
            mock_producer,
            mock_http_session,
            mock_fetch_content_success,
            mock_store_content_success,
            mock_spell_check_success,
        )

        # Assert
        mock_producer.send_and_wait.assert_called_once()

        # Extract the published message
        call_args = mock_producer.send_and_wait.call_args
        message_bytes = call_args[0][1]
        published_data = json.loads(message_bytes.decode("utf-8"))

        # Validate the message can be parsed as EventEnvelope[SpellcheckResultDataV1]
        envelope = EventEnvelope[SpellcheckResultDataV1].model_validate(published_data)

        # Verify envelope structure
        assert envelope.event_type == "huleedu.essay.spellcheck.completed.v1"
        assert envelope.source_service == "spell-checker-service"
        assert envelope.correlation_id is not None

        # Verify data structure
        result_data = envelope.data
        assert result_data.event_name == ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED
        assert result_data.status == EssayStatus.SPELLCHECKED_SUCCESS
        assert result_data.entity_ref.entity_id == sample_essay_id
        assert result_data.corrections_made is not None and result_data.corrections_made >= 0
        assert result_data.storage_metadata is not None
        assert result_data.system_metadata.processing_stage == ProcessingStage.COMPLETED

    @pytest.mark.asyncio
    async def test_correlation_id_propagation(
        self,
        spellcheck_request_envelope: EventEnvelope[SpellcheckResultDataV1],
        mock_producer: Any,
        mock_http_session: Any,
        mock_fetch_content_success: Any,
        mock_store_content_success: Any,
        mock_spell_check_success: Any,
        sample_essay_id: str,
    ) -> None:
        """Test that correlation ID is properly propagated from request to response."""
        # Arrange
        original_correlation_id = spellcheck_request_envelope.correlation_id

        # Create a Kafka message with the envelope
        kafka_message = MagicMock()
        kafka_message.topic = "test-topic"
        kafka_message.partition = 0
        kafka_message.offset = 123
        kafka_message.key = sample_essay_id.encode("utf-8")
        kafka_message.value = spellcheck_request_envelope.model_dump(mode="json")

        # Act
        await process_single_message(
            kafka_message,
            mock_producer,
            mock_http_session,
            mock_fetch_content_success,
            mock_store_content_success,
            mock_spell_check_success,
        )

        # Assert
        mock_producer.send_and_wait.assert_called_once()

        # Extract and verify correlation ID
        call_args = mock_producer.send_and_wait.call_args
        message_bytes = call_args[0][1]
        published_data = json.loads(message_bytes.decode("utf-8"))

        envelope = EventEnvelope[SpellcheckResultDataV1].model_validate(published_data)
        assert envelope.correlation_id == original_correlation_id
