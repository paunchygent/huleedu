from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from huleedu_nlp_shared.normalization import SpellNormalizer
from huleedu_nlp_shared.normalization.models import SpellNormalizationResult
from huleedu_nlp_shared.normalization.protocols import (
    ParallelProcessorProtocol,
    SpellcheckerSettingsProtocol,
    WhitelistProtocol,
)


@dataclass
class DummySettings(SpellcheckerSettingsProtocol):
    ENABLE_PARALLEL_PROCESSING: bool = False
    MAX_CONCURRENT_CORRECTIONS: int = 5
    SPELLCHECK_BATCH_SIZE: int = 10
    PARALLEL_TIMEOUT_SECONDS: float = 1.0
    PARALLEL_PROCESSING_MIN_WORDS: int = 2
    ENABLE_CORRECTION_LOGGING: bool = False
    _log_dir: Path = Path("./.tmp_spell_logs")

    @property
    def effective_correction_log_dir(self) -> str:
        return str(self._log_dir)


class DummyWhitelist(WhitelistProtocol):
    def __init__(self, words: set[str] | None = None) -> None:
        self._words = {word.lower() for word in (words or set())}

    def is_whitelisted(self, word: str) -> bool:
        return word.lower() in self._words


class DummyParallelProcessor(ParallelProcessorProtocol):
    def __init__(self, correction: str) -> None:
        self._correction = correction

    async def process_corrections_parallel(
        self,
        words_to_correct: list[tuple[int, str]],
        spell_checker_cache: dict[str, Any],
        correlation_id: UUID,
        essay_id: str | None = None,
    ) -> dict[int, tuple[str | None, float]]:
        return {idx: (self._correction, 0.01) for idx, _ in words_to_correct}


@pytest.mark.asyncio
async def test_sequential_spell_normalization_corrects_text() -> None:
    settings = DummySettings()
    whitelist = DummyWhitelist()
    normalizer = SpellNormalizer(
        l2_errors={"teh": "the"},
        whitelist=whitelist,
        parallel_processor=None,
        settings=settings,
    )

    result = await normalizer.normalize_text(text="teh tset", essay_id="essay-123")

    assert isinstance(result, SpellNormalizationResult)
    assert result.corrected_text.startswith("the")
    assert result.total_corrections >= 2


@pytest.mark.asyncio
async def test_whitelist_preserves_words() -> None:
    settings = DummySettings()
    whitelist = DummyWhitelist({"HuleEdu"})
    normalizer = SpellNormalizer(
        l2_errors={},
        whitelist=whitelist,
        parallel_processor=None,
        settings=settings,
    )

    original = "HuleEdu"
    text = f"{original} is amazng"
    result = await normalizer.normalize_text(text=text)

    assert original in result.corrected_text


@pytest.mark.asyncio
async def test_parallel_processing_path_uses_supplied_corrections() -> None:
    settings = DummySettings(ENABLE_PARALLEL_PROCESSING=True, PARALLEL_PROCESSING_MIN_WORDS=1)
    whitelist = DummyWhitelist()
    parallel_processor = DummyParallelProcessor("fixed")
    normalizer = SpellNormalizer(
        l2_errors={},
        whitelist=whitelist,
        parallel_processor=parallel_processor,
        settings=settings,
    )

    result = await normalizer.normalize_text(
        text="wrng",
        correlation_id=uuid4(),
    )

    assert "fixed" in result.corrected_text
