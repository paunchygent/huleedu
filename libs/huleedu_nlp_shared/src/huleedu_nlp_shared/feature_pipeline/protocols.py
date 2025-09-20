"""Protocols for feature pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable
from uuid import UUID, uuid4

from common_core.events.spellcheck_models import SpellcheckMetricsV1

from huleedu_nlp_shared.feature_pipeline.feature_context import FeatureContext
from huleedu_nlp_shared.normalization.models import SpellNormalizationResult

FeatureValue = float | int | str
FeatureMap = Mapping[str, FeatureValue]


@dataclass(slots=True)
class FeaturePipelineResult:
    """Bundle of extracted features and the shared context."""

    features: dict[str, FeatureValue]
    context: FeatureContext


@dataclass(slots=True)
class ExistingNormalizationPayload:
    """Information produced by the spellcheck phase."""

    normalized_text: str
    metrics: SpellcheckMetricsV1

    normalization_result: SpellNormalizationResult | None = None


@runtime_checkable
class FeatureExtractorProtocol(Protocol):
    """Interface implemented by feature bundles."""

    name: str

    async def extract(self, context: FeatureContext) -> FeatureMap:
        """Return a mapping of feature name to value."""


@runtime_checkable
class FeaturePipelineProtocol(Protocol):
    """Orchestrates feature extraction across registered bundles."""

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
        http_session: Any | None = None,
        correlation_id: UUID | None = None,
        metadata: Mapping[str, Any] | None = None,
        cefr_code: str | None = None,
        cefr_label: str | None = None,
    ) -> FeaturePipelineResult:
        """Extract features from the supplied text artefacts."""

    def register_extractor(self, extractor: FeatureExtractorProtocol) -> None:
        """Register a feature extractor instance."""

    def with_feature_toggle(self, extractor_name: str, enabled: bool) -> None:
        """Enable or disable an extractor by name."""


def ensure_correlation_id(value: UUID | None) -> UUID:
    """Return existing correlation id or generate a new one."""

    return value or uuid4()
