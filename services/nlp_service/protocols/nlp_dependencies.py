"""Protocols for NLP external dependencies following DI patterns."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from spacy.language import Language
    from spacy.tokens import Doc


class SpacyModelLoaderProtocol(Protocol):
    """Protocol for loading and managing spaCy models."""

    async def load_model(self, language: str) -> Language:
        """Load a spaCy model for the specified language.
        
        Args:
            language: Language code ("en" or "sv")
            
        Returns:
            Loaded spaCy Language model
            
        Raises:
            ValueError: If language is not supported
            RuntimeError: If model cannot be loaded
        """
        ...

    async def process_text(self, text: str, language: str) -> Doc:
        """Process text with the appropriate spaCy model.
        
        Args:
            text: Text to process
            language: Language code ("en" or "sv")
            
        Returns:
            Processed spaCy Doc object
        """
        ...


class LanguageDetectorProtocol(Protocol):
    """Protocol for language detection."""

    async def detect(self, text: str) -> str:
        """Detect the language of the given text.
        
        Args:
            text: Text to analyze
            
        Returns:
            ISO 639-1 language code (e.g., "en", "sv")
        """
        ...


class ZipfCalculatorProtocol(Protocol):
    """Protocol for calculating Zipf frequency metrics."""

    def calculate_zipf_frequency(self, token: str, language: str) -> float:
        """Calculate Zipf frequency for a single token.
        
        Args:
            token: Word token
            language: Language code
            
        Returns:
            Zipf frequency score (0-7 scale typically)
        """
        ...

    def calculate_metrics(
        self, tokens: list[str], language: str
    ) -> tuple[float, float]:
        """Calculate aggregate Zipf metrics for tokens.
        
        Args:
            tokens: List of word tokens
            language: Language code
            
        Returns:
            Tuple of (mean_zipf_frequency, percent_below_threshold)
        """
        ...


class LexicalDiversityCalculatorProtocol(Protocol):
    """Protocol for calculating lexical diversity metrics."""

    def calculate_mtld(self, tokens: list[str]) -> float:
        """Calculate Measure of Textual Lexical Diversity.
        
        Args:
            tokens: List of word tokens
            
        Returns:
            MTLD score (higher = more diverse)
        """
        ...

    def calculate_hdd(self, tokens: list[str]) -> float:
        """Calculate Hypergeometric Distribution D.
        
        Args:
            tokens: List of word tokens
            
        Returns:
            HDD score (0-1 scale, higher = more diverse)
        """
        ...


class PhraseologyCalculatorProtocol(Protocol):
    """Protocol for calculating phraseology metrics."""

    def calculate_pmi_scores(
        self, tokens: list[str]
    ) -> tuple[float, float, float, float]:
        """Calculate PMI/NPMI scores for bigrams and trigrams.
        
        Args:
            tokens: List of word tokens
            
        Returns:
            Tuple of (bigram_pmi, trigram_pmi, bigram_npmi, trigram_npmi)
        """
        ...


class SyntacticComplexityCalculatorProtocol(Protocol):
    """Protocol for calculating syntactic complexity metrics."""

    def calculate_dependency_distance(self, doc: Doc) -> float:
        """Calculate mean dependency distance.
        
        Args:
            doc: Processed spaCy Doc
            
        Returns:
            Mean dependency distance
        """
        ...

    def calculate_cohesion_scores(self, doc: Doc) -> tuple[float, float]:
        """Calculate cohesion scores.
        
        Args:
            doc: Processed spaCy Doc
            
        Returns:
            Tuple of (first_order_coherence, second_order_coherence)
        """
        ...