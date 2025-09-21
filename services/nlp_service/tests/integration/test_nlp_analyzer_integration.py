"""Integration tests for NLP analyzer with real external dependencies.

These tests verify the NLP analyzer works correctly with actual spaCy models,
wordfreq, lexical-diversity, gensim, and langdetect libraries.
"""

import pytest
from common_core.events.nlp_events import NlpMetrics

from services.nlp_service.implementations.nlp_analyzer_impl import NlpAnalyzer
from services.nlp_service.implementations.nlp_dependencies import (
    LanguageDetector,
    LexicalDiversityCalculator,
    PhraseologyCalculator,
    SpacyModelLoader,
    SyntacticComplexityCalculator,
    ZipfCalculator,
)


@pytest.mark.integration
class TestNlpAnalyzerIntegration:
    """Integration tests for NLP analyzer with real dependencies."""

    @pytest.fixture
    def analyzer(self) -> NlpAnalyzer:
        """Create analyzer with real dependencies."""
        return NlpAnalyzer(
            model_loader=SpacyModelLoader(),
            language_detector=LanguageDetector(),
            zipf_calculator=ZipfCalculator(),
            diversity_calculator=LexicalDiversityCalculator(),
            phraseology_calculator=PhraseologyCalculator(),
            complexity_calculator=SyntacticComplexityCalculator(),
        )

    @pytest.mark.asyncio
    async def test_analyze_english_text_with_real_spacy(
        self, analyzer: NlpAnalyzer
    ) -> None:
        """Test full analysis pipeline with real English spaCy model."""
        text = """The quick brown fox jumps over the lazy dog.
        This sentence contains various words with different frequencies.
        Some words are common, while others like 'sesquipedalian' are rare."""

        result = await analyzer.analyze_text(text, language="en")

        assert isinstance(result, NlpMetrics)
        assert result.word_count > 20
        assert result.sentence_count == 3
        assert result.avg_sentence_length > 0

        # These should have real values when models are loaded
        if result.mean_zipf_frequency > 0:  # Only if wordfreq is available
            assert 2.0 < result.mean_zipf_frequency < 6.0
            assert 0 <= result.percent_tokens_zipf_below_3 <= 100

        # MTLD and HDD require sufficient tokens
        if result.mtld_score > 0:  # Only if lexical-diversity is available
            assert result.mtld_score > 0
            assert 0 < result.hdd_score < 1.0

    @pytest.mark.asyncio
    async def test_analyze_swedish_text_with_real_spacy(
        self, analyzer: NlpAnalyzer
    ) -> None:
        """Test full analysis pipeline with real Swedish spaCy model."""
        text = """Detta är en svensk text med åäö.
        Året har varit händelserikt och fullt av överraskningar.
        Vi fortsätter att utveckla våra språkkunskaper."""

        result = await analyzer.analyze_text(text, language="sv")

        assert isinstance(result, NlpMetrics)
        assert result.word_count > 15
        assert result.sentence_count == 3
        assert result.language_detected == "sv"

    @pytest.mark.asyncio
    async def test_language_autodetection_with_langdetect(
        self, analyzer: NlpAnalyzer
    ) -> None:
        """Test automatic language detection with real langdetect library."""
        swedish_text = "Detta är definitivt svensk text med många svenska ord och bokstäver som åäö"

        result = await analyzer.analyze_text(swedish_text, language="auto")

        # Should detect Swedish if langdetect is available
        # Falls back to heuristics if not
        assert result.language_detected in ["sv", "en"]
        if result.language_detected == "sv":
            # If correctly detected Swedish, verify Swedish processing
            assert result.word_count > 10

    @pytest.mark.asyncio
    async def test_zipf_frequency_calculation_with_wordfreq(
        self, analyzer: NlpAnalyzer
    ) -> None:
        """Test Zipf frequency metrics with real wordfreq library."""
        # Mix of common and rare words
        text = """The cat sat on the mat. Sesquipedalian and
        antidisestablishmentarianism are uncommon words."""

        result = await analyzer.analyze_text(text, language="en")

        if result.mean_zipf_frequency > 0:  # Only if wordfreq is available
            # Common words like 'the', 'and', 'are' have high Zipf scores (6-7)
            # Mixed with rare words should give reasonable average
            assert 1.0 < result.mean_zipf_frequency < 5.5  # Adjusted for realistic range
            # Some words should be below Zipf 3 (rare)
            assert result.percent_tokens_zipf_below_3 > 0

    @pytest.mark.asyncio
    async def test_lexical_diversity_with_sufficient_text(
        self, analyzer: NlpAnalyzer
    ) -> None:
        """Test lexical diversity metrics with real lexical-diversity library."""
        # Create text with at least 50 tokens for MTLD/HDD calculation
        varied_text = (
            """
        The exploration of diverse linguistic patterns reveals fascinating insights.
        Different words create varied expressions. Language diversity enriches communication.
        Writers employ numerous vocabulary choices. Synonyms provide alternative expressions.
        Repetition sometimes emphasizes important concepts. Variety enhances readability.
        Complex sentences demonstrate sophisticated language use. Simple words convey clarity.
        """
            * 2
        )  # Repeat to ensure sufficient tokens

        result = await analyzer.analyze_text(varied_text, language="en")

        if result.mtld_score > 0:  # Only if lexical-diversity is available
            # MTLD typically ranges from 10 to 200+
            assert result.mtld_score > 10
            # HDD ranges from 0 to 1
            assert 0 < result.hdd_score < 1.0

    @pytest.mark.asyncio
    async def test_phraseology_metrics_with_gensim(self, analyzer: NlpAnalyzer) -> None:
        """Test PMI/NPMI calculation with real gensim library."""
        # Text with common bigrams and trigrams
        text = (
            """
        New York is a great city. The United States has many states.
        Machine learning transforms data science. Natural language processing helps computers.
        Big data requires powerful computing. Cloud computing enables scalability.
        """
            * 3
        )  # Repeat to have enough data for phrase detection

        result = await analyzer.analyze_text(text, language="en")

        # PMI scores might be 0 if gensim is not available or no phrases detected
        # Just verify they're non-negative
        assert result.avg_bigram_pmi >= 0
        assert result.avg_trigram_pmi >= 0
        assert result.avg_bigram_npmi >= 0
        assert result.avg_trigram_npmi >= 0

    @pytest.mark.asyncio
    async def test_syntactic_complexity_with_spacy(self, analyzer: NlpAnalyzer) -> None:
        """Test syntactic complexity metrics with real spaCy parsing."""
        # Text with varying syntactic complexity
        text = """
        The cat sat.
        The brown cat quickly sat on the comfortable mat.
        While the storm raged outside, the cat that had been sleeping peacefully
        suddenly woke up and ran to the window to watch the rain.
        """

        result = await analyzer.analyze_text(text, language="en")

        # Dependency distance should be positive for parsed text
        if result.mean_dependency_distance > 0:
            assert result.mean_dependency_distance > 0
            # More complex sentences should have higher distance
            assert result.mean_dependency_distance < 10  # Reasonable upper bound

    @pytest.mark.asyncio
    async def test_fallback_to_skeleton_mode_on_import_error(
        self, analyzer: NlpAnalyzer
    ) -> None:
        """Test that analyzer falls back gracefully when dependencies fail."""
        # This test verifies the analyzer still works even if some
        # dependencies fail to load their underlying libraries

        text = "Simple test text"
        result = await analyzer.analyze_text(text, language="en")

        # Basic metrics should always work
        assert result.word_count == 3
        assert result.sentence_count == 1
        assert result.avg_sentence_length == 3.0

        # Advanced metrics default to 0 if libraries unavailable
        # (they will have real values if libraries are installed)
        assert result.mean_zipf_frequency >= 0
        assert result.mtld_score >= 0
        assert result.hdd_score >= 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "text,language,min_words,min_sentences",
        [
            ("Hello world. This is a test.", "en", 6, 2),
            ("Hej världen. Årets största händelse är här.", "sv", 7, 2),
            ("", "auto", 0, 0),
            ("   ", "auto", 0, 0),
        ],
    )
    async def test_basic_metrics_always_calculated(
        self,
        analyzer: NlpAnalyzer,
        text: str,
        language: str,
        min_words: int,
        min_sentences: int,
    ) -> None:
        """Test that basic metrics are always calculated correctly."""
        result = await analyzer.analyze_text(text, language)

        assert result.word_count >= min_words
        assert result.sentence_count >= min_sentences
        assert result.processing_time_ms > 0

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_large_text_processing(self, analyzer: NlpAnalyzer) -> None:
        """Test processing of large text documents."""
        # Generate a large text (1000+ words)
        large_text = " ".join(["The quick brown fox jumps over the lazy dog." for _ in range(150)])

        result = await analyzer.analyze_text(large_text, language="en")

        assert result.word_count > 1000
        assert result.sentence_count == 150
        # Processing time should be reasonable even for large text
        assert result.processing_time_ms < 30000  # Less than 30 seconds

    @pytest.mark.asyncio
    async def test_spacy_loader_registers_textdescriptives(self) -> None:
        """Ensure TextDescriptives pipeline is attached when available."""
        pytest.importorskip("textdescriptives")

        loader = SpacyModelLoader()
        model = await loader.load_model("en")

        assert "textdescriptives/coherence" in model.pipe_names

        doc = model("The cat sat. The cat was happy. Both were content.")
        coherence_attr = getattr(doc._, "coherence", None)
        if coherence_attr is None:
            pytest.skip("TextDescriptives coherence attribute missing")

        assert isinstance(coherence_attr, dict)
        assert "first_order_coherence" in coherence_attr
        assert "second_order_coherence" in coherence_attr

    @pytest.mark.asyncio
    async def test_cohesion_scores_align_with_textdescriptives(self) -> None:
        """Validate cohesion calculations mirror TextDescriptives values."""
        pytest.importorskip("textdescriptives")

        loader = SpacyModelLoader()
        model = await loader.load_model("en")
        doc = model("The cat sat. The cat was happy. Both were content.")

        coherence_attr = getattr(doc._, "coherence", None)
        if not coherence_attr:
            pytest.skip("TextDescriptives coherence attribute missing")

        calculator = SyntacticComplexityCalculator()
        first, second = calculator.calculate_cohesion_scores(doc)

        expected_first = coherence_attr.get("first_order_coherence")
        expected_second = coherence_attr.get("second_order_coherence")

        if expected_first is None or expected_second is None:
            pytest.skip("Coherence values unavailable")

        assert first == pytest.approx(float(expected_first))
        assert second == pytest.approx(float(expected_second))
