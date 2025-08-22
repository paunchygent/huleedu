"""
Authentication flow integration tests for Identity Service.

Tests complete authentication workflows with real PostgreSQL database:
- Registration → Login → Token refresh flow
- Database state verification across User, UserProfile, RefreshSession tables
- Event publishing verification for UserRegisteredV1 and LoginSucceededV1
- Session management lifecycle with Swedish character support

Follows established testcontainers and Dishka DI override patterns.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from services.identity_service.api.schemas import (
    LoginRequest,
    PersonNameSchema,
    RefreshTokenRequest,
    RegisterRequest,
)
from services.identity_service.config import Settings
from services.identity_service.domain_handlers.authentication_handler import (
    AuthenticationHandler,
)
from services.identity_service.domain_handlers.registration_handler import (
    RegistrationHandler,
)
from services.identity_service.implementations.password_hasher_impl import (
    Argon2idPasswordHasher,
)
from services.identity_service.implementations.token_issuer_impl import (
    DevTokenIssuer,
)
from services.identity_service.implementations.user_repository_sqlalchemy_impl import (
    PostgresUserRepo,
)
from services.identity_service.models_db import Base, User, UserProfile
from services.identity_service.protocols import (
    AuditLoggerProtocol,
    IdentityEventPublisherProtocol,
    RateLimiterProtocol,
    SessionRepo,
    UserSessionRepositoryProtocol,
)


class TestAuthFlowIntegration:
    """Integration tests for complete authentication workflows with real PostgreSQL."""

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

    @pytest.fixture(autouse=True)
    async def clean_database(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Clean the database before each test."""
        from sqlalchemy import text

        async with session_factory() as session:
            async with session.begin():
                # Disable foreign key checks temporarily
                await session.execute(text("SET session_replication_role = replica;"))

                # Truncate all tables
                await session.execute(text("TRUNCATE TABLE user_sessions CASCADE"))
                await session.execute(text("TRUNCATE TABLE audit_logs CASCADE"))
                await session.execute(text("TRUNCATE TABLE event_outbox CASCADE"))
                await session.execute(text("TRUNCATE TABLE password_reset_tokens CASCADE"))
                await session.execute(text("TRUNCATE TABLE email_verification_tokens CASCADE"))
                await session.execute(text("TRUNCATE TABLE refresh_sessions CASCADE"))
                await session.execute(text("TRUNCATE TABLE user_profiles CASCADE"))
                await session.execute(text("TRUNCATE TABLE users CASCADE"))

                # Re-enable foreign key checks
                await session.execute(text("SET session_replication_role = DEFAULT;"))

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Mock event publisher for verifying event publishing."""
        return AsyncMock(spec=IdentityEventPublisherProtocol)

    @pytest.fixture
    def mock_rate_limiter(self) -> AsyncMock:
        """Mock rate limiter that always allows requests."""
        mock = AsyncMock(spec=RateLimiterProtocol)
        mock.check_rate_limit.return_value = (True, 5)  # allowed, remaining
        mock.increment.return_value = 1
        return mock

    @pytest.fixture
    def mock_audit_logger(self) -> AsyncMock:
        """Mock audit logger for tracking security events."""
        return AsyncMock(spec=AuditLoggerProtocol)

    @pytest.fixture
    def mock_session_repo(self) -> AsyncMock:
        """Mock session repository for refresh token storage."""
        mock = AsyncMock(spec=SessionRepo)
        mock.is_refresh_valid.return_value = True
        return mock

    @pytest.fixture
    def mock_user_session_repo(self) -> AsyncMock:
        """Mock user session repository for device tracking."""
        return AsyncMock(spec=UserSessionRepositoryProtocol)

    @pytest.fixture
    def password_hasher(self) -> Argon2idPasswordHasher:
        """Password hasher implementation."""
        return Argon2idPasswordHasher()

    @pytest.fixture
    def token_issuer(self) -> DevTokenIssuer:
        """Token issuer implementation with test JWT secret."""
        return DevTokenIssuer()

    @pytest.fixture
    def user_repo(self, database_engine: AsyncEngine) -> PostgresUserRepo:
        """User repository with real database."""
        return PostgresUserRepo(database_engine)

    @pytest.fixture
    def mock_profile_repo(self) -> AsyncMock:
        """Mock profile repository for user profile operations."""
        from services.identity_service.protocols import UserProfileRepositoryProtocol
        return AsyncMock(spec=UserProfileRepositoryProtocol)

    @pytest.fixture
    def registration_handler(
        self,
        user_repo: PostgresUserRepo,
        password_hasher: Argon2idPasswordHasher,
        mock_event_publisher: AsyncMock,
        mock_profile_repo: AsyncMock,
    ) -> RegistrationHandler:
        """Registration handler with real database and mocked dependencies."""
        mock_verification_handler = AsyncMock()
        return RegistrationHandler(
            user_repo=user_repo,
            password_hasher=password_hasher,
            event_publisher=mock_event_publisher,
            verification_handler=mock_verification_handler,
            profile_repository=mock_profile_repo,
        )

    @pytest.fixture
    def auth_handler(
        self,
        user_repo: PostgresUserRepo,
        token_issuer: DevTokenIssuer,
        password_hasher: Argon2idPasswordHasher,
        mock_session_repo: AsyncMock,
        mock_user_session_repo: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_rate_limiter: AsyncMock,
        mock_audit_logger: AsyncMock,
    ) -> AuthenticationHandler:
        """Authentication handler with real database and mocked dependencies."""
        return AuthenticationHandler(
            user_repo=user_repo,
            token_issuer=token_issuer,
            password_hasher=password_hasher,
            session_repo=mock_session_repo,
            user_session_repo=mock_user_session_repo,
            event_publisher=mock_event_publisher,
            rate_limiter=mock_rate_limiter,
            audit_logger=mock_audit_logger,
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "email",
        [
            "åsa.öberg@example.com",
            "nils.bergström@example.com",
            "test.user@example.com",
        ],
    )
    async def test_complete_registration_login_refresh_flow(
        self,
        email: str,
        registration_handler: RegistrationHandler,
        auth_handler: AuthenticationHandler,
        session_factory: async_sessionmaker[AsyncSession],
        mock_event_publisher: AsyncMock,
        mock_session_repo: AsyncMock,
        token_issuer: DevTokenIssuer,
    ) -> None:
        """Test complete authentication flow: registration → login → token refresh."""
        correlation_id = uuid4()

        # Test data - email comes from parametrization
        password = "SecurePass123!"
        org_id = "test-org"

        # Step 1: User registration
        register_request = RegisterRequest(
            email=email,
            password=password,
            person_name=PersonNameSchema(
                first_name="Test",
                last_name="User",
                legal_full_name="Test User",
            ),
            organization_name="Test Organization",
            org_id=org_id,
        )

        registration_result = await registration_handler.register_user(
            register_request, correlation_id
        )

        # Verify registration response
        assert registration_result.response.email == email
        assert registration_result.response.org_id == org_id
        assert registration_result.response.email_verification_required is True

        # Verify UserRegisteredV1 event was published
        mock_event_publisher.publish_user_registered.assert_called_once()
        published_user = mock_event_publisher.publish_user_registered.call_args[0][0]
        assert published_user["email"] == email
        assert published_user["org_id"] == org_id

        user_id = registration_result.response.user_id

        # Verify user was created in database
        async with session_factory() as session:
            user_stmt = select(User).where(User.id == UUID(user_id))
            user_result = await session.execute(user_stmt)
            created_user = user_result.scalar_one()

            assert created_user.email == email
            assert created_user.org_id == org_id
            assert created_user.roles == ["teacher"]
            assert created_user.email_verified is False

        # Step 1.5: Verify email (for integration test - bypass actual verification flow)
        async with session_factory() as session:
            # Update user to mark email as verified
            user_update_stmt = (
                update(User)
                .where(User.id == UUID(user_id))
                .values(email_verified=True)
            )
            await session.execute(user_update_stmt)
            await session.commit()

        # Step 2: User login
        login_request = LoginRequest(email=email, password=password)

        login_result = await auth_handler.login(
            login_request=login_request,
            correlation_id=correlation_id,
            ip_address="192.168.1.100",
            user_agent="TestClient/1.0",
            device_name="Chrome",
            device_type="desktop",
        )

        # Verify login response
        assert login_result.token_pair.access_token
        assert login_result.token_pair.refresh_token
        assert login_result.token_pair.token_type == "Bearer"
        assert login_result.token_pair.expires_in == 3600

        # Verify LoginSucceededV1 event was published
        mock_event_publisher.publish_login_succeeded.assert_called_once()
        login_user = mock_event_publisher.publish_login_succeeded.call_args[0][0]
        assert login_user["email"] == email

        # Verify refresh session was stored
        mock_session_repo.store_refresh.assert_called_once()

        # Verify user security fields were updated (failed attempts reset)
        async with session_factory() as session:
            user_stmt = select(User).where(User.id == UUID(user_id))
            user_result = await session.execute(user_stmt)
            logged_in_user = user_result.scalar_one()

            assert logged_in_user.failed_login_attempts == 0
            assert logged_in_user.last_login_at is not None
            assert logged_in_user.locked_until is None

        # Step 3: Token refresh
        refresh_request = RefreshTokenRequest(refresh_token=login_result.token_pair.refresh_token)

        refresh_result = await auth_handler.refresh_token(
            refresh_request=refresh_request,
            correlation_id=correlation_id,
        )

        # Verify refresh response
        assert refresh_result.response.access_token
        assert refresh_result.response.expires_in == 3600
        assert refresh_result.response.token_type == "Bearer"

        # Verify session was checked for validity
        mock_session_repo.is_refresh_valid.assert_called_once()

        # Verify new access token has same claims
        original_access_claims = token_issuer.verify(login_result.token_pair.access_token)
        new_access_claims = token_issuer.verify(refresh_result.response.access_token)

        assert original_access_claims["sub"] == new_access_claims["sub"]
        assert original_access_claims["org"] == new_access_claims["org"]
        assert original_access_claims["roles"] == new_access_claims["roles"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_user_profile_creation_during_registration(
        self,
        registration_handler: RegistrationHandler,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test that user profile can be created after registration."""
        correlation_id = uuid4()

        # Registration with Swedish characters
        register_request = RegisterRequest(
            email="nils.bergström@example.com",
            password="TestPass456!",
            person_name=PersonNameSchema(
                first_name="Nils",
                last_name="Bergström",
                legal_full_name="Nils Bergström",
            ),
            organization_name="Svenska Skolan",
            org_id="edu-org",
        )

        registration_result = await registration_handler.register_user(
            register_request, correlation_id
        )

        user_id = UUID(registration_result.response.user_id)

        # Manually create a user profile (simulating profile creation flow)
        async with session_factory() as session:
            async with session.begin():
                profile = UserProfile(
                    user_id=user_id,
                    first_name="Nils",
                    last_name="Bergström",
                    display_name="Teacher Nils",
                    locale="sv-SE",
                )
                session.add(profile)

        # Verify profile was created
        async with session_factory() as session:
            profile_stmt = select(UserProfile).where(UserProfile.user_id == user_id)
            profile_result = await session.execute(profile_stmt)
            created_profile = profile_result.scalar_one()

            assert created_profile.first_name == "Nils"
            assert created_profile.last_name == "Bergström"
            assert created_profile.display_name == "Teacher Nils"
            assert created_profile.locale == "sv-SE"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_session_management_lifecycle(
        self,
        auth_handler: AuthenticationHandler,
        registration_handler: RegistrationHandler,
        mock_session_repo: AsyncMock,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test session management with device tracking and cleanup."""
        correlation_id = uuid4()

        # Register user
        register_request = RegisterRequest(
            email="erik.öhman@example.com",
            password="SessionTest789!",
            person_name=PersonNameSchema(
                first_name="Erik",
                last_name="Öhman",
                legal_full_name="Erik Öhman",
            ),
            organization_name="Svenska Skolan",
            org_id="session-org",
        )

        registration_result = await registration_handler.register_user(
            register_request, correlation_id
        )

        # Verify email (for integration test - bypass actual verification flow)
        async with session_factory() as session:
            # Update user to mark email as verified
            user_update_stmt = (
                update(User)
                .where(User.id == UUID(registration_result.response.user_id))
                .values(email_verified=True)
            )
            await session.execute(user_update_stmt)
            await session.commit()

        # Login with device info
        login_request = LoginRequest(email="erik.öhman@example.com", password="SessionTest789!")

        login_result = await auth_handler.login(
            login_request=login_request,
            correlation_id=correlation_id,
            ip_address="10.0.0.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            device_name="Firefox",
            device_type="desktop",
        )

        # Verify refresh session stored with correct user_id
        mock_session_repo.store_refresh.assert_called_once()
        store_call_args = mock_session_repo.store_refresh.call_args[1]  # kwargs
        assert store_call_args["user_id"] == registration_result.response.user_id

        # Test logout
        logout_result = await auth_handler.logout(
            token=login_result.token_pair.access_token,
            correlation_id=correlation_id,
        )

        assert logout_result.message == "Logout successful"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_database_state_verification_after_operations(
        self,
        registration_handler: RegistrationHandler,
        auth_handler: AuthenticationHandler,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Test database state is correctly maintained across operations."""
        correlation_id = uuid4()

        # Register multiple users
        users_data = [
            ("maria.åkerlund@example.com", "Password1!", "org-1"),
            ("lars.holm@example.com", "Password2!", "org-2"),
        ]

        created_users = []
        for email, password, org_id in users_data:
            register_request = RegisterRequest(
                email=email,
                password=password,
                person_name=PersonNameSchema(
                    first_name="Maria" if "maria" in email else "Lars",
                    last_name="Åkerlund" if "maria" in email else "Holm",
                    legal_full_name="Maria Åkerlund" if "maria" in email else "Lars Holm",
                ),
                organization_name="Svenska Skolan",
                org_id=org_id,
            )
            result = await registration_handler.register_user(register_request, correlation_id)
            created_users.append((result.response.user_id, email, password))

        # Verify all users exist in database
        async with session_factory() as session:
            user_count_stmt = select(func.count(User.id))
            count_result = await session.execute(user_count_stmt)
            user_count = count_result.scalar()
            assert user_count == 2

            # Verify specific user data
            for user_id, email, _ in created_users:
                user_stmt = select(User).where(User.id == UUID(user_id))
                user_result = await session.execute(user_stmt)
                user = user_result.scalar_one()
                assert user.email == email
                assert user.email_verified is False
                assert user.failed_login_attempts == 0

        # Verify email for first user (for integration test - bypass actual verification flow)
        async with session_factory() as session:
            user_update_stmt = (
                update(User)
                .where(User.id == UUID(created_users[0][0]))
                .values(email_verified=True)
            )
            await session.execute(user_update_stmt)
            await session.commit()

        # Login first user and verify state changes
        login_request = LoginRequest(email=created_users[0][1], password=created_users[0][2])

        await auth_handler.login(
            login_request=login_request,
            correlation_id=correlation_id,
            ip_address="127.0.0.1",
            user_agent="IntegrationTest/1.0",
        )

        # Verify login updated user record
        async with session_factory() as session:
            user_stmt = select(User).where(User.id == UUID(created_users[0][0]))
            user_result = await session.execute(user_stmt)
            logged_in_user = user_result.scalar_one()

            assert logged_in_user.last_login_at is not None
            assert logged_in_user.failed_login_attempts == 0

            # Verify other user was not affected
            other_user_stmt = select(User).where(User.id == UUID(created_users[1][0]))
            other_user_result = await session.execute(other_user_stmt)
            other_user = other_user_result.scalar_one()

            assert other_user.last_login_at is None
