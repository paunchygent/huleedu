"""
Mock implementations for testing CJ Assessment Service.

This module contains mock implementations of protocols used across
multiple test files to reduce duplication and ensure consistency.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, AsyncContextManager, Type
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
        if self.should_fail_set:  # Simulate full Redis outage
            raise Exception("Redis connection failed")
        return self.keys.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """Set a key with TTL."""
        self.keys[key] = value
        return True

    async def ping(self) -> bool:
        """Mock PING operation required by RedisClientProtocol."""
        return True

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys from the mock Redis store."""
        count = 0
        for key in keys:
            self.delete_calls.append(key)
            if key in self.keys:
                del self.keys[key]
                count += 1
        return count


class MockDatabase(CJRepositoryProtocol):
    """Mock database that simulates real CJ assessment database operations."""

    def __init__(self) -> None:
        self.batches: dict[int, dict] = {}
        self.essays: dict[int, list] = {}
        self.comparison_pairs: dict[int, list] = {}  # Store comparison pairs by cj_batch_id
        self.next_batch_id = 1
        self.should_fail_create_batch = False

    def session(self) -> AsyncContextManager[AsyncSession]:
        """Provide async database session context manager."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Track session objects to be added
        session_objects: list[Any] = []

        def mock_add(obj: Any) -> None:
            """Mock session.add() to store objects temporarily."""
            session_objects.append(obj)

        async def mock_flush() -> None:
            """Mock session.flush() to persist objects to mock storage."""
            for obj in session_objects:
                # Handle ComparisonPair objects
                if hasattr(obj, "cj_batch_id") and hasattr(obj, "essay_a_els_id"):
                    batch_id = obj.cj_batch_id
                    if batch_id not in self.comparison_pairs:
                        self.comparison_pairs[batch_id] = []
                    self.comparison_pairs[batch_id].append(obj)
            session_objects.clear()

        async def mock_execute(stmt: Any) -> Any:
            """Mock session.execute() to return stored data based on query."""
            # Check if this is a SELECT query with columns vs SELECT entity
            is_column_select = (
                hasattr(stmt, "selected_columns")
                and stmt.selected_columns
                and len(stmt.selected_columns) == 2
            )

            query_str = str(stmt.compile(compile_kwargs={"literal_binds": True}))

            if "comparison_pairs" in query_str and "cj_batch_id" in query_str:
                # Extract batch ID from query
                import re

                match = re.search(r"cj_batch_id = (\d+)", query_str)
                if match:
                    cj_batch_id = int(match.group(1))
                    pairs = self.comparison_pairs.get(cj_batch_id, [])

                    if is_column_select:
                        # This is a column-based SELECT (like pair generation)
                        # Return tuples of (essay_a_els_id, essay_b_els_id) for pair generation
                        tuple_pairs = [(p.essay_a_els_id, p.essay_b_els_id) for p in pairs]
                        return MockResult(tuple_pairs)
                    else:
                        # This is a full entity SELECT (like scoring)
                        # Filter out pairs with error winners for scoring queries
                        if "winner" in query_str and "error" in query_str:
                            valid_pairs = [p for p in pairs if p.winner and p.winner != "error"]
                            return MockResult(valid_pairs)
                        return MockResult(pairs)

            # Handle ProcessedEssay queries
            if "processed_essays" in query_str:
                # Return empty list for essay queries in mock
                return MockResult([])

            return MockResult([])

        # Create a proper result mock that behaves like SQLAlchemy
        class MockResult:
            def __init__(self, data: list[Any] | None = None):
                self.data = data or []

            def scalars(self) -> Any:
                return MockScalars(self.data)

            def all(self) -> list[Any]:
                return self.data

            def first(self) -> Any:
                return self.data[0] if self.data else None

        class MockScalars:
            def __init__(self, data: list[Any] | None = None):
                self.data = data or []

            def all(self) -> list[Any]:
                return self.data

            def first(self) -> Any:
                return self.data[0] if self.data else None

        # Configure the mock session's methods
        mock_session.add = mock_add
        mock_session.flush = AsyncMock(side_effect=mock_flush)
        mock_session.execute = AsyncMock(side_effect=mock_execute)

        # Create a proper async context manager for begin()
        class MockTransaction:
            async def __aenter__(self) -> "MockTransaction":
                return self

            async def __aexit__(
                self,
                exc_type: Type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> bool | None:
                pass

        # begin() should return an awaitable MockTransaction for session.begin() usage
        async def mock_begin() -> MockTransaction:
            return MockTransaction()

        mock_session.begin = AsyncMock(side_effect=mock_begin)
        mock_session.commit.return_value = AsyncMock()  # Make commit() awaitable
        mock_session.rollback.return_value = AsyncMock()  # Make rollback() awaitable

        class MockAsyncContextManager:
            def __init__(self, session_to_return: AsyncMock):
                self._session = session_to_return

            async def __aenter__(self) -> AsyncMock:
                return self._session

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: TracebackType | None,
            ) -> bool | None:
                pass

        return MockAsyncContextManager(mock_session)

    def _extract_batch_id_from_stmt(self, stmt: Any) -> int | None:
        """Extract cj_batch_id from SQLAlchemy statement."""
        try:
            # Try to get WHERE clause conditions
            if hasattr(stmt, "whereclause") and stmt.whereclause is not None:
                # Look for cj_batch_id comparison
                where_str = str(stmt.whereclause)
                if "cj_batch_id" in where_str:
                    import re

                    match = re.search(r"cj_batch_id = (\d+)", where_str)
                    if match:
                        return int(match.group(1))
            return None
        except Exception:
            return None

    async def create_new_cj_batch(
        self,
        session: AsyncSession,
        bos_batch_id: str,
        event_correlation_id: str,  # Keep as str to match protocol
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
            def __init__(self, batch_id_val: int) -> None:
                self.id = batch_id_val

        return Batch(batch_id)

    async def create_or_update_cj_processed_essay(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        els_essay_id: str,
        text_storage_id: str,
        assessment_input_text: str,
        processing_metadata: dict | None = None,
    ) -> Any:
        """Create or update a processed essay record."""
        essay_data = {
            "els_essay_id": els_essay_id,
            "text_storage_id": text_storage_id,
            "assessment_input_text": assessment_input_text,
            "processing_metadata": processing_metadata or {},
        }
        self.essays.setdefault(cj_batch_id, []).append(essay_data)

        # Return a mock object with the expected attributes
        class MockProcessedEssay:
            def __init__(self) -> None:
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
        """Update essay scores within a batch."""
        # Mock implementation
        pass

    async def update_cj_batch_status(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        status: Any,
    ) -> None:
        """Update the status of a CJ batch."""
        # Mock implementation
        pass

    async def get_final_cj_rankings(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list[dict[str, Any]]:
        """Get the final ranked list of essays for a CJ batch."""
        return []

    async def initialize_db_schema(self) -> None:
        """Initialize the database schema for testing."""
        pass

    async def get_assessment_instruction(
        self,
        session: AsyncSession,
        assignment_id: str | None,
        course_id: str | None,
    ) -> Any | None:
        """Get assessment instruction by assignment or course ID."""
        # Mock implementation - return None for tests
        return None

    async def get_cj_batch_upload(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> Any | None:
        """Get CJ batch upload by ID."""
        # Return a mock batch upload with assignment_id
        if cj_batch_id in self.batches:
            class MockBatchUpload:
                def __init__(self, batch_id: int):
                    self.id = batch_id
                    self.assignment_id = "test-assignment-123"  # Default for testing
            return MockBatchUpload(cj_batch_id)
        return None
    
    async def get_anchor_essay_references(
        self,
        session: AsyncSession,
        assignment_id: str,
    ) -> list[Any]:
        """Get anchor essay references for an assignment."""
        # Mock implementation - return empty list for tests
        return []

    async def store_grade_projections(
        self,
        session: AsyncSession,
        projections: list[Any],
    ) -> None:
        """Store grade projections in database."""
        # Mock implementation - no-op for tests
        pass
