# Suggested content for: tests/processing/conftest.py
"""Shared fixtures for essay processor tests."""

import logging
import tempfile
from pathlib import Path
from typing import Tuple
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.cj_essay_assessment.config import Settings
from src.cj_essay_assessment.db.db_handler import DatabaseHandler
from src.cj_essay_assessment.db.models_db import (BatchStatusEnum, BatchUpload,
                                                  ProcessedEssay,
                                                  ProcessedEssayStatusEnum,
                                                  User)

# Determine project root to make data/essays path reliable
# This assumes conftest.py is in tests/processing/
PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def mock_settings() -> Settings:
    """Fixture for mock Settings object."""
    settings = MagicMock(spec=Settings)
    settings.default_spell_check_language = "en_US"
    settings.supported_spell_check_languages = ["en_US", "en_GB", "sv_SE"]

    # Point to the actual data/essays directory for real file loading
    # Ensure this path is correct relative to your project root when tests are run
    settings.essay_input_dir = str(PROJECT_ROOT / "data" / "essays")

    # Mock properties for paths that might be created by Settings
    settings._temp_dir_for_essay_input_path_conftest = tempfile.TemporaryDirectory()
    mock_path_for_essays_property = Path(
        settings._temp_dir_for_essay_input_path_conftest.name
    )  # If essay_input_path property is used
    type(settings).essay_input_path = PropertyMock(
        return_value=mock_path_for_essays_property
    )

    settings._temp_dir_for_cache_path_conftest = tempfile.TemporaryDirectory()
    mock_path_for_cache = Path(settings._temp_dir_for_cache_path_conftest.name)
    type(settings).cache_directory_path = PropertyMock(return_value=mock_path_for_cache)

    settings.nlp_features_to_compute = ["word_count", "avg_word_length"]
    return settings


@pytest.fixture
def mock_db_handler_with_sessions() -> tuple[DatabaseHandler, AsyncMock, AsyncMock]:
    handler = MagicMock(spec=DatabaseHandler)
    mock_session_obj1 = AsyncMock(spec=AsyncSession, name="mock_session_1")
    mock_session_obj1.flush = AsyncMock()
    mock_session_obj1.execute = AsyncMock()
    mock_session_obj1.commit = AsyncMock()

    mock_session_obj2 = AsyncMock(spec=AsyncSession, name="mock_session_2")
    mock_session_obj2.flush = AsyncMock()
    mock_session_obj2.execute = AsyncMock()
    mock_session_obj2.commit = AsyncMock()

    mock_ctx_mgr = MagicMock(name="db_handler.session_context_manager_mock")
    mock_ctx_mgr.__aenter__ = AsyncMock(
        side_effect=[
            mock_session_obj1,
            mock_session_obj2,
            mock_session_obj1,
            mock_session_obj2,
            mock_session_obj1,
            mock_session_obj2,
        ]
    )  # More for safety
    mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)

    handler.session = MagicMock(return_value=mock_ctx_mgr, name="db_handler.session_mock")
    handler.get_batch_by_id = AsyncMock(name="db_handler.get_batch_by_id_mock")
    handler.update_batch_status = AsyncMock(name="db_handler.update_batch_status_mock")
    handler.get_essays_by_batch = AsyncMock(name="db_handler.get_essays_by_batch_mock")

    return handler, mock_session_obj1, mock_session_obj2


@pytest.fixture
def sample_user() -> User:
    user = User(id=1, username="testuser_conftest")
    return user


@pytest.fixture
def sample_batch(sample_user: User) -> BatchUpload:
    batch = BatchUpload(
        id=10,
        user_id=sample_user.id,
        name="Test Batch Upload Conftest DOCX",  # Updated name
        status=BatchStatusEnum.PENDING,
    )
    batch.essays = []
    return batch


@pytest.fixture
def sample_essay_uploaded(sample_batch: BatchUpload) -> ProcessedEssay:
    """Fixture for a sample ProcessedEssay, intended to load a real DOCX file."""
    essay = ProcessedEssay(
        id=101,
        batch_id=sample_batch.id,
        # Use one of your actual filenames
        original_filename="MHHXGLCG 50 (SA24D ENG 5 WRITING 2025).docx",
        original_content=None,  # Set to None to trigger file loading by SUT
        status=ProcessedEssayStatusEnum.UPLOADED,
        processed_content=None,  # Will be populated by SUT
        processing_metadata={},
    )
    essay.batch = sample_batch
    return essay


@pytest.fixture
def sample_essay_processed(sample_batch: BatchUpload) -> ProcessedEssay:
    # This fixture can remain as is, or also be based on a docx if needed for other tests
    essay = ProcessedEssay(
        id=102,
        batch_id=sample_batch.id,
        original_filename="essay2_processed_conftest.docx",  # Example
        original_content="Some original pre-processed DOCX content.",
        processed_content="Some processed DOCX content.",
        status=ProcessedEssayStatusEnum.READY_FOR_PAIRING,
        processing_metadata={
            "spell_errors_count": 0,
            "file_attributes": {
                "word_count": 4,
                "character_count": 30,
                "original_filename_provided": "essay2_processed_conftest.docx",
            },
        },
    )
    essay.batch = sample_batch
    return essay


@pytest.fixture(autouse=True)
def caplog_interceptor(caplog: pytest.LogCaptureFixture) -> None:
    try:
        logger.remove()
    except ValueError:
        pass

    class PropagateHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            logging.getLogger(record.name).handle(record)

    logger.add(PropagateHandler(), format="{message}", level="DEBUG")
    caplog.set_level(logging.DEBUG)
