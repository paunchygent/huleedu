"""Database-backed content repository implementation for Content Service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import UUID, uuid4

from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_content_service_error,
    raise_resource_not_found,
)
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from services.content_service.models_db import StoredContent
from services.content_service.protocols import ContentRepositoryProtocol

logger = create_service_logger("content.repository.db")


class ContentRepository(ContentRepositoryProtocol):
    """Repository implementation for persisted content."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Initialize the repository with a database engine."""
        self._engine = engine
        self._sessionmaker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("Initialized ContentRepository with PostgreSQL-backed storage")

    @asynccontextmanager
    async def _get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a database session with proper transaction handling."""
        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def save_content(
        self,
        content_id: str,
        content_data: bytes,
        content_type: str,
        correlation_id: UUID | None = None,
    ) -> None:
        """Persist content bytes and metadata.

        Raises a content service error if the operation fails.
        """
        async with self._get_session() as session:
            try:
                stored = StoredContent(
                    content_id=content_id,
                    content_data=content_data,
                    content_size=len(content_data),
                    correlation_id=correlation_id,
                    content_type=content_type,
                )
                session.add(stored)

                logger.info(
                    "Stored content with ID: %s",
                    content_id,
                    extra={"correlation_id": str(correlation_id) if correlation_id else None},
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "Failed to store content %s: %s",
                    content_id,
                    exc,
                    extra={"correlation_id": str(correlation_id) if correlation_id else None},
                    exc_info=True,
                )
                raise_content_service_error(
                    service="content_service",
                    operation="save_content",
                    message=f"Failed to store content: {exc}",
                    correlation_id=correlation_id or uuid4(),
                    content_id=content_id,
                )

    async def get_content(
        self,
        content_id: str,
        correlation_id: UUID | None = None,
    ) -> tuple[bytes, str]:
        """Retrieve content bytes and content type by identifier.

        Raises RESOURCE_NOT_FOUND if the content does not exist.
        """
        async with self._get_session() as session:
            try:
                stmt = select(StoredContent).where(StoredContent.content_id == content_id)
                result = await session.execute(stmt)
                stored = result.scalar_one_or_none()

                if stored is None:
                    logger.warning(
                        "Content not found for ID: %s",
                        content_id,
                        extra={"correlation_id": str(correlation_id) if correlation_id else None},
                    )
                    raise_resource_not_found(
                        service="content_service",
                        operation="get_content",
                        resource_type="content",
                        resource_id=content_id,
                        correlation_id=correlation_id or uuid4(),
                    )

                logger.info(
                    "Loaded content for ID: %s",
                    content_id,
                    extra={"correlation_id": str(correlation_id) if correlation_id else None},
                )
                return stored.content_data, stored.content_type
            except HuleEduError:
                # Propagate domain errors (including RESOURCE_NOT_FOUND) unchanged
                raise
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "Unexpected error loading content %s: %s",
                    content_id,
                    exc,
                    extra={"correlation_id": str(correlation_id) if correlation_id else None},
                    exc_info=True,
                )
                raise_content_service_error(
                    service="content_service",
                    operation="get_content",
                    message=f"Failed to load content: {exc}",
                    correlation_id=correlation_id or uuid4(),
                    content_id=content_id,
                )

    async def content_exists(self, content_id: str) -> bool:
        """Check if content exists for the given identifier."""
        async with self._get_session() as session:
            stmt = select(StoredContent.content_id).where(StoredContent.content_id == content_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None
