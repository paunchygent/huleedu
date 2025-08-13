"""Refactored spaCy-based NLP analyzer with proper dependency injection."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from common_core.events.nlp_events import NlpMetrics
from huleedu_service_libs.logging_utils import create_service_logger

from services.nlp_service.protocols import NlpAnalyzerProtocol
from services.nlp_service.nlp_dependency_protocols import (
    LanguageDetectorProtocol,
    LexicalDiversityCalculatorProtocol,
    PhraseologyCalculatorProtocol,
    SpacyModelLoaderProtocol,
    SyntacticComplexityCalculatorProtocol,
    ZipfCalculatorProtocol,
)

if TYPE_CHECKING:
    from spacy.tokens import Doc

logger = create_service_logger("nlp_service.implementations.nlp_analyzer")


class NlpAnalyzerRefactored(NlpAnalyzerProtocol):
    """Production spaCy-based text analyzer with comprehensive linguistic metrics.
    
    Uses dependency injection for all external dependencies, following
    HuleEdu's DDD and Clean Code principles.
    """

    def __init__(
        self,
        model_loader: SpacyModelLoaderProtocol,
        language_detector: LanguageDetectorProtocol,
        zipf_calculator: ZipfCalculatorProtocol,
        diversity_calculator: LexicalDiversityCalculatorProtocol,
        phraseology_calculator: PhraseologyCalculatorProtocol,
        complexity_calculator: SyntacticComplexityCalculatorProtocol,
    ) -> None:
        """Initialize with injected dependencies.
        
        Args:
            model_loader: Manages spaCy model loading
            language_detector: Detects text language
            zipf_calculator: Calculates Zipf frequency metrics
            diversity_calculator: Calculates lexical diversity metrics
            phraseology_calculator: Calculates phraseology metrics
            complexity_calculator: Calculates syntactic complexity metrics
        """
        self.model_loader = model_loader
        self.language_detector = language_detector
        self.zipf_calculator = zipf_calculator
        self.diversity_calculator = diversity_calculator
        self.phraseology_calculator = phraseology_calculator
        self.complexity_calculator = complexity_calculator
        logger.info("SpacyNlpAnalyzer initialized with dependency injection")

    async def analyze_text(
        self,
        text: str,
        language: str = "auto",
    ) -> NlpMetrics:
        """Extract comprehensive text metrics using spaCy and supporting libraries.
        
        Args:
            text: The text to analyze
            language: Language code ("en", "sv") or "auto" for detection
            
        Returns:
            NlpMetrics with comprehensive linguistic analysis
        """
        start_time = time.time()
        
        # Handle empty text
        if not text.strip():
            processing_time_ms = max(1, int((time.time() - start_time) * 1000))
            return NlpMetrics(
                word_count=0,
                sentence_count=0,
                avg_sentence_length=0.0,
                language_detected="en",  # Default
                processing_time_ms=processing_time_ms,
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
        
        # Detect language if auto
        if language == "auto":
            language = await self.language_detector.detect(text)
            logger.debug(f"Detected language: {language}")
        
        try:
            # Process text with spaCy
            doc = await self.model_loader.process_text(text, language)
            return await self._analyze_with_spacy(doc, text, language, start_time)
            
        except RuntimeError as e:
            # Fallback to skeleton mode if spaCy fails
            logger.warning(f"spaCy processing failed, using skeleton mode: {e}")
            return self._analyze_skeleton(text, language, start_time)

    async def _analyze_with_spacy(
        self,
        doc: Doc,
        text: str,
        language: str,
        start_time: float,
    ) -> NlpMetrics:
        """Perform full spaCy analysis with all advanced metrics.
        
        Args:
            doc: Processed spaCy Doc
            text: Original text
            language: Language code
            start_time: Analysis start time
            
        Returns:
            NlpMetrics with comprehensive analysis
        """
        # Extract basic metrics
        tokens = [token.text for token in doc if token.is_alpha]
        word_count = len(tokens)
        sentences = list(doc.sents)
        # Handle empty text - spaCy returns 1 empty sentence for empty text
        sentence_count = 0 if not text.strip() else len(sentences)
        avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0.0
        
        # Calculate advanced metrics using injected dependencies
        mean_zipf, percent_below_3 = self.zipf_calculator.calculate_metrics(tokens, language)
        mtld_score = self.diversity_calculator.calculate_mtld(tokens)
        hdd_score = self.diversity_calculator.calculate_hdd(tokens)
        
        bigram_pmi, trigram_pmi, bigram_npmi, trigram_npmi = (
            self.phraseology_calculator.calculate_pmi_scores(tokens)
        )
        
        mean_dep_dist = self.complexity_calculator.calculate_dependency_distance(doc)
        first_order, second_order = self.complexity_calculator.calculate_cohesion_scores(doc)
        
        # Calculate processing time
        processing_time_ms = max(1, int((time.time() - start_time) * 1000))
        
        logger.info(
            f"Completed full NLP analysis: {word_count} words, {sentence_count} sentences",
            extra={
                "word_count": word_count,
                "sentence_count": sentence_count,
                "language": language,
                "mean_zipf": mean_zipf,
                "mtld": mtld_score,
                "processing_time_ms": processing_time_ms,
            },
        )
        
        return NlpMetrics(
            word_count=word_count,
            sentence_count=sentence_count,
            avg_sentence_length=round(avg_sentence_length, 2),
            language_detected=language,
            processing_time_ms=processing_time_ms,
            mean_zipf_frequency=round(mean_zipf, 2),
            percent_tokens_zipf_below_3=round(percent_below_3, 2),
            mtld_score=round(mtld_score, 2),
            hdd_score=round(hdd_score, 2),
            mean_dependency_distance=round(mean_dep_dist, 2),
            first_order_coherence=round(first_order, 2),
            second_order_coherence=round(second_order, 2),
            avg_bigram_pmi=round(bigram_pmi, 2),
            avg_trigram_pmi=round(trigram_pmi, 2),
            avg_bigram_npmi=round(bigram_npmi, 2),
            avg_trigram_npmi=round(trigram_npmi, 2),
        )

    def _analyze_skeleton(
        self,
        text: str,
        language: str,
        start_time: float,
    ) -> NlpMetrics:
        """Basic text analysis without spaCy (skeleton mode).
        
        Args:
            text: Text to analyze
            language: Language code
            start_time: Analysis start time
            
        Returns:
            NlpMetrics with basic metrics only
        """
        # Split text into words (simple whitespace splitting)
        words = text.split()
        word_count = len(words)
        
        # Split into sentences (simple period/exclamation/question mark splitting)
        import re
        sentence_endings = re.compile(r'[.!?]+')
        sentences = [s.strip() for s in sentence_endings.split(text) if s.strip()]
        # For empty text, return 0 sentences not 1
        sentence_count = len(sentences) if text.strip() else 0
        
        # Calculate average sentence length
        avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0.0
        
        # Calculate processing time
        processing_time_ms = max(1, int((time.time() - start_time) * 1000))
        
        logger.info(
            f"Analyzed text (skeleton): {word_count} words, {sentence_count} sentences",
            extra={
                "word_count": word_count,
                "sentence_count": sentence_count,
                "language": language,
                "processing_time_ms": processing_time_ms,
            },
        )
        
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