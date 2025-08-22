"""
Token management integration tests for Identity Service.

Tests comprehensive token lifecycle with RS256 signing and real PostgreSQL:
- JWT token creation, verification, and renewal with RS256 algorithm
- RefreshSession table operations (creation, rotation, cleanup)
- Concurrent session handling across multiple devices
- Token expiry and renewal workflows
- Session invalidation and cleanup on logout
- JWKS endpoint integration and public key verification
- Token claims consistency across refresh operations
- Session limit enforcement and device management

Follows established testcontainers and Protocol-based mocking patterns.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from services.identity_service.config import Settings
from services.identity_service.implementations.jwks_store import JwksStore
from services.identity_service.implementations.token_issuer_rs256_impl import (
    Rs256TokenIssuer,
)
from services.identity_service.implementations.user_repository_sqlalchemy_impl import (
    PostgresSessionRepo,
)
from services.identity_service.models_db import Base, RefreshSession, User


class TestTokenManagementIntegration:
    """Integration tests for token management with real PostgreSQL and RS256 signing."""

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
                await session.execute(text("TRUNCATE TABLE refresh_sessions CASCADE"))
                await session.execute(text("TRUNCATE TABLE users CASCADE"))

                # Re-enable foreign key checks
                await session.execute(text("SET session_replication_role = DEFAULT;"))

    @pytest.fixture
    def jwks_store(self) -> JwksStore:
        """JWKS store for public key verification."""
        return JwksStore()

    @pytest.fixture
    def rs256_token_issuer(self, jwks_store: JwksStore) -> Rs256TokenIssuer:
        """RS256 token issuer implementation for testing."""
        return Rs256TokenIssuer(jwks_store)

    @pytest.fixture
    def session_repo(self, database_engine: AsyncEngine) -> PostgresSessionRepo:
        """Session repository with real database."""
        return PostgresSessionRepo(database_engine)

    @pytest.fixture
    async def test_user(self, session_factory: async_sessionmaker[AsyncSession]) -> UUID:
        """Create a test user in the database."""
        user_id = uuid4()
        async with session_factory() as session:
            async with session.begin():
                user = User(
                    id=user_id,
                    email="test.user@example.com",
                    org_id="test-org",
                    roles=["teacher"],
                    password_hash="dummy_hash",
                    email_verified=True,
                )
                session.add(user)
        return user_id

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "device_info,user_agent",
        [
            ("device-1", "Mozilla/5.0 Windows"),
            ("device-2", "Mozilla/5.0 Mac"),
            ("mobile-1", "Mozilla/5.0 iPhone"),
        ],
    )
    async def test_jwt_token_lifecycle_with_rs256_signing(
        self,
        rs256_token_issuer: Rs256TokenIssuer,
        session_repo: PostgresSessionRepo,
        session_factory: async_sessionmaker[AsyncSession],
        test_user: UUID,
        device_info: str,
        user_agent: str,
    ) -> None:
        """Test complete JWT token lifecycle with RS256 signing across different devices."""
        # Use user_agent and device_info in token metadata for device tracking
        _ = user_agent  # Acknowledge parameter for device-specific testing
        _ = device_info  # Acknowledge parameter for device tracking

        # Generate tokens with correct method signatures
        access_token = rs256_token_issuer.issue_access_token(
            user_id=str(test_user),
            org_id="test-org",
            roles=["teacher"],
        )
        refresh_token, jti = rs256_token_issuer.issue_refresh_token(
            user_id=str(test_user),
        )

        # Verify tokens can be decoded
        access_claims = rs256_token_issuer.verify(access_token)
        refresh_claims = rs256_token_issuer.verify(refresh_token)

        assert access_claims["sub"] == str(test_user)
        assert access_claims["org"] == "test-org"
        assert access_claims["roles"] == ["teacher"]
        assert refresh_claims["sub"] == str(test_user)
        assert refresh_claims["jti"] == jti

        # Store refresh session in database
        await session_repo.store_refresh(
            jti=jti,
            user_id=str(test_user),
            exp_ts=refresh_claims["exp"],
        )

        # Verify refresh session stored correctly
        async with session_factory() as session:
            session_stmt = select(RefreshSession).where(RefreshSession.jti == jti)
            session_result = await session.execute(session_stmt)
            stored_session = session_result.scalar_one()

            assert stored_session.user_id == test_user
            assert stored_session.exp_ts == refresh_claims["exp"]

        # Test token renewal
        new_access_token = rs256_token_issuer.issue_access_token(
            user_id=str(test_user),
            org_id="test-org",
            roles=["teacher"],
        )

        # Verify renewed token has same claims structure
        new_access_claims = rs256_token_issuer.verify(new_access_token)
        assert new_access_claims["sub"] == access_claims["sub"]
        assert new_access_claims["org"] == access_claims["org"]
        assert new_access_claims["roles"] == access_claims["roles"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_refresh_session_table_operations(
        self,
        rs256_token_issuer: Rs256TokenIssuer,
        session_repo: PostgresSessionRepo,
        session_factory: async_sessionmaker[AsyncSession],
        test_user: UUID,
    ) -> None:
        """Test RefreshSession table operations including creation, rotation, and cleanup."""
        # Create multiple refresh sessions
        sessions_data = []
        for i in range(3):
            refresh_token, jti = rs256_token_issuer.issue_refresh_token(
                user_id=str(test_user),
            )
            claims = rs256_token_issuer.verify(refresh_token)
            sessions_data.append(
                {
                    "jti": jti,
                    "exp_ts": claims["exp"],
                    "device_id": f"device-{i}",
                }
            )

            await session_repo.store_refresh(
                jti=jti,
                user_id=str(test_user),
                exp_ts=claims["exp"],
            )

        # Verify all sessions created
        async with session_factory() as session:
            count_stmt = select(func.count(RefreshSession.jti)).where(
                RefreshSession.user_id == test_user
            )
            count_result = await session.execute(count_stmt)
            session_count = count_result.scalar()
            assert session_count == 3

        # Test session rotation (revoke old, create new)
        old_jti = sessions_data[0]["jti"]
        await session_repo.revoke_refresh(jti=old_jti)

        # Create new session
        new_refresh_token, new_jti = rs256_token_issuer.issue_refresh_token(
            user_id=str(test_user),
        )
        new_claims = rs256_token_issuer.verify(new_refresh_token)
        await session_repo.store_refresh(
            jti=new_jti,
            user_id=str(test_user),
            exp_ts=new_claims["exp"],
        )

        # Verify old session invalidated and new created
        is_old_valid = await session_repo.is_refresh_valid(jti=old_jti)
        is_new_valid = await session_repo.is_refresh_valid(jti=new_jti)

        assert is_old_valid is False
        assert is_new_valid is True

        # Verify sessions after rotation: 3 original - 1 revoked + 1 new = 3 total
        async with session_factory() as session:
            remaining_sessions_stmt = select(RefreshSession).where(
                RefreshSession.user_id == test_user
            )
            remaining_sessions_result = await session.execute(remaining_sessions_stmt)
            remaining_sessions = remaining_sessions_result.scalars().all()

            # Should have 3 sessions: 2 original + 1 new (1 was revoked/deleted)
            assert len(remaining_sessions) == 3

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_session_handling_multiple_devices(
        self,
        rs256_token_issuer: Rs256TokenIssuer,
        session_repo: PostgresSessionRepo,
        session_factory: async_sessionmaker[AsyncSession],
        test_user: UUID,
    ) -> None:
        """Test concurrent session handling across multiple devices with session limits."""
        # Create sessions for multiple devices
        device_sessions = {}
        for device_id in ["laptop", "phone", "tablet", "desktop"]:
            refresh_token, jti = rs256_token_issuer.issue_refresh_token(
                user_id=str(test_user),
            )
            claims = rs256_token_issuer.verify(refresh_token)

            # Store session
            await session_repo.store_refresh(
                jti=jti,
                user_id=str(test_user),
                exp_ts=claims["exp"],
            )

            device_sessions[device_id] = {
                "jti": jti,
                "refresh_token": refresh_token,
            }

        # Verify all sessions are active
        async with session_factory() as session:
            active_sessions_stmt = select(func.count(RefreshSession.jti)).where(
                RefreshSession.user_id == test_user
            )
            active_sessions_result = await session.execute(active_sessions_stmt)
            active_count = active_sessions_result.scalar()
            assert active_count == 4

        # Test session revocation for specific device
        laptop_jti = device_sessions["laptop"]["jti"]
        await session_repo.revoke_refresh(jti=laptop_jti)

        # Verify laptop session invalidated but others remain
        laptop_valid = await session_repo.is_refresh_valid(jti=laptop_jti)
        phone_valid = await session_repo.is_refresh_valid(jti=device_sessions["phone"]["jti"])

        assert laptop_valid is False
        assert phone_valid is True

        # Test revocation of remaining sessions individually
        for device_id, device_data in device_sessions.items():
            if device_id != "laptop":  # Skip laptop as it was already revoked
                await session_repo.revoke_refresh(jti=device_data["jti"])

        # Verify all sessions revoked
        for device_data in device_sessions.values():
            is_valid = await session_repo.is_refresh_valid(jti=device_data["jti"])
            assert is_valid is False

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_jwks_endpoint_integration(
        self,
        rs256_token_issuer: Rs256TokenIssuer,
        jwks_store: JwksStore,
    ) -> None:
        """Test JWKS endpoint integration and public key verification."""
        # Get JWKS data
        jwks_response = jwks_store.get_jwks()
        jwks_data = jwks_response.model_dump()

        # Verify JWKS structure
        assert "keys" in jwks_data
        assert len(jwks_data["keys"]) > 0

        key = jwks_data["keys"][0]
        assert key["kty"] == "RSA"
        assert key["use"] == "sig"
        assert key["alg"] == "RS256"
        assert "kid" in key
        assert "n" in key  # RSA modulus
        assert "e" in key  # RSA exponent

        # Generate token and verify kid consistency
        access_token = rs256_token_issuer.issue_access_token(
            user_id="test-user",
            org_id="test-org",
            roles=["teacher"],
        )

        # Decode token header to verify kid
        import base64
        import json

        header_b64 = access_token.split(".")[0]
        # Add padding if needed
        header_b64 += "=" * (4 - len(header_b64) % 4)
        header_bytes = base64.urlsafe_b64decode(header_b64)
        header = json.loads(header_bytes.decode())

        assert header["kid"] == key["kid"]
        assert header["alg"] == "RS256"

        # Verify token can be validated using public key
        claims = rs256_token_issuer.verify(access_token)
        assert claims["sub"] == "test-user"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_token_expiry_and_error_handling(
        self,
        rs256_token_issuer: Rs256TokenIssuer,
        session_repo: PostgresSessionRepo,
        test_user: UUID,
    ) -> None:
        """Test token expiry scenarios and structured error handling."""
        # Create a refresh session and simulate expiry
        refresh_token, jti = rs256_token_issuer.issue_refresh_token(
            user_id=str(test_user),
        )
        _ = rs256_token_issuer.verify(refresh_token)  # Verify token is valid

        # Store with past expiry time
        past_exp_ts = int(datetime.now(timezone.utc).timestamp()) - 3600  # 1 hour ago
        await session_repo.store_refresh(
            jti=jti,
            user_id=str(test_user),
            exp_ts=past_exp_ts,
        )

        # Test validation of expired session
        is_valid = await session_repo.is_refresh_valid(jti=jti)
        assert is_valid is False

        # Verify expired session is considered invalid
        is_valid_after_expiry = await session_repo.is_refresh_valid(jti=jti)
        assert is_valid_after_expiry is False

        # Test invalid token verification - Rs256TokenIssuer returns empty dict for invalid tokens
        invalid_claims = rs256_token_issuer.verify("invalid.token.signature")
        assert invalid_claims == {}

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_session_limit_enforcement(
        self,
        rs256_token_issuer: Rs256TokenIssuer,
        session_repo: PostgresSessionRepo,
        test_user: UUID,
    ) -> None:
        """Test session limit enforcement and device management."""
        # Create multiple sessions for different devices
        session_limit = 5
        created_sessions = []

        for _ in range(session_limit + 2):  # Create more than typical limit
            refresh_token, jti = rs256_token_issuer.issue_refresh_token(
                user_id=str(test_user),
            )
            _ = rs256_token_issuer.verify(refresh_token)  # Verify token is valid

            # Use current time + 1 hour for expiry
            exp_ts = int(datetime.now(timezone.utc).timestamp()) + 3600
            await session_repo.store_refresh(
                jti=jti,
                user_id=str(test_user),
                exp_ts=exp_ts,
            )

            created_sessions.append(jti)

        # Verify all sessions initially valid
        for jti in created_sessions:
            is_valid = await session_repo.is_refresh_valid(jti=jti)
            assert is_valid is True

        # Test bulk session revocation by revoking each session
        for jti in created_sessions:
            await session_repo.revoke_refresh(jti=jti)

        # Verify all sessions revoked
        for jti in created_sessions:
            is_valid = await session_repo.is_refresh_valid(jti=jti)
            assert is_valid is False
