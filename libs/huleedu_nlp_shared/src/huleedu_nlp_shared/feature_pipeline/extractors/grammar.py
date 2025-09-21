"""Grammar overview feature extractor."""

from __future__ import annotations

from collections.abc import Mapping

from huleedu_nlp_shared.feature_pipeline.feature_context import FeatureContext
from huleedu_nlp_shared.feature_pipeline.protocols import FeatureExtractorProtocol, FeatureValue


class GrammarOverviewExtractor(FeatureExtractorProtocol):
    """Summarise non-spelling grammar errors for scaffolding purposes."""

    name = "grammar_overview"

    async def extract(self, context: FeatureContext) -> Mapping[str, FeatureValue]:
        analysis = context.grammar_analysis
        if analysis is None or context.word_count <= 0:
            return {
                "grammar_error_rate_p100w": 0.0,
                "grammar_total_error_count": 0,
            }

        non_spelling_errors = sum(
            1 for error in analysis.errors if error.category.upper() != "SPELLING"
        )
        rate = (non_spelling_errors / context.word_count) * 100 if context.word_count > 0 else 0.0

        return {
            "grammar_error_rate_p100w": float(rate),
            "grammar_total_error_count": non_spelling_errors,
        }
