"""Unit tests for SpacyNlpAnalyzer implementation.

Tests the NLP analyzer with comprehensive linguistic metrics including:
- Lexical sophistication (Zipf frequency)
- Lexical diversity (MTLD/HDD)
- Syntactic complexity (dependency distance)
- Cohesion (sentence similarity)
- Phraseology (PMI/NPMI)
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from common_core.events.nlp_events import NlpMetrics

from services.nlp_service.implementations.nlp_analyzer_impl import SpacyNlpAnalyzer


class TestAnalyzeText:
    """Tests for the main analyze_text method."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "text, language, expected_word_count, expected_sentence_count",
        [
            # Basic English text
            ("Hello world. This is a test.", "en", 6, 2),
            # Swedish text with special characters
            ("Hej världen. Årets största händelse är här.", "sv", 7, 2),
            # Single sentence
            ("This is a single sentence", "en", 5, 1),
            # Empty text
            ("", "auto", 0, 0),
            # Text with only spaces
            ("   ", "auto", 0, 0),
            # Text with multiple spaces between words
            ("Hello    world    test", "en", 3, 1),
            # Text with punctuation variations
            ("Hello! How are you? I am fine.", "en", 7, 3),
            # Long text (100 words)
            (" ".join(["word"] * 100) + ".", "en", 100, 1),
        ],
    )
    async def test_analyze_text_basic_metrics(
        self,
        text: str,
        language: str,
        expected_word_count: int,
        expected_sentence_count: int,
    ) -> None:
        """Test basic text metrics extraction in skeleton mode."""
        analyzer = SpacyNlpAnalyzer()
        
        # Analyzer starts in skeleton mode (models not loaded)
        result = await analyzer.analyze_text(text, language)
        
        assert isinstance(result, NlpMetrics)
        assert result.word_count == expected_word_count
        assert result.sentence_count == expected_sentence_count
        if expected_sentence_count > 0:
            assert result.avg_sentence_length == round(
                expected_word_count / expected_sentence_count, 2
            )
        else:
            assert result.avg_sentence_length == 0.0
        
        # Verify all advanced metrics default to 0 in skeleton mode
        assert result.mean_zipf_frequency == 0.0
        assert result.percent_tokens_zipf_below_3 == 0.0
        assert result.mtld_score == 0.0
        assert result.hdd_score == 0.0
        assert result.mean_dependency_distance == 0.0
        assert result.first_order_coherence == 0.0
        assert result.second_order_coherence == 0.0
        assert result.avg_bigram_pmi == 0.0
        assert result.avg_trigram_pmi == 0.0
        assert result.avg_bigram_npmi == 0.0
        assert result.avg_trigram_npmi == 0.0

    @pytest.mark.asyncio
    async def test_analyze_text_with_spacy_models(self) -> None:
        """Test analysis when spaCy models are available."""
        analyzer = SpacyNlpAnalyzer()
        
        # Mock spaCy models
        mock_doc = MagicMock()
        mock_doc.sents = [MagicMock(), MagicMock()]  # 2 sentences
        mock_token1 = MagicMock()
        mock_token1.text = "Hello"
        mock_token1.is_alpha = True
        mock_token2 = MagicMock()
        mock_token2.text = "world"
        mock_token2.is_alpha = True
        mock_doc.__iter__ = Mock(return_value=iter([mock_token1, mock_token2]))
        
        mock_nlp = MagicMock()
        mock_nlp.return_value = mock_doc
        
        # Set models as loaded
        analyzer.nlp_en = mock_nlp
        analyzer._models_loaded = True
        
        # Mock helper methods for metrics using patch.object
        with patch.object(analyzer, '_calculate_zipf_metrics', return_value=(4.5, 20.0)), \
             patch.object(analyzer, '_calculate_lexical_diversity', return_value=(75.0, 0.85)), \
             patch.object(analyzer, '_calculate_phraseology_metrics', return_value=(2.5, 3.0, 0.25, 0.30)):
            
            result = await analyzer.analyze_text("Hello world", "en")
            
            assert result.word_count == 2
            assert result.sentence_count == 2
            assert result.mean_zipf_frequency == 4.5
            assert result.percent_tokens_zipf_below_3 == 20.0
            assert result.mtld_score == 75.0
            assert result.hdd_score == 0.85

    @pytest.mark.asyncio
    async def test_processing_time_tracking(self) -> None:
        """Test that processing time is tracked correctly."""
        analyzer = SpacyNlpAnalyzer()
        
        result = await analyzer.analyze_text("Test text", "en")
        
        assert result.processing_time_ms > 0
        assert result.processing_time_ms < 5000  # Should be fast in skeleton mode


class TestLanguageDetection:
    """Tests for language detection functionality."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "text, expected_language",
        [
            # Swedish text with special characters
            ("Detta är en svensk text med åäö", "sv"),
            ("ÅÄÖ är svenska bokstäver", "sv"),
            # English text
            ("This is English text", "en"),
            # Mixed but predominantly Swedish
            ("Hello världen med svenska ÅÄÖ tecken", "sv"),
            # Empty defaults to English
            ("", "en"),
        ],
    )
    async def test_detect_language_heuristics(
        self, text: str, expected_language: str
    ) -> None:
        """Test language detection using heuristics when langdetect unavailable."""
        analyzer = SpacyNlpAnalyzer()
        
        # Test heuristic detection (when langdetect not available)
        detected = await analyzer._detect_language(text)
        assert detected == expected_language

    @pytest.mark.asyncio
    async def test_detect_language_with_langdetect(self) -> None:
        """Test language detection when langdetect is available."""
        analyzer = SpacyNlpAnalyzer()
        
        with patch("langdetect.detect") as mock_detect:
            mock_detect.return_value = "sv"
            
            detected = await analyzer._detect_language("Some Swedish text")
            assert detected == "sv"
            mock_detect.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_language_detection_in_analyze(self) -> None:
        """Test that auto language triggers detection."""
        analyzer = SpacyNlpAnalyzer()
        
        # Mock the detection method
        with patch.object(analyzer, '_detect_language', new_callable=AsyncMock) as mock_detect:
            mock_detect.return_value = "sv"
            
            result = await analyzer.analyze_text("Test text", "auto")
            
            mock_detect.assert_called_once_with("Test text")
            assert result.language_detected == "sv"


class TestZipfMetrics:
    """Tests for Zipf frequency calculations."""

    def test_calculate_zipf_metrics_with_wordfreq(self) -> None:
        """Test Zipf metric calculation when wordfreq is available."""
        analyzer = SpacyNlpAnalyzer()
        
        with patch("wordfreq.zipf_frequency") as mock_zipf:
            # Mock Zipf scores for each word
            mock_zipf.side_effect = [5.0, 4.0, 2.5, 1.5]  # Common, common, rare, very rare
            
            tokens = ["the", "cat", "exquisite", "sesquipedalian"]
            mean_zipf, percent_below_3 = analyzer._calculate_zipf_metrics(tokens, "en")
            
            assert mean_zipf == 3.25  # (5.0 + 4.0 + 2.5 + 1.5) / 4
            assert percent_below_3 == 50.0  # 2 out of 4 tokens below 3

    def test_calculate_zipf_metrics_without_wordfreq(self) -> None:
        """Test Zipf metrics fallback when wordfreq unavailable."""
        analyzer = SpacyNlpAnalyzer()
        
        with patch(
            "wordfreq.zipf_frequency",
            side_effect=ImportError,
        ):
            tokens = ["test", "words"]
            mean_zipf, percent_below_3 = analyzer._calculate_zipf_metrics(tokens, "en")
            
            assert mean_zipf == 0.0
            assert percent_below_3 == 0.0

    def test_calculate_zipf_metrics_empty_tokens(self) -> None:
        """Test Zipf metrics with empty token list."""
        analyzer = SpacyNlpAnalyzer()
        
        with patch("wordfreq.zipf_frequency") as mock_zipf:
            tokens: list[str] = []
            mean_zipf, percent_below_3 = analyzer._calculate_zipf_metrics(tokens, "en")
            
            assert mean_zipf == 0.0
            assert percent_below_3 == 0.0
            # zipf_frequency should not be called with empty tokens
            mock_zipf.assert_not_called()


class TestLexicalDiversity:
    """Tests for lexical diversity calculations."""

    def test_calculate_lexical_diversity_with_library(self) -> None:
        """Test MTLD/HDD calculation when lexical-diversity is available."""
        analyzer = SpacyNlpAnalyzer()
        
        mock_mtld = MagicMock(return_value=85.5)
        mock_hdd = MagicMock(return_value=0.92)
        
        with patch(
            "lexical_diversity.lex_div.mtld", mock_mtld
        ), patch(
            "lexical_diversity.lex_div.hdd", mock_hdd
        ):
            tokens = ["word"] * 100  # Sufficient tokens
            mtld, hdd = analyzer._calculate_lexical_diversity(tokens)
            
            assert mtld == 85.5
            assert hdd == 0.92
            mock_mtld.assert_called_once_with(tokens)
            mock_hdd.assert_called_once_with(tokens)

    def test_calculate_lexical_diversity_insufficient_tokens(self) -> None:
        """Test lexical diversity with too few tokens."""
        analyzer = SpacyNlpAnalyzer()
        
        mock_mtld = MagicMock()
        mock_hdd = MagicMock()
        with patch(
            "lexical_diversity.lex_div.mtld", mock_mtld
        ), patch(
            "lexical_diversity.lex_div.hdd", mock_hdd
        ):
            tokens = ["word"] * 10  # Less than 50 tokens
            mtld, hdd = analyzer._calculate_lexical_diversity(tokens)
            
            assert mtld == 0.0
            assert hdd == 0.0
            # Should not call ld functions with insufficient tokens
            mock_mtld.assert_not_called()
            mock_hdd.assert_not_called()

    def test_calculate_lexical_diversity_without_library(self) -> None:
        """Test lexical diversity fallback when library unavailable."""
        analyzer = SpacyNlpAnalyzer()
        
        with patch(
            "lexical_diversity.lex_div.mtld",
            side_effect=ImportError,
        ):
            tokens = ["word"] * 100
            mtld, hdd = analyzer._calculate_lexical_diversity(tokens)
            
            assert mtld == 0.0
            assert hdd == 0.0


class TestPhraseologyMetrics:
    """Tests for phraseology (PMI/NPMI) calculations."""

    def test_calculate_phraseology_metrics_with_gensim(self) -> None:
        """Test PMI/NPMI calculation when gensim is available."""
        analyzer = SpacyNlpAnalyzer()
        
        mock_phrases_class = MagicMock()
        mock_phrases_instance = MagicMock()
        mock_phrases_class.return_value = mock_phrases_instance
        
        # Mock find_phrases result
        mock_phrases_instance.find_phrases.return_value.items.return_value = [
            (("hello", "world"), 0.5),
            (("test", "phrase"), 0.3),
        ]
        
        with patch(
            "gensim.models.Phrases",
            mock_phrases_class,
        ):
            tokens = ["hello", "world", "test", "phrase"] * 5  # Sufficient tokens
            bigram_pmi, trigram_pmi, bigram_npmi, trigram_npmi = (
                analyzer._calculate_phraseology_metrics(tokens)
            )
            
            # Based on mock scores
            assert bigram_npmi == 0.4  # Average of 0.5 and 0.3
            assert bigram_pmi == 4.0  # NPMI * 10 (simplified)
            # Trigram scores will be 0 in our mock
            assert trigram_npmi == 0.0
            assert trigram_pmi == 0.0

    def test_calculate_phraseology_metrics_insufficient_tokens(self) -> None:
        """Test phraseology with too few tokens."""
        analyzer = SpacyNlpAnalyzer()
        
        mock_phrases_class = MagicMock()
        with patch(
            "gensim.models.Phrases",
            mock_phrases_class,
        ):
            tokens = ["word"] * 5  # Less than 10 tokens
            bigram_pmi, trigram_pmi, bigram_npmi, trigram_npmi = (
                analyzer._calculate_phraseology_metrics(tokens)
            )
            
            assert bigram_pmi == 0.0
            assert trigram_pmi == 0.0
            assert bigram_npmi == 0.0
            assert trigram_npmi == 0.0
            # Should not call Phrases with insufficient tokens
            mock_phrases_class.assert_not_called()

    def test_calculate_phraseology_metrics_without_gensim(self) -> None:
        """Test phraseology fallback when gensim unavailable."""
        analyzer = SpacyNlpAnalyzer()
        
        with patch(
            "gensim.models.Phrases",
            side_effect=ImportError,
        ):
            tokens = ["word"] * 20
            bigram_pmi, trigram_pmi, bigram_npmi, trigram_npmi = (
                analyzer._calculate_phraseology_metrics(tokens)
            )
            
            assert bigram_pmi == 0.0
            assert trigram_pmi == 0.0
            assert bigram_npmi == 0.0
            assert trigram_npmi == 0.0


class TestModelLoading:
    """Tests for spaCy model loading."""

    @pytest.mark.asyncio
    async def test_ensure_models_loaded_success(self) -> None:
        """Test successful spaCy model loading."""
        analyzer = SpacyNlpAnalyzer()
        
        mock_spacy = MagicMock()
        mock_en_model = MagicMock()
        mock_sv_model = MagicMock()
        mock_spacy.load.side_effect = [mock_en_model, mock_sv_model]
        
        with patch.dict("sys.modules", {"spacy": mock_spacy}):
            await analyzer._ensure_models_loaded()
            
            assert analyzer._models_loaded is True
            assert analyzer.nlp_en == mock_en_model
            assert analyzer.nlp_sv == mock_sv_model
            
            # Verify models were loaded with correct names
            mock_spacy.load.assert_any_call("en_core_web_sm")
            mock_spacy.load.assert_any_call("sv_core_news_sm")

    @pytest.mark.asyncio
    async def test_ensure_models_loaded_failure(self) -> None:
        """Test fallback when spaCy models cannot be loaded."""
        analyzer = SpacyNlpAnalyzer()
        
        # Mock ImportError when trying to import spacy
        with patch.dict("sys.modules"):
            if "spacy" in sys.modules:
                del sys.modules["spacy"]
            with patch("builtins.__import__", side_effect=ImportError("spacy not found")):
                await analyzer._ensure_models_loaded()
            
            assert analyzer._models_loaded is True  # Set to True to prevent repeated attempts
            assert analyzer.nlp_en is None
            assert analyzer.nlp_sv is None

    @pytest.mark.asyncio
    async def test_ensure_models_loaded_only_once(self) -> None:
        """Test that models are only loaded once."""
        analyzer = SpacyNlpAnalyzer()
        analyzer._models_loaded = True
        analyzer.nlp_en = MagicMock()
        
        mock_spacy = MagicMock()
        
        with patch.dict("sys.modules", {"spacy": mock_spacy}):
            await analyzer._ensure_models_loaded()
            
            # Should not try to load again
            mock_spacy.load.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_models_loaded_concurrent_calls(self) -> None:
        """Test that concurrent calls to ensure_models_loaded only load once."""
        import asyncio
        
        analyzer = SpacyNlpAnalyzer()
        
        mock_spacy = MagicMock()
        mock_en_model = MagicMock()
        mock_sv_model = MagicMock()
        mock_spacy.load.side_effect = [mock_en_model, mock_sv_model]
        
        with patch.dict("sys.modules", {"spacy": mock_spacy}):
            # Simulate concurrent calls
            tasks = [analyzer._ensure_models_loaded() for _ in range(5)]
            await asyncio.gather(*tasks)
            
            assert analyzer._models_loaded is True
            # Should only load models once despite concurrent calls
            assert mock_spacy.load.call_count == 2  # One for each language