from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from common_core.events.nlp_events import GrammarAnalysis, GrammarError, NlpMetrics
from common_core.events.spellcheck_models import SpellcheckMetricsV1
from huleedu_nlp_shared.feature_pipeline import (
    FeaturePipeline,
    FeaturePipelineResult,
)
from huleedu_nlp_shared.feature_pipeline.extractors import (
    GrammarOverviewExtractor,
    NormalizationFeaturesExtractor,
)
from huleedu_nlp_shared.normalization.models import SpellNormalizationResult


@dataclass
class StubSpellNormalizer:
    result: SpellNormalizationResult

    async def normalize_text(
        self,
        *,
        text: str,
        essay_id: str | None = None,
        correlation_id: UUID | None = None,
        language: str = "auto",
    ) -> SpellNormalizationResult:
        return self.result


@dataclass
class StubLanguageToolClient:
    analysis: GrammarAnalysis

    async def check_grammar(
        self,
        text: str,
        http_session: Any,
        correlation_id: UUID,
        language: str = "auto",
    ) -> GrammarAnalysis:
        return self.analysis


@dataclass
class StubNlpAnalyzer:
    metrics: NlpMetrics
    calls: int = 0
    latest_text: str | None = None

    async def analyze_text(self, text: str, language: str = "auto") -> NlpMetrics:
        self.calls += 1
        self.latest_text = text
        return self.metrics


def _grammar_analysis() -> GrammarAnalysis:
    errors = [
        GrammarError(
            rule_id="LT:SPELL1",
            message="Spelling error",
            short_message="Spelling",
            offset=0,
            length=4,
            replacements=["word"],
            category="SPELLING",
            severity="error",
            category_id="TYPOS",
            category_name="Spelling",
            context="teh",
            context_offset=0,
        ),
        GrammarError(
            rule_id="LT:GRAM1",
            message="Grammar error",
            short_message="Grammar",
            offset=5,
            length=4,
            replacements=["were"],
            category="GRAMMAR",
            severity="error",
            category_id="GRAMMAR",
            category_name="Grammar",
            context="was",
            context_offset=0,
        ),
        GrammarError(
            rule_id="LT:SPELL2",
            message="Spelling error",
            short_message="Spell",
            offset=10,
            length=3,
            replacements=["and"],
            category="SPELLING",
            severity="warning",
            category_id="TYPOS",
            category_name="Spelling",
            context="nad",
            context_offset=0,
        ),
    ]
    return GrammarAnalysis(
        error_count=len(errors),
        errors=errors,
        language="en",
        processing_time_ms=50,
    )


def _nlp_metrics() -> NlpMetrics:
    return NlpMetrics(
        word_count=200,
        sentence_count=10,
        avg_sentence_length=20.0,
        language_detected="en",
        processing_time_ms=42,
        mean_zipf_frequency=4.2,
        percent_tokens_zipf_below_3=12.5,
        mtld_score=100.0,
        hdd_score=0.72,
        mean_dependency_distance=1.4,
        phrasal_indices={},
        clausal_indices={},
        first_order_coherence=0.5,
        second_order_coherence=0.4,
        avg_bigram_pmi=0.1,
        avg_trigram_pmi=0.2,
        avg_bigram_npmi=0.05,
        avg_trigram_npmi=0.07,
    )


@pytest.mark.asyncio
async def test_pipeline_uses_existing_spellcheck_metrics() -> None:
    metrics = SpellcheckMetricsV1(
        total_corrections=3,
        l2_dictionary_corrections=1,
        spellchecker_corrections=2,
        word_count=200,
        correction_density=1.5,
    )

    analyzer = StubNlpAnalyzer(_nlp_metrics())

    pipeline = FeaturePipeline(
        spell_normalizer=None,
        language_tool_client=StubLanguageToolClient(_grammar_analysis()),
        nlp_analyzer=analyzer,
        extractors=[NormalizationFeaturesExtractor(), GrammarOverviewExtractor()],
    )

    result = await pipeline.extract_features(
        normalized_text="the best essay",
        raw_text="the best essay",  # optional, kept for auditing
        spellcheck_metrics=metrics,
        essay_id="essay-123",
        http_session=object(),
        correlation_id=uuid4(),
    )

    assert isinstance(result, FeaturePipelineResult)
    features = result.features

    expected_spelling_rate = ((3 + 2) / 200) * 100
    assert pytest.approx(features["spelling_error_rate_p100w"], rel=1e-6) == expected_spelling_rate
    assert features["aggregated_spelling_error_count"] == 5
    assert features["language_tool_spelling_error_count"] == 2
    assert features["grammar_total_error_count"] == 1

    assert analyzer.calls == 1
    assert analyzer.latest_text == "the best essay"


@pytest.mark.asyncio
async def test_pipeline_falls_back_to_spell_normalizer_when_metrics_absent() -> None:
    normalization_result = SpellNormalizationResult(
        corrected_text="fixed text",
        total_corrections=4,
        l2_dictionary_corrections=1,
        spellchecker_corrections=3,
        word_count=100,
        correction_density=4.0,
    )

    pipeline = FeaturePipeline(
        spell_normalizer=StubSpellNormalizer(normalization_result),
        language_tool_client=None,
        nlp_analyzer=None,
        extractors=[NormalizationFeaturesExtractor()],
    )

    result = await pipeline.extract_features(raw_text="raw text needing fixes")

    assert result.context.normalized_text == "fixed text"
    assert result.context.spellcheck_metrics.total_corrections == 4
    assert "spelling_error_rate_p100w" in result.features


@pytest.mark.asyncio
async def test_feature_toggle_disables_extractor() -> None:
    metrics = SpellcheckMetricsV1(
        total_corrections=0,
        l2_dictionary_corrections=0,
        spellchecker_corrections=0,
        word_count=100,
        correction_density=0.0,
    )

    pipeline = FeaturePipeline(
        spell_normalizer=None,
        language_tool_client=None,
        nlp_analyzer=None,
        extractors=[NormalizationFeaturesExtractor(), GrammarOverviewExtractor()],
        feature_toggles={"grammar_overview": False},
    )

    result = await pipeline.extract_features(
        normalized_text="normalized",
        spellcheck_metrics=metrics,
    )

    assert "grammar_error_rate_p100w" not in result.features
    assert "spelling_error_rate_p100w" in result.features
