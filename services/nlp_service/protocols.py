"""Protocol definitions for NLP Service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from opentelemetry.trace import Span

from aiohttp import ClientSession
from aiokafka import ConsumerRecord
from common_core.domain_enums import CourseCode
from common_core.events.envelope import EventEnvelope
from common_core.events.nlp_events import EssayMatchResult, StudentMatchSuggestion
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
