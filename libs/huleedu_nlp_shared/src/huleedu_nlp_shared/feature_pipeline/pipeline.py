"""Concrete feature pipeline implementation shared across services/tools."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Mapping, MutableMapping, Protocol, Sequence
from uuid import UUID

from common_core.events.nlp_events import GrammarAnalysis, NlpMetrics
from common_core.events.spellcheck_models import SpellcheckMetricsV1

from huleedu_nlp_shared.feature_pipeline.feature_context import FeatureContext
from huleedu_nlp_shared.feature_pipeline.protocols import (
    FeatureExtractorProtocol,
    FeaturePipelineProtocol,
    FeaturePipelineResult,
    FeatureValue,
    ensure_correlation_id,
)
from huleedu_nlp_shared.normalization import SpellNormalizer
from huleedu_nlp_shared.normalization.models import SpellNormalizationResult

if TYPE_CHECKING:  # pragma: no cover - typing only
    from aiohttp import ClientSession
else:  # pragma: no cover - runtime fallback
    ClientSession = Any  # type: ignore[assignment]


class LanguageToolClientLike(Protocol):
    """Subset of Language Tool client behaviours used by the pipeline."""

    async def check_grammar(
        self,
        text: str,
        http_session: ClientSession,
        correlation_id: UUID,
        language: str = "auto",
    ) -> GrammarAnalysis:
        """Return grammar analysis for the supplied text."""


class NlpAnalyzerLike(Protocol):
    """Subset of NLP analyzer behaviours used by the pipeline."""

    async def analyze_text(self, text: str, language: str = "auto") -> NlpMetrics:
        """Return NLP metrics for the supplied text."""


class FeaturePipeline(FeaturePipelineProtocol):
    """Shared implementation orchestrating feature extraction bundles."""

    def __init__(
        self,
        *,
        spell_normalizer: SpellNormalizer | None = None,
        language_tool_client: LanguageToolClientLike | None = None,
        nlp_analyzer: NlpAnalyzerLike | None = None,
        extractors: Sequence[FeatureExtractorProtocol] | None = None,
        feature_toggles: Mapping[str, bool] | None = None,
    ) -> None:
        self._spell_normalizer = spell_normalizer
        self._language_tool_client = language_tool_client
        self._nlp_analyzer = nlp_analyzer
        self._extractors: list[FeatureExtractorProtocol] = []
        self._feature_toggles: MutableMapping[str, bool] = dict(feature_toggles or {})

        if extractors:
            for extractor in extractors:
                self.register_extractor(extractor)

    async def extract_features(
        self,
        *,
        normalized_text: str | None = None,
        raw_text: str | None = None,
        spellcheck_metrics: SpellcheckMetricsV1 | None = None,
        prompt_text: str | None = None,
        prompt_id: str | None = None,
        essay_id: str | None = None,
        batch_id: str | None = None,
        language: str = "auto",
        http_session: ClientSession | None = None,
        correlation_id: UUID | None = None,
        metadata: Mapping[str, Any] | None = None,
        cefr_code: str | None = None,
        cefr_label: str | None = None,
    ) -> FeaturePipelineResult:
        resolved_correlation_id = ensure_correlation_id(correlation_id)

        normalization_result: SpellNormalizationResult | None = None
        if normalized_text is None or spellcheck_metrics is None:
            normalization_result = await self._resolve_normalization(
                raw_text=raw_text,
                essay_id=essay_id,
                language=language,
                correlation_id=resolved_correlation_id,
            )
            if normalization_result is None:
                raise ValueError(
                    "FeaturePipeline requires either (normalized_text + spellcheck_metrics) "
                    "or a SpellNormalizer with raw_text to compute them."
                )
            normalized_text = normalization_result.corrected_text
            spellcheck_metrics = _metrics_from_result(normalization_result)

        context = FeatureContext(
            normalized_text=normalized_text,
            spellcheck_metrics=spellcheck_metrics,
            raw_text=raw_text,
            prompt_text=prompt_text,
            prompt_id=prompt_id,
            essay_id=essay_id,
            batch_id=batch_id,
            cefr_code=cefr_code,
            cefr_label=cefr_label,
            metadata=dict(metadata or {}),
            correlation_id=resolved_correlation_id,
            language=language,
            http_session=http_session,
            feature_toggles=self._feature_toggles.copy(),
            normalization_result=normalization_result,
        )

        if self._language_tool_client is not None:
            if http_session is None:
                raise ValueError(
                    "FeaturePipeline requires an aiohttp.ClientSession when using a "
                    "LanguageTool client"
                )
            context.grammar_analysis = await self._language_tool_client.check_grammar(
                text=normalized_text,
                http_session=http_session,
                correlation_id=resolved_correlation_id,
                language=language,
            )

        if self._nlp_analyzer is not None:
            context.nlp_metrics = await self._nlp_analyzer.analyze_text(
                text=normalized_text,
                language=language,
            )

        features: MutableMapping[str, FeatureValue] = OrderedDict()
        for extractor in self._extractors:
            if not context.is_feature_enabled(extractor.name):
                continue
            extractor_features = await extractor.extract(context)
            for key, value in extractor_features.items():
                if key in features:
                    raise ValueError(
                        f"Duplicate feature name '{key}' produced by extractor '{extractor.name}'"
                    )
                features[key] = value

        return FeaturePipelineResult(features=dict(features), context=context)

    def register_extractor(self, extractor: FeatureExtractorProtocol) -> None:
        """Register an extractor in deterministic order."""

        if any(existing.name == extractor.name for existing in self._extractors):
            raise ValueError(f"Extractor with name '{extractor.name}' already registered")
        self._extractors.append(extractor)

    def with_feature_toggle(self, extractor_name: str, enabled: bool) -> None:
        """Set a feature toggle for a given extractor."""

        self._feature_toggles[extractor_name] = enabled

    async def _resolve_normalization(
        self,
        *,
        raw_text: str | None,
        essay_id: str | None,
        language: str,
        correlation_id: UUID,
    ) -> SpellNormalizationResult | None:
        if self._spell_normalizer is None or raw_text is None:
            return None
        return await self._spell_normalizer.normalize_text(
            text=raw_text,
            essay_id=essay_id,
            language=language,
            correlation_id=correlation_id,
        )

    @property
    def extractors(self) -> Sequence[FeatureExtractorProtocol]:
        """Expose registered extractors for inspection/testing."""

        return tuple(self._extractors)


def _metrics_from_result(result: SpellNormalizationResult) -> SpellcheckMetricsV1:
    """Convert SpellNormalizationResult into SpellcheckMetricsV1."""

    return SpellcheckMetricsV1(
        total_corrections=result.total_corrections,
        l2_dictionary_corrections=result.l2_dictionary_corrections,
        spellchecker_corrections=result.spellchecker_corrections,
        word_count=result.word_count,
        correction_density=result.correction_density,
    )
