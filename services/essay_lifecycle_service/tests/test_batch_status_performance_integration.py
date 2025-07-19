"""
Integration test for batch status performance optimization.

Tests the performance improvements with real PostgreSQL using testcontainers.
NO INFRASTRUCTURE IS MOCKED - this uses real database connections.
"""

from __future__ import annotations

import time
from collections.abc import Generator
from typing import Any

import pytest
from common_core.metadata_models import EntityReference
from common_core.status_enums import EssayStatus
from testcontainers.postgres import PostgresContainer

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import (
    PostgreSQLEssayRepository,
)


class TestBatchStatusPerformanceIntegration:
    """Integration test for batch status performance with real PostgreSQL."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> Generator[PostgresContainer, Any, None]:
        """Start PostgreSQL test container for performance testing."""
        container = PostgresContainer("postgres:15")
        container.start()
        yield container
        container.stop()

    class PostgreSQLTestSettings(Settings):
        """Test settings that override DATABASE_URL property."""

        def __init__(self, database_url: str) -> None:
            super().__init__()
            object.__setattr__(self, "_database_url", database_url)
            self.DATABASE_POOL_SIZE = 5  # Larger pool for performance testing
            self.DATABASE_MAX_OVERFLOW = 2
            self.DATABASE_POOL_PRE_PING = True
            self.DATABASE_POOL_RECYCLE = 3600

        @property
        def DATABASE_URL(self) -> str:
            """Override to return test database URL."""
            return str(object.__getattribute__(self, "_database_url"))

    @pytest.fixture
    async def postgres_repository(
        self, postgres_container: PostgresContainer
    ) -> PostgreSQLEssayRepository:
        """Create PostgreSQL repository with real database connection."""
        db_url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
        settings = self.PostgreSQLTestSettings(db_url)

        repository = PostgreSQLEssayRepository(settings)
        await repository.initialize_db_schema()
        return repository

    async def test_batch_status_performance_realistic_batch_size(
        self, postgres_repository: PostgreSQLEssayRepository
    ) -> None:
        """Test performance with realistic batch size (100 essays) using real database."""
        batch_id = "performance-test-batch-100"
        essay_count = 100

        # Create realistic batch of essays
        essay_refs = [
            EntityReference(entity_id=f"essay-{i:03d}", entity_type="essay", parent_id=batch_id)
            for i in range(essay_count)
        ]

        # Create all essays in batch
        await postgres_repository.create_essay_records_batch(essay_refs)

        # Update some essays to different statuses for variation
        for i in range(20):  # 20% to SPELLCHECKED_SUCCESS
            await postgres_repository.update_essay_state(
                f"essay-{i:03d}", EssayStatus.SPELLCHECKED_SUCCESS, {"performance_test": True}
            )

        for i in range(20, 30):  # 10% to SPELLCHECK_FAILED
            await postgres_repository.update_essay_state(
                f"essay-{i:03d}", EssayStatus.SPELLCHECK_FAILED, {"performance_test": True}
            )

        # Test old N+1 pattern performance (simulated)
        start_time = time.perf_counter()
        essays = await postgres_repository.list_essays_by_batch(batch_id)
        status_breakdown_individual = await postgres_repository.get_batch_status_summary(batch_id)
        old_pattern_time = time.perf_counter() - start_time

        # Test new combined method performance
        start_time = time.perf_counter()
        (
            combined_essays,
            combined_status_breakdown,
        ) = await postgres_repository.get_batch_summary_with_essays(batch_id)
        new_pattern_time = time.perf_counter() - start_time

        # Validate results are identical
        assert len(essays) == len(combined_essays) == essay_count
        assert status_breakdown_individual == combined_status_breakdown

        # Validate expected status distribution
        expected_summary = {
            EssayStatus.UPLOADED: 70,  # 70% remain in original status
            EssayStatus.SPELLCHECKED_SUCCESS: 20,  # 20% updated to success
            EssayStatus.SPELLCHECK_FAILED: 10,  # 10% updated to failed
        }
        assert combined_status_breakdown == expected_summary

        # Performance validation - combined method should be faster or comparable
        # Allow some tolerance for database variability
        print(f"Old pattern (2 queries): {old_pattern_time:.4f}s")
        print(f"New pattern (1 fetch + compute): {new_pattern_time:.4f}s")

        # The new pattern should not be significantly slower
        # (It may actually be faster due to avoiding the second query)
        assert new_pattern_time <= old_pattern_time * 1.5  # Allow 50% tolerance

    async def test_batch_status_performance_large_batch(
        self, postgres_repository: PostgreSQLEssayRepository
    ) -> None:
        """Test performance with large batch size (200 essays) using real database."""
        batch_id = "performance-test-batch-200"
        essay_count = 200

        # Create large batch of essays
        essay_refs = [
            EntityReference(
                entity_id=f"large-essay-{i:03d}", entity_type="essay", parent_id=batch_id
            )
            for i in range(essay_count)
        ]

        # Create all essays in batch
        await postgres_repository.create_essay_records_batch(essay_refs)

        # Update essays to various statuses to create realistic distribution
        status_updates = [
            (range(0, 50), EssayStatus.SPELLCHECKED_SUCCESS),  # 25% success
            (range(50, 70), EssayStatus.SPELLCHECK_FAILED),  # 10% failed
            (range(70, 120), EssayStatus.AWAITING_CJ_ASSESSMENT),  # 25% CJ assessment
            (range(120, 140), EssayStatus.CJ_ASSESSMENT_SUCCESS),  # 10% CJ success
            (range(140, 150), EssayStatus.CJ_ASSESSMENT_FAILED),  # 5% CJ failed
            # Remaining 25% stay as UPLOADED
        ]

        for essay_range, status in status_updates:
            for i in essay_range:
                await postgres_repository.update_essay_state(
                    f"large-essay-{i:03d}", status, {"large_batch_test": True}
                )

        # Measure performance of optimized get_batch_status_summary
        start_time = time.perf_counter()
        status_summary = await postgres_repository.get_batch_status_summary(batch_id)
        optimized_time = time.perf_counter() - start_time

        # Measure performance of combined method
        start_time = time.perf_counter()
        essays, combined_summary = await postgres_repository.get_batch_summary_with_essays(batch_id)
        combined_time = time.perf_counter() - start_time

        # Validate correct results
        assert len(essays) == essay_count
        assert status_summary == combined_summary

        # Validate expected distribution
        expected_counts = {
            EssayStatus.UPLOADED: 50,  # 25% remain uploaded
            EssayStatus.SPELLCHECKED_SUCCESS: 50,  # 25%
            EssayStatus.SPELLCHECK_FAILED: 20,  # 10%
            EssayStatus.AWAITING_CJ_ASSESSMENT: 50,  # 25%
            EssayStatus.CJ_ASSESSMENT_SUCCESS: 20,  # 10%
            EssayStatus.CJ_ASSESSMENT_FAILED: 10,  # 5%
        }
        assert combined_summary == expected_counts

        # Performance should be good for large batches
        print(f"Optimized status summary (200 essays): {optimized_time:.4f}s")
        print(f"Combined method (200 essays): {combined_time:.4f}s")

        # Both should complete in reasonable time for 200 essays
        assert optimized_time < 1.0  # Should be well under 1 second
        assert combined_time < 2.0  # Combined method does more work but should still be fast

    async def test_empty_batch_performance(
        self, postgres_repository: PostgreSQLEssayRepository
    ) -> None:
        """Test performance with empty batch (edge case)."""
        batch_id = "empty-performance-batch"

        # Test optimized method with empty batch
        start_time = time.perf_counter()
        status_summary = await postgres_repository.get_batch_status_summary(batch_id)
        optimized_time = time.perf_counter() - start_time

        # Test combined method with empty batch
        start_time = time.perf_counter()
        essays, combined_summary = await postgres_repository.get_batch_summary_with_essays(batch_id)
        combined_time = time.perf_counter() - start_time

        # Validate empty results
        assert status_summary == {}
        assert combined_summary == {}
        assert essays == []

        # Performance should be very fast for empty batches
        assert optimized_time < 0.1  # Should be very fast
        assert combined_time < 0.1  # Should also be very fast
