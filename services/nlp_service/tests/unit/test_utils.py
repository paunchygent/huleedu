"""Test utilities for NLP service unit tests.

Following HuleEdu patterns: explicit utilities, no conftest.
"""

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import AsyncMock, MagicMock

from services.nlp_service.nlp_dependency_protocols import (
    LanguageDetectorProtocol,
    LexicalDiversityCalculatorProtocol,
    PhraseologyCalculatorProtocol,
    SpacyModelLoaderProtocol,
    SyntacticComplexityCalculatorProtocol,
    ZipfCalculatorProtocol,
)


def create_mock_spacy_model_loader(
    should_fail: bool = False,
    doc_factory: Callable[[], Any] | None = None,
) -> MagicMock:
    """Create a mock spaCy model loader.

    Args:
        should_fail: If True, raises RuntimeError on load_model
        doc_factory: Optional factory for creating Doc objects

    Returns:
        Mock SpacyModelLoaderProtocol
    """
    mock = MagicMock(spec=SpacyModelLoaderProtocol)

    if should_fail:
        mock.load_model = AsyncMock(side_effect=RuntimeError("Model loading failed"))
        mock.process_text = AsyncMock(side_effect=RuntimeError("Model not loaded"))
    else:
        # Create mock spaCy model
        mock_model = MagicMock()
        mock.load_model = AsyncMock(return_value=mock_model)

        # Create mock Doc
        if doc_factory:
            mock.process_text = AsyncMock(side_effect=doc_factory)
        else:
            mock_doc = create_mock_doc()
            mock.process_text = AsyncMock(return_value=mock_doc)

    return mock


def create_mock_doc(
    tokens: list[str] | None = None,
    sentences: int = 1,
    with_dependency: bool = False,
) -> Any:
    """Create a mock spaCy Doc object.

    Args:
        tokens: List of token texts (defaults to ["hello", "world"])
        sentences: Number of sentences
        with_dependency: If True, add dependency parse info

    Returns:
        Mock Doc object
    """
    if tokens is None:
        tokens = ["hello", "world"]

    mock_doc = MagicMock()

    # Create mock tokens
    mock_tokens: list[Any] = []
    for i, text in enumerate(tokens):
        token = MagicMock()
        token.text = text
        token.is_alpha = text.isalpha()
        token.i = i

        if with_dependency:
            # Simple dependency structure
            token.head = mock_doc if i == 0 else mock_tokens[0]
        else:
            token.head = token  # Self-reference means root

        mock_tokens.append(token)

    # Set up iteration - needs to accept self argument
    mock_doc.__iter__ = lambda self: iter(mock_tokens)

    # Create mock sentences
    mock_sents = []
    tokens_per_sent = len(tokens) // sentences if sentences > 0 else len(tokens)
    for i in range(sentences):
        sent = MagicMock()
        start = i * tokens_per_sent
        end = start + tokens_per_sent if i < sentences - 1 else len(tokens)
        sent.tokens = mock_tokens[start:end]
        mock_sents.append(sent)

    mock_doc.sents = mock_sents

    # Add optional attributes for TextDescriptives
    mock_doc._ = MagicMock()

    return mock_doc


def create_mock_language_detector(
    default_language: str = "en",
    detection_map: dict[str, str] | None = None,
) -> MagicMock:
    """Create a mock language detector.

    Args:
        default_language: Default language to return
        detection_map: Optional mapping of text patterns to languages

    Returns:
        Mock LanguageDetectorProtocol
    """
    mock = MagicMock(spec=LanguageDetectorProtocol)

    if detection_map:

        async def detect(text: str) -> str:
            for pattern, lang in detection_map.items():
                if pattern in text:
                    return lang
            return default_language

        mock.detect = AsyncMock(side_effect=detect)
    else:
        mock.detect = AsyncMock(return_value=default_language)

    return mock


def create_mock_zipf_calculator(
    mean_zipf: float = 0.0,
    percent_below_3: float = 0.0,
    per_token_scores: dict[str, float] | None = None,
) -> MagicMock:
    """Create a mock Zipf calculator.

    Args:
        mean_zipf: Mean Zipf frequency to return
        percent_below_3: Percentage of tokens below threshold
        per_token_scores: Optional per-token Zipf scores

    Returns:
        Mock ZipfCalculatorProtocol
    """
    mock = MagicMock(spec=ZipfCalculatorProtocol)

    if per_token_scores:

        def calc_freq(token: str, _language: str) -> float:
            return per_token_scores.get(token.lower(), 0.0)

        mock.calculate_zipf_frequency = MagicMock(side_effect=calc_freq)

        # Calculate actual metrics from per-token scores
        def calc_metrics(tokens: list[str], _language: str) -> tuple[float, float]:
            scores = [per_token_scores.get(t.lower(), 0.0) for t in tokens]
            if scores:
                import numpy as np

                mean = float(np.mean(scores))
                below_3 = (sum(1 for s in scores if s < 3) / len(scores)) * 100
                return mean, below_3
            return 0.0, 0.0

        mock.calculate_metrics = MagicMock(side_effect=calc_metrics)
    else:
        mock.calculate_zipf_frequency = MagicMock(return_value=0.0)
        mock.calculate_metrics = MagicMock(return_value=(mean_zipf, percent_below_3))

    return mock


def create_mock_diversity_calculator(
    mtld: float = 0.0,
    hdd: float = 0.0,
) -> MagicMock:
    """Create a mock lexical diversity calculator.

    Args:
        mtld: MTLD score to return
        hdd: HDD score to return

    Returns:
        Mock LexicalDiversityCalculatorProtocol
    """
    mock = MagicMock(spec=LexicalDiversityCalculatorProtocol)
    mock.calculate_mtld = MagicMock(return_value=mtld)
    mock.calculate_hdd = MagicMock(return_value=hdd)
    return mock


def create_mock_phraseology_calculator(
    bigram_pmi: float = 0.0,
    trigram_pmi: float = 0.0,
    bigram_npmi: float = 0.0,
    trigram_npmi: float = 0.0,
) -> MagicMock:
    """Create a mock phraseology calculator.

    Args:
        bigram_pmi: Bigram PMI score
        trigram_pmi: Trigram PMI score
        bigram_npmi: Bigram NPMI score
        trigram_npmi: Trigram NPMI score

    Returns:
        Mock PhraseologyCalculatorProtocol
    """
    mock = MagicMock(spec=PhraseologyCalculatorProtocol)
    mock.calculate_pmi_scores = MagicMock(
        return_value=(bigram_pmi, trigram_pmi, bigram_npmi, trigram_npmi)
    )
    return mock


def create_mock_complexity_calculator(
    dependency_distance: float = 0.0,
    first_order_coherence: float = 0.0,
    second_order_coherence: float = 0.0,
) -> MagicMock:
    """Create a mock syntactic complexity calculator.

    Args:
        dependency_distance: Mean dependency distance
        first_order_coherence: First order coherence score
        second_order_coherence: Second order coherence score

    Returns:
        Mock SyntacticComplexityCalculatorProtocol
    """
    mock = MagicMock(spec=SyntacticComplexityCalculatorProtocol)
    mock.calculate_dependency_distance = MagicMock(return_value=dependency_distance)
    mock.calculate_cohesion_scores = MagicMock(
        return_value=(first_order_coherence, second_order_coherence)
    )
    return mock


class NlpAnalyzerTestFixture:
    """Fixture for creating fully configured NLP analyzer with mocked dependencies.

    This follows HuleEdu patterns - explicit test fixture instead of pytest fixtures.
    """

    def __init__(self) -> None:
        """Initialize with default mock dependencies."""
        self.model_loader = create_mock_spacy_model_loader()
        self.language_detector = create_mock_language_detector()
        self.zipf_calculator = create_mock_zipf_calculator()
        self.diversity_calculator = create_mock_diversity_calculator()
        self.phraseology_calculator = create_mock_phraseology_calculator()
        self.complexity_calculator = create_mock_complexity_calculator()

    def with_model_loader(self, model_loader: Any) -> NlpAnalyzerTestFixture:
        """Set custom model loader."""
        self.model_loader = model_loader
        return self

    def with_language_detector(self, detector: Any) -> NlpAnalyzerTestFixture:
        """Set custom language detector."""
        self.language_detector = detector
        return self

    def with_zipf_calculator(self, calculator: Any) -> NlpAnalyzerTestFixture:
        """Set custom Zipf calculator."""
        self.zipf_calculator = calculator
        return self

    def with_diversity_calculator(self, calculator: Any) -> NlpAnalyzerTestFixture:
        """Set custom diversity calculator."""
        self.diversity_calculator = calculator
        return self

    def with_phraseology_calculator(self, calculator: Any) -> NlpAnalyzerTestFixture:
        """Set custom phraseology calculator."""
        self.phraseology_calculator = calculator
        return self

    def with_complexity_calculator(self, calculator: Any) -> NlpAnalyzerTestFixture:
        """Set custom complexity calculator."""
        self.complexity_calculator = calculator
        return self

    def build(self) -> Any:
        """Build the NlpAnalyzer with configured dependencies."""
        from services.nlp_service.implementations.nlp_analyzer_impl import (
            NlpAnalyzer,
        )

        return NlpAnalyzer(
            model_loader=self.model_loader,
            language_detector=self.language_detector,
            zipf_calculator=self.zipf_calculator,
            diversity_calculator=self.diversity_calculator,
            phraseology_calculator=self.phraseology_calculator,
            complexity_calculator=self.complexity_calculator,
        )
