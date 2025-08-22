"""Integration tests for email verification workflow using real database.

Tests the complete email verification flow from request to verification
using testcontainers PostgreSQL and protocol-based mocking for events.
Covers behavioral outcomes and database operations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from huleedu_service_libs.error_handling import HuleEduError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.identity_service.api.schemas import (
    RequestEmailVerificationRequest,
    VerifyEmailRequest,
)
from services.identity_service.domain_handlers.verification_handler import VerificationHandler
from services.identity_service.implementations.user_repository_sqlalchemy_impl import (
    PostgresUserRepo,
)
from services.identity_service.models_db import Base, EmailVerificationToken, User
from services.identity_service.protocols import IdentityEventPublisherProtocol


class TestEmailVerificationIntegration:
    """Integration tests for email verification with real database operations."""

    @pytest.fixture(scope="function")
    def postgres_container(self) -> PostgresContainer:
        """Provide PostgreSQL testcontainer for testing."""
        with PostgresContainer("postgres:15-alpine") as container:
            yield container

    @pytest.fixture(scope="function")
    async def database_engine(
        self, postgres_container: PostgresContainer
    ) -> AsyncGenerator[AsyncEngine, None]:
        """Create async engine with testcontainer database."""
        # Get connection URL and convert to asyncpg
        conn_url = postgres_container.get_connection_url()
        if "+psycopg2://" in conn_url:
            conn_url = conn_url.replace("+psycopg2://", "+asyncpg://")

        engine = create_async_engine(conn_url, echo=False, pool_size=5, max_overflow=0)

        # Create database schema
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        try:
            yield engine
        finally:
            await engine.dispose()

    @pytest.fixture
    def session_factory(self, database_engine: AsyncEngine) -> async_sessionmaker:
        """Create session factory for direct database access."""
        return async_sessionmaker(database_engine, expire_on_commit=False)

    @pytest.fixture
    def user_repo(self, database_engine: AsyncEngine) -> PostgresUserRepo:
        """Create user repository with real database."""
        return PostgresUserRepo(database_engine)

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher for testing event emissions."""
        return AsyncMock(spec=IdentityEventPublisherProtocol)

    @pytest.fixture
    def verification_handler(
        self, user_repo: PostgresUserRepo, mock_event_publisher: AsyncMock
    ) -> VerificationHandler:
        """Create verification handler with real repository and mock events."""
        return VerificationHandler(
            user_repo=user_repo,
            event_publisher=mock_event_publisher,
        )

    @pytest.fixture
    async def unverified_user(self, user_repo: PostgresUserRepo) -> dict:
        """Create an unverified user in the database."""
        user_data = await user_repo.create_user(
            email="test@example.com",
            org_id="test-org",
            password_hash="hashed_password",
        )
        return user_data

    @pytest.fixture
    async def swedish_user(self, user_repo: PostgresUserRepo) -> dict:
        """Create an unverified user with Swedish email address."""
        user_data = await user_repo.create_user(
            email="åsa.öberg@skolan.se",
            org_id="swedish-school",
            password_hash="hashed_password",
        )
        return user_data

    class TestRequestEmailVerification:
        """Test email verification request workflow with database operations."""

        async def test_successful_verification_request_creates_token_in_database(
            self,
            verification_handler: VerificationHandler,
            mock_event_publisher: AsyncMock,
            unverified_user: dict,
            session_factory: async_sessionmaker,
        ) -> None:
            """Should create verification token in database and publish event."""
            # Arrange
            request_data = RequestEmailVerificationRequest()
            correlation_id = uuid4()

            # Act
            result = await verification_handler.request_email_verification(
                request_data, unverified_user["id"], correlation_id
            )

            # Assert response
            assert result.response.message == "Email verification token generated successfully"
            assert result.response.correlation_id == str(correlation_id)

            # Verify token created in database
            async with session_factory() as session:
                stmt = select(EmailVerificationToken).where(
                    EmailVerificationToken.user_id == UUID(unverified_user["id"])
                )
                result = await session.execute(stmt)
                token_records = result.scalars().all()
                assert len(token_records) == 1

                token_record = token_records[0]
                assert token_record.user_id == UUID(unverified_user["id"])
                assert token_record.token is not None
                assert token_record.used_at is None
                assert token_record.expires_at > datetime.now(UTC)

            # Verify event published
            mock_event_publisher.publish_email_verification_requested.assert_called_once()
            event_call_args = mock_event_publisher.publish_email_verification_requested.call_args[0]
            published_user = event_call_args[0]

            # User dict should match core fields (ignoring password_hash if present)
            assert published_user["id"] == unverified_user["id"]
            assert published_user["email"] == unverified_user["email"]
            assert published_user["org_id"] == unverified_user["org_id"]
            assert isinstance(event_call_args[1], str)  # token_id
            assert isinstance(event_call_args[2], datetime)  # expires_at
            assert event_call_args[3] == str(correlation_id)

        async def test_verification_request_with_swedish_email(
            self,
            verification_handler: VerificationHandler,
            mock_event_publisher: AsyncMock,
            swedish_user: dict,
            session_factory: async_sessionmaker,
        ) -> None:
            """Should handle Swedish characters in email addresses correctly."""
            # Arrange
            request_data = RequestEmailVerificationRequest()
            correlation_id = uuid4()

            # Act
            result = await verification_handler.request_email_verification(
                request_data, swedish_user["id"], correlation_id
            )

            # Assert success
            assert result.response.message == "Email verification token generated successfully"

            # Verify token created for Swedish user
            async with session_factory() as session:
                stmt = select(EmailVerificationToken).where(
                    EmailVerificationToken.user_id == UUID(swedish_user["id"])
                )
                result = await session.execute(stmt)
                token_records = result.scalars().all()
                assert len(token_records) == 1

            # Verify event published with Swedish user data
            mock_event_publisher.publish_email_verification_requested.assert_called_once()
            event_call_args = mock_event_publisher.publish_email_verification_requested.call_args[0]
            assert event_call_args[0]["email"] == "åsa.öberg@skolan.se"

        async def test_verification_request_invalidates_existing_tokens(
            self,
            verification_handler: VerificationHandler,
            unverified_user: dict,
            user_repo: PostgresUserRepo,
            session_factory: async_sessionmaker,
        ) -> None:
            """Should invalidate existing tokens before creating new one."""
            # Arrange: Create existing token
            existing_token = await user_repo.create_email_verification_token(
                unverified_user["id"],
                "existing-token",
                datetime.now(UTC) + timedelta(hours=24),
            )

            request_data = RequestEmailVerificationRequest()
            correlation_id = uuid4()

            # Act
            await verification_handler.request_email_verification(
                request_data, unverified_user["id"], correlation_id
            )

            # Assert: Existing token marked as used
            async with session_factory() as session:
                used_token = await session.get(EmailVerificationToken, existing_token["id"])
                assert used_token.used_at is not None

                # New token created
                stmt = (
                    select(EmailVerificationToken)
                    .where(EmailVerificationToken.user_id == UUID(unverified_user["id"]))
                    .order_by(EmailVerificationToken.created_at)
                )
                result = await session.execute(stmt)
                token_records = result.scalars().all()
                assert len(token_records) == 2  # Old (used) + new (unused)
                assert token_records[1].used_at is None  # New token unused

        async def test_verification_request_already_verified_user(
            self,
            verification_handler: VerificationHandler,
            unverified_user: dict,
            user_repo: PostgresUserRepo,
        ) -> None:
            """Should raise error when user email already verified."""
            # Arrange: Mark user as verified
            await user_repo.set_email_verified(unverified_user["id"])

            request_data = RequestEmailVerificationRequest()
            correlation_id = uuid4()

            # Act & Assert
            with pytest.raises(HuleEduError):
                await verification_handler.request_email_verification(
                    request_data, unverified_user["id"], correlation_id
                )

    class TestEmailVerification:
        """Test email verification using token with database operations."""

        async def test_successful_email_verification_updates_user_status(
            self,
            verification_handler: VerificationHandler,
            mock_event_publisher: AsyncMock,
            unverified_user: dict,
            user_repo: PostgresUserRepo,
            session_factory: async_sessionmaker,
        ) -> None:
            """Should verify email and update user status in database."""
            # Arrange: Create verification token
            token_record = await user_repo.create_email_verification_token(
                unverified_user["id"],
                "verification-token",
                datetime.now(UTC) + timedelta(hours=24),
            )

            verify_request = VerifyEmailRequest(token="verification-token")
            correlation_id = uuid4()

            # Act
            result = await verification_handler.verify_email(verify_request, correlation_id)

            # Assert response
            assert result.response.message == "Email verified successfully"

            # Verify user status updated in database
            async with session_factory() as session:
                user = await session.get(User, unverified_user["id"])
                assert user.email_verified is True

            # Verify token marked as used
            async with session_factory() as session:
                token = await session.get(EmailVerificationToken, token_record["id"])
                assert token.used_at is not None

            # Verify event published - handler gets user by ID which includes password_hash
            mock_event_publisher.publish_email_verified.assert_called_once()
            event_call_args = mock_event_publisher.publish_email_verified.call_args[0]
            published_user = event_call_args[0]
            published_correlation_id = event_call_args[1]

            assert published_user["id"] == unverified_user["id"]
            assert published_user["email"] == unverified_user["email"]
            assert published_correlation_id == str(correlation_id)

        async def test_token_one_time_use_enforcement(
            self,
            verification_handler: VerificationHandler,
            unverified_user: dict,
            user_repo: PostgresUserRepo,
        ) -> None:
            """Should prevent reuse of verification token."""
            # Arrange: Create and use token once
            await user_repo.create_email_verification_token(
                unverified_user["id"],
                "one-time-token",
                datetime.now(UTC) + timedelta(hours=24),
            )

            verify_request = VerifyEmailRequest(token="one-time-token")
            correlation_id = uuid4()

            # First use - should succeed
            await verification_handler.verify_email(verify_request, correlation_id)

            # Act & Assert: Second use should fail
            with pytest.raises(HuleEduError):
                await verification_handler.verify_email(verify_request, uuid4())

        async def test_expired_token_handling(
            self,
            verification_handler: VerificationHandler,
            unverified_user: dict,
            user_repo: PostgresUserRepo,
        ) -> None:
            """Should reject expired verification tokens."""
            # Arrange: Create expired token
            await user_repo.create_email_verification_token(
                unverified_user["id"],
                "expired-token",
                datetime.now(UTC) - timedelta(hours=1),  # Expired 1 hour ago
            )

            verify_request = VerifyEmailRequest(token="expired-token")
            correlation_id = uuid4()

            # Act & Assert
            with pytest.raises(HuleEduError):
                await verification_handler.verify_email(verify_request, correlation_id)

        async def test_invalid_token_handling(
            self,
            verification_handler: VerificationHandler,
        ) -> None:
            """Should reject non-existent verification tokens."""
            # Arrange
            verify_request = VerifyEmailRequest(token="non-existent-token")
            correlation_id = uuid4()

            # Act & Assert
            with pytest.raises(HuleEduError):
                await verification_handler.verify_email(verify_request, correlation_id)

        async def test_re_verification_request_handling(
            self,
            verification_handler: VerificationHandler,
            unverified_user: dict,
            user_repo: PostgresUserRepo,
        ) -> None:
            """Should handle new verification request after user already verified."""
            # Arrange: Verify user first
            await user_repo.set_email_verified(unverified_user["id"])

            # Create new token (simulating admin request or system error)
            await user_repo.create_email_verification_token(
                unverified_user["id"],
                "post-verification-token",
                datetime.now(UTC) + timedelta(hours=24),
            )

            verify_request = VerifyEmailRequest(token="post-verification-token")
            correlation_id = uuid4()

            # Act & Assert: Should reject verification of already verified user
            with pytest.raises(HuleEduError):
                await verification_handler.verify_email(verify_request, correlation_id)
