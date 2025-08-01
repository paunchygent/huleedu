"""
Unit tests for repository performance optimizations.

Tests the optimized batch status summary methods and the new combined
operation to ensure N+1 query patterns are eliminated.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus

from services.essay_lifecycle_service.state_store import EssayState, SQLiteEssayStateStore


class TestRepositoryPerformanceOptimizations:
    """Test suite for repository performance optimizations."""

    @pytest.fixture
    async def sqlite_store(self) -> SQLiteEssayStateStore:
        """Create SQLiteEssayStateStore instance with temporary database for testing."""
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.close()

        store = SQLiteEssayStateStore(database_path=temp_file.name)
        await store.initialize()
        return store

    @pytest.fixture
    def sample_essays(self) -> list[EssayState]:
        """Create sample essays with different statuses for testing."""
        base_time = datetime.now(UTC)

        return [
            EssayState(
                essay_id="essay-1",
                batch_id="test-batch",
                current_status=EssayStatus.UPLOADED,
                processing_metadata={},
                timeline={EssayStatus.UPLOADED.value: base_time},
                storage_references={ContentType.ORIGINAL_ESSAY: "storage-1"},
                created_at=base_time,
                updated_at=base_time,
            ),
            EssayState(
                essay_id="essay-2",
                batch_id="test-batch",
                current_status=EssayStatus.UPLOADED,
                processing_metadata={},
                timeline={EssayStatus.UPLOADED.value: base_time},
                storage_references={ContentType.ORIGINAL_ESSAY: "storage-2"},
                created_at=base_time,
                updated_at=base_time,
            ),
            EssayState(
                essay_id="essay-3",
                batch_id="test-batch",
                current_status=EssayStatus.SPELLCHECKED_SUCCESS,
                processing_metadata={},
                timeline={
                    EssayStatus.UPLOADED.value: base_time,
                    EssayStatus.SPELLCHECKED_SUCCESS.value: base_time,
                },
                storage_references={ContentType.ORIGINAL_ESSAY: "storage-3"},
                created_at=base_time,
                updated_at=base_time,
            ),
        ]

    async def test_sqlite_get_batch_summary_with_essays_single_fetch(
        self, sqlite_store: SQLiteEssayStateStore, sample_essays: list[EssayState]
    ) -> None:
        """Test that combined method fetches essays once and computes summary."""
        # Create test essays with default READY_FOR_PROCESSING status
        for essay in sample_essays:
            await sqlite_store.create_essay_record(
                essay.essay_id,
                batch_id=essay.batch_id,
                session=None,
            )

        # Update one essay to SPELLCHECKED_SUCCESS status
        await sqlite_store.update_essay_state(
            "essay-3", EssayStatus.SPELLCHECKED_SUCCESS, {"updated_for_test": True}, session=None
        )

        # Mock list_essays_by_batch to track calls
        with patch.object(
            sqlite_store, "list_essays_by_batch", wraps=sqlite_store.list_essays_by_batch
        ) as mock_list:
            essays, status_summary = await sqlite_store.get_batch_summary_with_essays("test-batch")

            # Verify list_essays_by_batch was called exactly once
            assert mock_list.call_count == 1

            # Verify we got the expected results
            assert len(essays) == 3
            assert status_summary == {
                EssayStatus.READY_FOR_PROCESSING: 2,
                EssayStatus.SPELLCHECKED_SUCCESS: 1,
            }

    async def test_batch_summary_with_essays_empty_batch(
        self, sqlite_store: SQLiteEssayStateStore
    ) -> None:
        """Test combined method handles empty batches correctly."""
        essays, status_summary = await sqlite_store.get_batch_summary_with_essays(
            "nonexistent-batch"
        )

        assert essays == []
        assert status_summary == {}

    async def test_batch_summary_consistent_results(
        self, sqlite_store: SQLiteEssayStateStore, sample_essays: list[EssayState]
    ) -> None:
        """Test that individual and combined methods return consistent results."""
        # Create test essays with initial UPLOADED status
        for essay in sample_essays:
            await sqlite_store.create_essay_record(
                essay.essay_id,
                session=None,
            )

        # Update one essay to SPELLCHECKED_SUCCESS status to create variation
        await sqlite_store.update_essay_state(
            "essay-3", EssayStatus.SPELLCHECKED_SUCCESS, {"updated_for_test": True}, session=None
        )

        # Get results from both methods
        individual_essays = await sqlite_store.list_essays_by_batch("test-batch")
        individual_summary = await sqlite_store.get_batch_status_summary("test-batch")

        combined_essays, combined_summary = await sqlite_store.get_batch_summary_with_essays(
            "test-batch"
        )

        # Verify consistency
        assert len(individual_essays) == len(combined_essays)
        assert individual_summary == combined_summary

        # Verify essay IDs match (order might differ)
        individual_ids = {essay.essay_id for essay in individual_essays}
        combined_ids = {essay.essay_id for essay in combined_essays}
        assert individual_ids == combined_ids
