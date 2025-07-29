"""Protocol definitions for NLP Service."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from aiohttp import ClientSession
from common_core.events.nlp_events import StudentMatchSuggestion
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
