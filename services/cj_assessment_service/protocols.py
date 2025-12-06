"""Protocol interfaces for CJ Assessment Service.

This module defines typing.Protocol interfaces for all major dependencies,
enabling clean architecture and testability.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncContextManager,
    Awaitable,
    Callable,
    Protocol,
    TypeVar,
)
from uuid import UUID

from common_core import LLMProviderType
from common_core.status_enums import CJBatchStateEnum
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from services.cj_assessment_service.cj_core_logic.batch_submission import BatchSubmissionResult
    from services.cj_assessment_service.models_api import (
        CJAssessmentRequestData,
        ComparisonResult,
        EssayForComparison,
    )
    from services.cj_assessment_service.models_db import (
        AnchorEssayReference,
        AssessmentInstruction,
        CJBatchState,
        CJBatchUpload,
        ComparisonPair,
        GradeProjection,
        ProcessedEssay,
    )

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
        prompt_blocks: list[dict[str, Any]] | None = None,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        provider_override: str | None = None,
        request_metadata: dict[str, Any] | None = None,
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
            request_metadata: Arbitrary metadata to echo back in callbacks

        Returns:
            The LLM response data containing the comparison result

        Raises:
            HuleEduError: On any failure to generate comparison
        """
        ...


class SessionProviderProtocol(Protocol):
    """Protocol for providing AsyncSession contexts for CJ database access."""

    def session(self) -> AsyncContextManager[AsyncSession]:
        """Provide async database session context manager."""
        ...  # pragma: no cover


class CJBatchRepositoryProtocol(Protocol):
    """Batch aggregate persistence operations (state + uploads)."""

    async def create_new_cj_batch(
        self,
        session: AsyncSession,
        bos_batch_id: str,
        event_correlation_id: str,
        language: str,
        course_code: str,
        initial_status: Any,  # CJBatchStatusEnum
        expected_essay_count: int,
        user_id: str | None = None,
        org_id: str | None = None,
    ) -> "CJBatchUpload": ...

    async def get_cj_batch_upload(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> "CJBatchUpload | None": ...

    async def get_batch_state(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> "CJBatchState | None": ...

    async def update_cj_batch_status(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        status: Any,
    ) -> None: ...

    async def get_stuck_batches(
        self,
        session: AsyncSession,
        states: list[CJBatchStateEnum],
        stuck_threshold: datetime,
    ) -> list["CJBatchState"]: ...

    async def get_batches_ready_for_completion(
        self,
        session: AsyncSession,
    ) -> list["CJBatchState"]: ...

    async def get_batch_state_for_update(
        self,
        session: AsyncSession,
        batch_id: int,
        for_update: bool = False,
    ) -> "CJBatchState | None": ...

    async def update_batch_state(
        self,
        session: AsyncSession,
        batch_id: int,
        state: CJBatchStateEnum,
    ) -> None: ...


class CJEssayRepositoryProtocol(Protocol):
    """Processed essay aggregate persistence operations."""

    async def create_or_update_cj_processed_essay(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        els_essay_id: str,
        text_storage_id: str,
        assessment_input_text: str,
        processing_metadata: dict | None = None,
    ) -> "ProcessedEssay": ...

    async def get_essays_for_cj_batch(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list["ProcessedEssay"]: ...

    async def update_essay_scores_in_batch(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        scores: dict[str, float],
    ) -> None: ...

    async def get_final_cj_rankings(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> list[dict[str, Any]]: ...


class CJComparisonRepositoryProtocol(Protocol):
    """Comparison pair persistence and retrieval operations."""

    async def get_comparison_pair_by_essays(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        essay_a_els_id: str,
        essay_b_els_id: str,
    ) -> "ComparisonPair | None": ...

    async def get_comparison_pair_by_correlation_id(
        self,
        session: AsyncSession,
        correlation_id: UUID,
    ) -> "ComparisonPair | None": ...

    async def store_comparison_results(
        self,
        session: AsyncSession,
        results: list["ComparisonResult"],
        cj_batch_id: int,
    ) -> None: ...

    async def get_comparison_pairs_for_batch(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> list[tuple[str, str]]: ...

    async def get_valid_comparisons_for_batch(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> list["ComparisonPair"]: ...

    async def get_coverage_metrics_for_batch(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> tuple[int, int]: ...


class AssessmentInstructionRepositoryProtocol(Protocol):
    """Assessment instruction persistence operations."""

    async def get_assessment_instruction(
        self,
        session: AsyncSession,
        assignment_id: str | None,
        course_id: str | None,
    ) -> "AssessmentInstruction | None": ...

    async def get_assignment_context(
        self,
        session: AsyncSession,
        assignment_id: str,
    ) -> dict[str, Any] | None: ...

    async def upsert_assessment_instruction(
        self,
        session: AsyncSession,
        *,
        assignment_id: str | None,
        course_id: str | None,
        instructions_text: str,
        grade_scale: str,
        student_prompt_storage_id: str | None = None,
        judge_rubric_storage_id: str | None = None,
    ) -> "AssessmentInstruction": ...

    async def list_assessment_instructions(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        grade_scale: str | None = None,
    ) -> tuple[list["AssessmentInstruction"], int]: ...

    async def delete_assessment_instruction(
        self,
        session: AsyncSession,
        *,
        assignment_id: str | None,
        course_id: str | None,
    ) -> bool: ...


class AnchorRepositoryProtocol(Protocol):
    """Anchor essay reference persistence operations."""

    async def upsert_anchor_reference(
        self,
        session: AsyncSession,
        *,
        assignment_id: str,
        anchor_label: str,
        grade: str,
        grade_scale: str,
        text_storage_id: str,
    ) -> int: ...

    async def get_anchor_essay_references(
        self,
        session: AsyncSession,
        assignment_id: str,
        grade_scale: str | None = None,
    ) -> list["AnchorEssayReference"]: ...


class GradeProjectionRepositoryProtocol(Protocol):
    """Grade projection persistence operations."""

    async def store_grade_projections(
        self,
        session: AsyncSession,
        projections: list["GradeProjection"],
    ) -> None: ...


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

    async def publish_resource_consumption(
        self,
        resource_event: Any,
        correlation_id: UUID,
    ) -> None:
        """Publish ResourceConsumptionV1 event using TRUE OUTBOX PATTERN.

        Args:
            resource_event: EventEnvelope[ResourceConsumptionV1]
            correlation_id: Correlation ID for tracing
        """
        ...


class LLMInteractionProtocol(Protocol):
    """Protocol for performing LLM-based essay comparisons."""

    async def perform_comparisons(
        self,
        tasks: list[Any],
        correlation_id: UUID,
        tracking_map: dict[tuple[str, str], UUID] | None = None,
        bos_batch_id: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        system_prompt_override: str | None = None,
        provider_override: str | LLMProviderType | None = None,
        metadata_context: dict[str, Any] | None = None,
    ) -> list[Any]:
        """Perform comparative judgment on a list of comparison tasks.

        Args:
            tasks: List of ComparisonTask objects
            correlation_id: Request correlation ID for tracing
            tracking_map: Optional per-pair correlation override map
            bos_batch_id: Optional BOS batch identifier propagated to metadata
            model_override: Optional model name override
            temperature_override: Optional temperature override (0.0-2.0)
            max_tokens_override: Optional max tokens override
            system_prompt_override: Optional system prompt override
            provider_override: Optional provider name override forwarded to LPS
            metadata_context: Optional metadata additions for downstream callbacks

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
        system_prompt_override: str | None = None,
        provider_override: str | LLMProviderType | None = None,
        metadata_context: dict[str, Any] | None = None,
    ) -> "BatchSubmissionResult":
        """Submit comparison batch with configurable batch size."""
        ...

    async def handle_batch_submission(
        self,
        cj_batch_id: int,
        comparison_tasks: list[Any],
        correlation_id: UUID,
        request_data: "CJAssessmentRequestData",
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
        system_prompt_override: str | None = None,
        provider_override: str | LLMProviderType | None = None,
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
        system_prompt_override: str | None = None,
        provider_override: str | LLMProviderType | None = None,
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


class PairMatchingStrategyProtocol(Protocol):
    """Strategy for computing comparison pairs per wave.

    Enables DI-swappable matching algorithms for CJ experiments.
    Default implementation uses graph-based optimal matching (Hungarian algorithm).
    """

    def compute_wave_pairs(
        self,
        essays: Sequence["EssayForComparison"],
        existing_pairs: set[tuple[str, str]],
        comparison_counts: dict[str, int],
        randomization_seed: int | None = None,
    ) -> list[tuple["EssayForComparison", "EssayForComparison"]]:
        """Compute pairs for one wave ensuring each essay appears at most once.

        Args:
            essays: Essays to match (should be even count after handle_odd_count)
            existing_pairs: Set of (essay_a_id, essay_b_id) tuples already compared
            comparison_counts: Dict mapping essay_id -> comparison count
            randomization_seed: Seed for tie-breaking randomization

        Returns:
            List of (essay_a, essay_b) tuples representing the optimal matching.
        """
        ...

    def compute_wave_size(self, n_essays: int) -> int:
        """Return expected wave size for given essay count.

        Args:
            n_essays: Total number of essays in batch

        Returns:
            Number of pairs per wave (typically n_essays // 2)
        """
        ...

    def handle_odd_count(
        self,
        essays: Sequence["EssayForComparison"],
        comparison_counts: dict[str, int],
    ) -> tuple[list["EssayForComparison"], "EssayForComparison | None"]:
        """Handle odd essay counts by excluding one essay.

        Args:
            essays: List of essays to filter
            comparison_counts: Dict mapping essay_id -> comparison count

        Returns:
            Tuple of (filtered_essays, excluded_essay or None)
        """
        ...


class PairOrientationStrategyProtocol(Protocol):
    """Strategy for deciding A/B orientation for comparison pairs.

    Centralises positional fairness decisions for both COVERAGE and RESAMPLING
    modes while remaining DI-swappable for experiments.
    """

    def choose_coverage_orientation(
        self,
        pair: tuple["EssayForComparison", "EssayForComparison"],
        per_essay_position_counts: dict[str, tuple[int, int]],
        rng: Any,
    ) -> tuple["EssayForComparison", "EssayForComparison"]:
        """Return (essay_a, essay_b) orientation for COVERAGE mode."""
        ...

    def choose_resampling_orientation(
        self,
        pair: tuple["EssayForComparison", "EssayForComparison"],
        per_pair_orientation_counts: dict[tuple[str, str], tuple[int, int]],
        per_essay_position_counts: dict[str, tuple[int, int]],
        rng: Any,
    ) -> tuple["EssayForComparison", "EssayForComparison"]:
        """Return (essay_a, essay_b) orientation for RESAMPLING mode."""
        ...
