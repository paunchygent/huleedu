"""Database handler for the CJ Essay Assessment system.

This module provides an asynchronous interface for SQLAlchemy operations,
including session management and CRUD operations for database models.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlalchemy.orm import selectinload

from src.cj_essay_assessment.config import Settings
from src.cj_essay_assessment.models_db import (Base, BatchStatusEnum,
                                               BatchUpload, ComparisonPair,
                                               ProcessedEssay, User)

# Type variable for entity models
T = TypeVar("T", bound=Base)


class DatabaseHandler:
    """Handler for database operations with async SQLAlchemy."""

    def __init__(self, settings: Settings, db_url: str | None = None):
        """Initialize the database handler with connection URL. Settings must be provided explicitly."""
        self.db_url = db_url or settings.database_url
        self.engine = create_async_engine(
            self.db_url,
            echo=False,
            future=True,  # Set to True for debugging SQL
        )
        self.async_session_maker = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def create_tables(self) -> None:
        """Create database tables if they don't exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager for database sessions."""
        session = self.async_session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    # User CRUD operations

    async def create_user(
        self,
        session: AsyncSession,
        username: str,
        email: str,
        full_name: str,
    ) -> User:
        """Create a new user."""
        user = User(username=username, email=email, full_name=full_name)
        session.add(user)
        await session.flush()
        return user

    async def get_user_by_id(self, session: AsyncSession, user_id: int) -> User | None:
        """Get a user by ID."""
        db_user: User | None = await session.get(User, user_id)
        if db_user is not None:
            assert isinstance(db_user, User)
        return db_user

    async def get_user_by_username(
        self,
        session: AsyncSession,
        username: str,
    ) -> User | None:
        """Get a user by username."""
        stmt = select(User).where(User.username == username)
        db_user: User | None = (await session.execute(stmt)).scalars().one_or_none()
        if db_user is not None:
            assert isinstance(db_user, User)
        return db_user

    # BatchUpload CRUD operations

    async def create_batch_upload(
        self,
        session: AsyncSession,
        user_id: int,
        name: str,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BatchUpload:
        """Create a new batch upload."""
        batch = BatchUpload(
            user_id=user_id,
            name=name,
            description=description,
            json_metadata=metadata or {},
        )
        session.add(batch)
        await session.flush()
        return batch

    async def get_batch_by_id(
        self,
        session: AsyncSession,
        batch_id: int,
        include_essays: bool = False,
    ) -> BatchUpload | None:
        """Get a batch upload by ID."""
        stmt = select(BatchUpload).where(BatchUpload.id == batch_id)

        if include_essays:
            stmt = stmt.options(selectinload(BatchUpload.essays))

        db_batch: BatchUpload | None = (
            (await session.execute(stmt)).scalars().one_or_none()
        )
        if db_batch is not None:
            assert isinstance(db_batch, BatchUpload)
        return db_batch

    async def get_batches_by_user(
        self,
        session: AsyncSession,
        user_id: int,
        include_essays: bool = False,
    ) -> list[BatchUpload]:
        """Get all batch uploads for a user."""
        stmt = select(BatchUpload).where(BatchUpload.user_id == user_id)

        if include_essays:
            stmt = stmt.options(selectinload(BatchUpload.essays))

        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_batch_status(
        self,
        session: AsyncSession,
        batch_id: int,
        status: BatchStatusEnum,
    ) -> BatchUpload | None:
        """Update a batch upload's status."""
        batch = await self.get_batch_by_id(session, batch_id)
        if batch:
            batch.status = status
            await session.flush()
        return batch

    # ProcessedEssay CRUD operations

    async def create_processed_essay(
        self,
        session: AsyncSession,
        batch_id: int,
        original_filename: str,
        original_content: str,
        processed_content: str,
        current_bt_score: float | None = None,
        processing_metadata: dict[str, Any] | None = None,
        nlp_features: dict[str, Any] | None = None,
    ) -> ProcessedEssay:
        """Create a new processed essay."""
        essay = ProcessedEssay(
            batch_id=batch_id,
            original_filename=original_filename,
            original_content=original_content,
            processed_content=processed_content,
            current_bt_score=current_bt_score,
            processing_metadata=processing_metadata or {},
            nlp_features=nlp_features or {},
        )
        session.add(essay)
        await session.flush()
        return essay

    async def get_essay_by_id(
        self,
        session: AsyncSession,
        essay_id: int,
    ) -> ProcessedEssay | None:
        """Get a processed essay by ID."""
        db_essay: ProcessedEssay | None = await session.get(ProcessedEssay, essay_id)
        if db_essay is not None:
            assert isinstance(db_essay, ProcessedEssay)
        return db_essay

    async def get_essays_by_batch(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> list[ProcessedEssay]:
        """Get all processed essays for a batch."""
        stmt = select(ProcessedEssay).where(ProcessedEssay.batch_id == batch_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_essay_bt_score(
        self,
        session: AsyncSession,
        essay_id: int,
        score: float,
    ) -> ProcessedEssay | None:
        """Update a processed essay's Bradley-Terry score."""
        essay = await self.get_essay_by_id(session, essay_id)
        if essay:
            essay.current_bt_score = score
            await session.flush()
        return essay

    # ComparisonPair CRUD operations

    async def create_comparison_pair(
        self,
        session: AsyncSession,
        batch_id: int,
        essay_a_id: int,
        essay_b_id: int,
        prompt_text: str,
        prompt_hash: str,
        winner: str | None = None,
        confidence: float | None = None,
        justification: str | None = None,
        raw_llm_response: str | None = None,
        error_message: str | None = None,
        from_cache: bool = False,
        processing_metadata: dict[str, Any] | None = None,
    ) -> ComparisonPair:
        """Create a new comparison pair."""
        pair = ComparisonPair(
            batch_id=batch_id,
            essay_a_id=essay_a_id,
            essay_b_id=essay_b_id,
            prompt_text=prompt_text,
            prompt_hash=prompt_hash,
            winner=winner,
            confidence=confidence,
            justification=justification,
            raw_llm_response=raw_llm_response,
            error_message=error_message,
            from_cache=from_cache,
            processing_metadata=processing_metadata or {},
        )
        session.add(pair)
        await session.flush()
        return pair

    async def get_comparison_pair_by_id(
        self,
        session: AsyncSession,
        pair_id: int,
    ) -> ComparisonPair | None:
        """Get a comparison pair by ID."""
        db_pair: ComparisonPair | None = await session.get(ComparisonPair, pair_id)
        if db_pair is not None:
            assert isinstance(db_pair, ComparisonPair)
        return db_pair

    async def get_comparison_pairs_by_essays(
        self,
        session: AsyncSession,
        essay_a_id: int,
        essay_b_id: int,
    ) -> list[ComparisonPair]:
        """Get all comparison pairs between two essays."""
        stmt = select(ComparisonPair).where(
            (ComparisonPair.essay_a_id == essay_a_id)
            & (ComparisonPair.essay_b_id == essay_b_id),
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_comparison_pairs_for_batch(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> list[ComparisonPair]:
        """Get all comparison pairs for essays in a batch."""
        # First get all essays in the batch
        essays = await self.get_essays_by_batch(session, batch_id)
        essay_ids = [essay.id for essay in essays]

        # Then find all comparison pairs involving these essays
        stmt = select(ComparisonPair).where(
            (ComparisonPair.essay_a_id.in_(essay_ids))
            & (ComparisonPair.essay_b_id.in_(essay_ids)),
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
