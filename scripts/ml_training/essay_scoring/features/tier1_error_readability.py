"""Tier 1 feature extraction: error density, readability, and core length."""

from __future__ import annotations

import hashlib
import json
import logging
import socket
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spacy.language import Language

from scripts.ml_training.essay_scoring.features.schema import Tier1Features
from scripts.ml_training.essay_scoring.features.spacy_pipeline import (
    ensure_textdescriptives_readability,
    load_spacy_model,
)
from scripts.ml_training.essay_scoring.features.utils import (
    density_per_100_words,
    normalize_whitespace,
    safe_divide,
)
from scripts.ml_training.essay_scoring.logging_utils import ProgressLogger
from scripts.ml_training.essay_scoring.offload.metrics import OffloadMetricsCollector

logger = logging.getLogger(__name__)

_CACHE_SCHEMA_VERSION = 1


@dataclass
class Tier1FeatureExtractor:
    """Extract Tier 1 features using LanguageTool and TextDescriptives."""

    language: str = "en-US"
    spacy_model: str = "en_core_web_sm"
    nlp: Language | None = None
    language_tool_url: str | None = None
    request_timeout_s: float = 60.0
    language_tool_cache_dir: Path | None = None
    language_tool_max_concurrency: int = 10
    language_tool_request_options: dict[str, Any] | None = None
    metrics: OffloadMetricsCollector | None = None

    def __post_init__(self) -> None:
        self._tool = None
        if self.language_tool_url is None:
            import language_tool_python  # noqa: PLC0415

            self._tool = language_tool_python.LanguageTool(self.language)
        if self.nlp is None:
            self.nlp = load_spacy_model(self.spacy_model)
        else:
            ensure_textdescriptives_readability(self.nlp)

    def extract(self, text: str) -> Tier1Features:
        """Extract Tier 1 features from essay text."""

        cleaned = normalize_whitespace(text)
        stats = self._compute_text_stats(cleaned)
        grammar_count, spelling_count, punctuation_count = self._error_counts(cleaned)
        return self._build_features(
            stats=stats,
            grammar_count=grammar_count,
            spelling_count=spelling_count,
            punctuation_count=punctuation_count,
        )

    def extract_batch(self, texts: list[str]) -> list[Tier1Features]:
        """Extract Tier 1 features for a batch of texts.

        If `language_tool_url` is configured, LanguageTool calls are executed in parallel
        (bounded by `language_tool_max_concurrency`) while spaCy/readability stays
        single-threaded.
        """

        if not texts:
            return []

        start = time.monotonic()
        cleaned_texts = [normalize_whitespace(text) for text in texts]
        progress = ProgressLogger(logger, "Tier1", len(cleaned_texts))

        if self.language_tool_url is None:
            logger.info("Tier1 start (mode=local, n=%d)", len(cleaned_texts))
            features: list[Tier1Features] = []
            if self.nlp is None:
                raise RuntimeError("spaCy pipeline not initialized for Tier 1 extractor.")
            for index, (cleaned, doc) in enumerate(
                zip(cleaned_texts, self.nlp.pipe(cleaned_texts), strict=True)
            ):
                logger.info(
                    "Tier1 item %d/%d start (chars=%d)", index + 1, len(texts), len(cleaned)
                )
                stats = self._compute_text_stats_from_doc(doc)
                grammar_count, spelling_count, punctuation_count = self._error_counts(cleaned)
                features.append(
                    self._build_features(
                        stats=stats,
                        grammar_count=grammar_count,
                        spelling_count=spelling_count,
                        punctuation_count=punctuation_count,
                    )
                )
                progress.update(index)
            logger.info(
                "Tier1 complete (mode=local, n=%d) in %.2fs", len(texts), time.monotonic() - start
            )
            return features

        logger.info(
            "Tier1 start (mode=remote, n=%d, max_concurrency=%d, cache_dir=%s)",
            len(cleaned_texts),
            int(self.language_tool_max_concurrency),
            str(self.language_tool_cache_dir)
            if self.language_tool_cache_dir is not None
            else "<disabled>",
        )
        max_workers = max(1, int(self.language_tool_max_concurrency))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(self._remote_error_counts, cleaned) for cleaned in cleaned_texts]

            stats_by_index: list[dict[str, float]] = []
            if self.nlp is None:
                raise RuntimeError("spaCy pipeline not initialized for Tier 1 extractor.")
            for index, (cleaned, doc) in enumerate(
                zip(cleaned_texts, self.nlp.pipe(cleaned_texts), strict=True)
            ):
                logger.info(
                    "Tier1 item %d/%d start (chars=%d)", index + 1, len(texts), len(cleaned)
                )
                stats_by_index.append(self._compute_text_stats_from_doc(doc))
                progress.update(index)

            logger.info("Tier1 awaiting LanguageTool results (n=%d)", len(futures))
            counts_by_index = [future.result() for future in futures]
            logger.info("Tier1 LanguageTool results complete (n=%d)", len(futures))

        features = []
        for stats, (grammar_count, spelling_count, punctuation_count) in zip(
            stats_by_index, counts_by_index, strict=True
        ):
            features.append(
                self._build_features(
                    stats=stats,
                    grammar_count=grammar_count,
                    spelling_count=spelling_count,
                    punctuation_count=punctuation_count,
                )
            )
        logger.info(
            "Tier1 complete (mode=remote, n=%d) in %.2fs", len(texts), time.monotonic() - start
        )
        return features

    def _compute_text_stats(self, cleaned: str) -> dict[str, float]:
        if self.nlp is None:
            raise RuntimeError("spaCy pipeline not initialized for Tier 1 extractor.")
        doc = self.nlp(cleaned)
        return self._compute_text_stats_from_doc(doc)

    @staticmethod
    def _compute_text_stats_from_doc(doc: object) -> dict[str, float]:
        words = [
            token.text
            for token in doc
            if not getattr(token, "is_space", False) and not getattr(token, "is_punct", False)
        ]
        sentences = [sent for sent in getattr(doc, "sents", [])]
        word_count = float(len(words))
        sentence_count = float(len(sentences))
        avg_sentence_length = safe_divide(word_count, sentence_count)

        ttr = safe_divide(len(set(token.lower() for token in words)), word_count)
        avg_word_length = safe_divide(sum(len(token) for token in words), word_count)

        readability = getattr(getattr(doc, "_", None), "readability", {})

        return {
            "word_count": float(word_count),
            "avg_sentence_length": float(avg_sentence_length),
            "ttr": float(ttr),
            "avg_word_length": float(avg_word_length),
            "flesch_kincaid": float(readability["flesch_kincaid_grade"]),
            "smog": float(readability["smog"]),
            "coleman_liau": float(readability["coleman_liau_index"]),
            "ari": float(readability["automated_readability_index"]),
        }

    @staticmethod
    def _build_features(
        *,
        stats: dict[str, float],
        grammar_count: float,
        spelling_count: float,
        punctuation_count: float,
    ) -> Tier1Features:
        word_count = stats["word_count"]
        return Tier1Features(
            grammar_density=density_per_100_words(grammar_count, word_count),
            spelling_density=density_per_100_words(spelling_count, word_count),
            punctuation_density=density_per_100_words(punctuation_count, word_count),
            flesch_kincaid=stats["flesch_kincaid"],
            smog=stats["smog"],
            coleman_liau=stats["coleman_liau"],
            ari=stats["ari"],
            avg_sentence_length=stats["avg_sentence_length"],
            ttr=stats["ttr"],
            word_count=word_count,
            avg_word_length=stats["avg_word_length"],
        )

    def _error_counts(self, text: str) -> tuple[float, float, float]:
        """Count grammar, spelling, and punctuation issues."""

        if self.language_tool_url is not None:
            return self._remote_error_counts(text)

        if self._tool is None:
            raise RuntimeError("Local LanguageTool not initialized.")

        matches = self._tool.check(text)
        grammar_count = 0.0
        spelling_count = 0.0
        punctuation_count = 0.0

        for match in matches:
            issue_type = str(getattr(match, "ruleIssueType", "")).lower()
            category = self._category_name(match)
            rule_id = str(getattr(match, "ruleId", "")).lower()

            if "punct" in category or "punct" in rule_id:
                punctuation_count += 1
            elif issue_type in {"misspelling", "typographical"} or "spell" in category:
                spelling_count += 1
            else:
                grammar_count += 1

        return grammar_count, spelling_count, punctuation_count

    def _remote_error_counts(self, text: str) -> tuple[float, float, float]:
        response, derived = self._remote_check_cached(text)
        if derived is not None:
            return derived

        errors = response.get("errors", [])

        grammar_count = 0.0
        spelling_count = 0.0
        punctuation_count = 0.0

        for error in errors:
            if not isinstance(error, dict):
                continue
            category_id = str(error.get("category_id") or error.get("category") or "").upper()
            rule_id = str(error.get("rule_id") or "").upper()

            if "PUNCT" in category_id or "PUNCT" in rule_id:
                punctuation_count += 1
            elif (
                category_id in {"TYPOS", "SPELLING", "TYPOGRAPHY", "MISSPELLING"}
                or "SPELL" in category_id
            ):
                spelling_count += 1
            else:
                grammar_count += 1

        return grammar_count, spelling_count, punctuation_count

    def _remote_check_cached(
        self, text: str
    ) -> tuple[dict[str, Any], tuple[float, float, float] | None]:
        if self.language_tool_url is None:
            raise RuntimeError("LanguageTool URL not configured for remote checks.")

        request_options = self.language_tool_request_options or {}
        cache_path = self._cache_path(text=text, request_options=request_options)
        if cache_path is not None and cache_path.exists():
            try:
                cached_text = cache_path.read_text(encoding="utf-8")
            except OSError:
                if self.metrics is not None:
                    self.metrics.record_cache_read_error(kind="language_tool")
                cached_text = ""
            try:
                cached = json.loads(cached_text)
            except json.JSONDecodeError:
                if self.metrics is not None:
                    self.metrics.record_cache_decode_error(kind="language_tool")
                cached = None
            if isinstance(cached, dict):
                response = cached.get("response")
                derived_counts = cached.get("derived_counts")
                if isinstance(response, dict) and isinstance(derived_counts, dict):
                    if self.metrics is not None:
                        self.metrics.record_cache_hit(kind="language_tool")
                    grammar = float(derived_counts.get("grammar", 0.0))
                    spelling = float(derived_counts.get("spelling", 0.0))
                    punctuation = float(derived_counts.get("punctuation", 0.0))
                    return response, (grammar, spelling, punctuation)
            if self.metrics is not None:
                self.metrics.record_cache_miss(kind="language_tool")
        elif cache_path is not None and self.metrics is not None:
            self.metrics.record_cache_miss(kind="language_tool")

        response = self._fetch_remote_language_tool_response(
            text=text, request_options=request_options
        )
        derived = self._derive_counts(response.get("errors", []))
        if cache_path is not None:
            self._write_cache(
                cache_path=cache_path,
                text=text,
                request_options=request_options,
                response=response,
                derived_counts=derived,
            )
            if self.metrics is not None:
                self.metrics.record_cache_write(kind="language_tool")
        return response, derived

    def _fetch_remote_language_tool_response(
        self, *, text: str, request_options: dict[str, Any]
    ) -> dict[str, Any]:
        url = self.language_tool_url.rstrip("/") + "/v1/check"
        payload: dict[str, Any] = {"text": text, "language": self.language}
        payload.update(request_options)
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_s) as resp:
                status = getattr(resp, "status", 200)
                body = resp.read()
        except urllib.error.HTTPError as exc:
            elapsed = time.monotonic() - start
            if self.metrics is not None:
                self.metrics.record_request_error(
                    kind="language_tool", duration_s=elapsed, error_kind="http_error"
                )
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"LanguageTool offload HTTP error status={exc.code} body={detail}"
            ) from exc
        except urllib.error.URLError as exc:
            elapsed = time.monotonic() - start
            is_timeout = isinstance(exc.reason, (TimeoutError, socket.timeout))
            if self.metrics is not None:
                self.metrics.record_request_error(
                    kind="language_tool",
                    duration_s=elapsed,
                    error_kind="timeout" if is_timeout else "connection_error",
                )
            raise RuntimeError(f"LanguageTool offload connection error: {exc}") from exc
        except socket.timeout as exc:
            elapsed = time.monotonic() - start
            if self.metrics is not None:
                self.metrics.record_request_error(
                    kind="language_tool", duration_s=elapsed, error_kind="timeout"
                )
            raise RuntimeError(f"LanguageTool offload timeout: {exc}") from exc

        if status != 200:
            elapsed = time.monotonic() - start
            if self.metrics is not None:
                self.metrics.record_request_error(
                    kind="language_tool", duration_s=elapsed, error_kind="http_error"
                )
            raise RuntimeError(f"LanguageTool offload returned status={status} bytes={len(body)}")

        elapsed = time.monotonic() - start
        if self.metrics is not None:
            self.metrics.record_request_ok(
                kind="language_tool",
                duration_s=elapsed,
                request_bytes=len(data),
                response_bytes=len(body),
                texts_in_request=1,
            )

        response = json.loads(body.decode("utf-8"))
        if not isinstance(response, dict):
            raise RuntimeError(f"LanguageTool offload returned invalid JSON type={type(response)}")
        return response

    @staticmethod
    def _derive_counts(errors: object) -> tuple[float, float, float]:
        if not isinstance(errors, list):
            return 0.0, 0.0, 0.0

        grammar_count = 0.0
        spelling_count = 0.0
        punctuation_count = 0.0

        for error in errors:
            if not isinstance(error, dict):
                continue
            category_id = str(error.get("category_id") or error.get("category") or "").upper()
            rule_id = str(error.get("rule_id") or "").upper()

            if "PUNCT" in category_id or "PUNCT" in rule_id:
                punctuation_count += 1
            elif (
                category_id in {"TYPOS", "SPELLING", "TYPOGRAPHY", "MISSPELLING"}
                or "SPELL" in category_id
            ):
                spelling_count += 1
            else:
                grammar_count += 1

        return grammar_count, spelling_count, punctuation_count

    def _cache_path(self, *, text: str, request_options: dict[str, Any]) -> Path | None:
        if self.language_tool_cache_dir is None:
            return None

        self.language_tool_cache_dir.mkdir(parents=True, exist_ok=True)

        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        key_payload = {
            "schema_version": _CACHE_SCHEMA_VERSION,
            "language_tool_url": self.language_tool_url,
            "language": self.language,
            "request_timeout_s": self.request_timeout_s,
            "request_options": request_options,
            "text_sha256": text_hash,
        }
        key_bytes = json.dumps(
            key_payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        cache_key = hashlib.sha256(key_bytes).hexdigest()
        return self.language_tool_cache_dir / f"{cache_key}.json"

    def _write_cache(
        self,
        *,
        cache_path: Path,
        text: str,
        request_options: dict[str, Any],
        response: dict[str, Any],
        derived_counts: tuple[float, float, float],
    ) -> None:
        grammar_count, spelling_count, punctuation_count = derived_counts
        payload = {
            "schema_version": _CACHE_SCHEMA_VERSION,
            "language_tool_url": self.language_tool_url,
            "language": self.language,
            "request_timeout_s": self.request_timeout_s,
            "request_options": request_options,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text_chars": len(text),
            "derived_counts": {
                "grammar": grammar_count,
                "spelling": spelling_count,
                "punctuation": punctuation_count,
            },
            "response": response,
        }
        tmp_path = cache_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp_path.replace(cache_path)

    @staticmethod
    def _category_name(match: object) -> str:
        """Extract a normalized category identifier from a match."""

        category = getattr(match, "category", None)
        if category is None:
            return ""
        if hasattr(category, "id"):
            return str(getattr(category, "id", "")).lower()
        if hasattr(category, "name"):
            return str(getattr(category, "name", "")).lower()
        return str(category).lower()
