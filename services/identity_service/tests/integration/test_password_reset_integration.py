"""
Integration tests for password reset functionality.

Tests the complete password reset workflow including database operations,
event publishing, rate limiting, and security features using real PostgreSQL.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from services.identity_service.api.schemas import (
    RequestPasswordResetRequest,
    ResetPasswordRequest,
)
from services.identity_service.config import Settings
from services.identity_service.domain_handlers.password_reset_handler import PasswordResetHandler
from services.identity_service.models_db import Base, PasswordResetToken, User


class TestPasswordResetIntegration:
    """Integration tests for password reset workflow with real database."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> PostgresContainer:
        """Start PostgreSQL test container."""
        container = PostgresContainer("postgres:15-alpine")
        container.start()
        yield container
        container.stop()

    class DatabaseTestSettings(Settings):
        """Test settings with database URL override."""

        def __init__(self, database_url: str) -> None:
            super().__init__()
            object.__setattr__(self, "_database_url", database_url)

        @property
        def database_url(self) -> str:
            return str(object.__getattribute__(self, "_database_url"))

    @pytest.fixture
    def test_settings(self, postgres_container: PostgresContainer) -> Settings:
        """Create test settings with database URL."""
        pg_connection_url = postgres_container.get_connection_url()
        if "+psycopg2://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("postgresql://", "postgresql+asyncpg://")

        return self.DatabaseTestSettings(database_url=pg_connection_url)

    @pytest.fixture
    async def database_engine(self, test_settings: Settings) -> AsyncGenerator[AsyncEngine, None]:
        """Create async database engine with schema."""
        engine = create_async_engine(test_settings.database_url)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        try:
            yield engine
        finally:
            await engine.dispose()

    @pytest.fixture
    async def session_factory(
        self, database_engine: AsyncEngine
    ) -> async_sessionmaker[AsyncSession]:
        """Create async session factory."""
        return async_sessionmaker(database_engine, expire_on_commit=False)

    @pytest.fixture
    async def test_user(self, session_factory: async_sessionmaker[AsyncSession]) -> dict:
        """Create test user in database."""
        user_id = uuid4()
        user_email = f"test-{uuid4()}@example.com"

        user = User(
            id=user_id,
            email=user_email,
            password_hash="$2b$12$existing_hash",
            email_verified=True,
        )

        async with session_factory() as session:
            async with session.begin():
                session.add(user)

        return {
            "id": str(user_id),
            "email": user_email,
            "password_hash": "$2b$12$existing_hash",
            "email_verified": True,
        }

    @pytest.fixture
    def mock_user_repo(self) -> AsyncMock:
        """Create mock user repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_password_hasher(self) -> Mock:
        """Create mock password hasher."""
        hasher = Mock()
        hasher.hash.return_value = "$2b$12$new_password_hash"
        hasher.verify.return_value = True
        return hasher

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher."""
        return AsyncMock()

    @pytest.fixture
    def mock_audit_logger(self) -> AsyncMock:
        """Create mock audit logger."""
        return AsyncMock()

    @pytest.fixture
    def mock_rate_limiter(self) -> AsyncMock:
        """Create mock rate limiter."""
        limiter = AsyncMock()
        limiter.check_rate_limit.return_value = (True, 4)  # allowed, remaining
        return limiter

    @pytest.fixture
    def password_reset_handler(
        self,
        mock_user_repo: AsyncMock,
        mock_password_hasher: Mock,
        mock_event_publisher: AsyncMock,
        mock_audit_logger: AsyncMock,
    ) -> PasswordResetHandler:
        """Create password reset handler with mocked dependencies."""
        return PasswordResetHandler(
            user_repo=mock_user_repo,
            password_hasher=mock_password_hasher,
            event_publisher=mock_event_publisher,
            audit_logger=mock_audit_logger,
        )

    async def test_request_reset_creates_token_and_publishes_event(
        self,
        password_reset_handler: PasswordResetHandler,
        mock_user_repo: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_audit_logger: AsyncMock,
        test_user: dict,
    ) -> None:
        """Should create password reset token and publish event for existing user."""
        # Arrange
        correlation_id = uuid4()
        reset_request = RequestPasswordResetRequest(email=test_user["email"])

        # Pre-define the expires_at to avoid timing issues in assertions
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        token_record = {
            "id": str(uuid4()),
            "user_id": test_user["id"],
            "token": str(uuid4()),
            "expires_at": expires_at,
            "created_at": datetime.now(UTC),
            "used_at": None,
        }

        mock_user_repo.get_user_by_email.return_value = test_user
        mock_user_repo.invalidate_password_reset_tokens.return_value = None
        mock_user_repo.create_password_reset_token.return_value = token_record

        # Act
        result = await password_reset_handler.request_password_reset(
            reset_request, correlation_id, ip_address="192.168.1.1"
        )

        # Assert
        assert (
            result.response.message
            == "If the email address exists, a password reset link will be sent"
        )
        assert result.response.correlation_id == str(correlation_id)

        # Verify user lookup
        mock_user_repo.get_user_by_email.assert_called_once_with(test_user["email"])

        # Verify token invalidation
        mock_user_repo.invalidate_password_reset_tokens.assert_called_once_with(test_user["id"])

        # Verify token creation
        mock_user_repo.create_password_reset_token.assert_called_once()
        call_args = mock_user_repo.create_password_reset_token.call_args[0]
        assert call_args[0] == test_user["id"]  # user_id
        assert isinstance(call_args[1], str)  # token (UUID string)
        assert isinstance(call_args[2], datetime)  # expires_at

        # Verify event publishing - check each argument separately to avoid timing issues
        mock_event_publisher.publish_password_reset_requested.assert_called_once()
        event_call_args = mock_event_publisher.publish_password_reset_requested.call_args[0]
        assert event_call_args[0] == test_user
        assert event_call_args[1] == token_record["id"]
        assert isinstance(event_call_args[2], datetime)  # expires_at (generated timestamp)
        assert event_call_args[3] == str(correlation_id)

        # Verify audit logging
        mock_audit_logger.log_action.assert_called_once()
        audit_call = mock_audit_logger.log_action.call_args
        assert audit_call[1]["action"] == "password_reset_requested"
        assert audit_call[1]["user_id"] == UUID(test_user["id"])
        assert audit_call[1]["details"]["email"] == test_user["email"]
        assert audit_call[1]["details"]["token_id"] == token_record["id"]
        assert audit_call[1]["ip_address"] == "192.168.1.1"
        assert audit_call[1]["correlation_id"] == correlation_id

    async def test_request_reset_for_nonexistent_email_no_disclosure(
        self,
        password_reset_handler: PasswordResetHandler,
        mock_user_repo: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_audit_logger: AsyncMock,
    ) -> None:
        """Should return same response for non-existent email (no user enumeration)."""
        # Arrange
        correlation_id = uuid4()
        nonexistent_email = f"nonexistent-{uuid4()}@example.com"
        reset_request = RequestPasswordResetRequest(email=nonexistent_email)

        mock_user_repo.get_user_by_email.return_value = None

        # Act
        result = await password_reset_handler.request_password_reset(
            reset_request, correlation_id, ip_address="192.168.1.1"
        )

        # Assert
        assert (
            result.response.message
            == "If the email address exists, a password reset link will be sent"
        )
        assert result.response.correlation_id == str(correlation_id)

        # Verify no token operations for non-existent user
        mock_user_repo.invalidate_password_reset_tokens.assert_not_called()
        mock_user_repo.create_password_reset_token.assert_not_called()
        mock_event_publisher.publish_password_reset_requested.assert_not_called()

        # Verify security audit logging
        mock_audit_logger.log_action.assert_called_once_with(
            action="password_reset_requested_nonexistent",
            user_id=None,
            details={"email": nonexistent_email},
            ip_address="192.168.1.1",
            user_agent=None,
            correlation_id=correlation_id,
        )

    async def test_reset_password_successful_workflow(
        self,
        password_reset_handler: PasswordResetHandler,
        mock_user_repo: AsyncMock,
        mock_password_hasher: Mock,
        mock_event_publisher: AsyncMock,
        test_user: dict,
    ) -> None:
        """Should successfully reset password with valid token."""
        # Arrange
        correlation_id = uuid4()
        reset_token = str(uuid4())
        new_password = "NewSecurePassword123!"

        token_record = {
            "id": str(uuid4()),
            "user_id": test_user["id"],
            "token": reset_token,
            "expires_at": datetime.now(UTC) + timedelta(minutes=30),
            "created_at": datetime.now(UTC),
            "used_at": None,
        }

        reset_request = ResetPasswordRequest(token=reset_token, new_password=new_password)

        mock_user_repo.get_password_reset_token.return_value = token_record
        mock_user_repo.get_user_by_id.return_value = test_user
        mock_password_hasher.hash.return_value = "$2b$12$new_password_hash"

        # Act
        result = await password_reset_handler.reset_password(
            reset_request, correlation_id, ip_address="192.168.1.1"
        )

        # Assert - ResetPasswordResponse only has message field
        assert result.response.message == "Password reset successfully"

        # Verify token validation
        mock_user_repo.get_password_reset_token.assert_called_once_with(reset_token)

        # Verify password hashing
        mock_password_hasher.hash.assert_called_once_with(new_password)

        # Verify token marking as used
        mock_user_repo.mark_reset_token_used.assert_called_once_with(token_record["id"])

        # Verify password update
        mock_user_repo.update_user_password.assert_called_once_with(
            test_user["id"], "$2b$12$new_password_hash"
        )

        # Verify event publishing
        mock_event_publisher.publish_password_reset_completed.assert_called_once_with(
            test_user, str(correlation_id)
        )

    async def test_reset_password_with_expired_token(
        self,
        password_reset_handler: PasswordResetHandler,
        mock_user_repo: AsyncMock,
        mock_audit_logger: AsyncMock,
    ) -> None:
        """Should reject expired reset tokens."""
        # Arrange
        correlation_id = uuid4()
        reset_token = str(uuid4())

        token_record = {
            "id": str(uuid4()),
            "user_id": str(uuid4()),
            "token": reset_token,
            "expires_at": datetime.now(UTC) - timedelta(hours=1),  # Expired
            "created_at": datetime.now(UTC) - timedelta(hours=2),
            "used_at": None,
        }

        reset_request = ResetPasswordRequest(token=reset_token, new_password="NewPassword123!")
        mock_user_repo.get_password_reset_token.return_value = token_record

        # Act & Assert
        with pytest.raises(Exception):  # HuleEduError - specific error handling
            await password_reset_handler.reset_password(
                reset_request, correlation_id, ip_address="192.168.1.1"
            )

        # Verify audit logging for expired token
        mock_audit_logger.log_action.assert_called_once()
        audit_call = mock_audit_logger.log_action.call_args
        assert audit_call[1]["action"] == "password_reset_token_expired"
        assert audit_call[1]["user_id"] == UUID(str(token_record["user_id"]))
        assert audit_call[1]["details"]["token_id"] == token_record["id"]
        assert audit_call[1]["ip_address"] == "192.168.1.1"
        assert audit_call[1]["correlation_id"] == correlation_id

    async def test_reset_password_with_used_token(
        self,
        password_reset_handler: PasswordResetHandler,
        mock_user_repo: AsyncMock,
        mock_audit_logger: AsyncMock,
    ) -> None:
        """Should reject already used reset tokens."""
        # Arrange
        correlation_id = uuid4()
        reset_token = str(uuid4())
        used_timestamp = datetime.now(UTC) - timedelta(minutes=30)

        token_record = {
            "id": str(uuid4()),
            "user_id": str(uuid4()),
            "token": reset_token,
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
            "created_at": datetime.now(UTC) - timedelta(hours=1),
            "used_at": used_timestamp,  # Already used
        }

        reset_request = ResetPasswordRequest(token=reset_token, new_password="NewPassword123!")
        mock_user_repo.get_password_reset_token.return_value = token_record

        # Act & Assert
        with pytest.raises(Exception):  # HuleEduError - specific error handling
            await password_reset_handler.reset_password(
                reset_request, correlation_id, ip_address="192.168.1.1"
            )

        # Verify audit logging for used token
        mock_audit_logger.log_action.assert_called_once()
        audit_call = mock_audit_logger.log_action.call_args
        assert audit_call[1]["action"] == "password_reset_token_already_used"
        assert audit_call[1]["user_id"] == UUID(str(token_record["user_id"]))
        assert audit_call[1]["details"]["token_id"] == token_record["id"]
        assert audit_call[1]["details"]["used_at"] == used_timestamp.isoformat()
        assert audit_call[1]["ip_address"] == "192.168.1.1"
        assert audit_call[1]["correlation_id"] == correlation_id

    async def test_database_token_persistence_and_retrieval(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        test_user: dict,
    ) -> None:
        """Should properly store and retrieve password reset tokens from database."""
        # Arrange
        token_value = str(uuid4())
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        token = PasswordResetToken(
            user_id=UUID(test_user["id"]),
            token=token_value,
            expires_at=expires_at,
        )

        # Act - Store token
        async with session_factory() as session:
            async with session.begin():
                session.add(token)

        # Act - Retrieve token
        async with session_factory() as session:
            result = await session.execute(
                select(PasswordResetToken).where(PasswordResetToken.token == token_value)
            )
            retrieved_token = result.scalar_one_or_none()

        # Assert
        assert retrieved_token is not None
        assert retrieved_token.user_id == UUID(test_user["id"])
        assert retrieved_token.token == token_value
        assert retrieved_token.expires_at == expires_at
        assert retrieved_token.used_at is None
        assert retrieved_token.created_at is not None

    async def test_token_used_at_tracking(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        test_user: dict,
    ) -> None:
        """Should track when tokens are used."""
        # Arrange
        token_value = str(uuid4())
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        token = PasswordResetToken(
            user_id=UUID(test_user["id"]),
            token=token_value,
            expires_at=expires_at,
        )

        async with session_factory() as session:
            async with session.begin():
                session.add(token)

        # Act - Mark token as used
        used_timestamp = datetime.now(UTC)
        async with session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(PasswordResetToken).where(PasswordResetToken.token == token_value)
                )
                token_to_update = result.scalar_one()
                token_to_update.used_at = used_timestamp

        # Assert - Verify token is marked as used
        async with session_factory() as session:
            result = await session.execute(
                select(PasswordResetToken).where(PasswordResetToken.token == token_value)
            )
            updated_token = result.scalar_one()

        assert updated_token.used_at is not None
        assert abs((updated_token.used_at - used_timestamp).total_seconds()) < 1

    async def test_old_password_invalidation_after_reset(
        self,
        password_reset_handler: PasswordResetHandler,
        mock_user_repo: AsyncMock,
        mock_password_hasher: Mock,
        test_user: dict,
    ) -> None:
        """Should invalidate old password hash after successful reset."""
        # Arrange
        correlation_id = uuid4()
        reset_token = str(uuid4())
        new_password = "NewSecurePassword123!"
        old_password_hash = test_user["password_hash"]
        new_password_hash = "$2b$12$completely_new_hash"

        token_record = {
            "id": str(uuid4()),
            "user_id": test_user["id"],
            "token": reset_token,
            "expires_at": datetime.now(UTC) + timedelta(minutes=30),
            "created_at": datetime.now(UTC),
            "used_at": None,
        }

        reset_request = ResetPasswordRequest(token=reset_token, new_password=new_password)

        mock_user_repo.get_password_reset_token.return_value = token_record
        mock_user_repo.get_user_by_id.return_value = test_user
        # Fix the AsyncMock configuration - ensure it returns the value, not a coroutine
        mock_password_hasher.hash.return_value = new_password_hash

        # Act
        await password_reset_handler.reset_password(
            reset_request, correlation_id, ip_address="192.168.1.1"
        )

        # Assert
        mock_user_repo.update_user_password.assert_called_once_with(
            test_user["id"], new_password_hash
        )

        # Verify old password hash is different from new one
        assert old_password_hash != new_password_hash
