"""Implementation classes for NLP dependency protocols."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import numpy as np
from huleedu_service_libs.logging_utils import create_service_logger

from services.nlp_service.nlp_dependency_protocols import (
    LanguageDetectorProtocol,
    LexicalDiversityCalculatorProtocol,
    PhraseologyCalculatorProtocol,
    SpacyModelLoaderProtocol,
    SyntacticComplexityCalculatorProtocol,
    ZipfCalculatorProtocol,
)

if TYPE_CHECKING:
    from spacy.language import Language
    from spacy.tokens import Doc

logger = create_service_logger("nlp_service.implementations.nlp_dependencies")


class SpacyModelLoader(SpacyModelLoaderProtocol):
    """Manages spaCy model loading and caching."""

    def __init__(self) -> None:
        """Initialize the model loader."""
        self._models: dict[str, Language] = {}
        self._lock = asyncio.Lock()

    async def load_model(self, language: str) -> Language:
        """Load and cache a spaCy model.

        Args:
            language: Language code ("en" or "sv")

        Returns:
            Loaded spaCy Language model

        Raises:
            ValueError: If language is not supported
            RuntimeError: If model cannot be loaded
        """
        if language not in ["en", "sv"]:
            raise ValueError(f"Unsupported language: {language}")

        async with self._lock:
            if language in self._models:
                return self._models[language]

            try:
                import spacy

                model_name = "en_core_web_sm" if language == "en" else "sv_core_news_sm"
                logger.info(f"Loading spaCy model: {model_name}")

                model = spacy.load(model_name)

                # Try to add TextDescriptives for advanced metrics
                try:
                    model.add_pipe("textdescriptives/all")
                    logger.info(f"Added TextDescriptives to {language} model")
                except Exception as e:
                    logger.warning(f"Could not add TextDescriptives: {e}")

                self._models[language] = model
                return model

            except Exception as e:
                logger.error(f"Failed to load spaCy model for {language}: {e}")
                raise RuntimeError(f"Cannot load spaCy model for {language}") from e

    async def process_text(self, text: str, language: str) -> Doc:
        """Process text with the appropriate spaCy model.

        Args:
            text: Text to process
            language: Language code ("en" or "sv")

        Returns:
            Processed spaCy Doc object
        """
        model = await self.load_model(language)
        return model(text)


class LanguageDetector(LanguageDetectorProtocol):
    """Detects language using langdetect with fallback heuristics."""

    async def detect(self, text: str) -> str:
        """Detect the language of the given text.

        Args:
            text: Text to analyze

        Returns:
            ISO 639-1 language code (e.g., "en", "sv")
        """
        try:
            from langdetect import detect

            # Use first 1000 chars for detection (performance)
            sample = text[:1000] if len(text) > 1000 else text
            detected = detect(sample)

            # Map to supported languages
            if detected == "sv":
                return "sv"
            else:
                return "en"  # Default to English

        except (ImportError, Exception) as e:
            logger.debug(f"Language detection failed, using heuristics: {e}")
            # Fallback: Simple heuristic for Swedish
            swedish_chars = set("åäöÅÄÖ")
            if any(char in swedish_chars for char in text):
                return "sv"
            return "en"


class ZipfCalculator(ZipfCalculatorProtocol):
    """Calculates Zipf frequency metrics for lexical sophistication."""

    def calculate_zipf_frequency(self, token: str, language: str) -> float:
        """Calculate Zipf frequency for a single token.

        Args:
            token: Word token
            language: Language code

        Returns:
            Zipf frequency score (0-7 scale typically)
        """
        try:
            from wordfreq import zipf_frequency

            return zipf_frequency(token.lower(), language)
        except ImportError:
            logger.warning("wordfreq not available")
            return 0.0

    def calculate_metrics(self, tokens: list[str], language: str) -> tuple[float, float]:
        """Calculate aggregate Zipf metrics for tokens.

        Args:
            tokens: List of word tokens
            language: Language code

        Returns:
            Tuple of (mean_zipf_frequency, percent_below_threshold)
        """
        if not tokens:
            return 0.0, 0.0

        try:
            from wordfreq import zipf_frequency

            zipf_scores = [zipf_frequency(token.lower(), language) for token in tokens]

            mean_zipf = float(np.mean(zipf_scores))
            percent_below_3 = (sum(1 for z in zipf_scores if z < 3) / len(zipf_scores)) * 100

            return mean_zipf, percent_below_3

        except ImportError:
            logger.warning("wordfreq not available")
            return 0.0, 0.0


class LexicalDiversityCalculator(LexicalDiversityCalculatorProtocol):
    """Calculates lexical diversity metrics (MTLD/HDD)."""

    def calculate_mtld(self, tokens: list[str]) -> float:
        """Calculate Measure of Textual Lexical Diversity.

        Args:
            tokens: List of word tokens

        Returns:
            MTLD score (higher = more diverse)
        """
        if len(tokens) < 50:  # Minimum for meaningful metrics
            return 0.0

        try:
            from lexical_diversity.lex_div import mtld

            return float(mtld(tokens))
        except (ImportError, Exception) as e:
            logger.warning(f"MTLD calculation failed: {e}")
            return 0.0

    def calculate_hdd(self, tokens: list[str]) -> float:
        """Calculate Hypergeometric Distribution D.

        Args:
            tokens: List of word tokens

        Returns:
            HDD score (0-1 scale, higher = more diverse)
        """
        if len(tokens) < 50:  # Minimum for meaningful metrics
            return 0.0

        try:
            from lexical_diversity.lex_div import hdd

            return float(hdd(tokens))
        except (ImportError, Exception) as e:
            logger.warning(f"HDD calculation failed: {e}")
            return 0.0


class PhraseologyCalculator(PhraseologyCalculatorProtocol):
    """Calculates phraseology metrics using gensim."""

    def calculate_pmi_scores(self, tokens: list[str]) -> tuple[float, float, float, float]:
        """Calculate PMI/NPMI scores for bigrams and trigrams.

        Args:
            tokens: List of word tokens

        Returns:
            Tuple of (bigram_pmi, trigram_pmi, bigram_npmi, trigram_npmi)
        """
        if len(tokens) < 10:  # Need minimum tokens for n-grams
            return 0.0, 0.0, 0.0, 0.0

        try:
            from gensim.models import Phrases
            from gensim.models.phrases import ENGLISH_CONNECTOR_WORDS

            # Prepare sentences (treat whole text as one sentence for now)
            sentences = [tokens]

            # Calculate bigram scores
            bigram_model = Phrases(
                sentences,
                min_count=1,
                threshold=1,
                connector_words=ENGLISH_CONNECTOR_WORDS,
                scoring="npmi",  # Use NPMI scoring
            )

            # Extract bigram scores
            bigram_scores = []
            for scored_bigram in bigram_model.find_phrases(sentences).items():
                bigram_scores.append(scored_bigram[1])  # Get the score

            # Calculate trigram scores (build on bigrams)
            bigram_sentences = [list(bigram_model[sentence]) for sentence in sentences]
            trigram_model = Phrases(
                bigram_sentences,
                min_count=1,
                threshold=1,
                connector_words=ENGLISH_CONNECTOR_WORDS,
                scoring="npmi",
            )

            trigram_scores = []
            for scored_trigram in trigram_model.find_phrases(bigram_sentences).items():
                trigram_scores.append(scored_trigram[1])

            # Calculate averages
            avg_bigram_npmi = float(np.mean(bigram_scores)) if bigram_scores else 0.0
            avg_trigram_npmi = float(np.mean(trigram_scores)) if trigram_scores else 0.0

            # PMI is approximately NPMI * log(vocab_size) - simplified here
            avg_bigram_pmi = avg_bigram_npmi * 10 if avg_bigram_npmi else 0.0
            avg_trigram_pmi = avg_trigram_npmi * 10 if avg_trigram_npmi else 0.0

            return avg_bigram_pmi, avg_trigram_pmi, avg_bigram_npmi, avg_trigram_npmi

        except (ImportError, Exception) as e:
            logger.warning(f"Phraseology calculation failed: {e}")
            return 0.0, 0.0, 0.0, 0.0


class SyntacticComplexityCalculator(SyntacticComplexityCalculatorProtocol):
    """Calculates syntactic complexity and cohesion metrics."""

    def calculate_dependency_distance(self, doc: Doc) -> float:
        """Calculate mean dependency distance.

        Args:
            doc: Processed spaCy Doc

        Returns:
            Mean dependency distance
        """
        # Check if TextDescriptives provided the metric
        if hasattr(doc._, "dependency_distance_mean"):
            return doc._.dependency_distance_mean or 0.0

        # Fallback: simple calculation
        distances = []
        for token in doc:
            if token.head != token:
                distance = abs(token.i - token.head.i)
                distances.append(distance)

        return float(np.mean(distances)) if distances else 0.0

    def calculate_cohesion_scores(self, doc: Doc) -> tuple[float, float]:
        """Calculate cohesion scores.

        Args:
            doc: Processed spaCy Doc

        Returns:
            Tuple of (first_order_coherence, second_order_coherence)
        """
        first_order = 0.0
        second_order = 0.0

        # Check if TextDescriptives provided metrics
        if hasattr(doc._, "first_order_coherence_scores"):
            scores = doc._.first_order_coherence_scores
            if scores:
                first_order = float(np.mean(scores))

        if hasattr(doc._, "second_order_coherence_scores"):
            scores = doc._.second_order_coherence_scores
            if scores:
                second_order = float(np.mean(scores))

        return first_order, second_order
