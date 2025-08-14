"""Protocol interfaces for CJ Assessment Service.

This module defines typing.Protocol interfaces for all major dependencies,
enabling clean architecture and testability.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncContextManager, Awaitable, Callable, Protocol, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from services.cj_assessment_service.cj_core_logic.batch_submission import BatchSubmissionResult

T = TypeVar("T")


class ContentClientProtocol(Protocol):
    """Protocol for fetching spellchecked essay text from content service."""

    async def fetch_content(self, storage_id: str, correlation_id: UUID) -> str:
        """Fetch essay text content by storage ID.

        Args:
            storage_id: The storage reference ID for the essay text
            correlation_id: Request correlation ID for tracing

        Returns:
            The essay text content

        Raises:
            HuleEduError: On any failure to fetch content
        """
        ...

    async def store_content(self, content: str, content_type: str = "text/plain") -> dict[str, str]:
        """Store content in Content Service.

        Args:
            content: The text content to store
            content_type: MIME type of content

        Returns:
            Dict with 'content_id' key containing the storage ID
        """
        ...


class RetryManagerProtocol(Protocol):
    """Protocol for managing LLM API retry logic."""

    async def with_retry(
        self,
        operation: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute operation with retry logic.

        Args:
            operation: Async callable to execute with retries
            *args: Positional arguments for the operation
            **kwargs: Keyword arguments for the operation

        Returns:
            The result from the successful operation

        Raises:
            HuleEduError: On permanent failure after all retries exhausted
        """
        ...


class LLMProviderProtocol(Protocol):
    """Protocol for individual LLM provider implementations."""

    async def generate_comparison(
        self,
        user_prompt: str,
        correlation_id: UUID,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        provider_override: str | None = None,
    ) -> dict[str, Any] | None:
        """Generate a comparison assessment using the LLM.

        Args:
            user_prompt: The user prompt containing essay comparison request
            correlation_id: Request correlation ID for tracing
            system_prompt_override: Optional system prompt override
            model_override: Optional model name override
            temperature_override: Optional temperature override (0.0-2.0)
            max_tokens_override: Optional max tokens override
            provider_override: Optional provider name override

        Returns:
            The LLM response data containing the comparison result

        Raises:
            HuleEduError: On any failure to generate comparison
        """
        ...


class CJRepositoryProtocol(Protocol):
    """Protocol for all database interactions specific to CJ assessment."""

    def session(self) -> AsyncContextManager[AsyncSession]:
        """Provide async database session context manager."""
        ...  # pragma: no cover

    async def get_assessment_instruction(
        self,
        session: AsyncSession,
        assignment_id: str | None,
        course_id: str | None,
    ) -> Any | None:  # AssessmentInstruction | None
        """Get assessment instruction by assignment or course ID."""
        ...

    async def get_cj_batch_upload(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> Any | None:  # CJBatchUpload | None
        """Get CJ batch upload by ID."""
        ...

    async def get_anchor_essay_references(
        self,
        session: AsyncSession,
        assignment_id: str,
    ) -> list[Any]:  # list[AnchorEssayReference]
        """Get anchor essay references for an assignment."""
        ...

    async def store_grade_projections(
        self,
        session: AsyncSession,
        projections: list[Any],  # list[GradeProjection]
    ) -> None:
        """Store grade projections in database."""
        ...

    async def create_new_cj_batch(
        self,
        session: AsyncSession,
        bos_batch_id: str,
        event_correlation_id: str,
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
        processing_metadata: dict | None = None,
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
        correlation_id: UUID,
    ) -> None:
        """Publish CJ assessment completion event."""
        ...

    async def publish_assessment_failed(
        self,
        failure_data: Any,
        correlation_id: UUID,
    ) -> None:
        """Publish CJ assessment failure event."""
        ...

    async def publish_assessment_result(
        self,
        result_data: Any,
        correlation_id: UUID,
    ) -> None:
        """Publish assessment results to RAS.

        This is a new method needed for dual event publishing.
        Implementation should use outbox pattern like publish_assessment_completed.
        """
        ...


class LLMInteractionProtocol(Protocol):
    """Protocol for performing LLM-based essay comparisons."""

    async def perform_comparisons(
        self,
        tasks: list[Any],
        correlation_id: UUID,
        tracking_map: dict[tuple[str, str], UUID] | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> list[Any]:
        """Perform comparative judgment on a list of comparison tasks.

        Args:
            tasks: List of ComparisonTask objects
            correlation_id: Request correlation ID for tracing
            model_override: Optional model name override
            temperature_override: Optional temperature override (0.0-2.0)
            max_tokens_override: Optional max tokens override

        Returns:
            List of ComparisonResult objects
        """
        ...


class BatchProcessorProtocol(Protocol):
    """Protocol for core batch submission orchestration."""

    async def submit_comparison_batch(
        self,
        cj_batch_id: int,
        comparison_tasks: list[Any],
        correlation_id: UUID,
        config_overrides: Any | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> "BatchSubmissionResult":
        """Submit comparison batch with configurable batch size."""
        ...

    async def handle_batch_submission(
        self,
        cj_batch_id: int,
        comparison_tasks: list[Any],
        correlation_id: UUID,
        request_data: dict[str, Any],
    ) -> "BatchSubmissionResult":
        """Handle batch submission with state tracking."""
        ...


class BatchCompletionCheckerProtocol(Protocol):
    """Protocol for batch completion evaluation and threshold checking."""

    async def check_batch_completion(
        self,
        cj_batch_id: int,
        correlation_id: UUID,
        config_overrides: Any | None = None,
    ) -> bool:
        """Check if batch is complete or has reached threshold."""
        ...


class BatchRetryProcessorProtocol(Protocol):
    """Protocol for retry batch processing and end-of-batch fairness logic."""

    async def submit_retry_batch(
        self,
        cj_batch_id: int,
        correlation_id: UUID,
        force_retry_all: bool = False,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> "BatchSubmissionResult | None":
        """Submit retry batch if threshold reached."""
        ...

    async def process_remaining_failed_comparisons(
        self,
        cj_batch_id: int,
        correlation_id: UUID,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> "BatchSubmissionResult | None":
        """Process all remaining failed comparisons at end of batch."""
        ...


class OutboxRepositoryProtocol(Protocol):
    """Protocol for outbox repository operations following TRUE OUTBOX PATTERN."""

    async def add_event(
        self,
        aggregate_id: str,
        aggregate_type: str,
        event_type: str,
        event_data: dict[str, Any],
        topic: str,
        event_key: str | None = None,
        session: AsyncSession | None = None,
    ) -> UUID:
        """Add event to outbox within current transaction for atomic consistency.

        Args:
            aggregate_id: ID of the aggregate this event relates to
            aggregate_type: Type of aggregate (e.g., 'cj_batch', 'grade_projection')
            event_type: Type of the event (e.g., 'cj.assessment.completed.v1')
            event_data: The event payload (must be JSON-serializable)
            topic: Kafka topic name for publishing
            event_key: Optional key for Kafka partitioning
            session: Optional AsyncSession for transaction sharing

        Returns:
            UUID: The ID of the created outbox event
        """
        ...

    async def get_unpublished_events(self, limit: int = 100) -> list[Any]:
        """Get unpublished events for relay worker processing."""
        ...

    async def mark_event_published(self, event_id: UUID) -> None:
        """Mark event as successfully published to Kafka."""
        ...


class AtomicRedisClientProtocol(Protocol):
    """Protocol for Redis client operations."""

    async def lpush(self, key: str, value: str) -> int:
        """Push value to Redis list for relay worker notification."""
        ...
