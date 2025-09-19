"""Protocols describing dependencies required by the shared spell normalizer."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID


class WhitelistProtocol(Protocol):
    """Words that should be skipped by the spell checker."""

    def is_whitelisted(self, word: str) -> bool:
        """Return True when the word should bypass correction."""


class ParallelProcessorProtocol(Protocol):
    """Parallel correction operations used by the existing service implementation."""

    async def process_corrections_parallel(
        self,
        words_to_correct: list[tuple[int, str]],
        spell_checker_cache: dict[str, Any],
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> dict[int, tuple[str | None, float]]:
        """Return corrections keyed by token index."""


class SpellcheckerSettingsProtocol(Protocol):
    """Subset of settings consumed by the spell normalizer."""

    ENABLE_PARALLEL_PROCESSING: bool
    MAX_CONCURRENT_CORRECTIONS: int
    SPELLCHECK_BATCH_SIZE: int
    PARALLEL_TIMEOUT_SECONDS: float
    PARALLEL_PROCESSING_MIN_WORDS: int
    ENABLE_CORRECTION_LOGGING: bool

    @property
    def effective_correction_log_dir(self) -> str:  # pragma: no cover - attribute proxy
        ...
