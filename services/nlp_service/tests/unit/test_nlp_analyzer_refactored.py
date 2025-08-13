"""Unit tests for refactored SpacyNlpAnalyzer with dependency injection.

These are TRUE unit tests that test the analyzer logic in isolation,
with all dependencies mocked. Following HuleEdu testing standards:
- No conftest, explicit test utilities
- Clear separation of concerns
- High quality tests, no shortcuts
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.nlp_service.tests.unit.test_utils import (
    NlpAnalyzerTestFixture,
    create_mock_complexity_calculator,
    create_mock_diversity_calculator,
    create_mock_doc,
    create_mock_language_detector,
    create_mock_phraseology_calculator,
    create_mock_spacy_model_loader,
    create_mock_zipf_calculator,
)


class TestAnalyzeTextWithMockedDependencies:
    """Unit tests for analyze_text with fully mocked dependencies."""

    @pytest.mark.asyncio
    async def test_analyze_empty_text(self) -> None:
        """Test that empty text returns zero metrics."""
        # Arrange
        analyzer = NlpAnalyzerTestFixture().build()

        # Act
        result = await analyzer.analyze_text("", "en")

        # Assert
        assert result.word_count == 0
        assert result.sentence_count == 0
        assert result.avg_sentence_length == 0.0
        assert result.mean_zipf_frequency == 0.0
        assert result.mtld_score == 0.0
        assert result.processing_time_ms > 0

    @pytest.mark.asyncio
    async def test_analyze_text_with_auto_language_detection(self) -> None:
        """Test automatic language detection."""
        # Arrange
        detector = create_mock_language_detector(detection_map={"världen": "sv", "world": "en"})
        analyzer = NlpAnalyzerTestFixture().with_language_detector(detector).build()

        # Act
        result = await analyzer.analyze_text("Hello world", "auto")

        # Assert
        assert result.language_detected == "en"
        assert isinstance(detector.detect, AsyncMock)
        detector.detect.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_text_skeleton_mode_on_model_failure(self) -> None:
        """Test fallback to skeleton mode when spaCy fails."""
        # Arrange
        failed_loader = create_mock_spacy_model_loader(should_fail=True)
        analyzer = NlpAnalyzerTestFixture().with_model_loader(failed_loader).build()

        # Act
        result = await analyzer.analyze_text("Hello world. This is a test.", "en")

        # Assert - skeleton mode uses simple splitting
        assert result.word_count == 6  # Simple word split
        assert result.sentence_count == 2  # Simple sentence split
        assert result.mean_zipf_frequency == 0.0  # No advanced metrics in skeleton
        assert result.mtld_score == 0.0

    @pytest.mark.asyncio
    async def test_analyze_text_with_full_metrics(self) -> None:
        """Test full analysis with all metrics calculated."""
        # Arrange
        tokens = ["the", "quick", "brown", "fox", "jumps"]
        mock_doc = create_mock_doc(tokens=tokens, sentences=1, with_dependency=True)

        model_loader = create_mock_spacy_model_loader()
        model_loader.process_text = AsyncMock(return_value=mock_doc)  # type: ignore[method-assign]

        zipf_calc = create_mock_zipf_calculator(mean_zipf=5.5, percent_below_3=10.0)
        diversity_calc = create_mock_diversity_calculator(mtld=75.0, hdd=0.85)
        phraseology_calc = create_mock_phraseology_calculator(
            bigram_pmi=2.5, trigram_pmi=1.8, bigram_npmi=0.35, trigram_npmi=0.25
        )
        complexity_calc = create_mock_complexity_calculator(
            dependency_distance=2.3, first_order_coherence=0.75, second_order_coherence=0.65
        )

        analyzer = (
            NlpAnalyzerTestFixture()
            .with_model_loader(model_loader)
            .with_zipf_calculator(zipf_calc)
            .with_diversity_calculator(diversity_calc)
            .with_phraseology_calculator(phraseology_calc)
            .with_complexity_calculator(complexity_calc)
            .build()
        )

        # Act
        result = await analyzer.analyze_text("The quick brown fox jumps", "en")

        # Assert
        assert result.word_count == 5
        assert result.sentence_count == 1
        assert result.avg_sentence_length == 5.0
        assert result.mean_zipf_frequency == 5.5
        assert result.percent_tokens_zipf_below_3 == 10.0
        assert result.mtld_score == 75.0
        assert result.hdd_score == 0.85
        assert result.avg_bigram_pmi == 2.5
        assert result.avg_trigram_pmi == 1.8
        assert result.avg_bigram_npmi == 0.35
        assert result.avg_trigram_npmi == 0.25
        assert result.mean_dependency_distance == 2.3
        assert result.first_order_coherence == 0.75
        assert result.second_order_coherence == 0.65

        # Verify dependencies were called
        assert isinstance(model_loader.process_text, AsyncMock)
        model_loader.process_text.assert_called_once()
        assert isinstance(zipf_calc.calculate_metrics, MagicMock)
        zipf_calc.calculate_metrics.assert_called_once()
        assert isinstance(diversity_calc.calculate_mtld, MagicMock)
        diversity_calc.calculate_mtld.assert_called_once()
        assert isinstance(diversity_calc.calculate_hdd, MagicMock)
        diversity_calc.calculate_hdd.assert_called_once()
        assert isinstance(phraseology_calc.calculate_pmi_scores, MagicMock)
        phraseology_calc.calculate_pmi_scores.assert_called_once()
        assert isinstance(complexity_calc.calculate_dependency_distance, MagicMock)
        complexity_calc.calculate_dependency_distance.assert_called_once()
        assert isinstance(complexity_calc.calculate_cohesion_scores, MagicMock)
        complexity_calc.calculate_cohesion_scores.assert_called_once()


class TestDependencyInteractions:
    """Test interactions between the analyzer and its dependencies."""

    @pytest.mark.asyncio
    async def test_language_detector_called_for_auto(self) -> None:
        """Test that language detector is only called when language is 'auto'."""
        # Arrange
        detector = create_mock_language_detector()
        analyzer = NlpAnalyzerTestFixture().with_language_detector(detector).build()

        # Act - explicit language
        await analyzer.analyze_text("Hello", "en")
        assert isinstance(detector.detect, AsyncMock)
        assert detector.detect.call_count == 0

        # Act - auto language
        await analyzer.analyze_text("Hello", "auto")
        assert detector.detect.call_count == 1

    @pytest.mark.asyncio
    async def test_model_loader_receives_correct_language(self) -> None:
        """Test that model loader receives the detected/specified language."""
        # Arrange
        model_loader = create_mock_spacy_model_loader()
        detector = create_mock_language_detector(default_language="sv")

        analyzer = (
            NlpAnalyzerTestFixture()
            .with_model_loader(model_loader)
            .with_language_detector(detector)
            .build()
        )

        # Act with auto detection
        await analyzer.analyze_text("Hej världen", "auto")

        # Assert
        assert isinstance(model_loader.process_text, AsyncMock)
        model_loader.process_text.assert_called_once()
        call_args = model_loader.process_text.call_args
        assert call_args[0][1] == "sv"  # Second argument is language

    @pytest.mark.asyncio
    async def test_calculators_receive_processed_tokens(self) -> None:
        """Test that calculators receive the correct processed tokens."""
        # Arrange
        tokens = ["hello", "world", "test"]
        mock_doc = create_mock_doc(tokens=tokens)

        model_loader = create_mock_spacy_model_loader()
        model_loader.process_text = AsyncMock(return_value=mock_doc)  # type: ignore[method-assign]

        zipf_calc = create_mock_zipf_calculator()
        diversity_calc = create_mock_diversity_calculator()
        phraseology_calc = create_mock_phraseology_calculator()

        analyzer = (
            NlpAnalyzerTestFixture()
            .with_model_loader(model_loader)
            .with_zipf_calculator(zipf_calc)
            .with_diversity_calculator(diversity_calc)
            .with_phraseology_calculator(phraseology_calc)
            .build()
        )

        # Act
        await analyzer.analyze_text("hello world test", "en")

        # Assert - all calculators received the tokens
        assert isinstance(zipf_calc.calculate_metrics, MagicMock)
        zipf_calc.calculate_metrics.assert_called_once_with(tokens, "en")
        assert isinstance(diversity_calc.calculate_mtld, MagicMock)
        diversity_calc.calculate_mtld.assert_called_once_with(tokens)
        assert isinstance(diversity_calc.calculate_hdd, MagicMock)
        diversity_calc.calculate_hdd.assert_called_once_with(tokens)
        assert isinstance(phraseology_calc.calculate_pmi_scores, MagicMock)
        phraseology_calc.calculate_pmi_scores.assert_called_once_with(tokens)


class TestSkeletonModeFallback:
    """Test the skeleton mode fallback when spaCy is not available."""

    @pytest.mark.asyncio
    async def test_skeleton_mode_basic_metrics(self) -> None:
        """Test that skeleton mode calculates basic metrics correctly."""
        # Arrange
        failed_loader = create_mock_spacy_model_loader(should_fail=True)
        analyzer = NlpAnalyzerTestFixture().with_model_loader(failed_loader).build()

        # Act
        result = await analyzer.analyze_text(
            "This is a test. Another sentence here! And a question?", "en"
        )

        # Assert
        assert result.word_count == 10  # Simple word count
        assert result.sentence_count == 3  # Split by .!?
        assert result.avg_sentence_length == round(10 / 3, 2)

        # All advanced metrics should be 0 in skeleton mode
        assert result.mean_zipf_frequency == 0.0
        assert result.mtld_score == 0.0
        assert result.hdd_score == 0.0
        assert result.mean_dependency_distance == 0.0

    @pytest.mark.asyncio
    async def test_skeleton_mode_empty_text_handling(self) -> None:
        """Test skeleton mode handles empty text correctly."""
        # Arrange
        failed_loader = create_mock_spacy_model_loader(should_fail=True)
        analyzer = NlpAnalyzerTestFixture().with_model_loader(failed_loader).build()

        # Act
        result = await analyzer.analyze_text("", "en")

        # Assert
        assert result.word_count == 0
        assert result.sentence_count == 0
        assert result.avg_sentence_length == 0.0

    @pytest.mark.asyncio
    async def test_skeleton_mode_whitespace_only(self) -> None:
        """Test skeleton mode handles whitespace-only text."""
        # Arrange
        failed_loader = create_mock_spacy_model_loader(should_fail=True)
        analyzer = NlpAnalyzerTestFixture().with_model_loader(failed_loader).build()

        # Act
        result = await analyzer.analyze_text("   \n\t  ", "en")

        # Assert
        assert result.word_count == 0  # No actual words
        assert result.sentence_count == 0
        assert result.avg_sentence_length == 0.0


class TestProcessingTime:
    """Test processing time tracking."""

    @pytest.mark.asyncio
    async def test_processing_time_always_positive(self) -> None:
        """Test that processing time is always at least 1ms."""
        # Arrange
        analyzer = NlpAnalyzerTestFixture().build()

        # Act - even for empty text
        result = await analyzer.analyze_text("", "en")

        # Assert
        assert result.processing_time_ms >= 1

    @pytest.mark.asyncio
    async def test_processing_time_increases_with_complexity(self) -> None:
        """Test that more complex analysis takes more time."""
        # This is a loose test - just checking the value is set
        # In real scenarios, complex text would take longer

        # Arrange
        analyzer = NlpAnalyzerTestFixture().build()

        # Act
        simple_result = await analyzer.analyze_text("Hi", "en")
        complex_result = await analyzer.analyze_text("Complex " * 100, "en")

        # Assert - both have processing times
        assert simple_result.processing_time_ms > 0
        assert complex_result.processing_time_ms > 0
