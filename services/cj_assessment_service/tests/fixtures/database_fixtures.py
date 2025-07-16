"""
Database fixtures for CJ Assessment Service integration tests.

Provides real database implementations with proper isolation and cleanup.
Replaces over-mocked internal components with actual database operations.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Generator
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.db_access_impl import (
    PostgreSQLCJRepositoryImpl,
)
from services.cj_assessment_service.models_db import Base
from services.cj_assessment_service.tests.fixtures.test_models_db import (
    TestBase,
    TestCJBatchUpload,
    TestProcessedEssay,
)
from services.cj_assessment_service.tests.fixtures.test_repository_impl import TestCJRepositoryImpl
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)

# ==================== Database Engine Fixtures ====================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create SQLite in-memory engine for fast integration tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
        # SQLite-specific optimizations
        connect_args={"check_same_thread": False},
    )

    # Create all tables using test-specific models
    async with engine.begin() as conn:
        await conn.run_sync(TestBase.metadata.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """Create PostgreSQL container for production-parity tests."""
    with PostgresContainer(
        "postgres:15",
        username="test_user",
        password="test_password",
        dbname="cj_assessment_test",
    ) as container:
        yield container


@pytest.fixture
async def postgres_engine(
    postgres_container: PostgresContainer,
) -> AsyncGenerator[AsyncEngine, None]:
    """Create PostgreSQL engine for production-parity tests."""
    database_url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")

    engine = create_async_engine(
        database_url,
        echo=False,
        future=True,
        # PostgreSQL-specific optimizations
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()


# ==================== Database Session Fixtures ====================


@pytest.fixture
async def db_session(sqlite_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create isolated database session with automatic rollback."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_maker = async_sessionmaker(
        sqlite_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_maker() as session:
        # Use a transaction that will be rolled back
        async with session.begin():
            yield session
            # Rollback happens automatically when exiting the context


@pytest.fixture
async def postgres_session(postgres_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create isolated PostgreSQL session with automatic rollback."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_maker = async_sessionmaker(
        postgres_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with session_maker() as session:
        # Use a transaction that will be rolled back
        async with session.begin():
            yield session
            # Rollback happens automatically when exiting the context


# ==================== Repository Fixtures ====================


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings with database configuration."""
    import os
    
    # Override database URL for testing
    os.environ["CJ_ASSESSMENT_SERVICE_DATABASE_URL_CJ"] = "sqlite+aiosqlite:///:memory:"
    
    settings = Settings()
    settings.DATABASE_POOL_SIZE = 5
    settings.DATABASE_MAX_OVERFLOW = 10
    settings.DATABASE_POOL_PRE_PING = True
    settings.DATABASE_POOL_RECYCLE = 3600
    settings.SERVICE_NAME = "cj_assessment_service"
    settings.CJ_ASSESSMENT_COMPLETED_TOPIC = "huleedu.cj_assessment.completed.v1"
    settings.CJ_ASSESSMENT_FAILED_TOPIC = "huleedu.cj_assessment.failed.v1"
    settings.BATCH_TIMEOUT_HOURS = 4
    settings.BATCH_MONITOR_INTERVAL_MINUTES = 5
    
    # Clean up after test
    yield settings
    
    # Clean up environment variable
    if "CJ_ASSESSMENT_SERVICE_DATABASE_URL_CJ" in os.environ:
        del os.environ["CJ_ASSESSMENT_SERVICE_DATABASE_URL_CJ"]


@pytest.fixture
async def real_repository(
    sqlite_engine: AsyncEngine, test_settings: Settings
) -> AsyncGenerator[CJRepositoryProtocol, None]:
    """Create real repository implementation with SQLite backend."""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    
    # Create session maker for test repository
    session_maker = async_sessionmaker(
        sqlite_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    
    repository = TestCJRepositoryImpl(session_maker=session_maker)

    # Initialize schema (already done in sqlite_engine fixture)
    await repository.initialize_db_schema()

    yield repository


@pytest.fixture
async def postgres_repository(
    postgres_engine: AsyncEngine, test_settings: Settings
) -> AsyncGenerator[CJRepositoryProtocol, None]:
    """Create real repository implementation with PostgreSQL backend."""
    repository = PostgreSQLCJRepositoryImpl(
        settings=test_settings,
        engine=postgres_engine,
    )

    # Initialize schema
    await repository.initialize_db_schema()

    yield repository


# ==================== External Service Mocks (Keep These) ====================


@pytest.fixture
def mock_content_client() -> AsyncMock:
    """Create mock content client for external service."""
    client = AsyncMock(spec=ContentClientProtocol)

    # Realistic essay content generator
    essay_templates = [
        "The impact of technology on modern education has been transformative. Digital tools have revolutionized how students learn and teachers instruct. From online resources to interactive platforms, the educational landscape continues to evolve rapidly.",
        "Climate change presents one of the greatest challenges of our time. Rising temperatures, extreme weather events, and ecosystem disruption demand immediate global action. Sustainable solutions require cooperation between governments, businesses, and individuals.",
        "The importance of mental health awareness cannot be overstated. Breaking down stigmas and providing accessible support services are crucial steps toward a healthier society. Early intervention and education play key roles in mental wellness.",
        "Artificial intelligence is reshaping industries across the globe. From healthcare diagnostics to financial analysis, AI applications continue to expand. However, ethical considerations and responsible development remain paramount concerns.",
        "Cultural diversity enriches our communities in countless ways. Embracing different perspectives, traditions, and experiences fosters innovation and understanding. Building inclusive societies requires ongoing effort and open dialogue.",
    ]

    async def fetch_content(storage_id: str, correlation_id: Any) -> str:
        """Generate realistic essay content based on storage ID."""
        # Use correlation_id for deterministic content selection
        content_seed = hash(f"{storage_id}-{correlation_id}") % len(essay_templates)

        # Extract essay number from storage ID if possible
        try:
            if "-" in storage_id:
                essay_num = int(storage_id.split("-")[-1])
                return essay_templates[essay_num % len(essay_templates)]
            else:
                return essay_templates[content_seed]
        except ValueError:
            return essay_templates[content_seed]

    client.fetch_content = AsyncMock(side_effect=fetch_content)
    client.fetch_essay_content = AsyncMock(side_effect=fetch_content)

    return client


@pytest.fixture
def mock_llm_interaction() -> AsyncMock:
    """Create mock LLM interaction for external service."""
    from common_core.domain_enums import EssayComparisonWinner
    from services.cj_assessment_service.models_api import (
        ComparisonResult,
        LLMAssessmentResponseSchema,
    )

    interaction = AsyncMock(spec=LLMInteractionProtocol)

    async def perform_comparisons(
        tasks: list[Any],
        correlation_id: Any,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> list[ComparisonResult]:
        """Generate realistic comparison results using provided parameters."""
        results = []

        # Use correlation_id for deterministic results in tests
        result_seed = hash(str(correlation_id)) % 100

        # Apply temperature override to confidence calculation
        base_confidence = 3.5
        if temperature_override is not None:
            # Higher temperature = more variation in confidence
            confidence_variance = temperature_override * 0.5
        else:
            confidence_variance = 0.5

        for i, task in enumerate(tasks):
            # Use model_override to influence winner selection
            bias_factor = 3 if model_override and "gpt" in model_override.lower() else 2

            # Simulate realistic winner selection with model bias
            winner = (
                EssayComparisonWinner.ESSAY_A
                if (i + result_seed) % bias_factor != 2
                else EssayComparisonWinner.ESSAY_B
            )

            # Create realistic assessment data with parameter influence
            confidence_value = base_confidence + (i % 3) * confidence_variance
            if max_tokens_override and max_tokens_override < 1000:
                # Lower token limit = slightly lower confidence
                confidence_value *= 0.9

            assessment = LLMAssessmentResponseSchema(
                winner=winner,
                confidence=min(5.0, confidence_value),  # Cap at 5.0
                justification=f"Essay {winner.value} demonstrates stronger argumentation and clarity.",
            )

            # Create comparison result
            result = ComparisonResult(
                task=task,
                llm_assessment=assessment,
                raw_llm_response_content=(
                    f'{{"winner": "{winner.value}", '
                    f'"confidence": {assessment.confidence}, '
                    f'"justification": "{assessment.justification}"}}'
                ),
                error_detail=None,
            )
            results.append(result)

        return results

    interaction.perform_comparisons = AsyncMock(side_effect=perform_comparisons)
    return interaction


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Create mock event publisher for Kafka publishing."""
    publisher = AsyncMock(spec=CJEventPublisherProtocol)
    publisher.publish_assessment_completed = AsyncMock()
    publisher.publish_assessment_failed = AsyncMock()
    return publisher


# ==================== Test Data Factories ====================


@pytest.fixture
async def sample_batch_data(
    real_repository: CJRepositoryProtocol,
    db_session: AsyncSession,
) -> TestCJBatchUpload:
    """Create sample batch data in the database."""
    from uuid import uuid4

    from services.cj_assessment_service.enums_db import CJBatchStatusEnum

    batch = await real_repository.create_new_cj_batch(
        session=db_session,
        bos_batch_id=str(uuid4()),
        event_correlation_id=str(uuid4()),
        language="en",
        course_code="ENG5",
        essay_instructions="Compare the quality of these essays.",
        initial_status=CJBatchStatusEnum.PENDING,
        expected_essay_count=10,
    )

    return batch


@pytest.fixture
async def sample_essays_data(
    real_repository: CJRepositoryProtocol,
    db_session: AsyncSession,
    sample_batch_data: TestCJBatchUpload,
) -> list[TestProcessedEssay]:
    """Create sample essay data in the database."""

    essays = []
    for i in range(10):
        essay = await real_repository.create_or_update_cj_processed_essay(
            session=db_session,
            cj_batch_id=sample_batch_data.id,
            els_essay_id=f"essay-{i}",
            text_storage_id=f"storage-{i}",
            assessment_input_text=f"Sample essay content {i}",
        )
        essays.append(essay)

    return essays


# ==================== Verification Helpers ====================


@pytest.fixture
def db_verification_helpers():
    """Provide database verification helper functions."""

    class DbVerificationHelpers:
        @staticmethod
        async def verify_batch_exists(session: AsyncSession, batch_id: int) -> bool:
            """Verify that a batch exists in the database."""
            result = await session.execute(
                select(TestCJBatchUpload).where(TestCJBatchUpload.id == batch_id)
            )
            return result.scalar_one_or_none() is not None

        @staticmethod
        async def verify_essay_count(session: AsyncSession, batch_id: int) -> int:
            """Count essays in a batch."""
            result = await session.execute(
                select(TestProcessedEssay).where(TestProcessedEssay.cj_batch_id == batch_id)
            )
            return len(list(result.scalars().all()))

        @staticmethod
        async def verify_no_data_leakage(session: AsyncSession) -> bool:
            """Verify that no data remains from previous tests."""
            batch_result = await session.execute(select(TestCJBatchUpload))
            essay_result = await session.execute(select(TestProcessedEssay))

            return (
                len(list(batch_result.scalars().all())) == 0
                and len(list(essay_result.scalars().all())) == 0
            )

    return DbVerificationHelpers()


# ==================== Performance Testing Fixtures ====================


@pytest.fixture
def performance_test_markers():
    """Provide performance test classification markers."""

    class PerformanceMarkers:
        @staticmethod
        def mark_expensive():
            """Mark test as expensive (requires PostgreSQL)."""
            return pytest.mark.expensive

        @staticmethod
        def mark_fast():
            """Mark test as fast (uses SQLite)."""
            return pytest.mark.fast

        @staticmethod
        def mark_integration():
            """Mark test as integration."""
            return pytest.mark.integration

    return PerformanceMarkers()
