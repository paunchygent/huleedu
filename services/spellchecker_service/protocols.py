from __future__ import annotations

# Local model is only for TYPE_CHECKING to avoid runtime circular import
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from aiohttp import ClientSession  # Changed from placeholder

# Import concrete types instead of placeholders if they are stable

if TYPE_CHECKING:
    pass
# Assuming common_core models might be used in signatures
from common_core.domain_enums import ContentType
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.metadata_models import SystemProcessingMetadata


class ContentClientProtocol(Protocol):
    async def fetch_content(
        self,
        storage_id: str,
        http_session: ClientSession,
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> str:
        """Fetches content string based on a storage ID with correlation tracking."""
        ...


class SpellLogicProtocol(Protocol):
    async def perform_spell_check(
        self,
        text: str,
        essay_id: str | None,
        original_text_storage_id: str,
        initial_system_metadata: SystemProcessingMetadata,
        correlation_id: UUID,
        language: str = "en",
    ) -> SpellcheckResultDataV1:
        """Performs spell check and returns a SpellcheckResultDataV1 with correlation tracking."""
        ...


class ResultStoreProtocol(Protocol):
    async def store_content(
        self,
        original_storage_id: str,
        content_type: ContentType,
        content: str,
        http_session: ClientSession,
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> str:
        """Stores content and returns a storage ID with correlation tracking."""
        ...


class SpellcheckEventPublisherProtocol(Protocol):
    async def publish_spellcheck_result(
        self,
        event_data: SpellcheckResultDataV1,
        correlation_id: UUID,
    ) -> None:
        """Publishes a spell check result event via outbox pattern."""
        ...


class WhitelistProtocol(Protocol):
    """Protocol for whitelist implementations."""

    def is_whitelisted(self, word: str) -> bool:
        """Check if word should be skipped for spell checking.

        Args:
            word: Word to check (case-insensitive matching)

        Returns:
            True if word is whitelisted, False otherwise
        """
        ...


class ParallelProcessorProtocol(Protocol):
    """Protocol for parallel word correction processing."""

    async def process_corrections_parallel(
        self,
        words_to_correct: list[tuple[int, str]],
        spell_checker_cache: dict[str, Any],
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> dict[int, tuple[str | None, float]]:
        """Process word corrections in parallel.

        Args:
            words_to_correct: List of (index, word) tuples to correct
            spell_checker_cache: Dictionary of cached SpellChecker instances by distance
            correlation_id: Request correlation ID for logging
            essay_id: Optional essay ID for logging context

        Returns:
            Dictionary mapping word index to (corrected_word, time_taken)
            Returns None for corrections that timeout or fail
        """
        ...
