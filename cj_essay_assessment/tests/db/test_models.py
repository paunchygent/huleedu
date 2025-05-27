"""Tests for database models."""

from collections.abc import AsyncGenerator
from datetime import datetime

import pytest
import sqlalchemy.exc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.cj_essay_assessment.config import Settings
from src.cj_essay_assessment.db_handler import DatabaseHandler
from src.cj_essay_assessment.models_db import (Base, BatchStatusEnum,
                                               BatchUpload, ComparisonPair,
                                               ProcessedEssay, User)


@pytest.fixture
async def db_handler() -> AsyncGenerator[DatabaseHandler, None]:
    """Fixture providing a test DatabaseHandler."""
    # Use a fresh in-memory SQLite database for tests
    test_settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
    handler = DatabaseHandler(test_settings)

    # Create all tables
    async with handler.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield handler

    # Cleanup
    async with handler.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await handler.engine.dispose()


@pytest.fixture
async def async_session(
    db_handler: DatabaseHandler,
) -> AsyncGenerator[AsyncSession, None]:
    """Fixture providing an async database session."""
    async with db_handler.session() as session:
        yield session


@pytest.fixture
async def test_user(async_session: AsyncSession) -> User:
    """Fixture providing a test user."""
    user = User(username="testuser", email="test@example.com", full_name="Test User")
    async_session.add(user)
    await async_session.flush()
    return user


@pytest.fixture
async def test_batch(async_session: AsyncSession, test_user: User) -> BatchUpload:
    """Fixture providing a test batch upload."""
    batch = BatchUpload(
        user_id=test_user.id,
        name="Test Batch",
        description="A test batch upload",
        json_metadata={"test_key": "test_value"},
    )
    async_session.add(batch)
    await async_session.flush()
    return batch


@pytest.fixture
async def test_essay(
    async_session: AsyncSession,
    test_batch: BatchUpload,
) -> ProcessedEssay:
    """Fixture providing a test processed essay."""
    essay = ProcessedEssay(
        batch_id=test_batch.id,
        original_filename="test_essay.docx",
        original_content="This is a test essay.",
        processed_content="This is a processed test essay.",
        current_bt_score=0.5,
        processing_metadata={"processed": True},
        nlp_features={"word_count": 5},
    )
    async_session.add(essay)
    await async_session.flush()
    return essay


@pytest.mark.asyncio
async def test_user_model_creation(async_session: AsyncSession) -> None:
    """Test creating a user model."""
    # Create a user
    user = User(username="testuser2", email="user2@example.com", full_name="Test User 2")
    async_session.add(user)
    await async_session.flush()

    # Verify the user was created with an ID
    assert user.id is not None
    assert user.username == "testuser2"
    assert user.email == "user2@example.com"
    assert user.full_name == "Test User 2"
    assert user.is_active is True
    assert isinstance(user.created_at, datetime)


@pytest.mark.asyncio
async def test_batch_upload_model_creation(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    """Test creating a batch upload model."""
    # Create a batch upload
    batch = BatchUpload(
        user_id=test_user.id,
        name="Test Batch 2",
        description="Another test batch",
        json_metadata={"source": "test"},
    )
    async_session.add(batch)
    await async_session.flush()

    # Verify the batch was created with an ID
    assert batch.id is not None
    assert batch.user_id == test_user.id
    assert batch.name == "Test Batch 2"
    assert batch.description == "Another test batch"
    assert batch.json_metadata == {"source": "test"}
    assert batch.status == BatchStatusEnum.PENDING
    assert isinstance(batch.upload_date, datetime)


@pytest.mark.asyncio
async def test_processed_essay_model_creation(
    async_session: AsyncSession,
    test_batch: BatchUpload,
) -> None:
    """Test creating a processed essay model."""
    # Create a processed essay
    essay = ProcessedEssay(
        batch_id=test_batch.id,
        original_filename="essay.docx",
        original_content="Original content.",
        processed_content="Processed content.",
        current_bt_score=0.75,
        processing_metadata={"spell_checked": True},
        nlp_features={"word_count": 2},
    )
    async_session.add(essay)
    await async_session.flush()

    # Verify the essay was created with an ID
    assert essay.id is not None
    assert essay.batch_id == test_batch.id
    assert essay.original_filename == "essay.docx"
    assert essay.original_content == "Original content."
    assert essay.processed_content == "Processed content."
    assert essay.current_bt_score == 0.75
    assert essay.processing_metadata == {"spell_checked": True}
    assert essay.nlp_features == {"word_count": 2}
    assert isinstance(essay.created_at, datetime)
    # New in Task 2.6: Default should be False
    assert essay.nlp_analysis_complete is False


@pytest.mark.asyncio
async def test_processed_essay_nlp_analysis_complete(
    async_session: AsyncSession,
    test_batch: BatchUpload,
) -> None:
    """Test the nlp_analysis_complete flag added in Task 2.6."""
    # Create a processed essay with default nlp_analysis_complete (False)
    essay = ProcessedEssay(
        batch_id=test_batch.id,
        original_filename="essay.docx",
        original_content="Original content.",
        processed_content="Processed content.",  # Required due to NOT NULL constraint
    )
    async_session.add(essay)
    await async_session.flush()

    # Verify nlp_analysis_complete is False by default
    assert essay.nlp_analysis_complete is False

    # Change nlp_analysis_complete to True
    essay.nlp_analysis_complete = True
    await async_session.flush()

    # Query the essay from the database to verify the change persisted
    stmt = select(ProcessedEssay).where(ProcessedEssay.id == essay.id)
    result = await async_session.execute(stmt)
    refreshed_essay = result.scalars().first()

    # Verify nlp_analysis_complete was saved as True
    assert refreshed_essay is not None
    assert refreshed_essay.nlp_analysis_complete is True


@pytest.mark.asyncio
async def test_comparison_pair_model_creation(
    async_session: AsyncSession,
    test_essay: ProcessedEssay,
) -> None:
    """Test creating a comparison pair model."""
    # Create another essay for comparison
    essay_b = ProcessedEssay(
        batch_id=test_essay.batch_id,
        original_filename="essay_b.docx",
        original_content="Essay B content.",
        processed_content="Processed Essay B.",
    )
    async_session.add(essay_b)
    await async_session.flush()

    # Create a comparison pair
    pair = ComparisonPair(
        batch_id=test_essay.batch_id,
        essay_a_id=test_essay.id,
        essay_b_id=essay_b.id,
        prompt_text="Compare these essays.",
        prompt_hash="abcdef123456",
        winner="essay_a",
        confidence=4.0,
        justification="Essay A is better.",
        raw_llm_response='{"winner": "essay_a"}',
        from_cache=False,
        processing_metadata={"model": "gpt-4"},
    )
    async_session.add(pair)
    await async_session.flush()

    # Verify the pair was created with an ID
    assert pair.id is not None
    assert pair.essay_a_id == test_essay.id
    assert pair.essay_b_id == essay_b.id
    assert pair.prompt_text == "Compare these essays."
    assert pair.prompt_hash == "abcdef123456"
    assert pair.winner == "essay_a"
    assert pair.confidence == 4.0
    assert pair.justification == "Essay A is better."
    assert pair.raw_llm_response == '{"winner": "essay_a"}'
    assert pair.from_cache is False
    assert pair.processing_metadata == {"model": "gpt-4"}
    assert isinstance(pair.created_at, datetime)


@pytest.mark.asyncio
async def test_user_batch_relationship(
    async_session: AsyncSession,
    test_user: User,
    test_batch: BatchUpload,
) -> None:
    """Test relationship between user and batch uploads."""
    # Refresh the user to load the relationship
    await async_session.refresh(test_user, ["batch_uploads"])

    # Verify the relationship works
    assert len(test_user.batch_uploads) == 1
    assert test_user.batch_uploads[0].id == test_batch.id
    assert test_user.batch_uploads[0].name == test_batch.name


@pytest.mark.asyncio
async def test_batch_essay_relationship(
    async_session: AsyncSession,
    test_batch: BatchUpload,
    test_essay: ProcessedEssay,
) -> None:
    """Test relationship between batch and essays."""
    # Refresh the batch to load the relationship
    await async_session.refresh(test_batch, ["essays"])

    # Verify the relationship works
    assert len(test_batch.essays) == 1
    assert test_batch.essays[0].id == test_essay.id
    assert test_batch.essays[0].original_filename == test_essay.original_filename


@pytest.mark.asyncio
async def test_essay_comparison_relationship(
    async_session: AsyncSession,
    test_essay: ProcessedEssay,
) -> None:
    """Test relationship between essays and comparison pairs."""
    # Create another essay for comparison
    essay_b = ProcessedEssay(
        batch_id=test_essay.batch_id,
        original_filename="essay_b.docx",
        original_content="Essay B content.",
        processed_content="Processed Essay B.",
    )
    async_session.add(essay_b)
    await async_session.flush()

    # Create a comparison pair
    pair = ComparisonPair(
        batch_id=test_essay.batch_id,
        essay_a_id=test_essay.id,
        essay_b_id=essay_b.id,
        prompt_text="Compare these essays.",
        prompt_hash="abcdef123456",
    )
    async_session.add(pair)
    await async_session.flush()

    # Refresh the essays to load the relationships
    await async_session.refresh(test_essay, ["comparison_pairs_a"])
    await async_session.refresh(essay_b, ["comparison_pairs_b"])

    # Verify the relationships work
    assert len(test_essay.comparison_pairs_a) == 1
    assert test_essay.comparison_pairs_a[0].id == pair.id
    assert len(essay_b.comparison_pairs_b) == 1
    assert essay_b.comparison_pairs_b[0].id == pair.id


@pytest.mark.asyncio
async def test_cascade_delete_batch_essays(
    async_session: AsyncSession,
    test_batch: BatchUpload,
    test_essay: ProcessedEssay,
) -> None:
    """Test that deleting a batch cascade deletes its essays."""
    # Delete the batch
    await async_session.delete(test_batch)
    await async_session.flush()

    # Try to find the essay - it should be gone
    stmt = select(ProcessedEssay).where(ProcessedEssay.id == test_essay.id)
    result = await async_session.execute(stmt)
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_unique_constraints(async_session: AsyncSession) -> None:
    """Test unique constraints on User model."""
    # Test unique username
    user1 = User(username="unique_user1", email="user1@example.com", full_name="User One")
    async_session.add(user1)
    await async_session.flush()  # Persist user1

    duplicate_username_user = User(
        username="unique_user1",  # Same username as user1
        email="user2@example.com",
        full_name="User Two",
    )
    async_session.add(duplicate_username_user)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        await async_session.flush()

    await async_session.rollback()  # Rollback the failed attempt

    # Test unique email
    # Ensure a user with the target email exists first for this part of the test
    user3 = User(
        username="unique_user3",
        email="user3_target@example.com",
        full_name="User Three",
    )
    async_session.add(user3)
    await async_session.flush()  # Persist user3

    duplicate_email_user = User(
        username="unique_user4",
        email="user3_target@example.com",  # Same email as user3
        full_name="User Four",
    )
    async_session.add(duplicate_email_user)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        await async_session.flush()

    await async_session.rollback()  # Clean up after this test part too


@pytest.mark.asyncio
async def test_batch_upload_status_enum_storage(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    """Test that BatchUpload.status stores Enum as string but hydrates to Enum object."""
    batch_name = "Enum Storage Test Batch"
    # Create a batch upload with a specific status
    batch = BatchUpload(
        user_id=test_user.id,
        name=batch_name,
        status=BatchStatusEnum.PROCESSING_ESSAYS,
    )
    async_session.add(batch)
    await async_session.flush()
    batch_id = batch.id
    await async_session.commit()  # Commit to ensure it's written and read back

    # Fetch from DB using a raw query to inspect stored value type if possible, or
    # just re-fetch. For simplicity, we'll re-fetch and check the attribute type.
    # This relies on SQLAlchemy's type handling on load.
    fetched_batch_stmt = select(BatchUpload).where(BatchUpload.id == batch_id)
    result = await async_session.execute(fetched_batch_stmt)
    fetched_batch = result.scalar_one_or_none()

    assert fetched_batch is not None
    assert fetched_batch.name == batch_name
    # Verify that the status attribute is an instance of BatchStatusEnum when loaded
    assert isinstance(fetched_batch.status, BatchStatusEnum)
    assert fetched_batch.status == BatchStatusEnum.PROCESSING_ESSAYS

    # To check actual DB storage (more involved, might need direct DB connection
    # or specific dialect features). For now, we trust SQLAlchemy's handling
    # with `values_callable`.
    # If we wanted to be extremely thorough, we could execute a raw SQL query:
    # async with async_session.connection() as conn:
    #     raw_result = await conn.execute(
    #         text(f"SELECT status FROM batch_uploads WHERE id = {batch_id}"))
    #     stored_status_value = raw_result.scalar_one()
    # assert stored_status_value == "PROCESSING_ESSAYS"  # Check it's stored as string
