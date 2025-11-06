"""Protocol definitions for NLP Service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from opentelemetry.trace import Span

from aiohttp import ClientSession
from aiokafka import ConsumerRecord
from common_core.domain_enums import CourseCode
from common_core.events.envelope import EventEnvelope
from common_core.events.nlp_events import (
    EssayMatchResult,
    GrammarAnalysis,
    NlpMetrics,
    StudentMatchSuggestion,
)
from huleedu_service_libs.protocols import KafkaPublisherProtocol


class ContentClientProtocol(Protocol):
    """Protocol for fetching essay content."""

    async def fetch_content(
        self,
        storage_id: str,
        http_session: ClientSession,
        correlation_id: UUID,
    ) -> str:
        """Fetch essay text content from Content Service."""
        ...


class ClassManagementClientProtocol(Protocol):
    """Protocol for fetching class rosters."""

    async def get_class_roster(
        self,
        class_id: str,
        http_session: ClientSession,
        correlation_id: UUID,
    ) -> list[dict]:  # TODO: Define StudentInfo model
        """Fetch student roster from Class Management Service."""
        ...


class RosterCacheProtocol(Protocol):
    """Protocol for caching class rosters."""

    async def get_roster(self, class_id: str) -> list[dict] | None:
        """Get cached roster if available."""
        ...

    async def set_roster(
        self,
        class_id: str,
        roster: list[dict],
        ttl_seconds: int = 3600,
    ) -> None:
        """Cache roster with TTL."""
        ...


class StudentMatcherProtocol(Protocol):
    """Protocol for student matching logic."""

    async def find_matches(
        self,
        essay_text: str,
        roster: list[dict],
        correlation_id: UUID,
    ) -> list[StudentMatchSuggestion]:
        """Find potential student matches in essay text."""
        ...


class NlpEventPublisherProtocol(Protocol):
    """Protocol for publishing NLP results."""

    async def publish_author_match_result(
        self,
        kafka_bus: KafkaPublisherProtocol,
        essay_id: str,
        suggestions: list[StudentMatchSuggestion],
        match_status: str,
        correlation_id: UUID,
    ) -> None:
        """Publish author match results to Kafka."""
        ...

    async def publish_batch_author_match_results(
        self,
        kafka_bus: KafkaPublisherProtocol,
        batch_id: str,
        class_id: str,
        course_code: CourseCode,
        match_results: list[EssayMatchResult],
        processing_summary: dict[str, int],
        correlation_id: UUID,
    ) -> None:
        """Publish batch author match results to Kafka."""
        ...

    async def publish_essay_nlp_completed(
        self,
        essay_id: str,
        text_storage_id: str,
        nlp_metrics: NlpMetrics,
        grammar_analysis: GrammarAnalysis,
        correlation_id: UUID,
        feature_outputs: dict[str, Any] | None = None,
        prompt_text: str | None = None,
        prompt_storage_id: str | None = None,
    ) -> None:
        """Publish NLP analysis completion event for a single essay.

        Note: No kafka_bus parameter - implementation uses outbox pattern internally.

        Args:
            essay_id: Essay identifier
            text_storage_id: Storage ID of essay content
            nlp_metrics: Basic text metrics from spaCy
            grammar_analysis: Grammar analysis from Language Tool
            correlation_id: Correlation ID for tracking
            feature_outputs: Optional feature outputs from the pipeline
            prompt_text: Hydrated student prompt text for the batch being processed
            prompt_storage_id: Storage identifier for the student prompt reference
        """
        ...

    async def publish_batch_nlp_analysis_completed(
        self,
        batch_id: str,
        total_essays: int,
        successful_count: int,
        failed_count: int,
        successful_essay_ids: list[str],
        failed_essay_ids: list[str],
        processing_time_seconds: float,
        correlation_id: UUID,
    ) -> None:
        """Publish batch NLP analysis completion event to ELS.

        This is the thin event for state management, following the dual event pattern.
        Rich business data goes to RAS via publish_essay_nlp_completed.

        Args:
            batch_id: Batch identifier
            total_essays: Total number of essays in batch
            successful_count: Number of successfully processed essays
            failed_count: Number of failed essays
            processing_time_seconds: Total batch processing time
            correlation_id: Correlation ID for tracking
        """
        ...


class CommandHandlerProtocol(Protocol):
    """Base protocol for all NLP command handlers."""

    async def can_handle(self, event_type: str) -> bool:
        """Check if this handler can process the given event type.

        Args:
            event_type: The event type string to check

        Returns:
            True if this handler can process the event type, False otherwise
        """
        ...

    async def handle(
        self,
        msg: ConsumerRecord,
        envelope: EventEnvelope,
        http_session: ClientSession,
        correlation_id: UUID,
        span: "Span | None" = None,
    ) -> bool:
        """Process the command and return success status.

        Args:
            msg: The Kafka message to process
            envelope: Already parsed event envelope
            http_session: HTTP session for external service calls
            correlation_id: Correlation ID for tracking
            span: Optional span for tracing

        Returns:
            True if processing succeeded, False otherwise
        """
        ...


# Phase 2: NLP Analysis Protocols


class NlpAnalyzerProtocol(Protocol):
    """Protocol for spaCy-based text analysis."""

    async def analyze_text(
        self,
        text: str,
        language: str = "auto",
    ) -> NlpMetrics:
        """Extract basic text metrics using spaCy.

        Args:
            text: The text to analyze
            language: Language code ("en", "sv") or "auto" for detection

        Returns:
            NlpMetrics with basic text statistics
        """
        ...


class LanguageToolClientProtocol(Protocol):
    """Protocol for Language Tool Service integration."""

    async def check_grammar(
        self,
        text: str,
        http_session: ClientSession,
        correlation_id: UUID,
        language: str = "auto",
    ) -> GrammarAnalysis:
        """Get grammar analysis from Language Tool Service.

        Args:
            text: The text to check for grammar errors
            language: Language code ("en", "sv") or "auto"
            http_session: HTTP session for external API calls
            correlation_id: Correlation ID for tracking

        Returns:
            GrammarAnalysis with detected errors and suggestions
        """
        ...
