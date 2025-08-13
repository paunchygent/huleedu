"""Dependency injection configuration for NLP analyzer dependencies.

Separated from main di.py to avoid monolithic file and maintain clear separation.
"""

from dishka import Provider, Scope, provide

from services.nlp_service.implementations.nlp_analyzer_refactored import NlpAnalyzerRefactored
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


class NlpDependencyProvider(Provider):
    """Provider for NLP analyzer dependencies.
    
    This is separate from the main NlpServiceProvider to maintain
    separation of concerns and avoid a monolithic DI configuration.
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
        return NlpAnalyzerRefactored(
            model_loader=model_loader,
            language_detector=language_detector,
            zipf_calculator=zipf_calculator,
            diversity_calculator=diversity_calculator,
            phraseology_calculator=phraseology_calculator,
            complexity_calculator=complexity_calculator,
        )