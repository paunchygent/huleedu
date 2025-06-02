"""Protocol interfaces for CJ Assessment Service.

This module defines typing.Protocol interfaces for all major dependencies,
enabling clean architecture and testability.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class ContentClientProtocol(Protocol):
    """Protocol for fetching spellchecked essay text from content service."""

    async def fetch_content(self, storage_id: str) -> str:
        """Fetch essay text content by storage ID.
        
        Args:
            storage_id: The storage reference ID for the essay text
            
        Returns:
            The essay text content
            
        Raises:
            Exception: If content cannot be fetched
        """
        ...


class LLMInteractionProtocol(Protocol):
    """Protocol for performing LLM-based essay comparisons."""

    async def perform_comparisons(self, tasks: List[Any]) -> List[Any]:
        """Perform comparative judgment on a list of comparison tasks.
        
        Args:
            tasks: List of ComparisonTask objects
            
        Returns:
            List of ComparisonResult objects
        """
        ...


class CJDatabaseProtocol(Protocol):
    """Protocol for all database interactions specific to CJ assessment."""

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide async database session context manager."""
        ...

    async def create_new_cj_batch(
        self,
        session: AsyncSession,
        bos_batch_id: str,
        event_correlation_id: Optional[str],
        language: str,
        course_code: str,
        essay_instructions: str,
        initial_status: Any,  # CJBatchStatusEnum
        expected_essay_count: int,
    ) -> Any:  # CJBatchUpload
        """Create a new CJ batch record."""
        ...

    async def create_or_update_cj_processed_essay(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        els_essay_id: str,
        text_storage_id: str,
        assessment_input_text: str,
    ) -> Any:  # CJ_ProcessedEssay
        """Create or update a processed essay record."""
        ...

    async def get_essays_for_cj_batch(
        self, session: AsyncSession, cj_batch_id: int
    ) -> List[Any]:  # List[CJ_ProcessedEssay]
        """Get all essays for a CJ batch."""
        ...

    async def get_comparison_pair_by_essays(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        essay_a_els_id: str,
        essay_b_els_id: str,
    ) -> Optional[Any]:  # Optional[CJ_ComparisonPair]
        """Check if comparison pair already exists."""
        ...

    async def store_comparison_results(
        self, session: AsyncSession, results: List[Any], cj_batch_id: int
    ) -> None:
        """Store comparison results to database."""
        ...

    async def update_essay_scores_in_batch(
        self, session: AsyncSession, cj_batch_id: int, scores: Dict[str, float]
    ) -> None:
        """Update essay Bradley-Terry scores."""
        ...

    async def update_cj_batch_status(
        self, session: AsyncSession, cj_batch_id: int, status: Any
    ) -> None:
        """Update CJ batch status."""
        ...

    async def get_final_cj_rankings(
        self, session: AsyncSession, cj_batch_id: int
    ) -> List[Dict[str, Any]]:
        """Get final rankings for a CJ batch."""
        ...

    async def initialize_db_schema(self) -> None:
        """Initialize database schema (create tables)."""
        ...


class CJEventPublisherProtocol(Protocol):
    """Protocol for publishing CJ assessment results."""

    async def publish_assessment_completed(
        self, completion_data: Any, correlation_id: Optional[UUID]
    ) -> None:
        """Publish CJ assessment completion event."""
        ...

    async def publish_assessment_failed(
        self, failure_data: Any, correlation_id: Optional[UUID]
    ) -> None:
        """Publish CJ assessment failure event."""
        ...
