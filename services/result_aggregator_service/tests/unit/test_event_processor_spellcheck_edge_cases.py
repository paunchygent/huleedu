"""Unit tests for EventProcessorImpl spellcheck result processing - edge cases
and special scenarios."""

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


def create_edge_case_spellcheck_event(
    essay_id: str = "essay_edge",
    batch_id: str | None = "batch_edge",
    status: EssayStatus = EssayStatus.SPELLCHECKED_SUCCESS,
    total_corrections: int = 0,
    l2_corrections: int = 0,
    spell_corrections: int = 0,
    word_count: int = 0,
    correction_density: float = 0.0,
    **kwargs: Any,
) -> tuple[EventEnvelope[SpellcheckResultV1], SpellcheckResultV1]:
    """Create edge case SpellcheckResultV1 event for testing."""
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
    )

    data = SpellcheckResultV1(
        event_name=ProcessingEvent.SPELLCHECK_RESULTS,
        entity_id=essay_id,
        entity_type="essay",
        parent_id=batch_id,
        batch_id=batch_id if batch_id else "",  # Explicit batch_id field, empty string for None case
        timestamp=kwargs.get("timestamp", datetime.now(UTC)),
        status=status,
        system_metadata=system_metadata,
        correlation_id=correlation_id,
        user_id=kwargs.get("user_id"),
        corrections_made=total_corrections,
        correction_metrics=metrics,
        original_text_storage_id=kwargs.get("original_text_storage_id", "storage_original_edge"),
        corrected_text_storage_id=kwargs.get("corrected_text_storage_id"),
        processing_duration_ms=kwargs.get("processing_duration_ms", 1000),
        processor_version=kwargs.get("processor_version", "pyspellchecker_1.0_L2_swedish"),
    )

    envelope = EventEnvelope[SpellcheckResultV1](
        event_type="SpellcheckResultV1",
        source_service="spellchecker-service",
        correlation_id=correlation_id,
        data=data,
        metadata=kwargs.get("envelope_metadata", {"trace_id": "trace_edge_001"}),
    )

    return envelope, data


class TestProcessSpellcheckResultEdgeCases:
    """Tests for edge cases and special scenarios in spellcheck result processing."""

    @pytest.mark.asyncio
    async def test_orphaned_essay_processing_no_batch_id(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test processing spellcheck result for orphaned essay (no batch association)."""
        # Arrange - Essay with no parent batch (orphaned)
        envelope, data = create_edge_case_spellcheck_event(
            batch_id=None,  # Orphaned essay
            essay_id="essay_orphaned_001",
            total_corrections=5,
            l2_corrections=3,
            spell_corrections=2,
            word_count=100,
            correction_density=5.0,
        )

        # Act & Assert - Should raise ValueError for missing batch_id
        with pytest.raises(ValueError, match="Missing batch_id"):
            await event_processor.process_spellcheck_result(envelope, data)

    @pytest.mark.asyncio
    async def test_duplicate_event_processing_idempotency(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test idempotent processing of duplicate spellcheck events."""
        # Arrange - Same event processed twice
        # Use same correlation ID (valid UUID format)
        same_correlation_id = str(uuid4())
        envelope, data = create_edge_case_spellcheck_event(
            essay_id="essay_duplicate",
            batch_id="batch_duplicate",
            correlation_id=same_correlation_id,
        )

        # Act - Process same event twice
        await event_processor.process_spellcheck_result(envelope, data)
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert - Repository should be called twice (no idempotency at this level)
        assert mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_count == 2
        assert mock_state_store.invalidate_batch.call_count == 2

    @pytest.mark.asyncio
    async def test_null_user_id_handling(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test handling of spellcheck event with null user_id."""
        # Arrange
        envelope, data = create_edge_case_spellcheck_event(
            user_id=None,  # Null user_id
            essay_id="essay_no_user",
            batch_id="batch_no_user",
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert - Processing should succeed despite null user_id
        mock_batch_repository.update_essay_spellcheck_result_with_metrics.assert_called_once()
        assert data.user_id is None

    @pytest.mark.asyncio
    async def test_null_corrected_text_storage_id_success(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test successful spellcheck with null corrected_text_storage_id."""
        # Arrange - Success but no corrected text stored
        envelope, data = create_edge_case_spellcheck_event(
            corrected_text_storage_id=None,
            total_corrections=0,  # No corrections made, so no corrected text
            status=EssayStatus.SPELLCHECKED_SUCCESS,
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["corrected_text_storage_id"] is None
        assert call_args.kwargs["status"] == ProcessingStage.COMPLETED

    @pytest.mark.asyncio
    async def test_invalid_correction_density_division_by_zero(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test handling of correction density when word count is zero."""
        # Arrange - Zero word count but corrections made (unusual case)
        envelope, data = create_edge_case_spellcheck_event(
            total_corrections=5,
            l2_corrections=3,
            spell_corrections=2,
            word_count=0,  # Zero word count
            correction_density=0.0,  # Should be 0 to avoid division by zero
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["word_count"] == 0
        assert call_args.kwargs["correction_density"] == 0.0
        assert call_args.kwargs["correction_count"] == 5

    @pytest.mark.asyncio
    async def test_corrections_exceed_word_count_edge_case(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test edge case where corrections exceed word count (possible with compound words)."""
        # Arrange - More corrections than words (possible scenario)
        envelope, data = create_edge_case_spellcheck_event(
            total_corrections=15,
            l2_corrections=8,
            spell_corrections=7,
            word_count=10,  # Only 10 words but 15 corrections
            correction_density=150.0,  # 15/10 * 100 = 150%
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["correction_count"] == 15
        assert call_args.kwargs["word_count"] == 10
        assert call_args.kwargs["correction_density"] == 150.0

    @pytest.mark.asyncio
    async def test_very_large_essay_metrics(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test processing very large essay with high metrics values."""
        # Arrange - Very large essay
        envelope, data = create_edge_case_spellcheck_event(
            total_corrections=5000,
            l2_corrections=3000,
            spell_corrections=2000,
            word_count=50000,  # 50,000 word essay
            correction_density=10.0,  # 5000/50000 * 100 = 10%
            processing_duration_ms=300000,  # 5 minutes processing
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["correction_count"] == 5000
        assert call_args.kwargs["word_count"] == 50000
        assert call_args.kwargs["correction_density"] == 10.0
        assert call_args.kwargs["processing_duration_ms"] == 300000

    @pytest.mark.asyncio
    async def test_minimal_processing_duration(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test very fast processing with minimal duration."""
        # Arrange - Very fast processing
        envelope, data = create_edge_case_spellcheck_event(
            processing_duration_ms=1,  # 1 millisecond
            total_corrections=0,
            word_count=5,
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["processing_duration_ms"] == 1

    @pytest.mark.asyncio
    async def test_mismatched_correction_totals(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test handling when L2 + spell corrections don't match total."""
        # Arrange - Mismatched totals (data consistency issue)
        envelope, data = create_edge_case_spellcheck_event(
            total_corrections=10,
            l2_corrections=6,
            spell_corrections=3,  # 6 + 3 = 9, but total is 10
            word_count=100,
            correction_density=10.0,
        )

        # Act - Should process without validation at this level
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert - Data is passed as-is without validation
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["correction_count"] == 10
        assert call_args.kwargs["l2_corrections"] == 6
        assert call_args.kwargs["spell_corrections"] == 3

    @pytest.mark.asyncio
    async def test_concurrent_updates_same_essay(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test concurrent updates to the same essay (simulating race conditions)."""
        # Arrange - Two events for same essay with different correlation IDs
        essay_id = "essay_concurrent"
        batch_id = "batch_concurrent"

        correlation_id_1 = str(uuid4())
        correlation_id_2 = str(uuid4())

        envelope1, data1 = create_edge_case_spellcheck_event(
            essay_id=essay_id,
            batch_id=batch_id,
            correlation_id=correlation_id_1,
            total_corrections=5,
        )

        envelope2, data2 = create_edge_case_spellcheck_event(
            essay_id=essay_id,
            batch_id=batch_id,
            correlation_id=correlation_id_2,
            total_corrections=8,
        )

        # Act - Process both events (simulating concurrent processing)
        await event_processor.process_spellcheck_result(envelope1, data1)
        await event_processor.process_spellcheck_result(envelope2, data2)

        # Assert - Both updates should be processed
        assert mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_count == 2
        assert mock_state_store.invalidate_batch.call_count == 2

        # Check that both correlations were processed
        calls = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args_list
        correlation_ids = [str(call.kwargs["correlation_id"]) for call in calls]
        assert correlation_id_1 in correlation_ids
        assert correlation_id_2 in correlation_ids

    @pytest.mark.asyncio
    async def test_extremely_high_correction_density(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test handling of extremely high correction density values."""
        # Arrange - Very high correction density
        envelope, data = create_edge_case_spellcheck_event(
            total_corrections=999,
            l2_corrections=500,
            spell_corrections=499,
            word_count=1,  # Single word with massive corrections
            correction_density=99900.0,  # 999/1 * 100 = 99,900%
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["correction_density"] == 99900.0
        assert call_args.kwargs["correction_count"] == 999

    @pytest.mark.asyncio
    async def test_empty_storage_ids_handling(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test handling of empty string storage IDs."""
        # Arrange
        envelope, data = create_edge_case_spellcheck_event(
            original_text_storage_id="",  # Empty string
            corrected_text_storage_id="",  # Empty string
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        # Empty strings should be passed as-is
        assert data.original_text_storage_id == ""
        assert call_args.kwargs["corrected_text_storage_id"] == ""

    @pytest.mark.asyncio
    async def test_negative_metrics_handling(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test handling of negative metric values (invalid but possible)."""
        # Arrange - Negative values (data corruption scenario)
        envelope, data = create_edge_case_spellcheck_event(
            total_corrections=-1,
            l2_corrections=-1,
            spell_corrections=0,
            word_count=-5,
            correction_density=-20.0,
        )

        # Act - Should process without validation
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert - Negative values passed through
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["correction_count"] == -1
        assert call_args.kwargs["word_count"] == -5
        assert call_args.kwargs["correction_density"] == -20.0
