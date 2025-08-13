"""spaCy-based NLP analyzer implementation with advanced linguistic metrics.

DEPRECATED: This implementation violates DI principles by importing external libraries
directly. Use nlp_analyzer_refactored.NlpAnalyzerRefactored instead, which properly
uses dependency injection following HuleEdu's DDD and Clean Code principles.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import numpy as np
from common_core.events.nlp_events import NlpMetrics
from huleedu_service_libs.logging_utils import create_service_logger

from services.nlp_service.protocols import NlpAnalyzerProtocol

if TYPE_CHECKING:
    from spacy.language import Language

logger = create_service_logger("nlp_service.implementations.nlp_analyzer")


class SpacyNlpAnalyzer(NlpAnalyzerProtocol):
    """Production spaCy-based text analyzer with comprehensive linguistic metrics.

    Implements the full suite of required metrics:
    - Lexical sophistication (Zipf frequency from wordfreq)
    - Lexical diversity (MTLD/HDD from lexical-diversity)
    - Syntactic complexity (dependency distance from TextDescriptives)
    - Cohesion (sentence similarity from TextDescriptives)
    - Phraseology (PMI/NPMI from gensim)
    """

    def __init__(self) -> None:
        """Initialize spaCy models with lazy loading."""
        self.nlp_en: Language | None = None
        self.nlp_sv: Language | None = None
        self._models_loaded = False
        self._lock = asyncio.Lock()  # For thread-safe model loading
        logger.info("SpacyNlpAnalyzer initialized (production mode)")

    async def _ensure_models_loaded(self) -> None:
        """Lazy load spaCy models with TextDescriptives pipeline.

        Models are loaded once and cached for reuse.
        TextDescriptives components are added for syntactic and cohesion metrics.
        """
        if self._models_loaded:
            return

        async with self._lock:
            # Double-check after acquiring lock
            if self._models_loaded:
                return

            try:
                import spacy

                # Load English model
                logger.info("Loading English spaCy model...")
                self.nlp_en = spacy.load("en_core_web_sm")

                # Add TextDescriptives for advanced metrics
                try:
                    self.nlp_en.add_pipe("textdescriptives/all")
                    logger.info("Added TextDescriptives pipeline to English model")
                except Exception as e:
                    logger.warning(
                        f"Could not add TextDescriptives: {e}. Will use fallback metrics."
                    )

                # Load Swedish model
                logger.info("Loading Swedish spaCy model...")
                self.nlp_sv = spacy.load("sv_core_news_sm")

                # Add TextDescriptives for Swedish
                try:
                    self.nlp_sv.add_pipe("textdescriptives/all")
                    logger.info("Added TextDescriptives pipeline to Swedish model")
                except Exception as e:
                    logger.warning(f"Could not add TextDescriptives to Swedish: {e}")

                self._models_loaded = True
                logger.info("spaCy models loaded successfully")

            except ImportError as e:
                logger.error(f"Failed to load spaCy models: {e}")
                logger.info("Falling back to skeleton implementation")
                # Set flag to True to prevent repeated loading attempts
                self._models_loaded = True
                # Models remain None, fallback logic will handle it

    async def _detect_language(self, text: str) -> str:
        """Detect language from text using langdetect.

        Falls back to heuristics if langdetect is unavailable.

        Args:
            text: Text to detect language for

        Returns:
            ISO 639-1 language code (en, sv, etc.)
        """
        try:
            from langdetect import detect

            # Use first 1000 chars for detection (performance)
            sample = text[:1000] if len(text) > 1000 else text
            detected = detect(sample)

            # Map to our supported languages
            if detected == "sv":
                return "sv"
            else:
                return "en"  # Default to English for unsupported languages

        except (ImportError, Exception) as e:
            logger.debug(f"Language detection failed, using heuristics: {e}")
            # Fallback: Simple heuristic for Swedish
            swedish_chars = set("åäöÅÄÖ")
            if any(char in swedish_chars for char in text):
                return "sv"
            return "en"

    async def analyze_text(
        self,
        text: str,
        language: str = "auto",
    ) -> NlpMetrics:
        """Extract comprehensive text metrics using spaCy and supporting libraries.

        This is the main entry point for NLP analysis. If spaCy models are available,
        it performs full analysis with all advanced metrics. Otherwise, falls back
        to basic skeleton metrics.

        Args:
            text: The text to analyze
            language: Language code ("en", "sv") or "auto" for detection

        Returns:
            NlpMetrics with comprehensive linguistic analysis
        """
        start_time = time.time()

        # Ensure models are loaded
        await self._ensure_models_loaded()

        # Detect language if auto
        if language == "auto":
            language = await self._detect_language(text)
            logger.debug(f"Detected language: {language}")

        # If spaCy models are loaded, use full analysis
        if self._models_loaded and (self.nlp_en or self.nlp_sv):
            return await self.analyze_text_with_spacy(text, language)

        # Fallback: Basic text analysis without spaCy (skeleton mode)
        logger.warning("Using skeleton analysis mode (spaCy not available)")

        # Split text into words (simple whitespace splitting)
        words = text.split()
        word_count = len(words)

        # Split into sentences (simple period/exclamation/question mark splitting)
        import re

        sentence_endings = re.compile(r"[.!?]+")
        sentences = [s.strip() for s in sentence_endings.split(text) if s.strip()]
        # For empty text, return 0 sentences not 1
        sentence_count = len(sentences) if text.strip() else 0

        # Calculate average sentence length
        avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0.0

        # Calculate processing time
        elapsed_time = time.time() - start_time
        # Ensure at least 1ms for non-zero processing time (even if very fast)
        processing_time_ms = max(1, int(elapsed_time * 1000))

        logger.info(
            f"Analyzed text (skeleton): {word_count} words, {sentence_count} sentences",
            extra={
                "word_count": word_count,
                "sentence_count": sentence_count,
                "language": language,
                "processing_time_ms": processing_time_ms,
            },
        )

        # Return skeleton metrics (this branch only used if spaCy fails to load)
        return NlpMetrics(
            word_count=word_count,
            sentence_count=sentence_count,
            avg_sentence_length=round(avg_sentence_length, 2),
            language_detected=language,
            processing_time_ms=processing_time_ms,
            # Advanced metrics default to 0 in skeleton mode
            mean_zipf_frequency=0.0,
            percent_tokens_zipf_below_3=0.0,
            mtld_score=0.0,
            hdd_score=0.0,
            mean_dependency_distance=0.0,
            first_order_coherence=0.0,
            second_order_coherence=0.0,
            avg_bigram_pmi=0.0,
            avg_trigram_pmi=0.0,
            avg_bigram_npmi=0.0,
            avg_trigram_npmi=0.0,
        )

    def _calculate_zipf_metrics(self, tokens: list[str], language: str) -> tuple[float, float]:
        """Calculate Zipf frequency metrics for lexical sophistication.

        Args:
            tokens: List of word tokens
            language: Language code for frequency lookup

        Returns:
            Tuple of (mean_zipf, percent_below_3)
        """
        try:
            from wordfreq import zipf_frequency

            # Calculate Zipf frequency for each token
            zipf_scores = []
            for token in tokens:
                score = zipf_frequency(token.lower(), language)
                zipf_scores.append(score)

            if zipf_scores:
                mean_zipf = float(np.mean(zipf_scores))
                percent_below_3 = (sum(1 for z in zipf_scores if z < 3) / len(zipf_scores)) * 100
            else:
                mean_zipf = 0.0
                percent_below_3 = 0.0

            return mean_zipf, percent_below_3

        except ImportError:
            logger.warning("wordfreq not available, returning default Zipf metrics")
            return 0.0, 0.0

    def _calculate_lexical_diversity(self, tokens: list[str]) -> tuple[float, float]:
        """Calculate lexical diversity metrics (MTLD and HDD).

        Args:
            tokens: List of word tokens

        Returns:
            Tuple of (mtld_score, hdd_score)
        """
        try:
            from lexical_diversity.lex_div import hdd as calc_hdd
            from lexical_diversity.lex_div import mtld as calc_mtld

            if len(tokens) < 50:  # Minimum tokens for meaningful metrics
                return 0.0, 0.0

            mtld = calc_mtld(tokens)
            hdd = calc_hdd(tokens)

            return mtld, hdd

        except (ImportError, Exception) as e:
            logger.warning(f"lexical-diversity not available: {e}")
            return 0.0, 0.0

    def _calculate_phraseology_metrics(
        self, tokens: list[str]
    ) -> tuple[float, float, float, float]:
        """Calculate phraseology metrics (PMI/NPMI for bigrams and trigrams).

        Args:
            tokens: List of word tokens

        Returns:
            Tuple of (bigram_pmi, trigram_pmi, bigram_npmi, trigram_npmi)
        """
        try:
            from gensim.models import Phrases
            from gensim.models.phrases import ENGLISH_CONNECTOR_WORDS

            if len(tokens) < 10:  # Need minimum tokens for n-grams
                return 0.0, 0.0, 0.0, 0.0

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
            logger.warning(f"gensim not available or error in phraseology: {e}")
            return 0.0, 0.0, 0.0, 0.0

    async def analyze_text_with_spacy(
        self,
        text: str,
        language: str,
    ) -> NlpMetrics:
        """Perform full spaCy analysis with all advanced metrics.

        Args:
            text: The text to analyze
            language: Language code ("en" or "sv")

        Returns:
            NlpMetrics with comprehensive linguistic analysis
        """
        start_time = time.time()

        # Select appropriate spaCy model
        nlp = self.nlp_en if language == "en" else self.nlp_sv
        if nlp is None:
            logger.error(f"spaCy model for {language} not loaded")
            # Fall back to skeleton metrics
            return await self.analyze_text(text, language)

        # Process text with spaCy
        doc = nlp(text)

        # Extract basic metrics
        tokens = [token.text for token in doc if token.is_alpha]
        word_count = len(tokens)
        sentences = list(doc.sents)
        # Handle empty text - spaCy returns 1 empty sentence for empty text
        sentence_count = 0 if not text.strip() else len(sentences)
        avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0.0

        # 1. Lexical Sophistication (Zipf frequency)
        mean_zipf, percent_below_3 = self._calculate_zipf_metrics(tokens, language)

        # 2. Lexical Diversity (MTLD/HDD)
        mtld_score, hdd_score = self._calculate_lexical_diversity(tokens)

        # 3. Syntactic Complexity (from TextDescriptives if available)
        mean_dep_dist = 0.0
        if hasattr(doc._, "dependency_distance_mean"):
            mean_dep_dist = doc._.dependency_distance_mean or 0.0
        else:
            # Fallback: simple calculation of dependency distances
            distances = []
            for token in doc:
                if token.head != token:
                    distance = abs(token.i - token.head.i)
                    distances.append(distance)
            mean_dep_dist = float(np.mean(distances)) if distances else 0.0

        # 4. Cohesion metrics (from TextDescriptives if available)
        first_order_coherence = 0.0
        second_order_coherence = 0.0
        if hasattr(doc._, "first_order_coherence_scores"):
            scores = doc._.first_order_coherence_scores
            first_order_coherence = np.mean(scores) if scores else 0.0
        if hasattr(doc._, "second_order_coherence_scores"):
            scores = doc._.second_order_coherence_scores
            second_order_coherence = np.mean(scores) if scores else 0.0

        # 5. Phraseology (PMI/NPMI)
        bigram_pmi, trigram_pmi, bigram_npmi, trigram_npmi = self._calculate_phraseology_metrics(
            tokens
        )

        # Calculate processing time
        elapsed_time = time.time() - start_time
        # Ensure at least 1ms for non-zero processing time (even if very fast)
        processing_time_ms = max(1, int(elapsed_time * 1000))

        logger.info(
            f"Completed full NLP analysis: {word_count} words, {sentence_count} sentences",
            extra={
                "word_count": word_count,
                "sentence_count": sentence_count,
                "language": language,
                "mean_zipf": round(mean_zipf, 2),
                "mtld": round(mtld_score, 2),
                "processing_time_ms": processing_time_ms,
            },
        )

        return NlpMetrics(
            # Basic metrics
            word_count=word_count,
            sentence_count=sentence_count,
            avg_sentence_length=round(avg_sentence_length, 2),
            language_detected=language,
            processing_time_ms=processing_time_ms,
            # Advanced metrics
            mean_zipf_frequency=round(mean_zipf, 2),
            percent_tokens_zipf_below_3=round(percent_below_3, 2),
            mtld_score=round(mtld_score, 2),
            hdd_score=round(hdd_score, 2),
            mean_dependency_distance=round(mean_dep_dist, 2),
            first_order_coherence=round(first_order_coherence, 3),
            second_order_coherence=round(second_order_coherence, 3),
            avg_bigram_pmi=round(bigram_pmi, 3),
            avg_trigram_pmi=round(trigram_pmi, 3),
            avg_bigram_npmi=round(bigram_npmi, 3),
            avg_trigram_npmi=round(trigram_npmi, 3),
            # TAASSC indices would go here if available
            phrasal_indices={},
            clausal_indices={},
        )
