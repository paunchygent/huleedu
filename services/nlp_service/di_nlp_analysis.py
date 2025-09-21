"""
NLP Analysis Components Provider.

This provider handles NLP analysis components:
- SpaCy-based NLP analyzer
- Language detection
- Linguistic metrics calculators (Zipf, diversity, complexity)

PROVIDES: NlpAnalyzerProtocol implementation used by
          NlpServiceInfrastructureProvider.provide_feature_pipeline()
"""

from dishka import Provider, Scope, provide

from services.nlp_service.implementations.nlp_analyzer_impl import NlpAnalyzer
from services.nlp_service.implementations.nlp_dependencies import (
    LanguageDetector,
    LexicalDiversityCalculator,
    PhraseologyCalculator,
    SpacyModelLoader,
    SyntacticComplexityCalculator,
    ZipfCalculator,
)
from services.nlp_service.nlp_dependency_protocols import (
    LanguageDetectorProtocol,
    LexicalDiversityCalculatorProtocol,
    PhraseologyCalculatorProtocol,
    SpacyModelLoaderProtocol,
    SyntacticComplexityCalculatorProtocol,
    ZipfCalculatorProtocol,
)
from services.nlp_service.protocols import NlpAnalyzerProtocol


class NlpAnalysisProvider(Provider):
    """Provider for NLP analysis components and dependencies.

    Provides the NlpAnalyzer implementation that performs linguistic
    analysis on text, used by the infrastructure provider's feature pipeline.
    """

    @provide(scope=Scope.APP)
    def provide_spacy_model_loader(self) -> SpacyModelLoaderProtocol:
        """Provide spaCy model loader."""
        return SpacyModelLoader()

    @provide(scope=Scope.APP)
    def provide_language_detector(self) -> LanguageDetectorProtocol:
        """Provide language detector."""
        return LanguageDetector()

    @provide(scope=Scope.APP)
    def provide_zipf_calculator(self) -> ZipfCalculatorProtocol:
        """Provide Zipf frequency calculator."""
        return ZipfCalculator()

    @provide(scope=Scope.APP)
    def provide_lexical_diversity_calculator(self) -> LexicalDiversityCalculatorProtocol:
        """Provide lexical diversity calculator."""
        return LexicalDiversityCalculator()

    @provide(scope=Scope.APP)
    def provide_phraseology_calculator(self) -> PhraseologyCalculatorProtocol:
        """Provide phraseology metrics calculator."""
        return PhraseologyCalculator()

    @provide(scope=Scope.APP)
    def provide_syntactic_complexity_calculator(self) -> SyntacticComplexityCalculatorProtocol:
        """Provide syntactic complexity calculator."""
        return SyntacticComplexityCalculator()

    @provide(scope=Scope.APP)
    def provide_nlp_analyzer(
        self,
        model_loader: SpacyModelLoaderProtocol,
        language_detector: LanguageDetectorProtocol,
        zipf_calculator: ZipfCalculatorProtocol,
        diversity_calculator: LexicalDiversityCalculatorProtocol,
        phraseology_calculator: PhraseologyCalculatorProtocol,
        complexity_calculator: SyntacticComplexityCalculatorProtocol,
    ) -> NlpAnalyzerProtocol:
        """Provide spaCy-based NLP analyzer with injected dependencies."""
        return NlpAnalyzer(
            model_loader=model_loader,
            language_detector=language_detector,
            zipf_calculator=zipf_calculator,
            diversity_calculator=diversity_calculator,
            phraseology_calculator=phraseology_calculator,
            complexity_calculator=complexity_calculator,
        )
