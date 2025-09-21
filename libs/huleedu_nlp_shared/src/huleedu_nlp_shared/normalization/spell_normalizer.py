"""Shared implementation of the spell normalization pipeline."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict
from uuid import UUID

from spellchecker import SpellChecker

from .models import SpellNormalizationResult
from .protocols import (
    ParallelProcessorProtocol,
    SpellcheckerSettingsProtocol,
    WhitelistProtocol,
)

logger = logging.getLogger("huleedu.nlp_shared.normalization")

# Global cache shared across all SpellNormalizer instances.
_spellchecker_cache: Dict[str, Any] = {}


class SpellNormalizer:
    """Port of the spell checker pipeline used by the Spellchecker Service."""

    def __init__(
        self,
        *,
        l2_errors: dict[str, str],
        whitelist: WhitelistProtocol | None,
        parallel_processor: ParallelProcessorProtocol | None,
        settings: SpellcheckerSettingsProtocol,
        logger_override: logging.Logger | None = None,
    ) -> None:
        self._l2_errors = l2_errors
        self._whitelist = whitelist
        self._parallel_processor = parallel_processor
        self._settings = settings
        self._logger = logger_override or logger

    async def normalize_text(
        self,
        *,
        text: str,
        essay_id: str | None = None,
        language: str = "en",
        correlation_id: UUID | None = None,
        enable_parallel: bool | None = None,
        max_concurrent: int | None = None,
        batch_size: int | None = None,
        parallel_timeout: float | None = None,
        min_words_for_parallel: int | None = None,
    ) -> SpellNormalizationResult:
        """Execute the spell normalization pipeline."""

        resolved_enable_parallel = (
            enable_parallel
            if enable_parallel is not None
            else self._settings.ENABLE_PARALLEL_PROCESSING
        )
        resolved_max_concurrent = (
            max_concurrent
            if max_concurrent is not None
            else self._settings.MAX_CONCURRENT_CORRECTIONS
        )
        resolved_batch_size = (
            batch_size if batch_size is not None else self._settings.SPELLCHECK_BATCH_SIZE
        )
        resolved_min_words_for_parallel = (
            min_words_for_parallel
            if min_words_for_parallel is not None
            else self._settings.PARALLEL_PROCESSING_MIN_WORDS
        )

        log_prefix = f"Essay {essay_id}: " if essay_id else ""
        log_extra: Dict[str, Any] = {
            "essay_id": essay_id,
            "text_length": len(text),
            "language": language,
        }
        if correlation_id:
            log_extra["correlation_id"] = str(correlation_id)

        self._logger.info(
            f"{log_prefix}Starting spell check algorithm (l2_errors: {len(self._l2_errors)})",
            extra=log_extra,
        )

        total_corrections = 0
        all_corrections: list[dict[str, Any]] = []

        # Phase 1: Apply L2 error corrections
        l2_corrections: list[dict[str, Any]] = []
        l2_start = time.time()

        for error_word, correction in self._l2_errors.items():
            pattern = re.compile(r"\b" + re.escape(error_word) + r"\b", re.IGNORECASE)
            matches = list(pattern.finditer(text))

            for match in matches:
                original = match.group()
                start = match.start()
                end = match.end()

                if original.isupper() and len(original) > 1:
                    replacement = correction.upper()
                elif original[0].isupper():
                    replacement = correction[0].upper() + correction[1:]
                else:
                    replacement = correction

                if original != replacement:
                    text = text[:start] + replacement + text[end:]
                    l2_corrections.append(
                        {
                            "original_word": original,
                            "corrected_word": replacement,
                            "start": start,
                            "end": end - 1,
                            "rule": "l2_swedish_learner",
                        }
                    )
                    total_corrections += 1

        l2_time = time.time() - l2_start
        self._logger.info(
            f"{log_prefix}L2 corrections completed: {len(l2_corrections)} corrections in {l2_time:.3f}s",
            extra={
                **log_extra,
                "l2_corrections_count": len(l2_corrections),
                "l2_time_seconds": l2_time,
            },
        )

        cache_key_d1 = f"{language}_d1"
        cache_key_d2 = f"{language}_d2"

        if cache_key_d1 not in _spellchecker_cache:
            self._logger.info(f"Creating SpellChecker instance for {language} with distance=1")
            _spellchecker_cache[cache_key_d1] = SpellChecker(language=language, distance=1)

        if cache_key_d2 not in _spellchecker_cache:
            self._logger.info(f"Creating SpellChecker instance for {language} with distance=2")
            _spellchecker_cache[cache_key_d2] = SpellChecker(language=language, distance=2)

        word_pattern = re.compile(r"\b[A-Za-z]+(?:['-][A-Za-z]+)*\b")
        pyspellchecker_start = time.time()

        tokens: list[str] = []
        last_end = 0
        for match in word_pattern.finditer(text):
            if match.start() > last_end:
                tokens.append(text[last_end : match.start()])
            tokens.append(match.group())
            last_end = match.end()
        if last_end < len(text):
            tokens.append(text[last_end:])

        words_to_check = [token for token in tokens if word_pattern.fullmatch(token)]
        lowercase_words = [w.lower() for w in words_to_check]

        whitelist_skip_count = 0
        words_to_spellcheck = []
        if self._whitelist:
            for idx, word in enumerate(lowercase_words):
                original_word = words_to_check[idx]
                if self._whitelist.is_whitelisted(original_word):
                    whitelist_skip_count += 1
                    self._logger.debug(
                        f"{log_prefix}Skipping whitelisted word: '{original_word}'",
                        extra={**log_extra, "whitelisted_word": original_word},
                    )
                else:
                    words_to_spellcheck.append(word)
        else:
            words_to_spellcheck = lowercase_words

        if whitelist_skip_count > 0:
            self._logger.info(
                f"{log_prefix}Skipped {whitelist_skip_count} whitelisted words",
                extra={**log_extra, "whitelist_skip_count": whitelist_skip_count},
            )

        spell_checker_d2 = _spellchecker_cache[cache_key_d2]
        unknown_check_start = time.time()
        misspelled_lowercase = spell_checker_d2.unknown(words_to_spellcheck)
        unknown_check_time = time.time() - unknown_check_start
        self._logger.info(
            f"{log_prefix}SpellChecker.unknown() time: {unknown_check_time:.3f}s, "
            f"found {len(misspelled_lowercase)} misspelled words",
            extra={
                **log_extra,
                "unknown_check_time_seconds": unknown_check_time,
                "misspelled_count": len(misspelled_lowercase),
            },
        )

        misspelled_words = {
            words_to_check[i]
            for i, lowercase_word in enumerate(lowercase_words)
            if lowercase_word in misspelled_lowercase
        }

        corrections_start = time.time()
        correction_times: list[float] = []
        words_needing_correction = []
        word_idx_counter = 0

        for token_text in tokens:
            if word_pattern.fullmatch(token_text):
                original_word = words_to_check[word_idx_counter]
                if self._whitelist and self._whitelist.is_whitelisted(original_word):
                    word_idx_counter += 1
                    continue
                if original_word in misspelled_words:
                    words_needing_correction.append((word_idx_counter, original_word))
                word_idx_counter += 1

        use_parallel = (
            resolved_enable_parallel
            and len(words_needing_correction) >= resolved_min_words_for_parallel
            and correlation_id is not None
        )

        pyspellchecker_corrections: list[dict[str, Any]] = []
        final_corrected_tokens: list[str] = []

        if use_parallel:
            if self._parallel_processor is None:
                raise ValueError(
                    "parallel_processor is required when parallel processing is enabled"
                )

            self._logger.info(
                f"{log_prefix}Using parallel processing for {len(words_needing_correction)} corrections",
                extra={
                    **log_extra,
                    "parallel_mode": True,
                    "words_to_correct": len(words_needing_correction),
                    "max_concurrent": resolved_max_concurrent,
                },
            )

            parallel_corrections: dict[int, tuple[str | None, float]] = {}
            for batch_start in range(0, len(words_needing_correction), resolved_batch_size):
                batch_end = min(batch_start + resolved_batch_size, len(words_needing_correction))
                batch_words = words_needing_correction[batch_start:batch_end]

                batch_corrections = await self._parallel_processor.process_corrections_parallel(
                    words_to_correct=batch_words,
                    spell_checker_cache=_spellchecker_cache,
                    correlation_id=correlation_id,
                    essay_id=essay_id,
                )
                parallel_corrections.update(batch_corrections)

            current_pos = 0
            word_idx_counter = 0

            for token_text in tokens:
                token_len = len(token_text)
                if word_pattern.fullmatch(token_text):
                    original_word = words_to_check[word_idx_counter]

                    if self._whitelist and self._whitelist.is_whitelisted(original_word):
                        final_corrected_tokens.append(original_word)
                    elif word_idx_counter in parallel_corrections:
                        corrected_word, correction_time = parallel_corrections[word_idx_counter]
                        correction_times.append(correction_time)

                        if corrected_word and corrected_word.lower() != original_word.lower():
                            corrected_word = _preserve_case(corrected_word, original_word)

                            if corrected_word != original_word:
                                pyspellchecker_corrections.append(
                                    {
                                        "original_word": original_word,
                                        "corrected_word": corrected_word,
                                        "start": current_pos,
                                        "end": current_pos + token_len - 1,
                                        "rule": "pyspellchecker_parallel",
                                    }
                                )
                                final_corrected_tokens.append(corrected_word)
                            else:
                                final_corrected_tokens.append(original_word)
                        else:
                            final_corrected_tokens.append(original_word)
                    else:
                        final_corrected_tokens.append(original_word)
                    word_idx_counter += 1
                else:
                    final_corrected_tokens.append(token_text)
                current_pos += token_len

        else:
            self._logger.info(
                f"{log_prefix}Using sequential processing for {len(words_needing_correction)} corrections",
                extra={
                    **log_extra,
                    "parallel_mode": False,
                    "words_to_correct": len(words_needing_correction),
                },
            )

            current_pos = 0
            word_idx_counter = 0

            for token_text in tokens:
                token_len = len(token_text)
                if word_pattern.fullmatch(token_text):
                    original_word = words_to_check[word_idx_counter]

                    if self._whitelist and self._whitelist.is_whitelisted(original_word):
                        final_corrected_tokens.append(original_word)
                    elif original_word in misspelled_words:
                        optimal_distance = _get_adaptive_edit_distance(original_word)
                        if optimal_distance == 1:
                            spell_checker = _spellchecker_cache[cache_key_d1]
                        else:
                            spell_checker = _spellchecker_cache[cache_key_d2]

                        correction_start = time.time()
                        corrected_word = spell_checker.correction(original_word.lower())
                        correction_time = time.time() - correction_start
                        correction_times.append(correction_time)

                        if correction_time > 0.1:
                            self._logger.warning(
                                f"{log_prefix}Slow correction: '{original_word}' -> '{corrected_word}' "
                                f"took {correction_time:.3f}s (distance={optimal_distance})",
                                extra={
                                    **log_extra,
                                    "slow_word": original_word,
                                    "correction_time_seconds": correction_time,
                                    "edit_distance": optimal_distance,
                                },
                            )
                        else:
                            self._logger.debug(
                                f"{log_prefix}Corrected '{original_word}' using distance={optimal_distance} "
                                f"in {correction_time:.3f}s",
                                extra={
                                    **log_extra,
                                    "word": original_word,
                                    "edit_distance": optimal_distance,
                                    "correction_time_seconds": correction_time,
                                },
                            )

                        if corrected_word and corrected_word.lower() != original_word.lower():
                            corrected_word = _preserve_case(corrected_word, original_word)

                            if corrected_word != original_word:
                                pyspellchecker_corrections.append(
                                    {
                                        "original_word": original_word,
                                        "corrected_word": corrected_word,
                                        "start": current_pos,
                                        "end": current_pos + token_len - 1,
                                        "rule": "pyspellchecker",
                                    }
                                )
                                final_corrected_tokens.append(corrected_word)
                            else:
                                final_corrected_tokens.append(original_word)
                        else:
                            final_corrected_tokens.append(original_word)
                    else:
                        final_corrected_tokens.append(original_word)
                    word_idx_counter += 1
                else:
                    final_corrected_tokens.append(token_text)
                current_pos += token_len

        corrections_total_time = time.time() - corrections_start
        max_correction_time = max(correction_times) if correction_times else 0
        avg_correction_time = (
            sum(correction_times) / len(correction_times) if correction_times else 0
        )

        pyspellchecker_time = time.time() - pyspellchecker_start

        corrected_text = "".join(final_corrected_tokens)
        total_corrections += len(pyspellchecker_corrections)
        all_corrections = l2_corrections + pyspellchecker_corrections
        word_count = len(words_to_check)
        correction_density = (total_corrections / word_count * 100) if word_count > 0 else 0.0

        self._logger.info(
            f"{log_prefix}Spell check completed: {total_corrections} total corrections (L2: "
            f"{len(l2_corrections)}, PySpell: {len(pyspellchecker_corrections)}). "
            f"Total time: {l2_time + pyspellchecker_time:.3f}s",
            extra={
                **log_extra,
                "total_corrections": total_corrections,
                "l2_corrections_count": len(l2_corrections),
                "pyspell_corrections_count": len(pyspellchecker_corrections),
                "l2_time_seconds": l2_time,
                "pyspell_time_seconds": pyspellchecker_time,
                "total_time_seconds": l2_time + pyspellchecker_time,
                "unknown_check_time_seconds": unknown_check_time,
                "corrections_apply_time_seconds": corrections_total_time,
                "max_correction_time_seconds": max_correction_time,
                "avg_correction_time_seconds": avg_correction_time,
                "misspelled_words_count": len(misspelled_words),
            },
        )

        if self._settings.ENABLE_CORRECTION_LOGGING and essay_id:
            try:
                output_dir = Path(self._settings.effective_correction_log_dir)
                output_dir.mkdir(parents=True, exist_ok=True)

                output_file = output_dir / f"{essay_id}_corrections.json"
                with open(output_file, "w", encoding="utf-8") as file_handle:
                    json.dump(
                        {
                            "essay_id": essay_id,
                            "total_corrections": total_corrections,
                            "l2_corrections": l2_corrections,
                            "pyspellchecker_corrections": pyspellchecker_corrections,
                            "all_corrections": all_corrections,
                            "original_length": len(text),
                            "corrected_length": len(corrected_text),
                            "processing_time": {
                                "l2_seconds": l2_time,
                                "pyspellchecker_seconds": pyspellchecker_time,
                                "total_seconds": l2_time + pyspellchecker_time,
                            },
                        },
                        file_handle,
                        indent=2,
                        ensure_ascii=False,
                    )

                self._logger.debug(
                    f"{log_prefix}Saved correction details to {output_file}",
                    extra={**log_extra, "output_file": str(output_file)},
                )
            except Exception as exc:  # pragma: no cover - defensive logging path
                self._logger.warning(
                    f"{log_prefix}Failed to save correction log: {exc}",
                    extra={**log_extra, "error": str(exc)},
                )

        return SpellNormalizationResult(
            corrected_text=corrected_text,
            total_corrections=total_corrections,
            l2_dictionary_corrections=len(l2_corrections),
            spellchecker_corrections=len(pyspellchecker_corrections),
            word_count=word_count,
            correction_density=correction_density,
        )


def _get_adaptive_edit_distance(word: str) -> int:
    if len(word) > 5:
        return 1
    if "-" in word or "'" in word:
        return 1
    return 2


def _preserve_case(corrected_word: str, original_word: str) -> str:
    if original_word.isupper() and len(original_word) > 1:
        return corrected_word.upper()
    if original_word.istitle():
        return corrected_word.title()
    if original_word[0].isupper():
        return corrected_word[0].upper() + corrected_word[1:]
    return corrected_word
