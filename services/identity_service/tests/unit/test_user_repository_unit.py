"""
Unit tests for UserRepository implementations following Rule 075 methodology.

Tests focus on repository structure, behavioral patterns, and error handling
without database dependencies. Uses DI principles with AsyncMock for database operations.
"""

from __future__ import annotations

import inspect
from datetime import datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from huleedu_service_libs.error_handling import HuleEduError, raise_processing_error
from sqlalchemy.ext.asyncio import AsyncEngine

from services.identity_service.implementations.user_repository_postgres_impl import (
    DevInMemoryUserRepo,
)
from services.identity_service.implementations.user_repository_sqlalchemy_impl import (
    PostgresSessionRepo,
    PostgresUserRepo,
)


class TestDevInMemoryUserRepo:
    """Tests for DevInMemoryUserRepo behavioral patterns and structure.

    Note: DevInMemoryUserRepo is a development scaffold with limited implementation.
    Tests focus only on implemented methods.
    """

    @pytest.fixture
    def repository(self) -> DevInMemoryUserRepo:
        """Create repository instance for testing."""
        return DevInMemoryUserRepo()  # type: ignore[abstract]

    @pytest.fixture
    def user_id(self) -> str:
        """Sample user ID for testing."""
        return "u-000001"

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Sample correlation ID for testing."""
        return uuid4()

    def test_repository_initialization_follows_correct_pattern(self) -> None:
        """Test repository initialization follows expected in-memory pattern."""
        # Act
        repo = DevInMemoryUserRepo()  # type: ignore[abstract]

        # Assert - repository initializes correct state
        assert repo._users_by_email == {}
        assert repo._seq == 0

    def test_repository_protocol_compliance(self, repository: DevInMemoryUserRepo) -> None:
        """Test repository implements available protocol methods."""
        # Assert - verify implemented protocol methods exist
        assert hasattr(repository, "create_user")
        assert hasattr(repository, "get_user_by_email")
        assert hasattr(repository, "set_email_verified")

        # Verify methods are async
        assert inspect.iscoroutinefunction(repository.create_user)
        assert inspect.iscoroutinefunction(repository.get_user_by_email)
        assert inspect.iscoroutinefunction(repository.set_email_verified)

        # Note: DevInMemoryUserRepo is a development scaffold, not full implementation

    @pytest.mark.parametrize(
        "email, org_id, expected_email_key",
        [
            ("åsa.öberg@skolan.se", "org-123", "åsa.öberg@skolan.se"),  # Swedish characters
            (
                "KARL.ÄNGSTRÖM@UNIVERSITY.SE",
                None,
                "karl.ängström@university.se",
            ),  # Case normalization
            ("teacher@example.com", "org-456", "teacher@example.com"),  # Standard ASCII
            ("josé.garcía@escuela.es", "org-789", "josé.garcía@escuela.es"),  # Spanish characters
        ],
    )
    async def test_create_user_handles_unicode_and_case_normalization(
        self,
        repository: DevInMemoryUserRepo,
        email: str,
        org_id: str | None,
        expected_email_key: str,
    ) -> None:
        """Test create_user handles Swedish characters and case normalization correctly."""
        # Arrange
        password_hash = "hashed_password_123"

        # Act
        result = await repository.create_user(email, org_id, password_hash)

        # Assert - user created with correct structure and normalization
        assert result["id"] == "u-000001"
        assert result["email"] == email
        assert result["org_id"] == org_id
        assert result["password_hash"] == password_hash
        assert result["roles"] == ["teacher"]
        assert result["email_verified"] is False
        assert isinstance(result["registered_at"], datetime)

        # Verify internal storage uses normalized key
        assert expected_email_key.lower() in repository._users_by_email

    async def test_create_multiple_users_increments_sequence(
        self, repository: DevInMemoryUserRepo
    ) -> None:
        """Test user creation increments sequence counter correctly."""
        # Act - create multiple users
        user1 = await repository.create_user("user1@example.com", None, "hash1")
        user2 = await repository.create_user("user2@example.com", None, "hash2")
        user3 = await repository.create_user("user3@example.com", None, "hash3")

        # Assert - sequence increments properly
        assert user1["id"] == "u-000001"
        assert user2["id"] == "u-000002"
        assert user3["id"] == "u-000003"
        assert repository._seq == 3

    @pytest.mark.parametrize(
        "lookup_email, stored_email, should_find",
        [
            ("åsa.öberg@skolan.se", "åsa.öberg@skolan.se", True),  # Exact match Swedish
            ("ÅSA.ÖBERG@SKOLAN.SE", "åsa.öberg@skolan.se", True),  # Case insensitive Swedish
            ("user@example.com", "user@example.com", True),  # Exact match ASCII
            ("USER@EXAMPLE.COM", "user@example.com", True),  # Case insensitive ASCII
            ("notfound@example.com", "user@example.com", False),  # Not found
        ],
    )
    async def test_get_user_by_email_case_insensitive_lookup(
        self,
        repository: DevInMemoryUserRepo,
        lookup_email: str,
        stored_email: str,
        should_find: bool,
    ) -> None:
        """Test get_user_by_email performs case-insensitive lookup correctly."""
        # Arrange - create user with stored email
        await repository.create_user(stored_email, "org-123", "password_hash")

        # Act
        result = await repository.get_user_by_email(lookup_email)

        # Assert
        if should_find:
            assert result is not None
            assert result["email"] == stored_email
            assert result["org_id"] == "org-123"
        else:
            assert result is None

    async def test_set_email_verified_updates_correct_user(
        self, repository: DevInMemoryUserRepo
    ) -> None:
        """Test set_email_verified updates the correct user's verification status."""
        # Arrange - create multiple users
        user1 = await repository.create_user("user1@example.com", None, "hash1")
        await repository.create_user("user2@example.com", None, "hash2")

        # Act - verify one user
        await repository.set_email_verified(user1["id"])

        # Assert - only first user is verified
        user1_updated = await repository.get_user_by_email("user1@example.com")
        user2_unchanged = await repository.get_user_by_email("user2@example.com")

        assert user1_updated is not None
        assert user2_unchanged is not None
        assert user1_updated["email_verified"] is True
        assert user2_unchanged["email_verified"] is False

    async def test_set_email_verified_with_nonexistent_user(
        self, repository: DevInMemoryUserRepo
    ) -> None:
        """Test set_email_verified handles nonexistent user gracefully."""
        # Act - attempt to verify nonexistent user (should not raise)
        await repository.set_email_verified("nonexistent-id")

        # Assert - no exception should be raised, operation completes silently
        # This tests the graceful handling pattern in the implementation


class TestPostgresUserRepo:
    """Tests for PostgresUserRepo behavioral patterns and structure."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock async engine."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def repository(self, mock_engine: AsyncMock) -> PostgresUserRepo:
        """Create repository with mocked engine."""
        return PostgresUserRepo(mock_engine)

    @pytest.fixture
    def user_id(self) -> str:
        """Sample user ID for testing."""
        return str(uuid4())

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Sample correlation ID for testing."""
        return uuid4()

    def test_repository_initialization_follows_correct_pattern(
        self, mock_engine: AsyncMock
    ) -> None:
        """Test repository initialization follows AsyncEngine injection pattern."""
        # Act
        repo = PostgresUserRepo(mock_engine)

        # Assert - repository stores session factory correctly
        assert repo._session_factory is not None
        # Verify async_sessionmaker is created (repository-managed sessions)
        assert hasattr(repo._session_factory, "__call__")

    def test_repository_protocol_compliance(self, repository: PostgresUserRepo) -> None:
        """Test repository implements required UserRepo protocol methods."""
        # Assert - verify core protocol methods exist
        assert hasattr(repository, "create_user")
        assert hasattr(repository, "get_user_by_email")
        assert hasattr(repository, "get_user_by_id")
        assert hasattr(repository, "set_email_verified")

        # Assert - verify token management methods exist
        assert hasattr(repository, "create_email_verification_token")
        assert hasattr(repository, "get_email_verification_token")
        assert hasattr(repository, "mark_token_used")
        assert hasattr(repository, "invalidate_user_tokens")

        # Assert - verify password reset methods exist
        assert hasattr(repository, "create_password_reset_token")
        assert hasattr(repository, "get_password_reset_token")
        assert hasattr(repository, "mark_reset_token_used")
        assert hasattr(repository, "invalidate_password_reset_tokens")

        # Assert - verify security methods exist
        assert hasattr(repository, "update_user_password")
        assert hasattr(repository, "update_security_fields")

        # Verify all methods are async
        for method_name in [
            "create_user",
            "get_user_by_email",
            "get_user_by_id",
            "set_email_verified",
            "create_email_verification_token",
            "get_email_verification_token",
            "mark_token_used",
            "invalidate_user_tokens",
            "create_password_reset_token",
            "get_password_reset_token",
            "mark_reset_token_used",
            "invalidate_password_reset_tokens",
            "update_user_password",
            "update_security_fields",
        ]:
            method = getattr(repository, method_name)
            assert inspect.iscoroutinefunction(method)

    def test_concurrent_repositories_have_isolated_session_makers(self) -> None:
        """Test that concurrent repository instances use isolated session makers."""
        # Arrange
        mock_engine1 = AsyncMock(spec=AsyncEngine)
        mock_engine2 = AsyncMock(spec=AsyncEngine)

        # Act
        repo1 = PostgresUserRepo(mock_engine1)
        repo2 = PostgresUserRepo(mock_engine2)

        # Assert - each repository has its own session maker (isolation)
        assert repo1._session_factory is not repo2._session_factory

    def test_error_handling_patterns_for_user_creation(
        self, user_id: str, correlation_id: UUID
    ) -> None:
        """Test error handling business logic for user creation without database calls."""
        # Test the error raising pattern using the factory function directly
        with pytest.raises(HuleEduError) as exc_info:
            raise_processing_error(
                service="identity_service",
                operation="create_user",
                message="Database constraint violation: email already exists",
                correlation_id=correlation_id,
                error_type="IntegrityError",
                user_email="åsa.öberg@skolan.se",
            )

        error = exc_info.value
        assert "Database constraint violation" in str(error)
        assert error.error_detail.service == "identity_service"
        assert error.error_detail.operation == "create_user"

    def test_error_handling_patterns_for_user_retrieval(
        self, user_id: str, correlation_id: UUID
    ) -> None:
        """Test error handling business logic for user retrieval without database calls."""
        # Test the error raising pattern for database connection issues
        with pytest.raises(HuleEduError) as exc_info:
            raise_processing_error(
                service="identity_service",
                operation="get_user_by_email",
                message="Database connection failed during user lookup",
                correlation_id=correlation_id,
                error_type="OperationalError",
                user_email="karl.ängström@university.se",
            )

        error = exc_info.value
        assert "Database connection failed" in str(error)
        assert error.error_detail.service == "identity_service"
        assert error.error_detail.operation == "get_user_by_email"

    def test_repository_method_signatures_match_protocol(
        self, repository: PostgresUserRepo
    ) -> None:
        """Test repository method signatures match the UserRepo protocol contract."""
        # Verify create_user signature
        create_user_sig = inspect.signature(repository.create_user)
        expected_params = ["email", "org_id", "password_hash"]
        actual_params = list(create_user_sig.parameters.keys())
        assert all(param in actual_params for param in expected_params)

        # Verify get_user_by_email signature
        get_by_email_sig = inspect.signature(repository.get_user_by_email)
        assert "email" in list(get_by_email_sig.parameters.keys())

        # Verify token methods signatures
        create_token_sig = inspect.signature(repository.create_email_verification_token)
        expected_token_params = ["user_id", "token", "expires_at"]
        actual_token_params = list(create_token_sig.parameters.keys())
        assert all(param in actual_token_params for param in expected_token_params)


class TestPostgresSessionRepo:
    """Tests for PostgresSessionRepo behavioral patterns and structure."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock async engine."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def repository(self, mock_engine: AsyncMock) -> PostgresSessionRepo:
        """Create session repository with mocked engine."""
        return PostgresSessionRepo(mock_engine)

    def test_repository_initialization_follows_correct_pattern(
        self, mock_engine: AsyncMock
    ) -> None:
        """Test session repository initialization follows AsyncEngine injection pattern."""
        # Act
        repo = PostgresSessionRepo(mock_engine)

        # Assert - repository stores session factory correctly
        assert repo._session_factory is not None
        assert hasattr(repo._session_factory, "__call__")

    def test_repository_protocol_compliance(self, repository: PostgresSessionRepo) -> None:
        """Test repository implements required SessionRepo protocol methods."""
        # Assert - verify protocol methods exist
        assert hasattr(repository, "store_refresh")
        assert hasattr(repository, "revoke_refresh")
        assert hasattr(repository, "is_refresh_valid")

        # Verify methods are async
        assert inspect.iscoroutinefunction(repository.store_refresh)
        assert inspect.iscoroutinefunction(repository.revoke_refresh)
        assert inspect.iscoroutinefunction(repository.is_refresh_valid)

    def test_repository_method_signatures_match_protocol(
        self, repository: PostgresSessionRepo
    ) -> None:
        """Test session repository method signatures match the SessionRepo protocol contract."""
        # Verify store_refresh signature
        store_sig = inspect.signature(repository.store_refresh)
        expected_params = ["user_id", "jti", "exp_ts"]
        actual_params = list(store_sig.parameters.keys())
        assert all(param in actual_params for param in expected_params)

        # Verify revoke_refresh signature
        revoke_sig = inspect.signature(repository.revoke_refresh)
        assert "jti" in list(revoke_sig.parameters.keys())

        # Verify is_refresh_valid signature
        valid_sig = inspect.signature(repository.is_refresh_valid)
        assert "jti" in list(valid_sig.parameters.keys())


class TestUserRepoErrorHandlingPatterns:
    """Test error handling patterns across UserRepo implementations."""

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Sample correlation ID for testing."""
        return uuid4()

    @pytest.mark.parametrize(
        "error_scenario, operation, error_type, expected_message",
        [
            (
                "duplicate_email",
                "create_user",
                "IntegrityError",
                "User creation failed: email already exists",
            ),
            (
                "invalid_user_id",
                "get_user_by_id",
                "ValueError",
                "Invalid user ID format provided",
            ),
            (
                "token_expired",
                "get_email_verification_token",
                "ValidationError",
                "Email verification token has expired",
            ),
            (
                "connection_timeout",
                "update_user_password",
                "OperationalError",
                "Database connection timeout during password update",
            ),
        ],
    )
    def test_structured_error_handling_patterns(
        self,
        correlation_id: UUID,
        error_scenario: str,
        operation: str,
        error_type: str,
        expected_message: str,
    ) -> None:
        """Test structured error handling patterns for various repository operations."""
        # Test the error raising pattern for different scenarios
        with pytest.raises(HuleEduError) as exc_info:
            raise_processing_error(
                service="identity_service",
                operation=operation,
                message=expected_message,
                correlation_id=correlation_id,
                error_type=error_type,
                scenario=error_scenario,
            )

        error = exc_info.value
        assert expected_message in str(error)
        assert error.error_detail.service == "identity_service"
        assert error.error_detail.operation == operation

    def test_unicode_handling_in_error_contexts(self, correlation_id: UUID) -> None:
        """Test error handling preserves Unicode characters correctly."""
        swedish_email = "åsa.öberg@skolan.se"

        with pytest.raises(HuleEduError) as exc_info:
            raise_processing_error(
                service="identity_service",
                operation="create_user",
                message=f"Duplicate email registration attempted: {swedish_email}",
                correlation_id=correlation_id,
                error_type="IntegrityError",
                user_email=swedish_email,
            )

        error = exc_info.value
        assert swedish_email in str(error)
        # Verify Unicode characters are preserved in error context
        assert "åsa.öberg" in str(error)
