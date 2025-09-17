"""Unit tests for EventProcessorImpl spellcheck result processing - successful scenarios."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckMetricsV1, SpellcheckResultV1
from common_core.metadata_models import SystemProcessingMetadata
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


def create_successful_spellcheck_event(
    essay_id: str = "essay_success",
    batch_id: str = "batch_success",
    total_corrections: int = 10,
    l2_corrections: int = 6,
    spell_corrections: int = 4,
    word_count: int = 200,
    correction_density: float = 5.0,
    processing_duration_ms: int = 1200,
    **kwargs: Any,
) -> tuple[EventEnvelope[SpellcheckResultV1], SpellcheckResultV1]:
    """Create a successful SpellcheckResultV1 event for testing."""
    correlation_id = kwargs.get("correlation_id", str(uuid4()))

    metrics = SpellcheckMetricsV1(
        total_corrections=total_corrections,
        l2_dictionary_corrections=l2_corrections,
        spellchecker_corrections=spell_corrections,
        word_count=word_count,
        correction_density=correction_density,
    )

    system_metadata = kwargs.get("system_metadata") or SystemProcessingMetadata(
        entity_id=essay_id,
        entity_type="essay",
        parent_id=batch_id,
        event="spellcheck_results",
        service="spellchecker-service",
        correlation_id=correlation_id,
    )

    data = SpellcheckResultV1(
        event_name=ProcessingEvent.SPELLCHECK_RESULTS,
        entity_id=essay_id,
        entity_type="essay",
        parent_id=batch_id,
        batch_id=batch_id,  # Explicit batch_id field
        timestamp=kwargs.get("timestamp", datetime.now(UTC)),
        status=EssayStatus.SPELLCHECKED_SUCCESS,
        system_metadata=system_metadata,
        correlation_id=correlation_id,
        user_id=kwargs.get("user_id", "user_success"),
        corrections_made=total_corrections,
        correction_metrics=metrics,
        original_text_storage_id=kwargs.get("original_text_storage_id", "storage_original_001"),
        corrected_text_storage_id=kwargs.get("corrected_text_storage_id", "storage_corrected_001"),
        processing_duration_ms=processing_duration_ms,
        processor_version=kwargs.get("processor_version", "pyspellchecker_1.0_L2_swedish"),
    )

    envelope = EventEnvelope[SpellcheckResultV1](
        event_type="SpellcheckResultV1",
        source_service="spellchecker-service",
        correlation_id=correlation_id,
        data=data,
        metadata=kwargs.get("envelope_metadata", {"trace_id": "trace_success_001"}),
    )

    return envelope, data


class TestProcessSpellcheckResultSuccess:
    """Tests for successful spellcheck result processing scenarios."""

    @pytest.mark.asyncio
    async def test_successful_processing_with_standard_metrics(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test successful processing of spellcheck result with standard metrics."""
        # Arrange
        envelope, data = create_successful_spellcheck_event()

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        mock_batch_repository.update_essay_spellcheck_result_with_metrics.assert_called_once_with(
            essay_id="essay_success",
            batch_id="batch_success",
            status=ProcessingStage.COMPLETED,
            correlation_id=envelope.correlation_id,
            correction_count=10,
            corrected_text_storage_id="storage_corrected_001",
            error_detail=None,
            l2_corrections=6,
            spell_corrections=4,
            word_count=200,
            correction_density=5.0,
            processing_duration_ms=1200,
        )

        mock_state_store.invalidate_batch.assert_called_once_with("batch_success")

    @pytest.mark.asyncio
    async def test_successful_processing_with_zero_corrections(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test successful processing when no corrections were needed."""
        # Arrange
        envelope, data = create_successful_spellcheck_event(
            total_corrections=0,
            l2_corrections=0,
            spell_corrections=0,
            correction_density=0.0,
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["correction_count"] == 0
        assert call_args.kwargs["l2_corrections"] == 0
        assert call_args.kwargs["spell_corrections"] == 0
        assert call_args.kwargs["correction_density"] == 0.0
        assert call_args.kwargs["status"] == ProcessingStage.COMPLETED

    @pytest.mark.asyncio
    async def test_successful_processing_correlation_id_tracking(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test that correlation ID is properly tracked through processing."""
        # Arrange
        test_correlation_id = str(uuid4())
        envelope, data = create_successful_spellcheck_event(correlation_id=test_correlation_id)

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert str(call_args.kwargs["correlation_id"]) == test_correlation_id

    @pytest.mark.asyncio
    async def test_successful_processing_timestamp_recording(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test that timestamp is correctly handled during processing."""
        # Arrange
        test_timestamp = datetime.now(UTC)
        envelope, data = create_successful_spellcheck_event(timestamp=test_timestamp)

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert - verify the event was processed without error
        mock_batch_repository.update_essay_spellcheck_result_with_metrics.assert_called_once()
        assert data.timestamp == test_timestamp

    @pytest.mark.asyncio
    async def test_successful_processing_storage_id_handling(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test storage ID handling for original and corrected text."""
        # Arrange
        original_storage_id = "storage_original_12345"
        corrected_storage_id = "storage_corrected_67890"

        envelope, data = create_successful_spellcheck_event(
            original_text_storage_id=original_storage_id,
            corrected_text_storage_id=corrected_storage_id,
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["corrected_text_storage_id"] == corrected_storage_id
        assert data.original_text_storage_id == original_storage_id

    @pytest.mark.asyncio
    async def test_successful_processing_user_id_tracking(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test user ID is properly tracked in successful processing."""
        # Arrange
        test_user_id = "user_test_12345"
        envelope, data = create_successful_spellcheck_event(user_id=test_user_id)

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        mock_batch_repository.update_essay_spellcheck_result_with_metrics.assert_called_once()
        assert data.user_id == test_user_id

    @pytest.mark.asyncio
    async def test_successful_processing_processor_version_tracking(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test processor version is properly tracked."""
        # Arrange
        processor_version = "pyspellchecker_2.0_L2_advanced"
        envelope, data = create_successful_spellcheck_event(processor_version=processor_version)

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        mock_batch_repository.update_essay_spellcheck_result_with_metrics.assert_called_once()
        assert data.processor_version == processor_version

    @pytest.mark.asyncio
    async def test_successful_processing_cache_invalidation(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test cache invalidation occurs after successful processing."""
        # Arrange
        test_batch_id = "batch_cache_test"
        envelope, data = create_successful_spellcheck_event(batch_id=test_batch_id)

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        mock_state_store.invalidate_batch.assert_called_once_with(test_batch_id)

    @pytest.mark.asyncio
    async def test_successful_processing_high_correction_density(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test successful processing of essays with high correction density."""
        # Arrange - High correction density scenario
        envelope, data = create_successful_spellcheck_event(
            total_corrections=50,
            l2_corrections=30,
            spell_corrections=20,
            word_count=100,
            correction_density=50.0,  # 50 corrections per 100 words
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["correction_density"] == 50.0
        assert call_args.kwargs["correction_count"] == 50
        assert call_args.kwargs["status"] == ProcessingStage.COMPLETED

    @pytest.mark.asyncio
    async def test_successful_processing_low_correction_density(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test successful processing of essays with low correction density."""
        # Arrange - Low correction density scenario
        envelope, data = create_successful_spellcheck_event(
            total_corrections=2,
            l2_corrections=1,
            spell_corrections=1,
            word_count=1000,
            correction_density=0.2,  # 0.2 corrections per 100 words
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["correction_density"] == 0.2
        assert call_args.kwargs["correction_count"] == 2
        assert call_args.kwargs["word_count"] == 1000
        assert call_args.kwargs["status"] == ProcessingStage.COMPLETED
