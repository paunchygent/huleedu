"""Shared context object passed to feature extractors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Mapping, MutableMapping
from uuid import UUID

from common_core.events.nlp_events import GrammarAnalysis, NlpMetrics
from common_core.events.spellcheck_models import SpellcheckMetricsV1

from huleedu_nlp_shared.normalization.models import SpellNormalizationResult

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from aiohttp import ClientSession
    from spacy.tokens import Doc
else:  # pragma: no cover - runtime fallback
    ClientSession = Any  # type: ignore[assignment]
    Doc = Any  # type: ignore[assignment]


@dataclass(slots=True)
class FeatureContext:
    """Canonical feature extraction context shared across bundles.

    The context centralises spellcheck metrics, normalized text, analyzer output,
    and any additional metadata so individual extractors remain stateless.
    """

    normalized_text: str
    spellcheck_metrics: SpellcheckMetricsV1
    raw_text: str | None = None
    prompt_text: str | None = None
    prompt_id: str | None = None
    essay_id: str | None = None
    batch_id: str | None = None
    cefr_code: str | None = None
    cefr_label: str | None = None
    metadata: MutableMapping[str, Any] = field(default_factory=dict)
    correlation_id: UUID | None = None
    language: str = "auto"
    http_session: ClientSession | None = None
    feature_toggles: Mapping[str, bool] | None = None

    normalization_result: SpellNormalizationResult | None = None
    grammar_analysis: GrammarAnalysis | None = None
    nlp_metrics: NlpMetrics | None = None

    _spacy_doc_loader: Callable[[], Awaitable[Doc]] | None = None
    _spacy_doc: Doc | None = field(default=None, init=False)

    _embedding_loader: Callable[[], Awaitable[Any]] | None = None
    _embeddings: Any | None = field(default=None, init=False)

    def set_spacy_doc_loader(self, loader: Callable[[], Awaitable[Doc]]) -> None:
        """Register a lazy loader for spaCy documents."""

        self._spacy_doc_loader = loader

    async def get_spacy_doc(self) -> Doc:
        """Return cached spaCy doc, invoking loader on demand."""

        if self._spacy_doc is None:
            if self._spacy_doc_loader is None:
                raise RuntimeError("spaCy document loader has not been configured")
            self._spacy_doc = await self._spacy_doc_loader()
        return self._spacy_doc

    def set_embedding_loader(self, loader: Callable[[], Awaitable[Any]]) -> None:
        """Register a lazy loader for embedding computations."""

        self._embedding_loader = loader

    async def get_embeddings(self) -> Any:
        """Return cached embeddings, invoking loader on demand."""

        if self._embeddings is None:
            if self._embedding_loader is None:
                raise RuntimeError("Embedding loader has not been configured")
            self._embeddings = await self._embedding_loader()
        return self._embeddings

    @property
    def word_count(self) -> int:
        """Word count from the spellcheck metrics."""

        return self.spellcheck_metrics.word_count

    @property
    def total_spell_corrections(self) -> int:
        """Total corrections recorded during spellcheck."""

        return self.spellcheck_metrics.total_corrections

    @property
    def l2_corrections(self) -> int:
        """Corrections originating from L2 learner dictionary."""

        return self.spellcheck_metrics.l2_dictionary_corrections

    @property
    def spellchecker_corrections(self) -> int:
        """Corrections originating from PySpellChecker."""

        return self.spellcheck_metrics.spellchecker_corrections

    @property
    def correction_density(self) -> float:
        """Corrections per 100 words captured during spellcheck."""

        return self.spellcheck_metrics.correction_density

    def is_feature_enabled(self, extractor_name: str) -> bool:
        """Return False when a feature extractor is toggled off."""

        if not self.feature_toggles:
            return True
        return self.feature_toggles.get(extractor_name, True)
