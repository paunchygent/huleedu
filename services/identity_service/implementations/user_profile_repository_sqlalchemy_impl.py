from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncGenerator
from uuid import UUID

from huleedu_service_libs.error_handling import raise_processing_error
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from services.identity_service.models_db import UserProfile
from services.identity_service.protocols import UserProfileRepositoryProtocol


class PostgresUserProfileRepo(UserProfileRepositoryProtocol):
    """PostgreSQL implementation of UserProfileRepositoryProtocol.

    Manages user profile data with proper error handling and session management.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _session_context(self) -> AsyncGenerator[AsyncSession, None]:
        """Context manager for database session handling."""
        async with self._session_factory() as session:
            yield session

    async def get_profile(self, user_id: UUID, correlation_id: UUID) -> UserProfile | None:
        """Get user profile by user_id.

        Args:
            user_id: The user's UUID
            correlation_id: Request correlation ID for observability

        Returns:
            UserProfile if found, None otherwise

        Raises:
            HuleEduError: If database operation fails
        """
        try:
            async with self._session_context() as session:
                stmt = select(UserProfile).where(UserProfile.user_id == user_id)
                result = await session.execute(stmt)
                profile: UserProfile | None = result.scalar_one_or_none()

                if profile:
                    # Prevent DetachedInstanceError by eager loading
                    await session.refresh(profile)

                return profile

        except SQLAlchemyError:
            raise_processing_error(
                service="identity_service",
                operation="get_user_profile",
                message="Database error during profile retrieval",
                correlation_id=correlation_id,
                error_type="SQLAlchemyError",
                user_id=str(user_id),
            )

    async def upsert_profile(
        self, user_id: UUID, profile_data: dict[str, Any], correlation_id: UUID
    ) -> UserProfile:
        """Create or update user profile.

        Args:
            user_id: The user's UUID
            profile_data: Profile fields to update
            correlation_id: Request correlation ID for observability

        Returns:
            The updated UserProfile instance

        Raises:
            HuleEduError: If database operation fails
        """
        try:
            async with self._session_context() as session:
                # Try to get existing profile
                stmt = select(UserProfile).where(UserProfile.user_id == user_id)
                result = await session.execute(stmt)
                profile: UserProfile | None = result.scalar_one_or_none()

                current_time = datetime.now(UTC).replace(tzinfo=None)

                if profile:
                    # Update existing profile
                    for field, value in profile_data.items():
                        if hasattr(profile, field):
                            setattr(profile, field, value)
                    profile.updated_at = current_time
                else:
                    # Create new profile
                    profile = UserProfile(
                        user_id=user_id,
                        created_at=current_time,
                        updated_at=current_time,
                        **profile_data,
                    )
                    session.add(profile)

                await session.flush()
                await session.refresh(profile)  # Prevent DetachedInstanceError
                await session.commit()

                return profile

        except SQLAlchemyError:
            raise_processing_error(
                service="identity_service",
                operation="upsert_user_profile",
                message="Database error during profile upsert",
                correlation_id=correlation_id,
                error_type="SQLAlchemyError",
                user_id=str(user_id),
            )
