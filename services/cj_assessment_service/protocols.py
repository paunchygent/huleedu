"""Protocol interfaces for CJ Assessment Service.

This module defines typing.Protocol interfaces for all major dependencies,
enabling clean architecture and testability.
"""

from __future__ import annotations

from typing import Any, AsyncContextManager, Protocol
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


class CacheProtocol(Protocol):
    """Protocol for caching LLM responses."""

    def generate_hash(self, prompt: str) -> str:
        """Generate a hash key for a given prompt."""
        ...

    def get_from_cache(self, cache_key: str) -> dict[str, Any] | None:
        """Retrieve data from cache using the provided key."""
        ...

    def add_to_cache(self, cache_key: str, data: dict[str, Any]) -> None:
        """Add data to cache with the provided key."""
        ...

    def clear_cache(self) -> None:
        """Clear all cached data."""
        ...

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        ...


class RetryManagerProtocol(Protocol):
    """Protocol for managing LLM API retry logic."""

    async def with_retry(
        self,
        operation: Any,  # Callable coroutine
        *args: Any,
        **kwargs: Any,
    ) -> tuple[Any, str | None]:
        """Execute operation with retry logic.

        Returns:
            Tuple of (result, error_message)
        """
        ...


class LLMProviderProtocol(Protocol):
    """Protocol for individual LLM provider implementations."""

    async def generate_comparison(
        self,
        user_prompt: str,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Generate a comparison assessment using the LLM.

        Args:
            user_prompt: The user prompt containing essay comparison request
            system_prompt_override: Optional system prompt override
            model_override: Optional model name override
            temperature_override: Optional temperature override (0.0-2.0)
            max_tokens_override: Optional max tokens override

        Returns:
            Tuple of (response_data, error_message)
        """
        ...


class CJRepositoryProtocol(Protocol):
    """Protocol for all database interactions specific to CJ assessment."""

    def session(self) -> AsyncContextManager[AsyncSession]:
        """Provide async database session context manager."""
        ...  # pragma: no cover

    async def create_new_cj_batch(
        self,
        session: AsyncSession,
        bos_batch_id: str,
        event_correlation_id: str | None,
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
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list[Any]:  # List[CJ_ProcessedEssay]
        """Get all essays for a CJ batch."""
        ...

    async def get_comparison_pair_by_essays(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        essay_a_els_id: str,
        essay_b_els_id: str,
    ) -> Any | None:  # Optional[CJ_ComparisonPair]
        """Check if comparison pair already exists."""
        ...

    async def store_comparison_results(
        self,
        session: AsyncSession,
        results: list[Any],
        cj_batch_id: int,
    ) -> None:
        """Store comparison results to database."""
        ...

    async def update_essay_scores_in_batch(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        scores: dict[str, float],
    ) -> None:
        """Update essay Bradley-Terry scores."""
        ...

    async def update_cj_batch_status(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        status: Any,
    ) -> None:
        """Update CJ batch status."""
        ...

    async def get_final_cj_rankings(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list[dict[str, Any]]:
        """Get final rankings for a CJ batch."""
        ...

    async def initialize_db_schema(self) -> None:
        """Initialize database schema (create tables)."""
        ...


class CJEventPublisherProtocol(Protocol):
    """Protocol for publishing CJ assessment results."""

    async def publish_assessment_completed(
        self,
        completion_data: Any,
        correlation_id: UUID | None,
    ) -> None:
        """Publish CJ assessment completion event."""
        ...

    async def publish_assessment_failed(
        self,
        failure_data: Any,
        correlation_id: UUID | None,
    ) -> None:
        """Publish CJ assessment failure event."""
        ...


class LLMInteractionProtocol(Protocol):
    """Protocol for performing LLM-based essay comparisons."""

    async def perform_comparisons(
        self,
        tasks: list[Any],
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> list[Any]:
        """Perform comparative judgment on a list of comparison tasks.

        Args:
            tasks: List of ComparisonTask objects
            model_override: Optional model name override
            temperature_override: Optional temperature override (0.0-2.0)
            max_tokens_override: Optional max tokens override

        Returns:
            List of ComparisonResult objects
        """
        ...
