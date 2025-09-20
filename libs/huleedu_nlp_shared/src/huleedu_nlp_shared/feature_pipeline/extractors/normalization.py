"""Feature extractor aggregating spellcheck metrics."""

from __future__ import annotations

from collections.abc import Mapping

from common_core.events.nlp_events import GrammarAnalysis

from huleedu_nlp_shared.feature_pipeline.feature_context import FeatureContext
from huleedu_nlp_shared.feature_pipeline.protocols import FeatureExtractorProtocol, FeatureValue


class NormalizationFeaturesExtractor(FeatureExtractorProtocol):
    """Aggregate spelling errors across spellcheck and grammar analysis results."""

    name = "normalization"

    async def extract(self, context: FeatureContext) -> Mapping[str, FeatureValue]:
        lt_spelling_errors = _count_spelling_errors(context.grammar_analysis)
        total_spelling_errors = context.total_spell_corrections + lt_spelling_errors

        word_count = context.word_count
        spelling_rate = 0.0
        if word_count > 0:
            spelling_rate = (total_spelling_errors / word_count) * 100

        return {
            "spelling_error_rate_p100w": float(spelling_rate),
            "aggregated_spelling_error_count": total_spelling_errors,
            "spell_normalizer_total_corrections": context.total_spell_corrections,
            "spell_normalizer_l2_corrections": context.l2_corrections,
            "spell_normalizer_spellchecker_corrections": context.spellchecker_corrections,
            "spell_normalizer_correction_density_p100w": float(context.correction_density),
            "language_tool_spelling_error_count": lt_spelling_errors,
        }


def _count_spelling_errors(analysis: GrammarAnalysis | None) -> int:
    """Count Language Tool errors classified as spelling issues."""

    if analysis is None:
        return 0
    return sum(1 for error in analysis.errors if error.category.upper() == "SPELLING")
