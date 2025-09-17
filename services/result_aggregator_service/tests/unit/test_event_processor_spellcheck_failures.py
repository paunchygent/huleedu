"""Unit tests for EventProcessorImpl spellcheck result processing - failure scenarios."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.error_enums import ErrorCode
from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckMetricsV1, SpellcheckResultV1
from common_core.metadata_models import SystemProcessingMetadata
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import EssayStatus, ProcessingStage

from services.result_aggregator_service.implementations.event_processor_impl import (
    EventProcessorImpl,
)
from services.result_aggregator_service.protocols import (
    BatchRepositoryProtocol,
    CacheManagerProtocol,
    EventPublisherProtocol,
    StateStoreProtocol,
)


@pytest.fixture
def mock_batch_repository() -> AsyncMock:
    """Create mock batch repository."""
    return AsyncMock(spec=BatchRepositoryProtocol)


@pytest.fixture
def mock_state_store() -> AsyncMock:
    """Create mock state store."""
    return AsyncMock(spec=StateStoreProtocol)


@pytest.fixture
def mock_cache_manager() -> AsyncMock:
    """Create mock cache manager."""
    return AsyncMock(spec=CacheManagerProtocol)


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Create mock event publisher."""
    return AsyncMock(spec=EventPublisherProtocol)


@pytest.fixture
def event_processor(
    mock_batch_repository: AsyncMock,
    mock_state_store: AsyncMock,
    mock_cache_manager: AsyncMock,
    mock_event_publisher: AsyncMock,
) -> EventProcessorImpl:
    """Create event processor with mocked dependencies."""
    return EventProcessorImpl(
        batch_repository=mock_batch_repository,
        state_store=mock_state_store,
        cache_manager=mock_cache_manager,
        event_publisher=mock_event_publisher,
    )


def create_failed_spellcheck_event(
    essay_id: str = "essay_failed",
    batch_id: str = "batch_failed",
    error_info: str = "Spellcheck service timeout",
    **kwargs: Any,
) -> tuple[EventEnvelope[SpellcheckResultV1], SpellcheckResultV1]:
    """Create a failed SpellcheckResultV1 event for testing."""
    correlation_id = kwargs.get("correlation_id", str(uuid4()))

    # For failed events, metrics might be partial or zero
    metrics = SpellcheckMetricsV1(
        total_corrections=kwargs.get("total_corrections", 0),
        l2_dictionary_corrections=kwargs.get("l2_corrections", 0),
        spellchecker_corrections=kwargs.get("spell_corrections", 0),
        word_count=kwargs.get("word_count", 0),
        correction_density=kwargs.get("correction_density", 0.0),
    )

    # Create system metadata with error info
    system_metadata = kwargs.get("system_metadata") or SystemProcessingMetadata(
        entity_id=essay_id,
        entity_type="essay",
        parent_id=batch_id,
        event="spellcheck_results",
        error_info={"error_message": error_info, "error_type": "spellcheck_failure"},
    )

    data = SpellcheckResultV1(
        event_name=ProcessingEvent.SPELLCHECK_RESULTS,
        entity_id=essay_id,
        entity_type="essay",
        parent_id=batch_id,
        batch_id=batch_id,  # Explicit batch_id field
        timestamp=kwargs.get("timestamp", datetime.now(UTC)),
        status=EssayStatus.SPELLCHECK_FAILED,
        system_metadata=system_metadata,
        correlation_id=correlation_id,
        user_id=kwargs.get("user_id", "user_failed"),
        corrections_made=kwargs.get("total_corrections", 0),
        correction_metrics=metrics,
        original_text_storage_id=kwargs.get("original_text_storage_id", "storage_original_failed"),
        corrected_text_storage_id=kwargs.get("corrected_text_storage_id", None),  # None for failed
        processing_duration_ms=kwargs.get("processing_duration_ms", 5000),
        processor_version=kwargs.get("processor_version", "pyspellchecker_1.0_L2_swedish"),
    )

    envelope = EventEnvelope[SpellcheckResultV1](
        event_type="SpellcheckResultV1",
        source_service="spellchecker-service",
        correlation_id=correlation_id,
        data=data,
        metadata=kwargs.get("envelope_metadata", {"trace_id": "trace_failed_001"}),
    )

    return envelope, data


class TestProcessSpellcheckResultFailures:
    """Tests for failed spellcheck result processing scenarios."""

    @pytest.mark.asyncio
    async def test_failed_spellcheck_with_error_detail_creation(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test processing failed spellcheck with proper error detail creation."""
        # Arrange
        error_message = "Service timeout after 30 seconds"
        envelope, data = create_failed_spellcheck_event(error_info=error_message)

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["status"] == ProcessingStage.FAILED
        assert call_args.kwargs["error_detail"] is not None

        error_detail = call_args.kwargs["error_detail"]
        assert isinstance(error_detail, ErrorDetail)
        assert error_detail.error_code == ErrorCode.SPELLCHECK_SERVICE_ERROR
        assert error_message in error_detail.message

        mock_state_store.invalidate_batch.assert_called_once_with("batch_failed")

    @pytest.mark.asyncio
    async def test_failed_spellcheck_no_corrected_text_storage_id(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test failed spellcheck with no corrected text storage ID."""
        # Arrange
        envelope, data = create_failed_spellcheck_event(corrected_text_storage_id=None)

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["corrected_text_storage_id"] is None
        assert call_args.kwargs["status"] == ProcessingStage.FAILED

    @pytest.mark.asyncio
    async def test_failed_spellcheck_with_partial_metrics(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test failed spellcheck that processed partially before failure."""
        # Arrange - Service started processing but failed partway through
        envelope, data = create_failed_spellcheck_event(
            total_corrections=5,  # Some corrections were made
            l2_corrections=3,
            spell_corrections=2,
            word_count=150,  # Word count was determined
            correction_density=3.33,  # Partial processing
            error_info="Connection lost during processing",
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["status"] == ProcessingStage.FAILED
        assert call_args.kwargs["correction_count"] == 5
        assert call_args.kwargs["l2_corrections"] == 3
        assert call_args.kwargs["spell_corrections"] == 2
        assert call_args.kwargs["word_count"] == 150
        assert call_args.kwargs["correction_density"] == 3.33

    @pytest.mark.asyncio
    async def test_failed_spellcheck_missing_essay_id_error(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test error handling when essay_id is missing."""
        # Arrange
        envelope, data = create_failed_spellcheck_event(essay_id="")

        # Act & Assert
        with pytest.raises(ValueError, match="Missing essay_id"):
            await event_processor.process_spellcheck_result(envelope, data)

        # Repository should not be called
        mock_batch_repository.update_essay_spellcheck_result_with_metrics.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_spellcheck_missing_batch_id_error(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test error handling when batch_id is missing."""
        # Arrange
        envelope, data = create_failed_spellcheck_event(batch_id="")

        # Act & Assert
        with pytest.raises(ValueError, match="Missing batch_id"):
            await event_processor.process_spellcheck_result(envelope, data)

        # Repository should not be called
        mock_batch_repository.update_essay_spellcheck_result_with_metrics.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_spellcheck_repository_error_propagation(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test that repository errors are properly propagated."""
        # Arrange
        envelope, data = create_failed_spellcheck_event()
        repository_error = Exception("Database connection failed")
        mock_batch_repository.update_essay_spellcheck_result_with_metrics.side_effect = (
            repository_error
        )

        # Act & Assert
        with pytest.raises(Exception, match="Database connection failed"):
            await event_processor.process_spellcheck_result(envelope, data)

    @pytest.mark.asyncio
    async def test_failed_spellcheck_zero_metrics_handling(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test handling of failed spellcheck with all zero metrics."""
        # Arrange
        envelope, data = create_failed_spellcheck_event(
            total_corrections=0,
            l2_corrections=0,
            spell_corrections=0,
            word_count=0,
            correction_density=0.0,
            error_info="Text analysis failed - invalid content",
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["correction_count"] == 0
        assert call_args.kwargs["l2_corrections"] == 0
        assert call_args.kwargs["spell_corrections"] == 0
        assert call_args.kwargs["word_count"] == 0
        assert call_args.kwargs["correction_density"] == 0.0
        assert call_args.kwargs["status"] == ProcessingStage.FAILED

    @pytest.mark.asyncio
    async def test_failed_spellcheck_error_detail_context_validation(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test that error detail contains proper context information."""
        # Arrange
        test_essay_id = "essay_context_test"
        test_batch_id = "batch_context_test"
        error_message = "Invalid language detected"

        envelope, data = create_failed_spellcheck_event(
            essay_id=test_essay_id,
            batch_id=test_batch_id,
            error_info=error_message,
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        error_detail = call_args.kwargs["error_detail"]

        assert error_detail.service == "result_aggregator_service"
        assert error_detail.operation == "process_spellcheck_result"
        assert error_detail.details["essay_id"] == test_essay_id
        assert error_detail.details["batch_id"] == test_batch_id
        assert error_detail.details["status"] == EssayStatus.SPELLCHECK_FAILED

    @pytest.mark.asyncio
    async def test_failed_spellcheck_without_system_metadata_error_info(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test failed spellcheck when system_metadata has no error_info."""
        # Arrange - Create system metadata without error_info
        system_metadata = SystemProcessingMetadata(
            entity_id="essay_no_error_info",
            entity_type="essay",
            parent_id="batch_no_error_info",
            event="spellcheck_results",
            service="spellchecker-service",
            correlation_id=str(uuid4()),
            # No error_info field
        )

        envelope, data = create_failed_spellcheck_event(
            essay_id="essay_no_error_info",
            batch_id="batch_no_error_info",
            system_metadata=system_metadata,
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert - No error_detail should be created
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["error_detail"] is None
        assert call_args.kwargs["status"] == ProcessingStage.FAILED

    @pytest.mark.asyncio
    async def test_failed_spellcheck_long_processing_duration(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test failed spellcheck with long processing duration before failure."""
        # Arrange
        long_duration_ms = 120000  # 2 minutes before timeout
        envelope, data = create_failed_spellcheck_event(
            processing_duration_ms=long_duration_ms,
            error_info="Processing timeout after 2 minutes",
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["processing_duration_ms"] == long_duration_ms
        assert call_args.kwargs["status"] == ProcessingStage.FAILED

        error_detail = call_args.kwargs["error_detail"]
        assert "timeout" in error_detail.message.lower()

    @pytest.mark.asyncio
    async def test_failed_spellcheck_different_error_codes(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test that different failure scenarios create appropriate error codes."""
        # This test validates that all spellcheck failures use SPELLCHECK_SERVICE_ERROR
        test_cases = [
            "Service unavailable",
            "Invalid text encoding",
            "Language detection failed",
            "Dictionary not found",
            "Processing quota exceeded",
        ]

        for i, error_message in enumerate(test_cases):
            envelope, data = create_failed_spellcheck_event(
                essay_id=f"essay_error_{i}",
                batch_id=f"batch_error_{i}",
                error_info=error_message,
            )

            # Act
            await event_processor.process_spellcheck_result(envelope, data)

            # Assert
            call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
            error_detail = call_args.kwargs["error_detail"]
            assert error_detail.error_code == ErrorCode.SPELLCHECK_SERVICE_ERROR
            assert error_message in error_detail.message
