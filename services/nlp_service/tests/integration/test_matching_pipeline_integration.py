"""
Integration tests for matching pipeline in NLP Service.

Tests the complete matching pipeline integration with real matchers, confidence calculation,
and roster matching behavior. Validates matching logic, deduplication, and status determination.

Following Rule 075 methodology for integration testing patterns.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from huleedu_service_libs.outbox import OutboxRepositoryProtocol

from services.nlp_service.di import NlpServiceInfrastructureProvider
from services.nlp_service.features.student_matching.matching.roster_matcher import RosterMatcher
from services.nlp_service.features.student_matching.models import (
    ExtractedIdentifier,
    ExtractionResult,
    MatchStatus,
    StudentInfo,
)


class MatchingTestProvider(Provider):
    """Test provider for missing dependencies."""

    @provide(scope=Scope.APP)
    def provide_outbox_repository(self) -> OutboxRepositoryProtocol:
        """Provide mock outbox repository for testing."""
        return AsyncMock(spec=OutboxRepositoryProtocol)


class TestMatchingPipelineIntegration:
    """Integration tests for matching pipeline with real component interactions."""

    @pytest.fixture
    async def test_container(self) -> AsyncGenerator[AsyncContainer, None]:
        """Create DI container with test configuration for matching components."""
        from sqlalchemy.ext.asyncio import create_async_engine

        # Use in-memory SQLite for testing
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

        # Create container with test provider for missing dependencies
        from services.nlp_service.di_nlp_analysis import NlpAnalysisProvider

        container = make_async_container(
            MatchingTestProvider(), NlpServiceInfrastructureProvider(engine), NlpAnalysisProvider()
        )

        try:
            yield container
        finally:
            await container.close()
            await engine.dispose()

    @pytest.fixture
    async def roster_matcher(self, test_container: AsyncContainer) -> RosterMatcher:
        """Get real roster matcher with all configured components."""
        return await test_container.get(RosterMatcher)

    @pytest.fixture
    def sample_roster(self) -> list[StudentInfo]:
        """Create sample student roster for testing."""
        return [
            StudentInfo(
                student_id="student-001",
                first_name="Anna",
                last_name="Andersson",
                full_legal_name="Anna Andersson",
                email="anna.andersson@student.gu.se",
            ),
            StudentInfo(
                student_id="student-002",
                first_name="John",
                last_name="Smith",
                full_legal_name="John Smith",
                email="john.smith@example.com",
            ),
            StudentInfo(
                student_id="student-003",
                first_name="Maria",
                last_name="Rodriguez",
                full_legal_name="Maria Rodriguez",
                email="maria.rodriguez@university.edu",
            ),
            StudentInfo(
                student_id="student-004",
                first_name="Erik",
                last_name="Johansson",
                full_legal_name="Erik Johansson",
                email="erik.johansson@kth.se",
            ),
        ]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_exact_email_match_integration(
        self, roster_matcher: RosterMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test matching with exact email match - highest confidence scenario."""
        # Arrange - Extracted result with exact email match
        extraction_result = ExtractionResult()
        extraction_result.possible_emails = [
            ExtractedIdentifier(
                value="anna.andersson@student.gu.se",
                confidence=0.95,
                source_strategy="examnet_format",
                location_hint="header",
            )
        ]
        extraction_result.possible_names = [
            ExtractedIdentifier(
                value="Anna Andersson",
                confidence=0.85,
                source_strategy="examnet_format",
                location_hint="header",
            )
        ]

        # Act - Run matching pipeline
        suggestions, match_status = await roster_matcher.match_student(
            extracted=extraction_result,
            roster=sample_roster,
        )

        # Assert - Should find exact match with high confidence
        assert match_status == MatchStatus.HIGH_CONFIDENCE
        assert len(suggestions) == 1

        suggestion = suggestions[0]
        assert suggestion.student_id == "student-001"
        assert suggestion.student_name == "Anna Andersson"
        assert suggestion.student_email == "anna.andersson@student.gu.se"
        assert suggestion.confidence_score >= 0.9  # Email matches get high confidence

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_exact_name_match_integration(
        self, roster_matcher: RosterMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test matching with exact name match but no email."""
        # Arrange - Extracted result with name only
        extraction_result = ExtractionResult()
        extraction_result.possible_names = [
            ExtractedIdentifier(
                value="John Smith",
                confidence=0.8,
                source_strategy="header_pattern",
                location_hint="header",
            )
        ]

        # Act - Run matching pipeline
        suggestions, match_status = await roster_matcher.match_student(
            extracted=extraction_result,
            roster=sample_roster,
        )

        # Assert - Should find name match
        assert match_status in [MatchStatus.NEEDS_REVIEW, MatchStatus.HIGH_CONFIDENCE]
        assert len(suggestions) >= 1

        # Should find John Smith
        john_suggestion = next((s for s in suggestions if s.student_id == "student-002"), None)
        assert john_suggestion is not None
        assert john_suggestion.student_name == "John Smith"
        assert "name" in john_suggestion.match_reasons[0].lower()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_partial_name_match_integration(
        self, roster_matcher: RosterMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test matching with partial name variations."""
        # Arrange - Extracted result with name variations
        extraction_result = ExtractionResult()
        extraction_result.possible_names = [
            # Test different name formats
            ExtractedIdentifier(
                value="Maria",  # First name only
                confidence=0.6,
                source_strategy="text_content",
                location_hint="body",
            ),
            ExtractedIdentifier(
                value="Rodriguez",  # Last name only
                confidence=0.7,
                source_strategy="text_content",
                location_hint="body",
            ),
        ]

        # Act - Run matching pipeline
        suggestions, match_status = await roster_matcher.match_student(
            extracted=extraction_result,
            roster=sample_roster,
        )

        # Assert - Should find partial matches
        assert match_status in [MatchStatus.NEEDS_REVIEW, MatchStatus.NO_MATCH]

        # Should find Maria Rodriguez through partial matching
        maria_suggestions = [s for s in suggestions if s.student_id == "student-003"]
        assert len(maria_suggestions) >= 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_no_match_found_integration(
        self, roster_matcher: RosterMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test matching when no identifiers match the roster."""
        # Arrange - Extracted result with unknown identifiers
        extraction_result = ExtractionResult()
        extraction_result.possible_names = [
            ExtractedIdentifier(
                value="Unknown Student",
                confidence=0.8,
                source_strategy="header_pattern",
                location_hint="header",
            )
        ]
        extraction_result.possible_emails = [
            ExtractedIdentifier(
                value="unknown@nowhere.com",
                confidence=0.9,
                source_strategy="email_anchor",
                location_hint="body",
            )
        ]

        # Act - Run matching pipeline
        suggestions, match_status = await roster_matcher.match_student(
            extracted=extraction_result,
            roster=sample_roster,
        )

        # Assert - Should find no matches
        assert match_status == MatchStatus.NO_MATCH
        assert len(suggestions) == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_matches_deduplication_integration(
        self, roster_matcher: RosterMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test that multiple matches for same student are deduplicated properly."""
        # Arrange - Extracted result with both name and email for same student
        extraction_result = ExtractionResult()
        extraction_result.possible_names = [
            ExtractedIdentifier(
                value="Erik Johansson",
                confidence=0.75,
                source_strategy="header_pattern",
                location_hint="header",
            )
        ]
        extraction_result.possible_emails = [
            ExtractedIdentifier(
                value="erik.johansson@kth.se",
                confidence=0.95,
                source_strategy="examnet_format",
                location_hint="header",
            )
        ]

        # Act - Run matching pipeline
        suggestions, match_status = await roster_matcher.match_student(
            extracted=extraction_result,
            roster=sample_roster,
        )

        # Assert - Should find single suggestion for Erik (deduplicated)
        assert match_status == MatchStatus.HIGH_CONFIDENCE

        # Should only have one suggestion for Erik despite name+email match
        erik_suggestions = [s for s in suggestions if s.student_id == "student-004"]
        assert len(erik_suggestions) == 1

        # Should prefer email match confidence
        erik_suggestion = erik_suggestions[0]
        assert erik_suggestion.confidence_score >= 0.9

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_empty_roster_handling_integration(self, roster_matcher: RosterMatcher) -> None:
        """Test matching behavior with empty roster."""
        # Arrange - Valid extraction result but empty roster
        extraction_result = ExtractionResult()
        extraction_result.possible_names = [
            ExtractedIdentifier(
                value="Test Student",
                confidence=0.8,
                source_strategy="header_pattern",
                location_hint="header",
            )
        ]

        # Act - Run matching pipeline with empty roster
        suggestions, match_status = await roster_matcher.match_student(
            extracted=extraction_result,
            roster=[],  # Empty roster
        )

        # Assert - Should handle gracefully
        assert match_status == MatchStatus.NO_MATCH
        assert len(suggestions) == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_empty_extraction_handling_integration(
        self, roster_matcher: RosterMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test matching behavior with empty extraction result."""
        # Arrange - Empty extraction result
        extraction_result = ExtractionResult()  # No identifiers extracted

        # Act - Run matching pipeline
        suggestions, match_status = await roster_matcher.match_student(
            extracted=extraction_result,
            roster=sample_roster,
        )

        # Assert - Should handle gracefully
        assert match_status == MatchStatus.NO_MATCH
        assert len(suggestions) == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_confidence_calculation_integration(
        self, roster_matcher: RosterMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test that confidence calculation integrates properly with matching."""
        # Arrange - Multiple extraction results with different confidence levels
        extraction_result = ExtractionResult()

        # High confidence email
        extraction_result.possible_emails = [
            ExtractedIdentifier(
                value="anna.andersson@student.gu.se",
                confidence=0.95,
                source_strategy="examnet_format",
                location_hint="header",
            )
        ]

        # Lower confidence name variation
        extraction_result.possible_names = [
            ExtractedIdentifier(
                value="A. Andersson",  # Abbreviated form
                confidence=0.6,
                source_strategy="text_content",
                location_hint="body",
            )
        ]

        # Act - Run matching pipeline
        suggestions, match_status = await roster_matcher.match_student(
            extracted=extraction_result,
            roster=sample_roster,
        )

        # Assert - Should prioritize email match confidence
        assert match_status == MatchStatus.HIGH_CONFIDENCE
        assert len(suggestions) == 1

        suggestion = suggestions[0]
        assert suggestion.student_id == "student-001"
        # Confidence should reflect the high email match, not the lower name confidence
        assert suggestion.confidence_score >= 0.9

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_roster_matching_with_swedish_characters_integration(
        self, roster_matcher: RosterMatcher
    ) -> None:
        """Test matching with Swedish characters and locale-specific names."""
        # Arrange - Swedish roster and extraction
        swedish_roster = [
            StudentInfo(
                student_id="student-se-001",
                first_name="Åsa",
                last_name="Lindström",
                full_legal_name="Åsa Lindström",
                email="asa.lindstrom@gu.se",
            ),
            StudentInfo(
                student_id="student-se-002",
                first_name="Björn",
                last_name="Öhrström",
                full_legal_name="Björn Öhrström",
                email="bjorn.ohrstrom@kth.se",
            ),
        ]

        extraction_result = ExtractionResult()
        extraction_result.possible_names = [
            ExtractedIdentifier(
                value="Åsa Lindström",
                confidence=0.85,
                source_strategy="examnet_format",
                location_hint="header",
            )
        ]
        extraction_result.possible_emails = [
            ExtractedIdentifier(
                value="asa.lindstrom@gu.se",
                confidence=0.9,
                source_strategy="examnet_format",
                location_hint="header",
            )
        ]

        # Act - Run matching pipeline
        suggestions, match_status = await roster_matcher.match_student(
            extracted=extraction_result,
            roster=swedish_roster,
        )

        # Assert - Should handle Swedish characters correctly
        assert match_status == MatchStatus.HIGH_CONFIDENCE
        assert len(suggestions) == 1

        suggestion = suggestions[0]
        assert suggestion.student_id == "student-se-001"
        assert suggestion.student_name == "Åsa Lindström"
        assert suggestion.confidence_score >= 0.85
