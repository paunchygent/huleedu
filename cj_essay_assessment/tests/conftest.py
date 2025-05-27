"""Pytest configuration for the CJ Essay Assessment tests.

This module contains shared fixtures and configuration for all test modules,
including Docker management via testcontainers for integration tests.
"""

# --- Loguru Configuration for Pytest ---
import logging  # Added import
# --- Standard Library ---
import os
import sys
import tracemalloc
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from pathlib import Path
from typing import Any, TypeVar
from unittest.mock import AsyncMock, patch

# --- Third-Party ---
import pytest
import pytest_asyncio
from loguru import \
    logger as \
    loguru_logger  # Added import and alias to avoid conflict if pytest uses 'logger'
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncSession,
                                    async_sessionmaker, create_async_engine)
from testcontainers.postgres import PostgresContainer

from src.cj_essay_assessment.db.models_db import (Base, BatchUpload,
                                                  ProcessedEssay, User)
# --- Application Imports ---
from src.cj_essay_assessment.llm_caller import ComparisonResult, ComparisonTask
from src.cj_essay_assessment.models_api import LLMAssessmentResponseSchema


class PropagateHandler(logging.Handler):
    def emit(self, record):
        logging.getLogger(record.name).handle(record)


@pytest.fixture(scope="session", autouse=True)
def configure_loguru_for_pytest_caplog():
    """Configure Loguru to propagate messages to standard logging for caplog.

    This is an autouse session fixture, so it runs once per test session.
    """
    # Remove default Loguru handler to prevent duplicate outputs if already configured elsewhere
    # Be cautious if other parts of the test suite rely on the default stderr sink
    try:
        loguru_logger.remove(0)  # Attempt to remove the default handler (ID 0)
    except ValueError:  # Handler 0 might not exist if Loguru isn't used or configured yet
        pass

    # Add a handler that sinks to our PropagateHandler
    # This ensures that Loguru's messages are passed to the standard logging system
    # which pytest's caplog can then capture.
    # Use a level that ensures all messages (DEBUG and above) are passed through.
    # The actual filtering can then be done by caplog or standard logging handlers if needed.
    loguru_logger.add(PropagateHandler(), format="{message}", level="DEBUG")
    # Set propagate to False for the root loguru logger to prevent direct output if not desired,
    # as we are now explicitly handling propagation via the handler.
    # However, for caplog to work, the loggers it captures *must* propagate.
    # The PropagateHandler itself ensures messages reach the named standard loggers.
    # loguru_logger.propagate = True # This line for the root loguru logger might be tricky, let's test without first


# --- Miscellaneous Setup ---
tracemalloc.start(10)

SRC_PATH = str(Path(__file__).parent.parent / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)


@pytest.fixture
def test_config_yml() -> str:
    """Return a path to a test config.yml file."""
    return os.path.join(os.path.dirname(__file__), "fixtures", "test_config.yml")


@pytest.fixture
def mock_env_vars() -> Generator[None, None, None]:
    """Provide common environment variables for testing (mocks .env loading)."""
    test_values = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "LOG_LEVEL": "DEBUG",
        "OPENAI_API_KEY": "test_openai_key",
        "ANTHROPIC_API_KEY": "test_anthropic_key",
        "GOOGLE_API_KEY": "test_google_key",
        "OPENROUTER_API_KEY": "test_openrouter_key",
    }
    with patch.dict(os.environ, test_values):
        with patch("pathlib.Path.exists", return_value=True):
            yield


@pytest.fixture
def yaml_config_data() -> dict[str, Any]:
    """Provide sample YAML configuration data."""
    return {
        "default_provider": "openai",
        "temperature": 0.5,
        "max_tokens_response": 500,
        "system_prompt": "Test prompt",
        "llm_providers": {
            "openai": {"api_base": "https://test.openai.com"},
            "anthropic": {"api_base": None},
            "google": {"api_base": None},
            "openrouter": {"api_base": "https://test.openrouter.ai/api/v1"},
        },
        "max_pairwise_comparisons": 100,
        "score_stability_threshold": 0.01,
    }


@pytest.fixture
def mock_yaml_file(
    yaml_config_data: dict[str, Any],
) -> Generator[dict[str, Any], None, None]:
    """Mock YAML file loading with provided config data."""
    yaml_content = yaml_config_data
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", create=True):
            with patch("yaml.safe_load", return_value=yaml_content):
                yield yaml_content


@pytest.fixture
def mock_hunspell_files(tmp_path: Path) -> Generator[dict[str, Path], None, None]:
    """Create mock Hunspell dictionary and affix files."""
    dic_file = tmp_path / "test.dic"
    aff_file = tmp_path / "test.aff"
    dic_file.write_text("5\nword1\nword2\nword3\nword4\nword5")
    # Break the long line for aff_file content
    aff_content_part1 = "SET UTF-8\nTRY "
    aff_content_part2 = "esianrtolcdugmphbyfvkwzESIANRTOLCDUGMPHBYFVKWZ"
    aff_file.write_text(aff_content_part1 + aff_content_part2)
    with patch.dict(
        os.environ,
        {"HUNSPELL_DIC_PATH": str(dic_file), "HUNSPELL_AFF_PATH": str(aff_file)},
    ):
        yield {"dic_path": dic_file, "aff_path": aff_file}


# --- Integration Test Fixtures using Testcontainers ---


T = TypeVar("T")


@pytest.fixture(scope="session")
def postgres_container(
    request: pytest.FixtureRequest,
) -> Generator[PostgresContainer, None, None]:
    """Manages the PostgreSQL Docker container for the test session using testcontainers.
    Reads credentials from environment variables (ideally loaded from .env).
    """
    container = PostgresContainer(
        image="postgres:14",
        username=os.getenv("POSTGRES_USER", "cj_user"),
        password=os.getenv("POSTGRES_PASSWORD", "cj_password"),
        dbname=os.getenv("POSTGRES_DB", "cj_assessment_db"),
    )
    try:
        print("\nStarting PostgreSQL container via testcontainers...")
        container.start()
        print("PostgreSQL container started.")
        yield container
    finally:
        print("\nStopping PostgreSQL container...")
        container.stop()
        print("PostgreSQL container stopped.")


@pytest_asyncio.fixture(scope="session")
async def async_db_engine(
    postgres_container: PostgresContainer,
) -> AsyncGenerator[AsyncEngine, None]:
    """Provides an SQLAlchemy AsyncEngine connected to the testcontainer PostgreSQL."""
    # Get the connection URL (might include +psycopg2)
    original_url = postgres_container.get_connection_url()
    # Replace the driver part to use asyncpg
    if original_url.startswith("postgresql+psycopg2://"):
        async_url = original_url.replace(
            "postgresql+psycopg2://",
            "postgresql+asyncpg://",
            1,
        )
    elif original_url.startswith("postgresql://"):
        async_url = original_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        # Fallback or raise error if URL format is unexpected
        raise ValueError(f"Unexpected PostgreSQL URL format: {original_url}")

    engine = create_async_engine(async_url, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def db_schema(async_db_engine: AsyncEngine) -> None:
    """Ensures the database schema is created cleanly for the test session.
    Drops all existing tables first, then creates them based on models_db.Base.
    """
    print("Applying database schema (drop/create)...")
    async with async_db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("Database schema applied.")


@pytest_asyncio.fixture(scope="function")
async def db_session(
    async_db_engine: AsyncEngine,
    db_schema: None,
) -> AsyncGenerator[AsyncSession, None]:
    """Provides an SQLAlchemy AsyncSession wrapped in a transaction for each test function.
    Depends on db_schema to ensure tables exist.
    """
    session_maker = async_sessionmaker(
        async_db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with session_maker() as session:
        async with session.begin_nested():
            yield session
    await session.close()


# --- Factory Fixtures (Rely on db_session) ---


@pytest_asyncio.fixture(scope="function")
async def user_factory(db_session: AsyncSession) -> Callable[..., Awaitable[User]]:
    async def _create_user(**kwargs: Any) -> User:
        defaults = {
            "username": f"testuser_{uuid.uuid4().hex[:8]}",
            "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
            "full_name": f"Test User {uuid.uuid4().hex[:4]}",
            "hashed_password": "test_password_hash",
        }
        attrs = {**defaults, **kwargs}
        user = User()
        for key, value in attrs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        db_session.add(user)
        await db_session.flush()
        await db_session.refresh(user)
        return user

    return _create_user


@pytest_asyncio.fixture(scope="function")
async def batch_upload_factory(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[BatchUpload]]:
    async def _create_batch_upload(user_id: int, **kwargs: Any) -> BatchUpload:
        defaults = {
            "name": f"Test Batch {uuid.uuid4().hex[:6]}",
            "status": "PENDING",
            "user_id": user_id,
            "description": "A test batch",
            "json_metadata": {"source": "factory"},
        }
        attrs = {**defaults, **kwargs}
        batch = BatchUpload()
        for key, value in attrs.items():
            if hasattr(batch, key):
                setattr(batch, key, value)
        db_session.add(batch)
        await db_session.flush()
        await db_session.refresh(batch)
        return batch

    return _create_batch_upload


@pytest_asyncio.fixture(scope="function")
async def processed_essay_factory(
    db_session: AsyncSession,
) -> Callable[..., Awaitable[ProcessedEssay]]:
    async def _create_processed_essay(batch_id: int, **kwargs: Any) -> ProcessedEssay:
        defaults = {
            "original_filename": f"essay_{uuid.uuid4().hex[:8]}.txt",
            "original_content": "This is sample factory essay content.",
            "processed_content": "This is sample factory essay content.",
            "status": "UPLOADED",
            "batch_id": batch_id,
            "processing_metadata": {},
            "nlp_features": {},
        }
        attrs = {**defaults, **kwargs}
        essay = ProcessedEssay()
        for key, value in attrs.items():
            if hasattr(essay, key):
                setattr(essay, key, value)
        db_session.add(essay)
        await db_session.flush()
        await db_session.refresh(essay)
        return essay

    return _create_processed_essay


# --- Mocking Fixtures ---


@pytest.fixture(scope="function")
def mock_llm_caller(mocker: MockerFixture) -> AsyncMock:
    """Mocks llm_caller.process_comparison_tasks_async, returns AsyncMock."""

    async def default_llm_side_effect(
        tasks: list[ComparisonTask],
        *args: Any,
        **kwargs: Any,
    ) -> list[ComparisonResult]:
        results = []
        for task_item in tasks:
            mock_assessment = LLMAssessmentResponseSchema(
                winner="Essay A",
                justification="Mocked: Essay A was preferred due to clarity.",
                confidence=4.5,
            )
            raw_response_content = (
                '{"winner": "Essay A", "justification": "Mocked...", "confidence": 4.5}'
            )
            results.append(
                ComparisonResult(
                    task=task_item,
                    llm_assessment=mock_assessment,
                    raw_llm_response_content=raw_response_content,
                    error_message=None,
                    from_cache=False,
                    prompt_hash=uuid.uuid4().hex,
                ),
            )
        return results

    try:
        mocked_function = mocker.patch(
            "src.cj_essay_assessment.main.process_comparison_tasks_async",
            new_callable=AsyncMock,
        )
    except AttributeError:
        mocked_function = mocker.patch(
            "src.cj_essay_assessment.llm_caller.process_comparison_tasks_async",
            new_callable=AsyncMock,
        )

    mocked_function.side_effect = default_llm_side_effect
    return mocked_function
