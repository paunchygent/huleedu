"""Tier 1 feature extraction: error density, readability, and core length."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

import language_tool_python
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
    tokenize_sentences,
    tokenize_words,
)


@dataclass
class Tier1FeatureExtractor:
    """Extract Tier 1 features using LanguageTool and TextDescriptives."""

    language: str = "en-US"
    spacy_model: str = "en_core_web_sm"
    nlp: Language | None = None
    language_tool_url: str | None = None
    request_timeout_s: float = 60.0

    def __post_init__(self) -> None:
        self._tool = None
        if self.language_tool_url is None:
            self._tool = language_tool_python.LanguageTool(self.language)
        if self.nlp is None:
            self.nlp = load_spacy_model(self.spacy_model)
        else:
            ensure_textdescriptives_readability(self.nlp)

    def extract(self, text: str) -> Tier1Features:
        """Extract Tier 1 features from essay text."""

        cleaned = normalize_whitespace(text)
        words = tokenize_words(cleaned, self.nlp)
        sentences = tokenize_sentences(cleaned, self.nlp)
        word_count = float(len(words))
        sentence_count = float(len(sentences))
        avg_sentence_length = safe_divide(word_count, sentence_count)

        ttr = safe_divide(len(set(token.lower() for token in words)), word_count)
        avg_word_length = safe_divide(sum(len(token) for token in words), word_count)

        grammar_count, spelling_count, punctuation_count = self._error_counts(cleaned)

        if self.nlp is None:
            raise RuntimeError("spaCy pipeline not initialized for Tier 1 extractor.")

        doc = self.nlp(cleaned)
        readability = doc._.readability

        return Tier1Features(
            grammar_density=density_per_100_words(grammar_count, word_count),
            spelling_density=density_per_100_words(spelling_count, word_count),
            punctuation_density=density_per_100_words(punctuation_count, word_count),
            flesch_kincaid=float(readability["flesch_kincaid_grade"]),
            smog=float(readability["smog"]),
            coleman_liau=float(readability["coleman_liau_index"]),
            ari=float(readability["automated_readability_index"]),
            avg_sentence_length=float(avg_sentence_length),
            ttr=float(ttr),
            word_count=float(word_count),
            avg_word_length=float(avg_word_length),
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
        url = self.language_tool_url.rstrip("/") + "/v1/check"
        payload = {"text": text, "language": self.language}
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_s) as resp:
                status = getattr(resp, "status", 200)
                body = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"LanguageTool offload HTTP error status={exc.code} body={detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LanguageTool offload connection error: {exc}") from exc

        if status != 200:
            raise RuntimeError(f"LanguageTool offload returned status={status} bytes={len(body)}")

        response = json.loads(body.decode("utf-8"))
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
