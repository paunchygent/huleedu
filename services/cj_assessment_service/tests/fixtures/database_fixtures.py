"""
Database fixtures for CJ Assessment Service integration tests.

Provides real database implementations with proper isolation and cleanup.
Replaces over-mocked internal components with actual database operations.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, AsyncIterator, Generator
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.anchor_repository import (
    PostgreSQLAnchorRepository,
)
from services.cj_assessment_service.implementations.assessment_instruction_repository import (
    PostgreSQLAssessmentInstructionRepository,
)
from services.cj_assessment_service.implementations.batch_repository import (
    PostgreSQLCJBatchRepository,
)
from services.cj_assessment_service.implementations.comparison_repository import (
    PostgreSQLCJComparisonRepository,
)
from services.cj_assessment_service.implementations.essay_repository import (
    PostgreSQLCJEssayRepository,
)
from services.cj_assessment_service.implementations.grade_projection_repository import (
    PostgreSQLGradeProjectionRepository,
)
from services.cj_assessment_service.implementations.session_provider_impl import (
    CJSessionProviderImpl,
)
from services.cj_assessment_service.models_db import Base
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
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
async def postgres_session(
    postgres_session_provider: CJSessionProviderImpl,
) -> AsyncGenerator[AsyncSession, None]:
    """Create isolated PostgreSQL session via session provider."""
    async with postgres_session_provider.session() as session:
        yield session


# ==================== Repository Fixtures ====================


@pytest.fixture
def test_settings() -> Generator[Settings, None, None]:
    """Create test settings with database configuration."""
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
    settings.DB_HOST = "sqlite"
    settings.DB_PORT = 0
    settings.DB_NAME = "cj_assessment_test"
    settings.PAIR_GENERATION_SEED = 42

    import os

    os.environ["CJ_ASSESSMENT_SERVICE_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

    yield settings

    if "CJ_ASSESSMENT_SERVICE_DATABASE_URL" in os.environ:
        del os.environ["CJ_ASSESSMENT_SERVICE_DATABASE_URL"]


@pytest.fixture
def postgres_session_provider(postgres_engine: AsyncEngine) -> CJSessionProviderImpl:
    """Provide session provider for integration tests."""
    return CJSessionProviderImpl(postgres_engine)


@pytest.fixture
def postgres_batch_repository() -> PostgreSQLCJBatchRepository:
    """Provide batch repository for integration tests."""
    return PostgreSQLCJBatchRepository()


@pytest.fixture
def postgres_essay_repository() -> PostgreSQLCJEssayRepository:
    """Provide essay repository for integration tests."""
    return PostgreSQLCJEssayRepository()


@pytest.fixture
def postgres_instruction_repository() -> PostgreSQLAssessmentInstructionRepository:
    """Provide instruction repository for integration tests."""
    return PostgreSQLAssessmentInstructionRepository()


@pytest.fixture
def postgres_anchor_repository() -> PostgreSQLAnchorRepository:
    """Provide anchor repository for integration tests."""
    return PostgreSQLAnchorRepository()


@pytest.fixture
def postgres_comparison_repository() -> PostgreSQLCJComparisonRepository:
    """Provide comparison repository for integration tests."""
    return PostgreSQLCJComparisonRepository()


@pytest.fixture
def postgres_grade_projection_repository() -> PostgreSQLGradeProjectionRepository:
    """Provide grade projection repository for integration tests."""
    return PostgreSQLGradeProjectionRepository()


# ==================== Aggregated Data Access Fixture ====================


class PostgresDataAccess:
    """Test façade routing to per-aggregate repos via shared session provider."""

    def __init__(
        self,
        session_provider: CJSessionProviderImpl,
        batch_repo: PostgreSQLCJBatchRepository,
        essay_repo: PostgreSQLCJEssayRepository,
        instruction_repo: PostgreSQLAssessmentInstructionRepository,
        anchor_repo: PostgreSQLAnchorRepository,
        comparison_repo: PostgreSQLCJComparisonRepository,
        grade_projection_repo: PostgreSQLGradeProjectionRepository,
    ) -> None:
        self.session_provider = session_provider
        self.batch_repo = batch_repo
        self.essay_repo = essay_repo
        self.instruction_repo = instruction_repo
        self.anchor_repo = anchor_repo
        self.comparison_repo = comparison_repo
        self.grade_projection_repo = grade_projection_repo

    # Session context manager (compatibility with previous fixture)
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_provider.session() as session:
            yield session

    # Batch operations
    async def create_new_cj_batch(self, *args: Any, **kwargs: Any) -> Any:
        return await self.batch_repo.create_new_cj_batch(*args, **kwargs)

    async def get_batch_state(self, *args: Any, **kwargs: Any) -> Any:
        return await self.batch_repo.get_batch_state(*args, **kwargs)

    async def get_cj_batch_upload(self, *args: Any, **kwargs: Any) -> Any:
        return await self.batch_repo.get_cj_batch_upload(*args, **kwargs)

    async def update_cj_batch_status(self, *args: Any, **kwargs: Any) -> None:
        await self.batch_repo.update_cj_batch_status(*args, **kwargs)

    # Essay operations
    async def create_or_update_cj_processed_essay(self, *args: Any, **kwargs: Any) -> Any:
        return await self.essay_repo.create_or_update_cj_processed_essay(*args, **kwargs)

    async def get_essays_for_cj_batch(self, *args: Any, **kwargs: Any) -> Any:
        return await self.essay_repo.get_essays_for_cj_batch(*args, **kwargs)

    async def update_essay_scores_in_batch(self, *args: Any, **kwargs: Any) -> None:
        await self.essay_repo.update_essay_scores_in_batch(*args, **kwargs)

    async def get_final_cj_rankings(self, *args: Any, **kwargs: Any) -> Any:
        return await self.essay_repo.get_final_cj_rankings(*args, **kwargs)

    # Instruction operations
    async def upsert_assessment_instruction(self, *args: Any, **kwargs: Any) -> Any:
        return await self.instruction_repo.upsert_assessment_instruction(*args, **kwargs)

    async def get_assessment_instruction(self, *args: Any, **kwargs: Any) -> Any:
        return await self.instruction_repo.get_assessment_instruction(*args, **kwargs)

    # Anchor operations
    async def upsert_anchor_reference(self, *args: Any, **kwargs: Any) -> Any:
        return await self.anchor_repo.upsert_anchor_reference(*args, **kwargs)

    async def get_anchor_essay_references(self, *args: Any, **kwargs: Any) -> Any:
        return await self.anchor_repo.get_anchor_essay_references(*args, **kwargs)

    # Comparison operations
    async def store_comparison_results(self, *args: Any, **kwargs: Any) -> None:
        await self.comparison_repo.store_comparison_results(*args, **kwargs)

    async def get_comparison_pair_by_correlation_id(self, *args: Any, **kwargs: Any) -> Any:
        return await self.comparison_repo.get_comparison_pair_by_correlation_id(*args, **kwargs)

    async def get_comparison_pairs_for_batch(self, *args: Any, **kwargs: Any) -> Any:
        return await self.comparison_repo.get_comparison_pairs_for_batch(*args, **kwargs)

    async def get_valid_comparisons_for_batch(self, *args: Any, **kwargs: Any) -> Any:
        return await self.comparison_repo.get_valid_comparisons_for_batch(*args, **kwargs)


@pytest.fixture
def postgres_data_access(
    postgres_session_provider: CJSessionProviderImpl,
    postgres_batch_repository: PostgreSQLCJBatchRepository,
    postgres_essay_repository: PostgreSQLCJEssayRepository,
    postgres_instruction_repository: PostgreSQLAssessmentInstructionRepository,
    postgres_anchor_repository: PostgreSQLAnchorRepository,
    postgres_comparison_repository: PostgreSQLCJComparisonRepository,
    postgres_grade_projection_repository: PostgreSQLGradeProjectionRepository,
) -> PostgresDataAccess:
    """Aggregate fixture exposing legacy repository methods via per-aggregate repos."""

    return PostgresDataAccess(
        session_provider=postgres_session_provider,
        batch_repo=postgres_batch_repository,
        essay_repo=postgres_essay_repository,
        instruction_repo=postgres_instruction_repository,
        anchor_repo=postgres_anchor_repository,
        comparison_repo=postgres_comparison_repository,
        grade_projection_repo=postgres_grade_projection_repository,
    )


@pytest.fixture
def postgres_repository(postgres_data_access: PostgresDataAccess) -> PostgresDataAccess:
    """Backward-compatible fixture alias returning PostgresDataAccess façade."""

    return postgres_data_access


# ==================== External Service Mocks (Keep These) ====================


@pytest.fixture
def mock_content_client() -> AsyncMock:
    """Create mock content client for external service."""
    client = AsyncMock(spec=ContentClientProtocol)

    # Realistic essay content generator
    essay_templates = [
        (
            "The impact of technology on modern education has been transformative. "
            "Digital tools have revolutionized how students learn and teachers instruct. "
            "From online resources to interactive platforms, "
            "the educational landscape continues to evolve rapidly."
        ),
        (
            "Climate change presents one of the greatest challenges of our time. "
            "Rising temperatures, extreme weather events, and ecosystem disruption "
            "demand immediate global action. "
            "Sustainable solutions require cooperation between governments, "
            "businesses, and individuals."
        ),
        (
            "The importance of mental health awareness cannot be overstated. "
            "Breaking down stigmas and providing accessible support services "
            "are crucial steps toward a healthier society. "
            "Early intervention and education play key roles in mental wellness."
        ),
        (
            "Artificial intelligence is reshaping industries across the globe. "
            "From healthcare diagnostics to financial analysis, "
            "AI applications continue to expand. "
            "However, ethical considerations and responsible development remain paramount concerns."
        ),
        (
            "Cultural diversity enriches our communities in countless ways. "
            "Embracing different perspectives, traditions, and experiences "
            "fosters innovation and understanding. "
            "Building inclusive societies requires ongoing effort and open dialogue."
        ),
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
def mock_llm_interaction_async() -> AsyncMock:
    """Create mock LLM interaction that simulates async processing.

    Returns None for all comparisons to simulate async processing.
    The CallbackSimulator will process these as callbacks.
    """
    from services.cj_assessment_service.protocols import LLMInteractionProtocol

    interaction = AsyncMock(spec=LLMInteractionProtocol)

    async def perform_comparisons_async(
        tasks: list[Any],
        correlation_id: Any,
        tracking_map: dict[tuple[str, str], Any] | None = None,
        bos_batch_id: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        system_prompt_override: str | None = None,
        provider_override: str | Any | None = None,
        metadata_context: dict[str, Any] | None = None,
    ) -> list[None]:
        """Return None for all tasks to simulate async processing."""
        # Store the tasks for the callback simulator to use
        interaction._submitted_tasks = tasks
        interaction._correlation_id = correlation_id

        # Return None for each task (async processing)
        return [None] * len(tasks)

    interaction.perform_comparisons = AsyncMock(side_effect=perform_comparisons_async)
    return interaction


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
        tracking_map: dict[tuple[str, str], Any] | None = None,
        bos_batch_id: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        system_prompt_override: str | None = None,
        provider_override: str | Any | None = None,
        metadata_context: dict[str, Any] | None = None,
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
                justification=f"Essay {winner.value} demonstrates stronger "
                f"argumentation and clarity.",
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
    publisher.publish_assessment_result = AsyncMock()  # Added for dual event publishing to RAS
    return publisher


# ==================== Verification Helpers ====================
# Verification helpers removed - tests now use production models directly


@pytest.fixture
def db_verification_helpers() -> Any:
    """Provide database verification helper functions using production models."""
    from services.cj_assessment_service.models_db import CJBatchUpload, ProcessedEssay

    class DbVerificationHelpers:
        @staticmethod
        async def verify_batch_exists(session: AsyncSession, batch_id: int) -> bool:
            """Verify that a batch exists in the database."""
            result = await session.execute(
                select(CJBatchUpload).where(CJBatchUpload.id == batch_id)
            )
            return result.scalar_one_or_none() is not None

        @staticmethod
        async def verify_essay_count(session: AsyncSession, batch_id: int) -> int:
            """Count essays in a batch."""
            result = await session.execute(
                select(ProcessedEssay).where(ProcessedEssay.cj_batch_id == batch_id)
            )
            return len(list(result.scalars().all()))

        @staticmethod
        async def verify_no_data_leakage(session: AsyncSession) -> bool:
            """Verify that no data remains from previous tests."""
            batch_result = await session.execute(select(CJBatchUpload))
            essay_result = await session.execute(select(ProcessedEssay))

            return (
                len(list(batch_result.scalars().all())) == 0
                and len(list(essay_result.scalars().all())) == 0
            )

        @staticmethod
        async def find_batch_by_bos_id(
            session: AsyncSession, bos_batch_id: str
        ) -> CJBatchUpload | None:
            """Find CJ batch by BOS batch ID."""
            result = await session.execute(
                select(CJBatchUpload).where(CJBatchUpload.bos_batch_id == bos_batch_id)
            )
            return result.scalar_one_or_none()

    return DbVerificationHelpers()


# ==================== Database Cleanup Fixtures ====================


@pytest.fixture(autouse=True)
async def clean_database_between_tests(postgres_engine: AsyncEngine) -> AsyncIterator[None]:
    """Clean database tables between tests for proper isolation.

    This fixture ensures test isolation by truncating tables after each test,
    respecting the repository-managed sessions architectural pattern.
    """
    # Yield first to let the test run
    yield

    # Clean up after test completes
    from services.cj_assessment_service.models_db import (
        CJBatchUpload,
        ComparisonPair,
        ProcessedEssay,
    )

    async with postgres_engine.begin() as conn:
        # Disable foreign key checks for truncation
        await conn.execute(text("SET session_replication_role = replica;"))

        # Truncate tables in dependency order (children first)
        await conn.execute(text(f"TRUNCATE TABLE {ComparisonPair.__tablename__} CASCADE;"))
        await conn.execute(text(f"TRUNCATE TABLE {ProcessedEssay.__tablename__} CASCADE;"))
        await conn.execute(text(f"TRUNCATE TABLE {CJBatchUpload.__tablename__} CASCADE;"))

        # Re-enable foreign key checks
        await conn.execute(text("SET session_replication_role = DEFAULT;"))


@pytest.fixture
def performance_test_markers() -> Any:
    """Provide performance test classification markers."""

    class PerformanceMarkers:
        @staticmethod
        def mark_expensive() -> Any:
            """Mark test as expensive (requires PostgreSQL)."""
            return pytest.mark.expensive

        @staticmethod
        def mark_fast() -> Any:
            """Mark test as fast (uses SQLite)."""
            return pytest.mark.fast

        @staticmethod
        def mark_integration() -> Any:
            """Mark test as integration."""
            return pytest.mark.integration

    return PerformanceMarkers()
