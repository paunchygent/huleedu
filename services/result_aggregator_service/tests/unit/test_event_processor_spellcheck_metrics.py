"""Unit tests for EventProcessorImpl spellcheck result processing with full metrics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
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


def create_spellcheck_result_event(
    essay_id: str = "essay_123",
    batch_id: str = "batch_456",
    status: EssayStatus = EssayStatus.SPELLCHECKED_SUCCESS,
    total_corrections: int = 15,
    l2_corrections: int = 8,
    spell_corrections: int = 7,
    word_count: int = 250,
    correction_density: float = 6.0,
    processing_duration_ms: int = 1500,
    **kwargs: Any,
) -> tuple[EventEnvelope[SpellcheckResultV1], SpellcheckResultV1]:
    """Create a SpellcheckResultV1 event with metrics for testing."""
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
        timestamp=kwargs.get("timestamp", datetime.now(UTC)),
        status=status,
        system_metadata=system_metadata,
        correlation_id=correlation_id,
        user_id=kwargs.get("user_id", "user_abc"),
        corrections_made=total_corrections,
        correction_metrics=metrics,
        original_text_storage_id=kwargs.get("original_text_storage_id", "storage_original"),
        corrected_text_storage_id=kwargs.get("corrected_text_storage_id", "storage_corrected"),
        processing_duration_ms=processing_duration_ms,
        processor_version=kwargs.get("processor_version", "pyspellchecker_1.0_L2_swedish"),
    )

    envelope = EventEnvelope[SpellcheckResultV1](
        event_type="SpellcheckResultV1",
        source_service="spellchecker-service",
        correlation_id=correlation_id,
        data=data,
        metadata=kwargs.get("envelope_metadata", {"trace_id": "trace_123"}),
    )

    return envelope, data


class TestProcessSpellcheckResultMetrics:
    """Tests for process_spellcheck_result method with full metrics."""

    @pytest.mark.asyncio
    async def test_successful_spellcheck_with_full_metrics(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
        mock_state_store: AsyncMock,
    ) -> None:
        """Test processing successful spellcheck with complete metrics."""
        # Arrange
        essay_id = "essay_123"
        batch_id = "batch_456"
        total_corrections = 15
        l2_corrections = 8
        spell_corrections = 7
        word_count = 250
        correction_density = 6.0
        processing_duration_ms = 1500

        envelope, data = create_spellcheck_result_event(
            essay_id=essay_id,
            batch_id=batch_id,
            total_corrections=total_corrections,
            l2_corrections=l2_corrections,
            spell_corrections=spell_corrections,
            word_count=word_count,
            correction_density=correction_density,
            processing_duration_ms=processing_duration_ms,
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        mock_batch_repository.update_essay_spellcheck_result_with_metrics.assert_called_once_with(
            essay_id=essay_id,
            batch_id=batch_id,
            status=ProcessingStage.COMPLETED,
            correlation_id=envelope.correlation_id,
            correction_count=total_corrections,
            corrected_text_storage_id="storage_corrected",
            error_detail=None,
            l2_corrections=l2_corrections,
            spell_corrections=spell_corrections,
            word_count=word_count,
            correction_density=correction_density,
            processing_duration_ms=processing_duration_ms,
        )

        mock_state_store.invalidate_batch.assert_called_once_with(batch_id)

    @pytest.mark.asyncio
    async def test_correction_count_validation(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test that total corrections match the sum of L2 and spell corrections."""
        # Arrange - Create metrics where total equals l2 + spell corrections
        total_corrections = 20
        l2_corrections = 12
        spell_corrections = 8

        envelope, data = create_spellcheck_result_event(
            total_corrections=total_corrections,
            l2_corrections=l2_corrections,
            spell_corrections=spell_corrections,
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["correction_count"] == total_corrections
        assert call_args.kwargs["l2_corrections"] == l2_corrections
        assert call_args.kwargs["spell_corrections"] == spell_corrections

    @pytest.mark.asyncio
    async def test_correction_density_calculation_validation(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test correction density calculation (corrections per 100 words)."""
        # Arrange - Test various density scenarios
        test_cases = [
            {"corrections": 10, "words": 100, "expected_density": 10.0},  # 10%
            {"corrections": 5, "words": 200, "expected_density": 2.5},  # 2.5%
            {"corrections": 25, "words": 500, "expected_density": 5.0},  # 5%
            {"corrections": 1, "words": 50, "expected_density": 2.0},  # 2%
        ]

        for i, case in enumerate(test_cases):
            total_corrections = cast(int, case["corrections"])
            l2_corrections = total_corrections // 2
            spell_corrections = total_corrections - l2_corrections

            envelope, data = create_spellcheck_result_event(
                essay_id=f"essay_{i}",
                total_corrections=total_corrections,
                l2_corrections=l2_corrections,
                spell_corrections=spell_corrections,
                word_count=cast(int, case["words"]),
                correction_density=cast(float, case["expected_density"]),
            )

            # Act
            await event_processor.process_spellcheck_result(envelope, data)

            # Assert
            call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
            assert call_args.kwargs["correction_density"] == case["expected_density"]
            assert call_args.kwargs["word_count"] == case["words"]

    @pytest.mark.asyncio
    async def test_l2_vs_spellchecker_breakdown(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test L2 dictionary vs general spellchecker correction breakdown."""
        # Arrange - Test different L2/spellchecker ratios
        test_scenarios = [
            {"l2": 15, "spell": 0, "total": 15, "scenario": "L2 only"},
            {"l2": 0, "spell": 10, "total": 10, "scenario": "Spellchecker only"},
            {"l2": 8, "spell": 7, "total": 15, "scenario": "Mixed corrections"},
            {"l2": 20, "spell": 5, "total": 25, "scenario": "L2 heavy"},
            {"l2": 3, "spell": 17, "total": 20, "scenario": "Spellchecker heavy"},
        ]

        for i, scenario in enumerate(test_scenarios):
            envelope, data = create_spellcheck_result_event(
                essay_id=f"essay_{i}",
                total_corrections=cast(int, scenario["total"]),
                l2_corrections=cast(int, scenario["l2"]),
                spell_corrections=cast(int, scenario["spell"]),
            )

            # Act
            await event_processor.process_spellcheck_result(envelope, data)

            # Assert
            call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
            assert call_args.kwargs["l2_corrections"] == scenario["l2"], (
                f"Failed for {scenario['scenario']}"
            )
            assert call_args.kwargs["spell_corrections"] == scenario["spell"], (
                f"Failed for {scenario['scenario']}"
            )
            assert call_args.kwargs["correction_count"] == scenario["total"], (
                f"Failed for {scenario['scenario']}"
            )

    @pytest.mark.asyncio
    async def test_processing_duration_tracking(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test processing duration is correctly tracked."""
        # Arrange
        processing_durations = [500, 1000, 2500, 5000, 10000]  # Various durations in ms

        for i, duration in enumerate(processing_durations):
            envelope, data = create_spellcheck_result_event(
                essay_id=f"essay_{i}",
                processing_duration_ms=duration,
            )

            # Act
            await event_processor.process_spellcheck_result(envelope, data)

            # Assert
            call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
            assert call_args.kwargs["processing_duration_ms"] == duration

    @pytest.mark.asyncio
    async def test_large_essay_metrics(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test handling of large essays with high correction counts."""
        # Arrange - Simulate large essay
        envelope, data = create_spellcheck_result_event(
            total_corrections=150,  # High correction count
            l2_corrections=90,
            spell_corrections=60,
            word_count=2500,  # Large essay
            correction_density=6.0,  # 150/2500 * 100
            processing_duration_ms=8500,  # Longer processing time
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["correction_count"] == 150
        assert call_args.kwargs["l2_corrections"] == 90
        assert call_args.kwargs["spell_corrections"] == 60
        assert call_args.kwargs["word_count"] == 2500
        assert call_args.kwargs["correction_density"] == 6.0
        assert call_args.kwargs["processing_duration_ms"] == 8500

    @pytest.mark.asyncio
    async def test_minimal_essay_metrics(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test handling of minimal essays with few or no corrections."""
        # Arrange - Simulate small essay with no corrections
        envelope, data = create_spellcheck_result_event(
            total_corrections=0,
            l2_corrections=0,
            spell_corrections=0,
            word_count=25,  # Very small essay
            correction_density=0.0,  # No corrections
            processing_duration_ms=200,  # Fast processing
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        assert call_args.kwargs["correction_count"] == 0
        assert call_args.kwargs["l2_corrections"] == 0
        assert call_args.kwargs["spell_corrections"] == 0
        assert call_args.kwargs["word_count"] == 25
        assert call_args.kwargs["correction_density"] == 0.0
        assert call_args.kwargs["processing_duration_ms"] == 200

    @pytest.mark.asyncio
    async def test_all_metrics_fields_passed_to_repository(
        self,
        event_processor: EventProcessorImpl,
        mock_batch_repository: AsyncMock,
    ) -> None:
        """Test that all metric fields are correctly passed to the repository."""
        # Arrange
        expected_values = {
            "essay_id": "essay_test_all",
            "batch_id": "batch_test_all",
            "status": ProcessingStage.COMPLETED,
            "correction_count": 42,
            "corrected_text_storage_id": "storage_corrected_all",
            "error_detail": None,
            "l2_corrections": 25,
            "spell_corrections": 17,
            "word_count": 300,
            "correction_density": 14.0,
            "processing_duration_ms": 3200,
        }

        envelope, data = create_spellcheck_result_event(
            essay_id=cast(str, expected_values["essay_id"]),
            batch_id=cast(str, expected_values["batch_id"]),
            total_corrections=cast(int, expected_values["correction_count"]),
            l2_corrections=cast(int, expected_values["l2_corrections"]),
            spell_corrections=cast(int, expected_values["spell_corrections"]),
            word_count=cast(int, expected_values["word_count"]),
            correction_density=cast(float, expected_values["correction_density"]),
            processing_duration_ms=cast(int, expected_values["processing_duration_ms"]),
            corrected_text_storage_id=cast(str, expected_values["corrected_text_storage_id"]),
        )

        # Act
        await event_processor.process_spellcheck_result(envelope, data)

        # Assert - Check all fields are passed correctly
        call_args = mock_batch_repository.update_essay_spellcheck_result_with_metrics.call_args
        for field, expected_value in expected_values.items():
            if field != "status":  # status is ProcessingStage enum
                assert call_args.kwargs[field] == expected_value, f"Field {field} mismatch"

        assert call_args.kwargs["status"] == ProcessingStage.COMPLETED
        assert call_args.kwargs["correlation_id"] == envelope.correlation_id
