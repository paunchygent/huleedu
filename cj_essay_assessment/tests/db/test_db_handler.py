"""Tests for the database handler."""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.future import select

from src.cj_essay_assessment.config import Settings
from src.cj_essay_assessment.db_handler import DatabaseHandler
from src.cj_essay_assessment.models_db import (Base, BatchStatusEnum,
                                               ProcessedEssayStatusEnum, User)


@pytest.fixture
async def db_handler() -> AsyncGenerator[DatabaseHandler, None]:
    """Fixture providing a test DatabaseHandler."""
    # Use a fresh in-memory SQLite database for tests
    test_settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
    handler = DatabaseHandler(test_settings)

    # Create all tables
    await handler.create_tables()

    yield handler

    # Cleanup
    async with handler.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await handler.engine.dispose()


@pytest.mark.asyncio
async def test_create_tables(db_handler: DatabaseHandler) -> None:
    """Test creating database tables."""
    # Tables should have been created by the fixture
    async with db_handler.engine.begin() as conn:
        # Get the list of tables
        tables = await conn.run_sync(
            lambda sync_conn: sync_conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'"),
            )
            .scalars()
            .all(),
        )

        # Check that our tables exist
        assert "users" in tables
        assert "batch_uploads" in tables
        assert "processed_essays" in tables
        assert "comparison_pairs" in tables


@pytest.mark.asyncio
async def test_session_context_manager(db_handler: DatabaseHandler) -> None:
    """Test that the session context manager works correctly."""
    # Create a user in the session
    async with db_handler.session() as session:
        user = User(username="testuser", email="test@example.com", full_name="Test User")
        session.add(user)

    # Verify the user was committed to the database
    async with db_handler.session() as session:
        stmt = select(User).where(User.username == "testuser")
        result = await session.execute(stmt)
        fetched_user = result.scalar_one_or_none()

        assert fetched_user is not None
        assert fetched_user.username == "testuser"
        assert fetched_user.email == "test@example.com"


@pytest.mark.asyncio
async def test_create_user(db_handler: DatabaseHandler) -> None:
    """Test creating a user through the handler."""
    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            username="newuser",
            email="new@example.com",
            full_name="New User",
        )

        assert user.id is not None
        assert user.username == "newuser"
        assert user.email == "new@example.com"
        assert user.full_name == "New User"


@pytest.mark.asyncio
async def test_get_user_by_id(db_handler: DatabaseHandler) -> None:
    """Test retrieving a user by ID."""
    # Create a user
    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
        )
        user_id = user.id

    # Retrieve the user by ID
    async with db_handler.session() as session:
        retrieved_user = await db_handler.get_user_by_id(session, user_id)

        assert retrieved_user is not None
        assert retrieved_user.id == user_id
        assert retrieved_user.username == "testuser"


@pytest.mark.asyncio
async def test_get_user_by_username(db_handler: DatabaseHandler) -> None:
    """Test retrieving a user by username."""
    # Create a user
    async with db_handler.session() as session:
        await db_handler.create_user(
            session,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
        )

    # Retrieve the user by username
    async with db_handler.session() as session:
        retrieved_user = await db_handler.get_user_by_username(session, "testuser")

        assert retrieved_user is not None
        assert retrieved_user.username == "testuser"
        assert retrieved_user.email == "test@example.com"


@pytest.mark.asyncio
async def test_create_batch_upload(db_handler: DatabaseHandler) -> None:
    """Test creating a batch upload."""
    # Create a user first
    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
        )
        user_id = user.id

    # Create a batch upload
    async with db_handler.session() as session:
        batch = await db_handler.create_batch_upload(
            session,
            user_id=user_id,
            name="Test Batch",
            description="A test batch",
            metadata={"source": "test"},
        )

        assert batch.id is not None
        assert batch.user_id == user_id
        assert batch.name == "Test Batch"
        assert batch.description == "A test batch"
        assert batch.json_metadata == {"source": "test"}
        assert batch.status == BatchStatusEnum.PENDING


@pytest.mark.asyncio
async def test_get_batch_by_id(db_handler: DatabaseHandler) -> None:
    """Test retrieving a batch by ID."""
    # Create a user and batch
    user_id = None
    batch_id = None

    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
        )
        user_id = user.id

        batch = await db_handler.create_batch_upload(
            session,
            user_id=user_id,
            name="Test Batch",
        )
        batch_id = batch.id

    # Retrieve the batch by ID
    async with db_handler.session() as session:
        retrieved_batch = await db_handler.get_batch_by_id(session, batch_id)

        assert retrieved_batch is not None
        assert retrieved_batch.id == batch_id
        assert retrieved_batch.user_id == user_id
        assert retrieved_batch.name == "Test Batch"


@pytest.mark.asyncio
async def test_get_batches_by_user(db_handler: DatabaseHandler) -> None:
    """Test retrieving all batches for a user."""
    # Create a user and multiple batches
    user_id = None

    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
        )
        user_id = user.id

        await db_handler.create_batch_upload(session, user_id=user_id, name="Batch 1")

        await db_handler.create_batch_upload(session, user_id=user_id, name="Batch 2")

    # Retrieve all batches for the user
    async with db_handler.session() as session:
        batches = await db_handler.get_batches_by_user(session, user_id)

        assert len(batches) == 2
        assert all(batch.user_id == user_id for batch in batches)
        assert {batch.name for batch in batches} == {"Batch 1", "Batch 2"}


@pytest.mark.asyncio
async def test_update_batch_status(db_handler: DatabaseHandler) -> None:
    """Test updating a batch's status."""
    # Create a user and batch
    batch_id = None

    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
        )

        batch = await db_handler.create_batch_upload(
            session,
            user_id=user.id,
            name="Test Batch",
        )
        batch_id = batch.id

    # Update the batch status
    async with db_handler.session() as session:
        updated_batch = await db_handler.update_batch_status(
            session,
            batch_id,
            BatchStatusEnum.PROCESSING_ESSAYS,
        )

        assert updated_batch is not None
        assert updated_batch.status == BatchStatusEnum.PROCESSING_ESSAYS

    # Verify the status was updated in the database
    async with db_handler.session() as session:
        retrieved_batch = await db_handler.get_batch_by_id(session, batch_id)
        assert retrieved_batch is not None, "Batch should exist after update"
        assert retrieved_batch.status == BatchStatusEnum.PROCESSING_ESSAYS
        assert isinstance(retrieved_batch.status, BatchStatusEnum)


@pytest.mark.asyncio
async def test_create_processed_essay(db_handler: DatabaseHandler) -> None:
    """Test creating a processed essay."""
    # Create a user and batch first
    user_id = None
    batch_id = None

    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
        )
        user_id = user.id

        batch = await db_handler.create_batch_upload(
            session,
            user_id=user_id,
            name="Test Batch",
        )
        batch_id = batch.id

    # Create a processed essay
    async with db_handler.session() as session:
        essay = await db_handler.create_processed_essay(
            session,
            batch_id=batch_id,
            original_filename="essay1.txt",
            original_content="This is the original essay.",
            processed_content="This is the processed essay.",
            current_bt_score=0.5,
            processing_metadata={"status": "processed"},
            nlp_features={"word_count": 100},
        )

        assert essay.id is not None
        assert essay.batch_id == batch_id
        assert essay.original_filename == "essay1.txt"
        assert essay.original_content == "This is the original essay."
        assert essay.processed_content == "This is the processed essay."
        assert essay.current_bt_score == 0.5
        assert essay.processing_metadata == {"status": "processed"}
        assert essay.nlp_features == {"word_count": 100}
        assert essay.status == ProcessedEssayStatusEnum.UPLOADED


@pytest.mark.asyncio
async def test_create_comparison_pair(db_handler: DatabaseHandler) -> None:
    """Test creating a comparison pair."""
    # Create user, batch, and essays
    essay_a_id = None
    essay_b_id = None

    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            username="testuser",
            email="test@example.com",
            full_name="Test User",
        )
        batch = await db_handler.create_batch_upload(
            session,
            user_id=user.id,
            name="Test Batch",
        )
        essay_a = await db_handler.create_processed_essay(
            session,
            batch_id=batch.id,
            original_filename="a.txt",
            original_content="Essay A",
            processed_content="Essay A processed",
        )
        essay_a_id = essay_a.id
        essay_b = await db_handler.create_processed_essay(
            session,
            batch_id=batch.id,
            original_filename="b.txt",
            original_content="Essay B",
            processed_content="Essay B processed",
        )
        essay_b_id = essay_b.id

    # Create a comparison pair
    async with db_handler.session() as session:
        assert essay_a_id is not None  # Ensure IDs are set
        assert essay_b_id is not None

        pair = await db_handler.create_comparison_pair(
            session,
            batch_id=batch.id,
            essay_a_id=essay_a_id,
            essay_b_id=essay_b_id,
            prompt_text="Compare A and B",
            prompt_hash="somehash123",
            winner="Essay A",
            confidence=4.5,
            justification="A was better.",
            raw_llm_response='{"winner": "Essay A"}',
            processing_metadata={"model_used": "gpt-test"},
        )

        assert pair.id is not None
        assert pair.essay_a_id == essay_a_id
        assert pair.essay_b_id == essay_b_id
        assert pair.prompt_text == "Compare A and B"
        assert pair.prompt_hash == "somehash123"
        assert pair.winner == "Essay A"
        assert pair.confidence == 4.5
        assert pair.justification == "A was better."
        assert pair.raw_llm_response == '{"winner": "Essay A"}'
        assert pair.processing_metadata == {"model_used": "gpt-test"}
        assert pair.error_message is None
        assert pair.from_cache is False


# --- Start of new tests ---


@pytest.mark.asyncio
async def test_get_batch_by_id_with_essays(db_handler: DatabaseHandler) -> None:
    """Test get_batch_by_id with include_essays=True."""
    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            "user1",
            "user1@test.com",
            "User One",
        )
        batch = await db_handler.create_batch_upload(
            session,
            user.id,
            "Batch With Essays",
        )
        essay1 = await db_handler.create_processed_essay(
            session,
            batch.id,
            "e1.txt",
            "Content1",
            "Processed1",
            current_bt_score=0.1,
        )
        essay2 = await db_handler.create_processed_essay(
            session,
            batch.id,
            "e2.txt",
            "Content2",
            "Processed2",
            current_bt_score=0.2,
        )

    async with db_handler.session() as session:
        retrieved_batch = await db_handler.get_batch_by_id(
            session,
            batch.id,
            include_essays=True,
        )
        assert retrieved_batch is not None
        assert len(retrieved_batch.essays) == 2
        essay_ids = {e.id for e in retrieved_batch.essays}
        assert essay1.id in essay_ids
        assert essay2.id in essay_ids


@pytest.mark.asyncio
async def test_get_batches_by_user_with_essays(db_handler: DatabaseHandler) -> None:
    """Test get_batches_by_user with include_essays=True."""
    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            "user2",
            "user2@test.com",
            "User Two",
        )
        batch1 = await db_handler.create_batch_upload(
            session,
            user.id,
            "Batch1 For User2",
        )
        await db_handler.create_processed_essay(
            session,
            batch1.id,
            "b1e1.txt",
            "B1E1",
            "B1E1P",
        )

        batch2 = await db_handler.create_batch_upload(
            session,
            user.id,
            "Batch2 For User2",
        )
        await db_handler.create_processed_essay(
            session,
            batch2.id,
            "b2e1.txt",
            "B2E1",
            "B2E1P",
        )
        await db_handler.create_processed_essay(
            session,
            batch2.id,
            "b2e2.txt",
            "B2E2",
            "B2E2P",
        )

    async with db_handler.session() as session:
        retrieved_batches = await db_handler.get_batches_by_user(
            session,
            user.id,
            include_essays=True,
        )
        assert len(retrieved_batches) == 2
        for b in retrieved_batches:
            if b.id == batch1.id:
                assert len(b.essays) == 1
            elif b.id == batch2.id:
                assert len(b.essays) == 2
            else:
                pytest.fail("Unexpected batch ID")


@pytest.mark.asyncio
async def test_update_essay_bt_score_non_existent_essay(
    db_handler: DatabaseHandler,
) -> None:
    """Test update_essay_bt_score for a non-existent essay."""
    async with db_handler.session() as session:
        result = await db_handler.update_essay_bt_score(
            session,
            essay_id=99999,
            score=10.0,
        )
        assert result is None


@pytest.mark.asyncio
async def test_create_comparison_pair_with_optional_fields(
    db_handler: DatabaseHandler,
) -> None:
    """Test create_comparison_pair with various optional fields."""
    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            "user_cp",
            "user_cp@test.com",
            "User CP",
        )
        batch = await db_handler.create_batch_upload(session, user.id, "CP Batch")
        essay_a = await db_handler.create_processed_essay(
            session,
            batch.id,
            "cpa.txt",
            "CPA",
            "CPAP",
        )
        essay_b = await db_handler.create_processed_essay(
            session,
            batch.id,
            "cpb.txt",
            "CPB",
            "CPBP",
        )

        # Test 1: Minimal optional fields
        pair1 = await db_handler.create_comparison_pair(
            session,
            batch_id=batch.id,
            essay_a_id=essay_a.id,
            essay_b_id=essay_b.id,
            prompt_text="Compare A and B (Minimal)",
            prompt_hash="minimalhash",
            # All other optionals are None by default
        )
        assert pair1.id is not None
        assert pair1.winner is None
        assert pair1.confidence is None
        assert pair1.justification is None
        assert pair1.raw_llm_response is None
        assert pair1.error_message is None
        assert pair1.from_cache is False
        assert pair1.processing_metadata == {}

        # Test 2: All optional fields populated
        pair2 = await db_handler.create_comparison_pair(
            session,
            batch_id=batch.id,
            essay_a_id=essay_a.id,
            essay_b_id=essay_b.id,
            prompt_text="Compare A and B (Full)",
            prompt_hash="fullhash",
            winner="Essay B",
            confidence=3.0,
            justification="B was okay.",
            raw_llm_response='{"winner": "Essay B"}',
            error_message="Some minor warning perhaps",  # Test with an error message
            from_cache=True,
            processing_metadata={"llm": "fancy-model"},
        )
        assert pair2.id is not None
        assert pair2.winner == "Essay B"
        assert pair2.confidence == 3.0
        assert pair2.justification == "B was okay."
        assert pair2.raw_llm_response == '{"winner": "Essay B"}'
        assert pair2.error_message == "Some minor warning perhaps"
        assert pair2.from_cache is True
        assert pair2.processing_metadata == {"llm": "fancy-model"}


@pytest.mark.asyncio
async def test_get_comparison_pairs_by_essays_exists_and_not_exists(
    db_handler: DatabaseHandler,
) -> None:
    """Test get_comparison_pairs_by_essays for existence and non-existence."""
    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            "user_gcpbe",
            "user_gcpbe@test.com",
            "User GCPBE",
        )
        batch = await db_handler.create_batch_upload(session, user.id, "GCPBE Batch")
        essay_a = await db_handler.create_processed_essay(
            session,
            batch.id,
            "gcpa.txt",
            "GCPA",
            "GCPAP",
        )
        essay_b = await db_handler.create_processed_essay(
            session,
            batch.id,
            "gcpb.txt",
            "GCPB",
            "GCPBP",
        )
        essay_c = await db_handler.create_processed_essay(
            session,
            batch.id,
            "gcpc.txt",
            "GCPC",
            "GCPCP",
        )

        # Create a pair between A and B
        await db_handler.create_comparison_pair(
            session,
            batch_id=batch.id,
            essay_a_id=essay_a.id,
            essay_b_id=essay_b.id,
            prompt_text="A vs B",
            prompt_hash="avsb",
        )

        # Check for A vs B (should exist)
        pairs_ab = await db_handler.get_comparison_pairs_by_essays(
            session,
            essay_a.id,
            essay_b.id,
        )
        assert len(pairs_ab) == 1
        assert pairs_ab[0].essay_a_id == essay_a.id
        assert pairs_ab[0].essay_b_id == essay_b.id

        # Check for A vs C (should not exist)
        pairs_ac = await db_handler.get_comparison_pairs_by_essays(
            session,
            essay_a.id,
            essay_c.id,
        )
        assert len(pairs_ac) == 0

        # Check for B vs A (should exist if query is order-agnostic)
        # Current method is specific to a_id, b_id order
        # Symmetric retrieval would need db_handler changes
        # This tests the current direct query
        pairs_ba = await db_handler.get_comparison_pairs_by_essays(
            session,
            essay_b.id,
            essay_a.id,
        )
        # Expect 0 with current directional query
        assert len(pairs_ba) == 0


@pytest.mark.asyncio
async def test_get_comparison_pairs_for_batch_no_essays(
    db_handler: DatabaseHandler,
) -> None:
    """Test get_comparison_pairs_for_batch when the batch has no essays."""
    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            "user_gcpf_ne",
            "user_gcpf_ne@test.com",
            "User GCPFB NE",
        )
        batch = await db_handler.create_batch_upload(session, user.id, "GCPFB NE Batch")

        pairs = await db_handler.get_comparison_pairs_for_batch(session, batch.id)
        assert len(pairs) == 0


@pytest.mark.asyncio
async def test_get_comparison_pairs_for_batch_with_essays_no_pairs(
    db_handler: DatabaseHandler,
) -> None:
    """Test get_comparison_pairs_for_batch with essays but no pairs."""
    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            "user_gcpf_wenp",
            "user_gcpf_wenp@test.com",
            "User GCPFB WENP",
        )
        batch = await db_handler.create_batch_upload(session, user.id, "GCPFB WENP Batch")
        await db_handler.create_processed_essay(
            session,
            batch.id,
            "gcpf_e1.txt",
            "E1",
            "E1P",
        )
        await db_handler.create_processed_essay(
            session,
            batch.id,
            "gcpf_e2.txt",
            "E2",
            "E2P",
        )

        pairs = await db_handler.get_comparison_pairs_for_batch(session, batch.id)
        assert len(pairs) == 0


@pytest.mark.asyncio
async def test_get_comparison_pairs_for_batch_with_essays_and_pairs(
    db_handler: DatabaseHandler,
) -> None:
    """Test get_comparison_pairs_for_batch with essays and pairs."""
    async with db_handler.session() as session:
        user = await db_handler.create_user(
            session,
            "user_gcpf_wep",
            "user_gcpf_wep@test.com",
            "User GCPFB WEP",
        )
        batch = await db_handler.create_batch_upload(session, user.id, "GCPFB WEP Batch")
        e1 = await db_handler.create_processed_essay(
            session,
            batch.id,
            "gcpf_we_e1.txt",
            "E1",
            "E1P",
        )
        e2 = await db_handler.create_processed_essay(
            session,
            batch.id,
            "gcpf_we_e2.txt",
            "E2",
            "E2P",
        )
        e3 = await db_handler.create_processed_essay(
            session,
            batch.id,
            "gcpf_we_e3.txt",
            "E3",
            "E3P",
        )
        # Pair between e1 and e2
        await db_handler.create_comparison_pair(
            session,
            batch_id=batch.id,
            essay_a_id=e1.id,
            essay_b_id=e2.id,
            prompt_text="e1 vs e2",
            prompt_hash="hash12",
        )
        # Pair between e1 and e3
        await db_handler.create_comparison_pair(
            session,
            batch_id=batch.id,
            essay_a_id=e1.id,
            essay_b_id=e3.id,
            prompt_text="e1 vs e3",
            prompt_hash="hash13",
        )
        # Pair between e2 and e3
        await db_handler.create_comparison_pair(
            session,
            batch_id=batch.id,
            essay_a_id=e2.id,
            essay_b_id=e3.id,
            prompt_text="e2 vs e3",
            prompt_hash="hash23",
        )

        # Create a pair for a different batch to ensure it's not picked up
        other_user = await db_handler.create_user(
            session,
            "other_user",
            "other@test.com",
            "Other User",
        )
        other_batch = await db_handler.create_batch_upload(
            session,
            other_user.id,
            "Other Batch",
        )
        other_e1 = await db_handler.create_processed_essay(
            session,
            other_batch.id,
            "oe1.txt",
            "OE1",
            "OE1P",
        )
        other_e2 = await db_handler.create_processed_essay(
            session,
            other_batch.id,
            "oe2.txt",
            "OE2",
            "OE2P",
        )
        await db_handler.create_comparison_pair(
            session,
            batch_id=other_batch.id,
            essay_a_id=other_e1.id,
            essay_b_id=other_e2.id,
            prompt_text="oe1 vs oe2",
            prompt_hash="hash_other",
        )

        pairs = await db_handler.get_comparison_pairs_for_batch(session, batch.id)
        assert len(pairs) == 3  # Should only get pairs for the specified batch
        pair_essay_ids = set()
        for p in pairs:
            pair_essay_ids.add(tuple(sorted((p.essay_a_id, p.essay_b_id))))

        assert tuple(sorted((e1.id, e2.id))) in pair_essay_ids
        assert tuple(sorted((e1.id, e3.id))) in pair_essay_ids
        assert tuple(sorted((e2.id, e3.id))) in pair_essay_ids


# --- End of new tests ---
