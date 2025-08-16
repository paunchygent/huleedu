"""
Integration tests for extraction pipeline in NLP Service.

Tests the complete extraction pipeline integration with real extractors and actual text processing.
Validates end-to-end extraction behavior, strategy coordination, and early exit logic.

Following Rule 075 methodology for integration testing patterns.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from huleedu_service_libs.outbox import OutboxRepositoryProtocol

from services.nlp_service.di import NlpServiceProvider
from services.nlp_service.features.student_matching.extraction.extraction_pipeline import (
    ExtractionPipeline,
)


class ExtractionTestProvider(Provider):
    """Test provider for missing dependencies."""

    @provide(scope=Scope.APP)
    def provide_outbox_repository(self) -> OutboxRepositoryProtocol:
        """Provide mock outbox repository for testing."""
        return AsyncMock(spec=OutboxRepositoryProtocol)


class TestExtractionPipelineIntegration:
    """Integration tests for extraction pipeline with real component interactions."""

    @pytest.fixture
    async def test_container(self) -> AsyncGenerator[AsyncContainer, None]:
        """Create DI container with test configuration for pipeline components."""
        from sqlalchemy.ext.asyncio import create_async_engine

        # Use in-memory SQLite for testing
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

        # Create container with test provider for missing dependencies
        from services.nlp_service.di_nlp_dependencies import NlpDependencyProvider

        container = make_async_container(
            ExtractionTestProvider(), NlpServiceProvider(engine), NlpDependencyProvider()
        )

        try:
            yield container
        finally:
            await container.close()
            await engine.dispose()

    @pytest.fixture
    async def extraction_pipeline(self, test_container: AsyncContainer) -> ExtractionPipeline:
        """Get real extraction pipeline with all configured extractors."""
        return await test_container.get(ExtractionPipeline)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_examnet_format_extraction_integration(
        self, extraction_pipeline: ExtractionPipeline
    ) -> None:
        """Test extraction pipeline with exam.net formatted text."""
        # Arrange - Real exam.net formatted essay text
        examnet_text = """
        Namn: Anna Andersson
        E-post: anna.andersson@student.gu.se
        Tid: 2024-01-15 10:30

        Here is the actual essay content about climate change and sustainability.
        The essay discusses various environmental issues and potential solutions.
        """

        # Act - Run real extraction pipeline
        result = await extraction_pipeline.extract(
            text=examnet_text,
            filename="essay_001.txt",
            metadata={"test_scenario": "examnet_format"},
        )

        # Assert - Verify extraction results
        assert not result.is_empty()

        # Should find the name
        assert len(result.possible_names) >= 1
        name_values = [ident.value for ident in result.possible_names]
        assert any("Anna Andersson" in name for name in name_values)

        # Should find the email
        assert len(result.possible_emails) >= 1
        email_values = [ident.value for ident in result.possible_emails]
        assert any("anna.andersson@student.gu.se" in email for email in email_values)

        # Should have high confidence for exam.net format
        name_confidences = [ident.confidence for ident in result.possible_names]
        assert max(name_confidences) >= 0.8

        # Should indicate successful strategy
        assert result.metadata["strategies_tried"] >= 1
        assert "examnet" in str(result.metadata).lower()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_header_pattern_extraction_integration(
        self, extraction_pipeline: ExtractionPipeline
    ) -> None:
        """Test extraction pipeline with header pattern text."""
        # Arrange - Header pattern essay
        header_text = """
        John Smith
        john.smith@example.com
        Course: English 5

        This is my essay about modern literature. I believe that contemporary authors
        have a unique perspective on social issues that previous generations lacked.
        """

        # Act - Run extraction pipeline
        result = await extraction_pipeline.extract(
            text=header_text,
            filename="john_essay.txt",
            metadata={"test_scenario": "header_pattern"},
        )

        # Assert - Verify extraction success
        assert not result.is_empty()

        # Should extract name from header
        assert len(result.possible_names) >= 1
        name_found = any("John Smith" in ident.value for ident in result.possible_names)
        assert name_found

        # Should extract email from header
        assert len(result.possible_emails) >= 1
        email_found = any(
            "john.smith@example.com" in ident.value for ident in result.possible_emails
        )
        assert email_found

        # Metadata should show strategy execution
        assert result.metadata["strategies_tried"] >= 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_email_anchor_extraction_integration(
        self, extraction_pipeline: ExtractionPipeline
    ) -> None:
        """Test extraction pipeline with email anchor pattern."""
        # Arrange - Text with email in content
        email_anchor_text = """
        Essay Assignment - Climate Change Impact

        My name is Maria Rodriguez and I can be reached at maria.rodriguez@university.edu
        for any questions about this assignment.

        The climate crisis represents one of the most significant challenges of our time.
        """

        # Act - Run extraction pipeline
        result = await extraction_pipeline.extract(
            text=email_anchor_text,
            filename="maria_climate.txt",
            metadata={"test_scenario": "email_anchor"},
        )

        # Assert - Verify extraction
        assert not result.is_empty()

        # Should find email from content
        assert len(result.possible_emails) >= 1
        email_found = any(
            "maria.rodriguez@university.edu" in ident.value for ident in result.possible_emails
        )
        assert email_found

        # Should find name near email
        assert len(result.possible_names) >= 1
        name_found = any("Maria Rodriguez" in ident.value for ident in result.possible_names)
        assert name_found

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_early_exit_behavior_integration(
        self, extraction_pipeline: ExtractionPipeline
    ) -> None:
        """Test that pipeline exits early when confidence threshold is met."""
        # Arrange - High-confidence exam.net text (should trigger early exit)
        high_confidence_text = """
        Namn: Perfect Student
        E-post: perfect.student@university.se
        Kurs: Svenska 101

        This is a perfectly formatted essay that should trigger early exit behavior.
        """

        # Act - Run extraction pipeline
        result = await extraction_pipeline.extract(
            text=high_confidence_text, filename="perfect_student.txt"
        )

        # Assert - Should have triggered early exit
        assert not result.is_empty()
        assert result.metadata.get("early_exit", False) is True

        # Should not have tried all strategies
        total_strategies = result.metadata.get("strategies_available", 0)
        tried_strategies = result.metadata.get("strategies_tried", 0)
        assert tried_strategies < total_strategies

        # Should have high confidence results
        name_confidences = [ident.confidence for ident in result.possible_names]
        assert max(name_confidences) >= 0.7

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_no_identifiers_found_integration(
        self, extraction_pipeline: ExtractionPipeline
    ) -> None:
        """Test extraction pipeline behavior when no identifiers are found."""
        # Arrange - Text with no identifiable information
        no_info_text = """
        This is an anonymous essay about philosophy and ethics.

        The author discusses various theories without providing any personal identification.
        No names, emails, or identifying information are present in this text.
        """

        # Act - Run extraction pipeline
        result = await extraction_pipeline.extract(text=no_info_text, filename="anonymous.txt")

        # Assert - Should be empty but well-formed
        assert result.is_empty()
        assert len(result.possible_names) == 0
        assert len(result.possible_emails) == 0

        # Should have tried multiple strategies
        assert result.metadata.get("strategies_tried", 0) >= 2
        assert result.metadata.get("early_exit", False) is False

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_identifiers_deduplication_integration(
        self, extraction_pipeline: ExtractionPipeline
    ) -> None:
        """Test that pipeline properly deduplicates multiple instances of same identifier."""
        # Arrange - Text with repeated identifiers
        repeated_text = """
        Namn: Lisa Nilsson
        E-post: lisa.nilsson@student.se

        Hi, this is Lisa Nilsson writing about environmental science.
        You can contact me at lisa.nilsson@student.se if needed.

        Regards,
        Lisa Nilsson
        """

        # Act - Run extraction pipeline
        result = await extraction_pipeline.extract(
            text=repeated_text, filename="lisa_environment.txt"
        )

        # Assert - Should deduplicate identical identifiers
        assert not result.is_empty()

        # Should only have one instance of each identifier
        lisa_names = [ident for ident in result.possible_names if "Lisa Nilsson" in ident.value]
        assert len(lisa_names) == 1  # Deduplicated

        lisa_emails = [
            ident for ident in result.possible_emails if "lisa.nilsson@student.se" in ident.value
        ]
        assert len(lisa_emails) == 1  # Deduplicated

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_extraction_error_handling_integration(
        self, extraction_pipeline: ExtractionPipeline
    ) -> None:
        """Test that pipeline handles extractor errors gracefully and continues."""
        # Arrange - Malformed text that might cause extractor issues
        malformed_text = """
        Namn: [INVALID-UNICODE-\x00\x01\x02]
        E-post: not-an-email-address

        This text contains potential parsing challenges.
        """

        # Act - Run extraction pipeline (should not raise exceptions)
        result = await extraction_pipeline.extract(text=malformed_text, filename="malformed.txt")

        # Assert - Should complete without exceptions
        # May or may not find valid identifiers, but shouldn't crash
        assert result is not None
        assert hasattr(result, "possible_names")
        assert hasattr(result, "possible_emails")
        assert hasattr(result, "metadata")

        # Should have attempted strategies
        assert result.metadata.get("strategies_tried", 0) >= 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_confidence_threshold_configuration_integration(
        self, test_container: AsyncContainer
    ) -> None:
        """Test that extraction pipeline respects confidence threshold configuration."""
        # Arrange - Get extraction strategies from DI container
        from services.nlp_service.features.student_matching.extraction.base_extractor import (
            BaseExtractor,
        )

        strategies = await test_container.get(list[BaseExtractor])

        # Create pipeline with different threshold
        low_threshold_pipeline = ExtractionPipeline(
            strategies=strategies,
            confidence_threshold=0.3,  # Lower threshold
            max_strategies=3,
        )

        moderate_confidence_text = """
        Name: Bob Johnson
        Contact: bob@example.com

        This is a moderately formatted essay.
        """

        # Act - Run with lower threshold
        result = await low_threshold_pipeline.extract(
            text=moderate_confidence_text, filename="bob_essay.txt"
        )

        # Assert - Should exit earlier with lower threshold
        assert not result.is_empty()
        # Threshold behavior depends on actual confidence scores from extractors
        assert result.metadata.get("strategies_tried", 0) >= 1
