"""
End-to-end integration tests for complete student matching pipeline in NLP Service.

Tests the full flow from essay text extraction through student matching using real-world
essay patterns and student rosters. Validates the entire pipeline working together.

Following Rule 075 methodology for integration testing patterns.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from huleedu_service_libs.outbox import OutboxRepositoryProtocol

from services.nlp_service.di import NlpServiceInfrastructureProvider
from services.nlp_service.protocols import StudentMatcherProtocol


class EndToEndTestProvider(Provider):
    """Test provider for missing dependencies."""

    @provide(scope=Scope.APP)
    def provide_outbox_repository(self) -> OutboxRepositoryProtocol:
        """Provide mock outbox repository for testing."""
        return AsyncMock(spec=OutboxRepositoryProtocol)


class TestEndToEndStudentMatchingIntegration:
    """End-to-end integration tests for complete student matching pipeline."""

    @pytest.fixture
    async def test_container(self) -> AsyncGenerator[AsyncContainer, None]:
        """Create DI container with test configuration for full pipeline."""
        from sqlalchemy.ext.asyncio import create_async_engine

        # Use in-memory SQLite for testing
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

        # Create container with test provider for missing dependencies
        from services.nlp_service.di_nlp_analysis import NlpAnalysisProvider

        container = make_async_container(
            EndToEndTestProvider(), NlpServiceInfrastructureProvider(engine), NlpAnalysisProvider()
        )

        try:
            yield container
        finally:
            await container.close()
            await engine.dispose()

    @pytest.fixture
    async def student_matcher(self, test_container: AsyncContainer) -> StudentMatcherProtocol:
        """Get real student matcher with all configured components."""
        matcher: StudentMatcherProtocol = await test_container.get(StudentMatcherProtocol)
        return matcher

    @pytest.fixture
    def book_report_class_roster(self) -> list[dict]:
        """Create class roster based on Book Report ES24B students."""
        # Using the real student names from the Book Report folder
        students = [
            {
                "student_id": "001",
                "first_name": "Alva",
                "last_name": "Lemos",
                "full_legal_name": "Alva Lemos",
                "email": "alva.lemos@school.se",
            },
            {
                "student_id": "002",
                "first_name": "Amanda",
                "last_name": "Frantz",
                "full_legal_name": "Amanda Frantz",
                "email": "amanda.frantz@school.se",
            },
            {
                "student_id": "003",
                "first_name": "Arve",
                "last_name": "Bergström",
                "full_legal_name": "Arve Bergström",
                "email": "arve.bergstrom@school.se",
            },
            {
                "student_id": "004",
                "first_name": "Axel",
                "last_name": "Karlsson",
                "full_legal_name": "Axel Karlsson",
                "email": "axel.karlsson@school.se",
            },
            {
                "student_id": "005",
                "first_name": "Cornelia",
                "last_name": "Kardborn",
                "full_legal_name": "Cornelia Kardborn",
                "email": "cornelia.kardborn@school.se",
            },
            {
                "student_id": "006",
                "first_name": "Ebba",
                "last_name": "Noren Bergsröm",
                "full_legal_name": "Ebba Noren Bergsröm",
                "email": "ebba.noren@school.se",
            },
            {
                "student_id": "007",
                "first_name": "Ebba",
                "last_name": "Saviluoto",
                "full_legal_name": "Ebba Saviluoto",
                "email": "ebba.saviluoto@school.se",
            },
            {
                "student_id": "008",
                "first_name": "Edgar",
                "last_name": "Gezelius",
                "full_legal_name": "Edgar Gezelius",
                "email": "edgar.gezelius@school.se",
            },
            {
                "student_id": "009",
                "first_name": "Elin",
                "last_name": "Bogren",
                "full_legal_name": "Elin Bogren",
                "email": "elin.bogren@school.se",
            },
            {
                "student_id": "010",
                "first_name": "Ellie",
                "last_name": "Rankin",
                "full_legal_name": "Ellie Rankin",
                "email": "ellie.rankin@school.se",
            },
            {
                "student_id": "011",
                "first_name": "Elvira",
                "last_name": "Johansson",
                "full_legal_name": "Elvira Johansson",
                "email": "elvira.johansson@school.se",
            },
            {
                "student_id": "012",
                "first_name": "Emil",
                "last_name": "Pihlman",
                "full_legal_name": "Emil Pihlman",
                "email": "emil.pihlman@school.se",
            },
            {
                "student_id": "013",
                "first_name": "Emil",
                "last_name": "Zäll Jernberg",
                "full_legal_name": "Emil Zäll Jernberg",
                "email": "emil.zall@school.se",
            },
            {
                "student_id": "014",
                "first_name": "Emma",
                "last_name": "Wüst",
                "full_legal_name": "Emma Wüst",
                "email": "emma.wust@school.se",
            },
            {
                "student_id": "015",
                "first_name": "Erik",
                "last_name": "Arvman",
                "full_legal_name": "Erik Arvman",
                "email": "erik.arvman@school.se",
            },
            {
                "student_id": "016",
                "first_name": "Figg",
                "last_name": "Eriksson",
                "full_legal_name": "Figg Eriksson",
                "email": "figg.eriksson@school.se",
            },
            {
                "student_id": "017",
                "first_name": "Jagoda",
                "last_name": "Struzik",
                "full_legal_name": "Jagoda Struzik",
                "email": "jagoda.struzik@school.se",
            },
            {
                "student_id": "018",
                "first_name": "Jonathan",
                "last_name": "Hedqvist",
                "full_legal_name": "Jonathan Hedqvist",
                "email": "jonathan.hedqvist@school.se",
            },
            {
                "student_id": "019",
                "first_name": "Leon",
                "last_name": "Gustavsson",
                "full_legal_name": "Leon Gustavsson",
                "email": "leon.gustavsson@school.se",
            },
            {
                "student_id": "020",
                "first_name": "Manuel",
                "last_name": "Gren",
                "full_legal_name": "Manuel Gren",
                "email": "manuel.gren@school.se",
            },
            {
                "student_id": "021",
                "first_name": "Melek",
                "last_name": "Özturk",
                "full_legal_name": "Melek Özturk",
                "email": "melek.ozturk@school.se",
            },
            {
                "student_id": "022",
                "first_name": "Nelli",
                "last_name": "Moilanen",
                "full_legal_name": "Nelli Moilanen",
                "email": "nelli.moilanen@school.se",
            },
            {
                "student_id": "023",
                "first_name": "Sam",
                "last_name": "Höglund Öman",
                "full_legal_name": "Sam Höglund Öman",
                "email": "sam.hoglund@school.se",
            },
            {
                "student_id": "024",
                "first_name": "Stella",
                "last_name": "Sellström",
                "full_legal_name": "Stella Sellström",
                "email": "stella.sellstrom@school.se",
            },
            {
                "student_id": "025",
                "first_name": "Test",
                "last_name": "Person",
                "full_legal_name": "Test Person",
                "email": "test.person@school.se",
            },
            {
                "student_id": "026",
                "first_name": "Vera",
                "last_name": "Karlberg",
                "full_legal_name": "Vera Karlberg",
                "email": "vera.karlberg@school.se",
            },
            {
                "student_id": "027",
                "first_name": "Simon",
                "last_name": "Pub",
                "full_legal_name": "Simon Pub",
                "email": "simon.pub@school.se",
            },
            {
                "student_id": "028",
                "first_name": "Tindra",
                "last_name": "Cruz",
                "full_legal_name": "Tindra Cruz",
                "email": "tindra.cruz@school.se",
            },
        ]
        return students

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_essay_elvira_johansson(
        self, student_matcher: StudentMatcherProtocol, book_report_class_roster: list[dict]
    ) -> None:
        """Test complete matching pipeline with Elvira Johansson's real essay."""
        # Arrange - Real essay text from Elvira Johansson
        essay_text = """Elvira Johansson 2025-03-06
Prov: Book Report ES24B
Antal ord: 607
(un)arranged marriage


Dear mr Rai.
I'm wrighting this letter to you because it can be interessting for you as an author to get som
feedback and toughts for yor book. I think your novel (un)arranged marrige is okej. It was
interresting to read how it can be in different cultures. And when you grow up wiyh a
particular culture others can seem a bit wicked or wouldent be socialy exapteble in other
countrys and cultures. However it was quite boring.


The book is about Manjit- the maincharacter, who stuggles to be seeen as an iduvidual. And we
get to follow his thougts and how he repons to the enviroment his in. All the hate he gets
from his father and that he has no freedom or anything to say for him self. And that hes
tying to find a way to get out of the arranged marrige."""

        correlation_id = uuid4()

        # Act - Run complete student matching pipeline
        suggestions = await student_matcher.find_matches(
            essay_text=essay_text,
            roster=book_report_class_roster,
            correlation_id=correlation_id,
        )

        # Assert - Should find Elvira Johansson by name extraction
        assert len(suggestions) >= 1

        top_suggestion = suggestions[0]
        assert top_suggestion.student_id == "011"
        assert top_suggestion.student_name == "Elvira Johansson"
        assert top_suggestion.confidence_score >= 0.8  # High confidence from name match

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_essay_sam_hoglund_oman(
        self, student_matcher: StudentMatcherProtocol, book_report_class_roster: list[dict]
    ) -> None:
        """Test matching with Swedish characters - Sam Höglund Öman's real essay."""
        # Arrange - Real essay text from Sam Höglund Öman
        essay_text = """Sam Höglund Öman 2025-03-06
Prov: Book Report ES24B
Antal ord: 627
Sam - (Un)arranged Marriage


The book "(Un)arranged Marriage" is about a teenage boy from an Indian family that are living
in England. Manny's family wants him to be a good Punjabi man and marry a girl of their
choice at the age of seventeen. However, he doesn't want that and tries his hardest to
avoid it. In this essay I am going to discuss the theme of expectations and the pressure
Manny feels to live up to them, which I believe is a big and important subject in the book.


First off, I want to talk about how well I think the author managed to describe Manny's
feelings and reactions to the pressure of his family. It was made clear that he didn't have
a choice, that he couldn't just tell his family that he didn't want to."""

        correlation_id = uuid4()

        # Act - Run complete matching pipeline
        suggestions = await student_matcher.find_matches(
            essay_text=essay_text,
            roster=book_report_class_roster,
            correlation_id=correlation_id,
        )

        # Assert - Should correctly match Sam Höglund Öman
        assert len(suggestions) >= 1

        top_suggestion = suggestions[0]
        assert top_suggestion.student_id == "023"
        assert top_suggestion.student_name == "Sam Höglund Öman"
        assert top_suggestion.confidence_score >= 0.8

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_essay_emil_zall_jernberg(
        self, student_matcher: StudentMatcherProtocol, book_report_class_roster: list[dict]
    ) -> None:
        """Test matching with complex multi-part names - Emil Zäll Jernberg's real essay."""
        # Arrange - Real essay text from Emil Zäll Jernberg
        essay_text = """Emil Zäll Jernberg 2025-03-27
Prov: Book Report ES24B
Antal ord: 472
My Favorite Character


Today i will be talking about my favorite charater in the book. And it's Junior. Junior is
from a place called the rez. And through his years he got picked on because of his
apperience and where he was from. I choose this character because I was also picked on at
my old school because i was late into puperty, so they didn't treat me like they did with
the others."""

        correlation_id = uuid4()

        # Act - Run complete matching pipeline
        suggestions = await student_matcher.find_matches(
            essay_text=essay_text,
            roster=book_report_class_roster,
            correlation_id=correlation_id,
        )

        # Assert - Should correctly match Emil Zäll Jernberg
        assert len(suggestions) >= 1

        top_suggestion = suggestions[0]
        assert top_suggestion.student_id == "013"
        assert top_suggestion.student_name == "Emil Zäll Jernberg"
        assert top_suggestion.confidence_score >= 0.8

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_essay_alva_lemos(
        self, student_matcher: StudentMatcherProtocol, book_report_class_roster: list[dict]
    ) -> None:
        """Test matching with Alva Lemos's real essay."""
        # Arrange - Real essay text from Alva Lemos
        essay_text = """Alva Lemos 2025-03-06
Prov: Book Report ES24B
Antal ord: 699
Dear Mr. Melvin Burgess


    I read your book Junk and I would like to tell you what I thought of it.
The topic of your book was about drugs and about being homeless.
It took place in the 1980s in Bristol which is located in the South west of England. The
story starts off quite innocently with introducing our two main characters.
Later on in the book it is shown when both Gemma has turned to drugs and alcohol the more
time that went by. She starts doing stronger and harder drugs which eventuallty led to a
severe addiction. The same went for Tar."""

        correlation_id = uuid4()

        # Act - Run complete matching pipeline
        suggestions = await student_matcher.find_matches(
            essay_text=essay_text,
            roster=book_report_class_roster,
            correlation_id=correlation_id,
        )

        # Assert - Should find Alva Lemos through name extraction
        assert len(suggestions) >= 1

        top_suggestion = suggestions[0]
        assert top_suggestion.student_id == "001"
        assert top_suggestion.student_name == "Alva Lemos"
        assert top_suggestion.confidence_score >= 0.8

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_no_identifiers_in_essay(
        self, student_matcher: StudentMatcherProtocol, book_report_class_roster: list[dict]
    ) -> None:
        """Test behavior when essay contains no identifying information."""
        # Arrange - Anonymous essay
        essay_text = """
        Book Report: 1984 by George Orwell

        This dystopian novel presents a terrifying vision of totalitarian control.
        The protagonist Winston Smith struggles against the oppressive Party...

        The themes of surveillance and thought control remain relevant today...
        """

        correlation_id = uuid4()

        # Act - Run complete matching pipeline
        suggestions = await student_matcher.find_matches(
            essay_text=essay_text,
            roster=book_report_class_roster,
            correlation_id=correlation_id,
        )

        # Assert - Should return empty suggestions
        assert len(suggestions) == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_performance_with_multiple_real_essays(
        self, student_matcher: StudentMatcherProtocol, book_report_class_roster: list[dict]
    ) -> None:
        """Test that matching performs well with multiple real essay formats."""
        # Arrange - Multiple real essay formats based on actual patterns
        essay_texts = [
            "Amanda Frantz 2025-03-06\nProv: Book Report ES24B\nAntal ord: 523\n\nBook Analysis...",
            "Cornelia Kardborn 2025-03-06\nBook Report ES24B\n\nDear Author...",
            "Edgar Gezelius 2025-03-06\nES24B Literary Analysis\n\nThis essay explores...",
        ]

        # Act - Run multiple matches
        all_suggestions = []
        for essay_text in essay_texts:
            suggestions = await student_matcher.find_matches(
                essay_text=essay_text,
                roster=book_report_class_roster,
                correlation_id=uuid4(),
            )
            all_suggestions.extend(suggestions)

        # Assert - Should find matches for the essays
        assert len(all_suggestions) >= 2  # At least 2 matches

        # Verify we found some of the expected students
        found_ids = {s.student_id for s in all_suggestions}
        # At least Amanda and Cornelia should be found with high confidence
        assert any(id in found_ids for id in ["002", "005", "008"])

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_essay_with_email_in_header_hilda_grahn(
        self, student_matcher: StudentMatcherProtocol, book_report_class_roster: list[dict]
    ) -> None:
        """Test essay with email on line 3 - Hilda Grahn format."""
        # Add Hilda to the roster
        extended_roster = book_report_class_roster + [
            {
                "student_id": "029",
                "first_name": "Hilda",
                "last_name": "Grahn",
                "full_legal_name": "Hilda Grahn",
                "email": "hg17001@harryda.se",
            }
        ]

        essay_text = """Hilda Grahn 2024-08-30
Prov: Eng 5 SA24D My Personal Objectives 2
HG17001@harryda.se
Antal ord: 226
Hilda Grahn SA24D

Hi! My name is Hilda Grahn and I live in Landvetter. I usually don´t speak english that
much outside of school. I do watch Tiktok and some of the videos I watch are when people
are speaking english."""

        correlation_id = uuid4()

        # Act
        suggestions = await student_matcher.find_matches(
            essay_text=essay_text,
            roster=extended_roster,
            correlation_id=correlation_id,
        )

        # Assert - Should find Hilda by both name and email
        assert len(suggestions) >= 1

        top_suggestion = suggestions[0]
        assert top_suggestion.student_id == "029"
        assert top_suggestion.student_name == "Hilda Grahn"
        assert (
            top_suggestion.confidence_score >= 0.9
        )  # Very high confidence with both name and email

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_essay_with_email_leo_svartling(
        self, student_matcher: StudentMatcherProtocol, book_report_class_roster: list[dict]
    ) -> None:
        """Test essay with email extraction - Leo Svartling format."""
        # Add Leo to the roster
        extended_roster = book_report_class_roster + [
            {
                "student_id": "030",
                "first_name": "Leo",
                "last_name": "Svartling",
                "full_legal_name": "Leo Svartling",
                "email": "ls17003@harryda.se",
            }
        ]

        essay_text = """Leo Svartling 2024-08-30
Prov: Eng 5 SA24D My Personal Objectives 2
LS17003@harryda.se
Antal ord: 252

Hello my name is leo! I like to play videogames on my freemtime wich helps  me speak
english alot. But id say that my main source of english is from my boxing training where
my trainer doesnt know any swedish, so over there i only have conversations in english
with everybody."""

        correlation_id = uuid4()

        # Act
        suggestions = await student_matcher.find_matches(
            essay_text=essay_text,
            roster=extended_roster,
            correlation_id=correlation_id,
        )

        # Assert
        assert len(suggestions) >= 1

        top_suggestion = suggestions[0]
        assert top_suggestion.student_id == "030"
        assert top_suggestion.student_name == "Leo Svartling"
        assert top_suggestion.confidence_score >= 0.9

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_essay_with_email_elina_rouzveh(
        self, student_matcher: StudentMatcherProtocol, book_report_class_roster: list[dict]
    ) -> None:
        """Test essay with email and complex name - Elina Rouzveh format."""
        # Add Elina to the roster
        extended_roster = book_report_class_roster + [
            {
                "student_id": "031",
                "first_name": "Elina",
                "last_name": "Rouzveh",
                "full_legal_name": "Elina Rouzveh",
                "email": "ec21004@harryda.se",
            }
        ]

        essay_text = """Elina Rouzveh 2023-02-27
Prov: Exam SA21C: Love, Relationships and Society
ec21004@harryda.se
Antal ord: 515
Focusing on Romantic Love is Bad for us

The phenomenon Romantic Love has been a topic of discussion for centuries. May I offer a
somewhat contreversiall opinion on this topic, romantic love consumes us to the point where
it is indeed bad for us."""

        correlation_id = uuid4()

        # Act
        suggestions = await student_matcher.find_matches(
            essay_text=essay_text,
            roster=extended_roster,
            correlation_id=correlation_id,
        )

        # Assert
        assert len(suggestions) >= 1

        top_suggestion = suggestions[0]
        assert top_suggestion.student_id == "031"
        assert top_suggestion.student_name == "Elina Rouzveh"
        assert top_suggestion.confidence_score >= 0.9
