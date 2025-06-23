"""
Mock implementations for testing CJ Assessment Service.

This module contains mock implementations of protocols used across
multiple test files to reduce duplication and ensure consistency.
"""

from __future__ import annotations

from typing import Any, AsyncContextManager
from unittest.mock import AsyncMock

from huleedu_service_libs.protocols import RedisClientProtocol
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.protocols import CJRepositoryProtocol


class MockRedisClient(RedisClientProtocol):
    """Mock Redis client for idempotency testing."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []
        self.delete_calls: list[str] = []
        self.should_fail_set = False
        self.should_fail_delete = False

    async def set_if_not_exists(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Set a key only if it doesn't exist with optional TTL."""
        self.set_calls.append((key, str(value), ttl_seconds or 0))
        if self.should_fail_set:
            raise Exception("Redis connection failed")
        if key in self.keys:
            return False
        self.keys[key] = str(value)
        return True

    async def delete_key(self, key: str) -> int:
        """Delete a key from the mock Redis store."""
        self.delete_calls.append(key)
        if self.should_fail_delete:
            raise Exception("Redis connection failed")
        if key in self.keys:
            del self.keys[key]
            return 1
        return 0

    async def get(self, key: str) -> str | None:
        """Get a value from the mock Redis store."""
        return self.keys.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """Set a key with TTL."""
        self.keys[key] = value
        return True


class MockDatabase(CJRepositoryProtocol):
    """Mock database that simulates real CJ assessment database operations."""

    def __init__(self) -> None:
        self.batches: dict[int, dict] = {}
        self.essays: dict[int, list] = {}
        self.next_batch_id = 1
        self.should_fail_create_batch = False

    def session(self) -> AsyncContextManager[AsyncSession]:
        """Provide async database session context manager."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Create a proper result mock that behaves like SQLAlchemy
        class MockResult:
            def scalars(self):
                return MockScalars()

            def all(self):
                return []

        class MockScalars:
            def all(self):
                return []  # Return empty list for rankings query

        # Configure the mock session's methods
        mock_session.execute = AsyncMock(return_value=MockResult())

        # Create a proper async context manager for begin()
        class MockTransaction:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        # begin() should return an awaitable MockTransaction for session.begin() usage
        async def mock_begin():
            return MockTransaction()

        mock_session.begin = AsyncMock(side_effect=mock_begin)
        mock_session.commit.return_value = AsyncMock()  # Make commit() awaitable
        mock_session.rollback.return_value = AsyncMock()  # Make rollback() awaitable

        class AsyncContextManagerMock:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        return AsyncContextManagerMock()

    async def create_new_cj_batch(
        self,
        session: AsyncSession,
        bos_batch_id: str,
        event_correlation_id: str | None,  # Keep as str to match protocol
        language: str,
        course_code: str,
        essay_instructions: str,
        initial_status: Any,
        expected_essay_count: int,
    ) -> Any:
        """Create a new CJ batch record."""
        if self.should_fail_create_batch:
            raise Exception("DB create batch failed")
        batch_id = self.next_batch_id
        self.next_batch_id += 1
        self.batches[batch_id] = {
            "bos_batch_id": bos_batch_id,
            "event_correlation_id": event_correlation_id,
            "language": language,
            "course_code": course_code,
            "essay_instructions": essay_instructions,
            "initial_status": initial_status,
            "expected_essay_count": expected_essay_count,
        }

        class Batch:
            def __init__(self, batch_id_val):
                self.id = batch_id_val

        return Batch(batch_id)

    async def create_or_update_cj_processed_essay(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        els_essay_id: str,
        text_storage_id: str,
        assessment_input_text: str,
    ) -> Any:
        """Create or update a processed essay record."""
        essay_data = {
            "els_essay_id": els_essay_id,
            "text_storage_id": text_storage_id,
            "assessment_input_text": assessment_input_text,
        }
        self.essays.setdefault(cj_batch_id, []).append(essay_data)

        # Return a mock object with the expected attributes
        class MockProcessedEssay:
            def __init__(self):
                self.current_bt_score = 0.0
                self.els_essay_id = els_essay_id
                self.text_storage_id = text_storage_id
                self.assessment_input_text = assessment_input_text

        return MockProcessedEssay()

    async def get_essays_for_cj_batch(self, session: AsyncSession, cj_batch_id: int) -> list[dict]:
        """Get all essays for a CJ batch."""
        return self.essays.get(cj_batch_id, [])

    async def get_comparison_pair_by_essays(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        essay_a_els_id: str,
        essay_b_els_id: str,
    ) -> Any | None:
        """Check if comparison pair already exists."""
        # Mock implementation - no need for actual behavior in these tests
        return None

    async def store_comparison_results(
        self,
        session: AsyncSession,
        results: list[Any],
        cj_batch_id: int,
    ) -> None:
        """Store comparison results to database."""
        # Mock implementation - no need for actual behavior in these tests
        pass

    async def update_essay_scores_in_batch(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        scores: dict[str, float],
    ) -> None:
        """Update essay Bradley-Terry scores."""
        # Mock implementation - no need for actual behavior in these tests
        pass

    async def update_cj_batch_status(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        status: Any,
    ) -> None:
        """Update CJ batch status."""
        # Mock implementation - no need for actual behavior in these tests
        pass

    async def get_final_cj_rankings(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list[dict[str, Any]]:
        """Get final rankings for a CJ batch."""
        return []  # Mock implementation for tests

    async def initialize_db_schema(self) -> None:
        """Initialize database schema (create tables)."""
        # Mock implementation - no need for actual behavior in these tests
        pass
