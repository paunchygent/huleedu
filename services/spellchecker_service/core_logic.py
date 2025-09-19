from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from huleedu_nlp_shared.normalization import SpellNormalizationResult, SpellNormalizer
from huleedu_nlp_shared.normalization.spell_normalizer import (
    _spellchecker_cache as _shared_spellchecker_cache,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.spellchecker_service.config import settings

# OpenTelemetry tracing handled by HuleEduError automatically

if TYPE_CHECKING:  # pragma: no cover - imported for static typing only
    from services.spellchecker_service.protocols import ParallelProcessorProtocol, WhitelistProtocol

logger = create_service_logger("spellchecker_service.core_logic")


class SpellcheckMetrics(SpellNormalizationResult):
    """Backward compatible alias for the shared normalization result."""


# Re-export cache so existing tests and utilities keep working without change.
_spellchecker_cache = _shared_spellchecker_cache


async def default_perform_spell_check_algorithm(
    text: str,
    l2_errors: dict[str, str],
    essay_id: str | None = None,
    language: str = "en",
    correlation_id: UUID | None = None,
    whitelist: WhitelistProtocol | None = None,
    parallel_processor: ParallelProcessorProtocol | None = None,
    enable_parallel: bool = True,
    max_concurrent: int = 10,
    batch_size: int = 100,
    parallel_timeout: float = 5.0,
    min_words_for_parallel: int = 5,
) -> SpellcheckMetrics:
    """Delegate to the shared SpellNormalizer while preserving legacy signature."""

    normalizer = SpellNormalizer(
        l2_errors=l2_errors,
        whitelist=whitelist,
        parallel_processor=parallel_processor,
        settings=settings,
        logger_override=logger,
    )

    result = await normalizer.normalize_text(
        text=text,
        essay_id=essay_id,
        language=language,
        correlation_id=correlation_id,
        enable_parallel=enable_parallel,
        max_concurrent=max_concurrent,
        batch_size=batch_size,
        parallel_timeout=parallel_timeout,
        min_words_for_parallel=min_words_for_parallel,
    )

    return SpellcheckMetrics.model_validate(result.model_dump())
