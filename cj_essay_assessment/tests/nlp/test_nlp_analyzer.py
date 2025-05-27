"""Tests for the NLP Analyzer module (spaCy + TextDescriptives version).

This test suite covers the functionality of nlp_analyzer.py, including:
- spaCy model loading and textdescriptives pipe integration.
- Individual NLP feature calculation/extraction functions using spaCy Doc objects.
- The main orchestration function `compute_and_store_nlp_stats`.
- Database interaction for fetching essays and storing results.
"""

import logging
from collections.abc import Callable, Generator, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import spacy
from spacy.tokens import Doc
from sqlalchemy.ext.asyncio import AsyncSession

# Imports from the source code being tested
from src.cj_essay_assessment.config import Settings
from src.cj_essay_assessment.db.db_handler import DatabaseHandler
from src.cj_essay_assessment.db.models_db import (ProcessedEssay,
                                                  ProcessedEssayStatusEnum)
from src.cj_essay_assessment.models_api import EssayForComparison
from src.cj_essay_assessment.nlp_analyzer import (
    SPACY_MODEL_NAME, TEXTDESCRIPTIVES_PIPE_NAME,
    _calculate_noun_to_verb_ratio, _ensure_spacy_model_loaded,
    _extract_avg_word_length, _extract_readability_flesch_kincaid_grade,
    _extract_word_count, compute_and_store_nlp_stats)

# --- Token Factory Functions (Moved outside test function) ---


class TokenIteratorFactory:
    """Callable class to create fresh iterators with fresh tokens."""

    def __init__(self, token_list_factory: Callable[[], list[MagicMock]]) -> None:
        self._token_list_factory = token_list_factory
        self.call_count = 0

    def __call__(self) -> Iterator[MagicMock]:
        self.call_count += 1
        print(
            f"DEBUG: TokenIteratorFactory called ({self.call_count} times for "
            f"{self._token_list_factory.__name__}). Creating new token list.",
        )
        # Crucially, call the factory function *here* to get fresh tokens
        new_token_list = self._token_list_factory()
        return iter(new_token_list)


# --- Fixtures ---


@pytest.fixture(autouse=True)
def reset_global_nlp_model_fixture() -> Generator[None, None, None]:
    """Resets nlp_analyzer.NLP_MODEL for each test."""
    import src.cj_essay_assessment.nlp_analyzer as nlp_analyzer_module

    original_model = nlp_analyzer_module.NLP_MODEL
    nlp_analyzer_module.NLP_MODEL = None
    try:
        yield
    finally:
        nlp_analyzer_module.NLP_MODEL = original_model


@pytest.fixture
def mock_settings() -> MagicMock:
    """Fixture for a mocked Settings object."""
    settings = MagicMock(spec=Settings)
    settings.nlp_features_to_compute = [
        "word_count",
        "avg_word_length",
        "noun_to_verb_ratio",
        "flesch_kincaid_grade",
        "spelling_errors_count",
    ]
    return settings


@pytest.fixture
def mock_db_handler() -> MagicMock:
    """Fixture for a mocked DatabaseHandler object."""
    db_handler = MagicMock(spec=DatabaseHandler)

    # Mock the session object that __aenter__ will return
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.flush = AsyncMock()  # Mock the flush method on the session

    # Configure the async context manager mock for db_handler.session()
    session_context_manager = AsyncMock()
    session_context_manager.__aenter__.return_value = mock_session
    session_context_manager.__aexit__.return_value = None

    # Make db_handler.session return the configured context manager mock
    db_handler.session = MagicMock(return_value=session_context_manager)

    # Mock the method that gets called *with* the session
    db_handler.get_essay_by_id = AsyncMock(return_value=None)
    db_handler.get_batch_by_id_with_essays = (
        AsyncMock()
    )  # Add mocks for other used methods if needed
    db_handler.update_batch_status = AsyncMock()

    return db_handler


@pytest.fixture
def sample_essay_api_model() -> EssayForComparison:
    """Fixture for a sample EssayForComparison Pydantic model."""
    return EssayForComparison(
        id=1,
        original_filename="test_essay.txt",
        text_content="This is a sample essay text for testing purposes.",
        current_bt_score=0.5,
    )


@pytest.fixture
def sample_processed_essay_orm() -> ProcessedEssay:
    """Fixture for a sample ProcessedEssay ORM model."""
    essay = ProcessedEssay(
        id=1,
        batch_id=1,
        original_filename="test_essay.txt",
        original_content="Original text.",
        processed_content="Detta är en exempeltext. Den har några ord och meningar.",
        status=ProcessedEssayStatusEnum.SPELLCHECKED,
        nlp_features=None,  # Start with None, to be populated
        processing_metadata={"spell_errors_count": 2},  # Example pre-existing metadata
    )
    return essay


@pytest.fixture
def mock_spacy_doc() -> MagicMock:
    """Creates a mock spaCy Doc with mocked textdescriptives attributes."""
    doc_mock = MagicMock(spec=Doc)

    # Use the separate factory function for consistency (optional but good practice)
    # Keep using the lambda side_effect here as it was working for Case 1 previously
    doc_mock.__iter__.side_effect = lambda: iter(create_mock_spacy_doc_tokens())
    doc_mock.__len__.return_value = len(create_mock_spacy_doc_tokens())
    doc_mock.text = "Detta är en exempeltext."

    # Mock textdescriptives attributes accessed via `doc._.`
    doc_mock._ = MagicMock()
    doc_mock._.counts = {"n_tokens": 5}
    doc_mock._.token_length = {"mean": 4.0}
    doc_mock._.readability = {"flesch_kincaid_grade": 8.5}

    return doc_mock


# --- Tests for _ensure_spacy_model_loaded ---


@pytest.mark.asyncio
@patch("spacy.load")
async def test_ensure_spacy_model_loaded_success(
    mock_spacy_load: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test successful loading of spaCy model and adding textdescriptives pipe."""
    mock_nlp_instance = MagicMock(spec=spacy.language.Language)
    mock_nlp_instance.meta = {"name": SPACY_MODEL_NAME.split("_")[0], "lang": "sv"}
    mock_nlp_instance.pipe_names = []  # Start with no pipes
    mock_nlp_instance.add_pipe = MagicMock()
    mock_spacy_load.return_value = mock_nlp_instance

    caplog.set_level(logging.INFO)
    assert await _ensure_spacy_model_loaded(SPACY_MODEL_NAME) is True
    mock_spacy_load.assert_called_once_with(SPACY_MODEL_NAME)

    import src.cj_essay_assessment.nlp_analyzer as nlp_analyzer_module

    assert mock_nlp_instance == nlp_analyzer_module.NLP_MODEL
    mock_nlp_instance.add_pipe.assert_called_once_with(TEXTDESCRIPTIVES_PIPE_NAME)
    assert f"spaCy model '{SPACY_MODEL_NAME}' loaded successfully" in caplog.text
    assert f"Added '{TEXTDESCRIPTIVES_PIPE_NAME}' pipe to spaCy model." in caplog.text


@pytest.mark.asyncio
@patch("spacy.load")
async def test_ensure_spacy_model_already_loaded_with_pipe(
    mock_spacy_load: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test behavior when model is already loaded WITH the textdescriptives pipe."""
    import src.cj_essay_assessment.nlp_analyzer as nlp_analyzer_module

    mock_nlp_instance = MagicMock(spec=spacy.language.Language)
    mock_nlp_instance.meta = {"name": SPACY_MODEL_NAME.split("_")[0], "lang": "sv"}
    mock_nlp_instance.pipe_names = [
        TEXTDESCRIPTIVES_PIPE_NAME.split("/")[0],
    ]  # Simulate pipe already exists
    nlp_analyzer_module.NLP_MODEL = mock_nlp_instance

    caplog.set_level(logging.DEBUG)
    assert await _ensure_spacy_model_loaded(SPACY_MODEL_NAME) is True
    mock_spacy_load.assert_not_called()
    assert f"with '{TEXTDESCRIPTIVES_PIPE_NAME}' pipe already loaded." in caplog.text


@pytest.mark.asyncio
@patch("spacy.load", side_effect=OSError("Model not found"))
async def test_ensure_spacy_model_not_found(
    mock_spacy_load: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test handling OSError when model is not found."""
    caplog.set_level(logging.ERROR)
    assert await _ensure_spacy_model_loaded("non_existent_model") is False
    mock_spacy_load.assert_called_once_with("non_existent_model")

    import src.cj_essay_assessment.nlp_analyzer as nlp_analyzer_module

    assert nlp_analyzer_module.NLP_MODEL is None
    assert "spaCy model 'non_existent_model' not found." in caplog.text


# --- Tests for individual NLP feature functions ---


def test_extract_word_count(
    mock_spacy_doc: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test word count extraction from textdescriptives mock."""
    caplog.set_level(logging.WARNING)
    assert _extract_word_count(mock_spacy_doc) == 5
    # Test missing attribute/key
    del mock_spacy_doc._.counts["n_tokens"]
    assert _extract_word_count(mock_spacy_doc) is None
    assert "Could not extract word count" in caplog.text
    # Test None input
    assert _extract_word_count(None) is None


def test_extract_avg_word_length(
    mock_spacy_doc: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test average word length extraction from textdescriptives mock."""
    caplog.set_level(logging.WARNING)
    assert _extract_avg_word_length(mock_spacy_doc) == 4.0
    # Test missing attribute/key
    del mock_spacy_doc._.token_length["mean"]
    assert _extract_avg_word_length(mock_spacy_doc) is None
    assert "Could not extract avg word length" in caplog.text
    # Test None input
    assert _extract_avg_word_length(None) is None


# Define simple token factory functions outside the test function
def create_mock_spacy_doc_tokens() -> list:
    """Creates tokens similar to the mock_spacy_doc fixture."""
    return [
        MagicMock(text="Detta", is_alpha=True, pos_="PRON"),
        MagicMock(text="är", is_alpha=True, pos_="VERB"),
        MagicMock(text="en", is_alpha=True, pos_="DET"),
        MagicMock(text="exempeltext", is_alpha=True, pos_="NOUN"),
        MagicMock(text=".", is_alpha=False, pos_="PUNCT"),
    ]


def create_no_verbs_token_list() -> list:
    """Creates mock tokens with only NOUNs using constructor kwargs."""
    token1 = MagicMock(is_alpha=True, pos_="NOUN")
    token2 = MagicMock(is_alpha=True, pos_="NOUN")
    return [token1, token2]


def create_no_nouns_token_list() -> list:
    """Creates mock tokens with only VERBs using constructor kwargs."""
    token1 = MagicMock(is_alpha=True, pos_="VERB")
    return [token1]


def test_calculate_noun_to_verb_ratio(mock_spacy_doc: MagicMock) -> None:
    """Test noun-to-verb ratio calculation (manual from Doc)."""
    # Case 1: Uses mock_spacy_doc fixture (1 NOUN, 1 VERB)
    # (Ensure mock_spacy_doc fixture also uses create_mock_spacy_doc_tokens if desired)
    assert _calculate_noun_to_verb_ratio(mock_spacy_doc) == 1.0

    # --- Case 2: Test no verbs -> inf ---
    # Use MagicMock WITHOUT spec=Doc for the iterable mock
    doc_no_verbs = MagicMock()
    # Use lambda for the side_effect, calling the appropriate factory
    doc_no_verbs.__iter__.side_effect = lambda: iter(create_no_verbs_token_list())
    assert _calculate_noun_to_verb_ratio(doc_no_verbs) == float("inf")

    # --- Case 3: Test no nouns -> 0.0 ---
    # Use MagicMock WITHOUT spec=Doc for the iterable mock
    doc_no_nouns = MagicMock()
    # Use lambda for the side_effect, calling the appropriate factory
    doc_no_nouns.__iter__.side_effect = lambda: iter(create_no_nouns_token_list())
    assert _calculate_noun_to_verb_ratio(doc_no_nouns) == 0.0

    # --- Case 4: Test None input ---
    assert _calculate_noun_to_verb_ratio(None) is None


def test_extract_readability_flesch_kincaid_grade(
    mock_spacy_doc: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test Flesch-Kincaid grade extraction from textdescriptives mock."""
    caplog.set_level(logging.WARNING)
    assert _extract_readability_flesch_kincaid_grade(mock_spacy_doc) == 8.5
    # Test missing attribute/key
    del mock_spacy_doc._.readability["flesch_kincaid_grade"]
    assert _extract_readability_flesch_kincaid_grade(mock_spacy_doc) is None
    assert "Flesch-Kincaid grade attribute not found" in caplog.text
    # Test None input
    assert _extract_readability_flesch_kincaid_grade(None) is None


# --- Tests for compute_and_store_nlp_stats ---


@pytest.mark.asyncio
@patch(
    "src.cj_essay_assessment.nlp_analyzer._ensure_spacy_model_loaded",
    new_callable=AsyncMock,
)
@patch("src.cj_essay_assessment.nlp_analyzer.NLP_MODEL")
async def test_compute_all_nlp_stats_updates_db(
    mock_nlp_model_global: MagicMock,
    mock_ensure_spacy: AsyncMock,
    mock_db_handler: MagicMock,
    mock_settings: MagicMock,
    sample_essay_api_model: EssayForComparison,
    sample_processed_essay_orm: ProcessedEssay,
    mock_spacy_doc: MagicMock,  # Use the general doc mock fixture
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test NLP stats computation and DB storage (TextDescriptives)."""
    caplog.set_level(logging.INFO)
    mock_ensure_spacy.return_value = True

    # Configure the mock_nlp_model_global to return the mock_spacy_doc
    # This simulates the NLP_MODEL(text) call
    mock_nlp_model_global.return_value = mock_spacy_doc
    # Make the mock callable (like the real nlp object)
    # No, NLP_MODEL itself isn't called, it's used like: doc = NLP_MODEL(text)
    # So, we need to patch NLP_MODEL itself, and make *it* return the doc when called.
    # The @patch decorator already replaces NLP_MODEL with a mock.
    # We need to configure *that* mock's return value when it's called.
    # The first mock argument 'mock_nlp_model_global' *is* the patched NLP_MODEL.
    mock_nlp_model_global.side_effect = (
        lambda text: mock_spacy_doc
    )  # Make it return the fixture doc when called

    mock_db_handler.get_essay_by_id.return_value = sample_processed_essay_orm

    await compute_and_store_nlp_stats(
        mock_db_handler,
        mock_settings,
        [sample_essay_api_model],
    )

    mock_ensure_spacy.assert_called_once()
    # Get the mock session instance used within the 'async with' block
    mock_session_instance = mock_db_handler.session.return_value.__aenter__.return_value
    mock_db_handler.get_essay_by_id.assert_called_once_with(
        mock_session_instance,
        sample_essay_api_model.id,
    )
    # Check that the NLP model (the patched global) was called with the essay text
    mock_nlp_model_global.assert_called_once_with(
        sample_processed_essay_orm.processed_content,
    )

    # Verify results stored in the DB mock object
    assert sample_processed_essay_orm.nlp_features is not None
    # Use values derived from mock_spacy_doc and the ORM fixture
    assert (
        sample_processed_essay_orm.nlp_features["word_count"] == 5
    )  # From mock_spacy_doc._.counts
    assert (
        sample_processed_essay_orm.nlp_features["avg_word_length"] == 4.0
    )  # From mock_spacy_doc._.token_length
    assert (
        sample_processed_essay_orm.nlp_features["noun_to_verb_ratio"] == 1.0
    )  # Calculated from mock_spacy_doc tokens
    assert (
        sample_processed_essay_orm.nlp_features["flesch_kincaid_grade"] == 8.5
    )  # From mock_spacy_doc._.readability
    assert (
        sample_processed_essay_orm.nlp_features["spelling_errors_count"] == 2
    )  # From ORM fixture metadata

    # Verify nlp_analysis_complete flag was set to True (Task 2.6 implementation)
    assert sample_processed_essay_orm.nlp_analysis_complete is True

    mock_session_instance.flush.assert_called()  # Should be called at least once
    # Check commit was called at the end
    mock_session_instance.commit.assert_called_once()
    assert (
        f"Essay ID {sample_processed_essay_orm.id}: NLP analysis completed and flag set to True."
        in caplog.text
    )


@pytest.mark.asyncio
@patch(
    "src.cj_essay_assessment.nlp_analyzer._ensure_spacy_model_loaded",
    new_callable=AsyncMock,
)
async def test_compute_nlp_stats_model_load_fail(
    mock_ensure_spacy: AsyncMock,
    mock_db_handler: MagicMock,
    mock_settings: MagicMock,
    sample_essay_api_model: EssayForComparison,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that computation halts if spaCy model fails to load."""
    mock_ensure_spacy.return_value = False
    caplog.set_level(logging.ERROR)

    await compute_and_store_nlp_stats(
        mock_db_handler,
        mock_settings,
        [sample_essay_api_model],
    )

    mock_ensure_spacy.assert_called_once()
    mock_db_handler.get_essay_by_id.assert_not_called()
    assert "Halting NLP statistics computation" in caplog.text


@pytest.mark.asyncio
@patch(
    "src.cj_essay_assessment.nlp_analyzer._ensure_spacy_model_loaded",
    new_callable=AsyncMock,
)
@patch("src.cj_essay_assessment.nlp_analyzer.NLP_MODEL")
async def test_compute_nlp_stats_essay_not_found(
    mock_nlp_model_global: MagicMock,
    mock_ensure_spacy: AsyncMock,
    mock_db_handler: MagicMock,
    mock_settings: MagicMock,
    sample_essay_api_model: EssayForComparison,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test behavior for essay not found in DB."""
    mock_ensure_spacy.return_value = True
    mock_db_handler.get_essay_by_id.return_value = None

    caplog.set_level(logging.WARNING)
    await compute_and_store_nlp_stats(
        mock_db_handler,
        mock_settings,
        [sample_essay_api_model],
    )
    # Get the mock session instance
    mock_session_instance = mock_db_handler.session.return_value.__aenter__.return_value
    mock_db_handler.get_essay_by_id.assert_called_once_with(
        mock_session_instance,
        sample_essay_api_model.id,
    )
    assert f"Essay ID {sample_essay_api_model.id} not found" in caplog.text
    mock_nlp_model_global.assert_not_called()


@pytest.mark.asyncio
@patch(
    "src.cj_essay_assessment.nlp_analyzer._ensure_spacy_model_loaded",
    new_callable=AsyncMock,
)
@patch("src.cj_essay_assessment.nlp_analyzer.NLP_MODEL")
async def test_compute_nlp_stats_empty_text_content(
    mock_nlp_model_global: MagicMock,
    mock_ensure_spacy: AsyncMock,
    mock_db_handler: MagicMock,
    mock_settings: MagicMock,
    sample_essay_api_model: EssayForComparison,
    sample_processed_essay_orm: ProcessedEssay,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test essay with no processed content."""
    mock_ensure_spacy.return_value = True
    sample_processed_essay_orm.processed_content = ""  # Make content empty
    mock_db_handler.get_essay_by_id.return_value = sample_processed_essay_orm

    caplog.set_level(logging.WARNING)
    await compute_and_store_nlp_stats(
        mock_db_handler,
        mock_settings,
        [sample_essay_api_model],
    )

    # Get the mock session instance
    mock_session_instance = mock_db_handler.session.return_value.__aenter__.return_value
    mock_db_handler.get_essay_by_id.assert_called_once_with(
        mock_session_instance,
        sample_essay_api_model.id,
    )

    assert (
        f"Essay ID {sample_processed_essay_orm.id} has no processed text content"
        in caplog.text
    )
    assert sample_processed_essay_orm.nlp_features == {}
    # Status should not change - NLP tasks won't change the essay status anymore as per Task 2.6 requirements
    mock_nlp_model_global.assert_not_called()
    mock_session_instance.flush.assert_called_once()
    mock_session_instance.commit.assert_called_once()


@pytest.mark.asyncio
@patch(
    "src.cj_essay_assessment.nlp_analyzer._ensure_spacy_model_loaded",
    new_callable=AsyncMock,
)
@patch("src.cj_essay_assessment.nlp_analyzer.NLP_MODEL")
@patch("src.cj_essay_assessment.nlp_analyzer._extract_avg_word_length")
async def test_compute_nlp_stats_feature_extraction_error(
    mock_extract_avg_word_length: MagicMock,
    mock_nlp_model_global: MagicMock,
    mock_ensure_spacy: AsyncMock,
    mock_db_handler: MagicMock,
    mock_settings: MagicMock,
    sample_essay_api_model: EssayForComparison,
    sample_processed_essay_orm: ProcessedEssay,
    mock_spacy_doc: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test handling of a specific error during one feature extraction."""
    caplog.set_level(logging.ERROR)
    mock_ensure_spacy.return_value = True
    mock_nlp_model_global.return_value = mock_spacy_doc
    mock_db_handler.get_essay_by_id.return_value = sample_processed_essay_orm

    # Make the patched feature extractor raise a specific error
    mock_extract_avg_word_length.side_effect = KeyError("Simulated key error")

    await compute_and_store_nlp_stats(
        mock_db_handler,
        mock_settings,
        [sample_essay_api_model],
    )

    # Get the mock session instance
    mock_session_instance = mock_db_handler.session.return_value.__aenter__.return_value

    # Verify the specific error was logged
    assert "Feature 'avg_word_length' error" in caplog.text
    assert "Simulated key error" in caplog.text

    # Verify the feature is None in the result
    assert sample_processed_essay_orm.nlp_features is not None
    assert sample_processed_essay_orm.nlp_features["avg_word_length"] is None

    # Verify other features were still computed (using values from mock_spacy_doc)
    assert sample_processed_essay_orm.nlp_features["word_count"] == 5
    assert sample_processed_essay_orm.nlp_features["noun_to_verb_ratio"] == 1.0
    assert sample_processed_essay_orm.nlp_features["flesch_kincaid_grade"] == 8.5

    # Verify the overall essay status is still NLP_ANALYZED, not ERROR_PROCESSING
    # Status should not be changed by NLP - Status updates removed per Task 2.6 requirements

    # Verify db interactions
    mock_session_instance.flush.assert_called()
    mock_session_instance.commit.assert_called_once()


@pytest.mark.asyncio
@patch(
    "src.cj_essay_assessment.nlp_analyzer._ensure_spacy_model_loaded",
    new_callable=AsyncMock,
)
@patch("src.cj_essay_assessment.nlp_analyzer.NLP_MODEL")
async def test_compute_nlp_stats_specific_processing_error(
    mock_nlp_model_global: MagicMock,
    mock_ensure_spacy: AsyncMock,
    mock_db_handler: MagicMock,
    mock_settings: MagicMock,
    sample_essay_api_model: EssayForComparison,
    sample_processed_essay_orm: ProcessedEssay,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test handling of specific errors (e.g., TypeError) during main processing."""
    caplog.set_level(logging.ERROR)
    mock_ensure_spacy.return_value = True
    mock_db_handler.get_essay_by_id.return_value = sample_processed_essay_orm

    # Make the NLP_MODEL call raise a specific error
    mock_nlp_model_global.side_effect = TypeError("Simulated type error on doc creation")

    await compute_and_store_nlp_stats(
        mock_db_handler,
        mock_settings,
        [sample_essay_api_model],
    )

    # Get the mock session instance
    mock_session_instance = mock_db_handler.session.return_value.__aenter__.return_value

    # Verify the specific error was logged
    assert "Specific processing error" in caplog.text
    assert "Simulated type error on doc creation" in caplog.text

    # Verify the essay status is ERROR_PROCESSING
    assert sample_processed_essay_orm.nlp_analysis_complete is False

    # Verify metadata was updated
    assert sample_processed_essay_orm.processing_metadata is not None
    assert (
        sample_processed_essay_orm.processing_metadata.get("nlp_error")
        == "Simulated type error on doc creation"
    )

    # Verify the nested flush for the error status was called
    # The first call inside the specific error handler
    mock_session_instance.flush.assert_called_once()

    # Verify commit was still called at the end to finalize the transaction
    mock_session_instance.commit.assert_called_once()


@pytest.mark.asyncio
@patch(
    "src.cj_essay_assessment.nlp_analyzer._ensure_spacy_model_loaded",
    new_callable=AsyncMock,
)
@patch("src.cj_essay_assessment.nlp_analyzer.NLP_MODEL")
async def test_compute_nlp_stats_general_processing_error(
    mock_nlp_model_global: MagicMock,
    mock_ensure_spacy: AsyncMock,
    mock_db_handler: MagicMock,
    mock_settings: MagicMock,
    sample_essay_api_model: EssayForComparison,
    sample_processed_essay_orm: ProcessedEssay,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test handling of general/unexpected errors during main processing."""
    caplog.set_level(logging.ERROR)
    mock_ensure_spacy.return_value = True
    mock_db_handler.get_essay_by_id.return_value = sample_processed_essay_orm

    # Make the NLP_MODEL call raise a generic Exception
    mock_nlp_model_global.side_effect = Exception("Simulated generic error")

    await compute_and_store_nlp_stats(
        mock_db_handler,
        mock_settings,
        [sample_essay_api_model],
    )

    # Get the mock session instance
    mock_session_instance = mock_db_handler.session.return_value.__aenter__.return_value

    # Verify the general error was logged (using logger.exception)
    assert "Unexpected error processing NLP stats" in caplog.text
    assert "Simulated generic error" in caplog.text

    # Verify the essay status is ERROR_PROCESSING
    assert sample_processed_essay_orm.nlp_analysis_complete is False

    # Verify metadata was updated
    assert sample_processed_essay_orm.processing_metadata is not None
    assert (
        sample_processed_essay_orm.processing_metadata.get("nlp_error")
        == "Unexpected: Simulated generic error"
    )

    # Verify the nested flush for the error status was called
    mock_session_instance.flush.assert_called_once()

    # Verify commit was still called at the end
    mock_session_instance.commit.assert_called_once()


@pytest.mark.asyncio
@patch(
    "src.cj_essay_assessment.nlp_analyzer._ensure_spacy_model_loaded",
    new_callable=AsyncMock,
)
@patch("src.cj_essay_assessment.nlp_analyzer.NLP_MODEL")
async def test_compute_nlp_stats_error_save_fails(
    mock_nlp_model_global: MagicMock,
    mock_ensure_spacy: AsyncMock,
    mock_db_handler: MagicMock,
    mock_settings: MagicMock,
    sample_essay_api_model: EssayForComparison,
    sample_processed_essay_orm: ProcessedEssay,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test handling when saving the ERROR_PROCESSING status itself fails."""
    caplog.set_level(logging.CRITICAL)  # Expect critical log message
    mock_ensure_spacy.return_value = True
    mock_db_handler.get_essay_by_id.return_value = sample_processed_essay_orm

    # Make the NLP_MODEL call raise an error to trigger error handling
    mock_nlp_model_global.side_effect = TypeError("Trigger error path")

    # Mock the session flush call *within* the error handler to fail
    mock_session_instance = mock_db_handler.session.return_value.__aenter__.return_value
    mock_session_instance.flush = AsyncMock(side_effect=Exception("DB flush failed"))

    await compute_and_store_nlp_stats(
        mock_db_handler,
        mock_settings,
        [sample_essay_api_model],
    )

    # Verify the critical log message was emitted
    assert "Failed to save NLP error info" in caplog.text
    assert "DB flush failed" in caplog.text

    # Verify the essay status was set to ERROR_PROCESSING before the failed flush
    assert sample_processed_essay_orm.nlp_analysis_complete is False

    # Verify the flush was attempted (once, within the specific error handler)
    mock_session_instance.flush.assert_called_once()

    # Verify commit was still called at the end (attempting to finalize)
    mock_session_instance.commit.assert_called_once()
