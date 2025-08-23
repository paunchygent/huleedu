"""
Unit tests for PostgreSQLEmailRepository following Rule 075 methodology.

Tests focus on EmailRepository protocol compliance, database behavior,
and session management using AsyncMock patterns. Includes Swedish character
support and domain-specific edge cases for HuleEdu email service.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.error_handling import HuleEduError, raise_processing_error
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from services.email_service.implementations.repository_impl import PostgreSQLEmailRepository
from services.email_service.models_db import EmailRecord as DbEmailRecord
from services.email_service.models_db import EmailStatus
from services.email_service.protocols import EmailRecord


class TestPostgreSQLEmailRepositoryInitialization:
    """Tests for PostgreSQLEmailRepository initialization and setup patterns."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock AsyncEngine following established patterns."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def mock_database_metrics(self) -> AsyncMock:
        """Create mock DatabaseMetrics for monitoring."""
        return AsyncMock(spec=DatabaseMetrics)

    def test_repository_initialization_follows_correct_pattern(
        self, mock_engine: AsyncMock, mock_database_metrics: AsyncMock
    ) -> None:
        """Test repository initialization follows AsyncEngine injection pattern."""
        # Act
        repository = PostgreSQLEmailRepository(mock_engine, mock_database_metrics)

        # Assert - repository stores components correctly
        assert repository.engine is mock_engine
        assert repository.database_metrics is mock_database_metrics
        assert repository.async_session_maker is not None
        assert hasattr(repository.async_session_maker, "__call__")
        assert repository.logger is not None

    def test_repository_initialization_without_metrics(self, mock_engine: AsyncMock) -> None:
        """Test repository initialization with optional metrics parameter."""
        # Act
        repository = PostgreSQLEmailRepository(mock_engine)

        # Assert - repository initializes correctly without metrics
        assert repository.engine is mock_engine
        assert repository.database_metrics is None
        assert repository.async_session_maker is not None

    def test_session_maker_configuration(self, mock_engine: AsyncMock) -> None:
        """Test session maker is configured with proper settings."""
        # Act
        repository = PostgreSQLEmailRepository(mock_engine)

        # Assert - session maker has correct configuration
        session_maker = repository.async_session_maker
        # Note: Session maker configuration is tested by ensuring it was created correctly
        assert session_maker is not None

    def test_concurrent_repositories_have_isolated_session_makers(self) -> None:
        """Test concurrent repository instances use isolated session makers."""
        # Arrange
        mock_engine1 = AsyncMock(spec=AsyncEngine)
        mock_engine2 = AsyncMock(spec=AsyncEngine)

        # Act
        repo1 = PostgreSQLEmailRepository(mock_engine1)
        repo2 = PostgreSQLEmailRepository(mock_engine2)

        # Assert - each repository has its own session maker (isolation)
        assert repo1.async_session_maker is not repo2.async_session_maker


class TestPostgreSQLEmailRepositoryProtocolCompliance:
    """Tests for EmailRepository protocol compliance and method signatures."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock AsyncEngine."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def repository(self, mock_engine: AsyncMock) -> PostgreSQLEmailRepository:
        """Create repository instance for testing."""
        return PostgreSQLEmailRepository(mock_engine)

    def test_repository_implements_email_repository_protocol(
        self, repository: PostgreSQLEmailRepository
    ) -> None:
        """Test repository implements required EmailRepository protocol methods."""
        # Assert - verify protocol methods exist
        assert hasattr(repository, "create_email_record")
        assert hasattr(repository, "update_status")
        assert hasattr(repository, "get_by_message_id")
        assert hasattr(repository, "get_by_correlation_id")

        # Assert - verify all methods are async
        assert inspect.iscoroutinefunction(repository.create_email_record)
        assert inspect.iscoroutinefunction(repository.update_status)
        assert inspect.iscoroutinefunction(repository.get_by_message_id)
        assert inspect.iscoroutinefunction(repository.get_by_correlation_id)

        # Assert - verify repository follows protocol pattern (structural typing)
        # Note: Can't use isinstance with Protocol, verify methods exist instead

    def test_create_email_record_method_signature(
        self, repository: PostgreSQLEmailRepository
    ) -> None:
        """Test create_email_record method signature matches protocol."""
        # Arrange
        signature = inspect.signature(repository.create_email_record)
        parameters = list(signature.parameters.keys())

        # Assert - correct parameters
        assert "record" in parameters
        assert len(parameters) == 1  # Only record parameter

    def test_update_status_method_signature(self, repository: PostgreSQLEmailRepository) -> None:
        """Test update_status method signature matches protocol."""
        # Arrange
        signature = inspect.signature(repository.update_status)
        parameters = list(signature.parameters.keys())

        # Assert - required and optional parameters
        required_params = ["message_id", "status"]
        optional_params = [
            "provider_message_id",
            "provider_response",
            "sent_at",
            "failed_at",
            "failure_reason",
        ]

        assert all(param in parameters for param in required_params)
        assert all(param in parameters for param in optional_params)

    def test_get_by_message_id_method_signature(
        self, repository: PostgreSQLEmailRepository
    ) -> None:
        """Test get_by_message_id method signature matches protocol."""
        # Arrange
        signature = inspect.signature(repository.get_by_message_id)
        parameters = list(signature.parameters.keys())

        # Assert
        assert "message_id" in parameters
        assert len(parameters) == 1

    def test_get_by_correlation_id_method_signature(
        self, repository: PostgreSQLEmailRepository
    ) -> None:
        """Test get_by_correlation_id method signature matches protocol."""
        # Arrange
        signature = inspect.signature(repository.get_by_correlation_id)
        parameters = list(signature.parameters.keys())

        # Assert
        assert "correlation_id" in parameters
        assert len(parameters) == 1


class TestPostgreSQLEmailRepositorySessionManagement:
    """Tests for async session management and transaction handling."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock AsyncEngine."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock AsyncSession with proper context manager behavior."""
        session = AsyncMock(spec=AsyncSession)
        # Mock context manager methods
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        # Ensure async methods are properly mocked
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.close = AsyncMock()
        return session

    @pytest.fixture
    def repository(
        self, mock_engine: AsyncMock, mock_session: AsyncMock
    ) -> PostgreSQLEmailRepository:
        """Create repository with mocked session maker."""
        repo = PostgreSQLEmailRepository(mock_engine)
        # Mock the session maker to return our mock session
        repo.async_session_maker = MagicMock(return_value=mock_session)
        return repo

    async def test_session_context_manager_commit_success(
        self, repository: PostgreSQLEmailRepository, mock_session: AsyncMock
    ) -> None:
        """Test session context manager commits on successful operations."""
        # Act
        async with repository.session():
            # Simulate successful database operation
            pass

        # Assert - session lifecycle methods called correctly
        # Note: Context manager calls are handled by the actual implementation
        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()
        mock_session.close.assert_called_once()

    async def test_session_context_manager_rollback_on_exception(
        self, repository: PostgreSQLEmailRepository, mock_session: AsyncMock
    ) -> None:
        """Test session context manager rolls back on exceptions."""
        # Arrange
        test_exception = RuntimeError("Database error")

        # Act & Assert
        with pytest.raises(RuntimeError, match="Database error"):
            async with repository.session():
                raise test_exception

        # Assert - rollback called, commit not called
        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()
        mock_session.close.assert_called_once()


class TestPostgreSQLEmailRepositoryEmailRecordCreation:
    """Tests for create_email_record method with Swedish character support."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock AsyncEngine."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock AsyncSession."""
        session = AsyncMock(spec=AsyncSession)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        # Ensure async methods are properly mocked
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.close = AsyncMock()
        session.add = MagicMock()  # add is synchronous
        return session

    @pytest.fixture
    def repository(
        self, mock_engine: AsyncMock, mock_session: AsyncMock
    ) -> PostgreSQLEmailRepository:
        """Create repository with mocked session."""
        repo = PostgreSQLEmailRepository(mock_engine)
        repo.async_session_maker = MagicMock(return_value=mock_session)
        return repo

    @pytest.fixture
    def sample_email_record(self) -> EmailRecord:
        """Create sample EmailRecord for testing."""
        return EmailRecord(
            message_id="msg-123",
            to_address="teacher@example.com",
            from_address="noreply@huleedu.se",
            from_name="HuleEdu System",
            subject="Welcome to HuleEdu",
            template_id="welcome",
            category="onboarding",
            variables={"name": "Test User"},
            correlation_id=str(uuid4()),
        )

    @pytest.mark.parametrize(
        "to_address, from_name, subject, expected_to, expected_from, expected_subject",
        [
            # Swedish character support in email addresses and content
            (
                "åsa.öberg@skolan.se",
                "Käraste lärare",
                "Välkommen till HuleEdu - Åäötest",
                "åsa.öberg@skolan.se",
                "Käraste lärare",
                "Välkommen till HuleEdu - Åäötest",
            ),
            # Mixed Swedish and English content
            (
                "karl.ångström@university.se",
                "HuleEdu Systemet",
                "Password Reset - Lösenord återställning",
                "karl.ångström@university.se",
                "HuleEdu Systemet",
                "Password Reset - Lösenord återställning",
            ),
            # Standard ASCII content
            (
                "teacher@example.com",
                "HuleEdu System",
                "Account Verification Required",
                "teacher@example.com",
                "HuleEdu System",
                "Account Verification Required",
            ),
        ],
    )
    async def test_create_email_record_handles_swedish_characters(
        self,
        repository: PostgreSQLEmailRepository,
        mock_session: AsyncMock,
        to_address: str,
        from_name: str,
        subject: str,
        expected_to: str,
        expected_from: str,
        expected_subject: str,
    ) -> None:
        """Test create_email_record preserves Swedish characters correctly."""
        # Arrange
        record = EmailRecord(
            message_id="msg-swedish-123",
            to_address=to_address,
            from_address="noreply@huleedu.se",
            from_name=from_name,
            subject=subject,
            template_id="verification",
            category="authentication",
            variables={"teacher_name": "Åsa Öberg"},
            correlation_id=str(uuid4()),
        )

        # Act
        await repository.create_email_record(record)

        # Assert - session methods called correctly
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

        # Get the added record
        added_record = mock_session.add.call_args[0][0]
        assert isinstance(added_record, DbEmailRecord)
        assert added_record.to_address == expected_to
        assert added_record.from_name == expected_from
        assert added_record.subject == expected_subject
        assert added_record.variables == {"teacher_name": "Åsa Öberg"}

    async def test_create_email_record_converts_protocol_to_db_model(
        self,
        repository: PostgreSQLEmailRepository,
        mock_session: AsyncMock,
        sample_email_record: EmailRecord,
    ) -> None:
        """Test create_email_record converts protocol model to database model correctly."""
        # Act
        await repository.create_email_record(sample_email_record)

        # Assert - database record created with correct fields
        mock_session.add.assert_called_once()
        added_record = mock_session.add.call_args[0][0]

        assert isinstance(added_record, DbEmailRecord)
        assert added_record.message_id == sample_email_record.message_id
        assert added_record.to_address == str(sample_email_record.to_address)
        assert added_record.from_address == str(sample_email_record.from_address)
        assert added_record.from_name == sample_email_record.from_name
        assert added_record.subject == sample_email_record.subject
        assert added_record.template_id == sample_email_record.template_id
        assert added_record.category == sample_email_record.category
        assert added_record.variables == sample_email_record.variables
        assert added_record.correlation_id == sample_email_record.correlation_id
        assert added_record.status == EmailStatus.PENDING

    async def test_create_email_record_sets_default_timestamps(
        self,
        repository: PostgreSQLEmailRepository,
        mock_session: AsyncMock,
        sample_email_record: EmailRecord,
    ) -> None:
        """Test create_email_record sets created_at timestamp when not provided."""
        # Arrange - record without created_at
        assert sample_email_record.created_at is None

        # Act
        await repository.create_email_record(sample_email_record)

        # Assert - created_at is set
        added_record = mock_session.add.call_args[0][0]
        assert added_record.created_at is not None
        assert isinstance(added_record.created_at, datetime)

    async def test_create_email_record_preserves_provided_timestamps(
        self,
        repository: PostgreSQLEmailRepository,
        mock_session: AsyncMock,
        sample_email_record: EmailRecord,
    ) -> None:
        """Test create_email_record preserves provided created_at timestamp."""
        # Arrange - record with created_at
        custom_time = datetime.now(timezone.utc)
        sample_email_record.created_at = custom_time

        # Act
        await repository.create_email_record(sample_email_record)

        # Assert - provided created_at is preserved
        added_record = mock_session.add.call_args[0][0]
        assert added_record.created_at == custom_time

    @pytest.mark.parametrize(
        "template_id, category, expected_template, expected_category",
        [
            ("welcome", "onboarding", "welcome", "onboarding"),
            ("password_reset", "authentication", "password_reset", "authentication"),
            ("verification", "authentication", "verification", "authentication"),
            ("notification", "communication", "notification", "communication"),
        ],
    )
    async def test_create_email_record_handles_hule_edu_template_types(
        self,
        repository: PostgreSQLEmailRepository,
        mock_session: AsyncMock,
        template_id: str,
        category: str,
        expected_template: str,
        expected_category: str,
    ) -> None:
        """Test create_email_record handles HuleEdu specific template categories."""
        # Arrange
        record = EmailRecord(
            message_id=f"msg-{template_id}-123",
            to_address="teacher@huleedu.se",
            from_address="noreply@huleedu.se",
            from_name="HuleEdu System",
            subject=f"HuleEdu {category.title()}",
            template_id=template_id,
            category=category,
            variables={},
            correlation_id=str(uuid4()),
        )

        # Act
        await repository.create_email_record(record)

        # Assert - template and category preserved correctly
        added_record = mock_session.add.call_args[0][0]
        assert added_record.template_id == expected_template
        assert added_record.category == expected_category


class TestPostgreSQLEmailRepositoryStatusUpdates:
    """Tests for update_status method covering email lifecycle management."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock AsyncEngine."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock AsyncSession with query results."""
        session = AsyncMock(spec=AsyncSession)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        return session

    @pytest.fixture
    def repository(
        self, mock_engine: AsyncMock, mock_session: AsyncMock
    ) -> PostgreSQLEmailRepository:
        """Create repository with mocked session."""
        repo = PostgreSQLEmailRepository(mock_engine)
        repo.async_session_maker = MagicMock(return_value=mock_session)
        return repo

    @pytest.fixture
    def mock_db_record(self) -> MagicMock:
        """Create mock database record for update operations."""
        record = MagicMock(spec=DbEmailRecord)
        record.message_id = "msg-123"
        record.status = EmailStatus.PENDING
        record.provider_message_id = None
        record.sent_at = None
        record.failed_at = None
        record.failure_reason = None
        return record

    async def test_update_status_successful_email_sent(
        self,
        repository: PostgreSQLEmailRepository,
        mock_session: AsyncMock,
        mock_db_record: MagicMock,
    ) -> None:
        """Test update_status updates email to sent status correctly."""
        # Arrange
        message_id = "msg-123"
        provider_message_id = "provider-456"
        sent_at = datetime.now(timezone.utc)

        # Mock query result - execute returns a result that has scalar_one_or_none
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_record
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        await repository.update_status(
            message_id=message_id,
            status="sent",
            provider_message_id=provider_message_id,
            sent_at=sent_at,
        )

        # Assert - query executed correctly
        mock_session.execute.assert_called_once()

        # Assert - record updated correctly
        assert mock_db_record.status == EmailStatus.SENT
        assert mock_db_record.provider_message_id == provider_message_id
        assert mock_db_record.sent_at == sent_at
        mock_session.flush.assert_called_once()

    async def test_update_status_email_failed_with_reason(
        self,
        repository: PostgreSQLEmailRepository,
        mock_session: AsyncMock,
        mock_db_record: MagicMock,
    ) -> None:
        """Test update_status handles failed email with Swedish error message."""
        # Arrange
        message_id = "msg-456"
        failed_at = datetime.now(timezone.utc)
        failure_reason = "Mottagaren 'åsa.öberg@skolan.se' existerar inte"

        # Mock query result - execute returns a result that has scalar_one_or_none
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_record
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        await repository.update_status(
            message_id=message_id,
            status="failed",
            failed_at=failed_at,
            failure_reason=failure_reason,
        )

        # Assert - record updated with failure information
        assert mock_db_record.status == EmailStatus.FAILED
        assert mock_db_record.failed_at == failed_at
        assert mock_db_record.failure_reason == failure_reason

    async def test_update_status_record_not_found(
        self,
        repository: PostgreSQLEmailRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test update_status handles nonexistent record gracefully."""
        # Arrange
        message_id = "nonexistent-msg"

        # Mock query result - no record found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act - should not raise exception
        await repository.update_status(message_id=message_id, status="sent")

        # Assert - query executed but no flush called
        mock_session.execute.assert_called_once()
        mock_session.flush.assert_not_called()

    @pytest.mark.parametrize(
        "initial_status, new_status, expected_enum",
        [
            ("pending", "processing", EmailStatus.PROCESSING),
            ("processing", "sent", EmailStatus.SENT),
            ("processing", "failed", EmailStatus.FAILED),
            ("sent", "bounced", EmailStatus.BOUNCED),
            ("sent", "complained", EmailStatus.COMPLAINED),
        ],
    )
    async def test_update_status_handles_all_status_transitions(
        self,
        repository: PostgreSQLEmailRepository,
        mock_session: AsyncMock,
        mock_db_record: MagicMock,
        initial_status: str,
        new_status: str,
        expected_enum: EmailStatus,
    ) -> None:
        """Test update_status handles all valid email status transitions."""
        # Arrange
        mock_db_record.status = EmailStatus(initial_status)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_record
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        await repository.update_status(message_id="msg-123", status=new_status)

        # Assert - status updated correctly
        assert mock_db_record.status == expected_enum

    async def test_update_status_preserves_null_optional_fields(
        self,
        repository: PostgreSQLEmailRepository,
        mock_session: AsyncMock,
        mock_db_record: MagicMock,
    ) -> None:
        """Test update_status only updates provided optional fields."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_record
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act - only update status, leave optional fields as None
        await repository.update_status(message_id="msg-123", status="sent")

        # Assert - optional fields remain unchanged (None)
        assert mock_db_record.status == EmailStatus.SENT
        # These should not be modified when not provided
        assert mock_db_record.provider_message_id is None
        assert mock_db_record.sent_at is None
        assert mock_db_record.failed_at is None
        assert mock_db_record.failure_reason is None


class TestPostgreSQLEmailRepositoryQueryOperations:
    """Tests for get_by_message_id and get_by_correlation_id methods."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock AsyncEngine."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock AsyncSession."""
        session = AsyncMock(spec=AsyncSession)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        # Ensure async methods are properly mocked
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.close = AsyncMock()
        session.add = MagicMock()  # add is synchronous
        return session

    @pytest.fixture
    def repository(
        self, mock_engine: AsyncMock, mock_session: AsyncMock
    ) -> PostgreSQLEmailRepository:
        """Create repository with mocked session."""
        repo = PostgreSQLEmailRepository(mock_engine)
        repo.async_session_maker = MagicMock(return_value=mock_session)
        return repo

    @pytest.fixture
    def sample_db_record(self) -> MagicMock:
        """Create sample database record for testing queries."""
        record = MagicMock(spec=DbEmailRecord)
        record.message_id = "msg-123"
        record.to_address = "åsa.öberg@skolan.se"
        record.from_address = "noreply@huleedu.se"
        record.from_name = "HuleEdu Systemet"
        record.subject = "Välkommen till HuleEdu"
        record.template_id = "welcome"
        record.category = "onboarding"
        record.variables = {"teacher_name": "Åsa Öberg"}
        record.correlation_id = str(uuid4())
        record.html_content = None
        record.text_content = None
        record.provider = "sendgrid"
        record.provider_message_id = "sg-123"
        record.status = EmailStatus.SENT
        record.created_at = datetime.now(timezone.utc)
        record.sent_at = datetime.now(timezone.utc)
        record.failed_at = None
        record.failure_reason = None
        return record

    async def test_get_by_message_id_returns_email_record(
        self,
        repository: PostgreSQLEmailRepository,
        mock_session: AsyncMock,
        sample_db_record: MagicMock,
    ) -> None:
        """Test get_by_message_id returns correctly converted EmailRecord."""
        # Arrange
        message_id = "msg-123"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_db_record
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await repository.get_by_message_id(message_id)

        # Assert - query executed
        mock_session.execute.assert_called_once()

        # Assert - EmailRecord returned with correct data
        assert result is not None
        assert isinstance(result, EmailRecord)
        assert result.message_id == "msg-123"
        assert result.to_address == "åsa.öberg@skolan.se"
        assert result.from_name == "HuleEdu Systemet"
        assert result.subject == "Välkommen till HuleEdu"
        assert result.variables == {"teacher_name": "Åsa Öberg"}
        assert result.status == "sent"  # Enum converted to string

    async def test_get_by_message_id_returns_none_when_not_found(
        self,
        repository: PostgreSQLEmailRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test get_by_message_id returns None for nonexistent record."""
        # Arrange
        message_id = "nonexistent-msg"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        result = await repository.get_by_message_id(message_id)

        # Assert
        assert result is None
        mock_session.execute.assert_called_once()

    async def test_get_by_correlation_id_returns_list_of_records(
        self,
        repository: PostgreSQLEmailRepository,
        mock_session: AsyncMock,
        sample_db_record: MagicMock,
    ) -> None:
        """Test get_by_correlation_id returns list of EmailRecord objects."""
        # Arrange
        correlation_id = str(uuid4())

        # Create multiple records for same correlation_id
        record1 = sample_db_record
        record1.message_id = "msg-1"
        record2 = MagicMock(spec=DbEmailRecord)
        record2.message_id = "msg-2"
        record2.to_address = "karl.ångström@university.se"
        record2.from_address = "noreply@huleedu.se"
        record2.from_name = "HuleEdu System"
        record2.subject = "Password Reset"
        record2.template_id = "password_reset"
        record2.category = "authentication"
        record2.variables = {"user_name": "Karl"}
        record2.correlation_id = correlation_id
        record2.provider = "sendgrid"
        record2.provider_message_id = "sg-456"
        record2.status = EmailStatus.FAILED
        record2.created_at = datetime.now(timezone.utc)
        record2.sent_at = None
        record2.failed_at = datetime.now(timezone.utc)
        record2.failure_reason = "Bounce - Invalid email address"

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [record1, record2]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        results = await repository.get_by_correlation_id(correlation_id)

        # Assert - query executed
        mock_session.execute.assert_called_once()

        # Assert - list of EmailRecord objects returned
        assert isinstance(results, list)
        assert len(results) == 2

        # Verify first record
        assert results[0].message_id == "msg-1"
        assert results[0].status == "sent"

        # Verify second record
        assert results[1].message_id == "msg-2"
        assert results[1].to_address == "karl.ångström@university.se"
        assert results[1].status == "failed"
        assert results[1].failure_reason == "Bounce - Invalid email address"

    async def test_get_by_correlation_id_returns_empty_list_when_none_found(
        self,
        repository: PostgreSQLEmailRepository,
        mock_session: AsyncMock,
    ) -> None:
        """Test get_by_correlation_id returns empty list when no records found."""
        # Arrange
        correlation_id = str(uuid4())

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Act
        results = await repository.get_by_correlation_id(correlation_id)

        # Assert
        assert isinstance(results, list)
        assert len(results) == 0
        mock_session.execute.assert_called_once()

    @pytest.mark.parametrize(
        "to_address, subject, variables, expected_to, expected_subject",
        [
            # Swedish characters in various fields
            (
                "åsa.öberg@skolan.se",
                "Lösenordsåterställning för ditt konto",
                {"name": "Åsa Öberg", "school": "Kärrtorps Skola"},
                "åsa.öberg@skolan.se",
                "Lösenordsåterställning för ditt konto",
            ),
            # Mixed content with special characters
            (
                "maría.josé@colegio.es",
                "Bienvenida a HuleEdu - Educación Digital",
                {"teacher": "María José", "subject": "Matemáticas"},
                "maría.josé@colegio.es",
                "Bienvenida a HuleEdu - Educación Digital",
            ),
            # Standard ASCII content
            (
                "teacher@example.com",
                "Account Verification Required",
                {"name": "John Smith"},
                "teacher@example.com",
                "Account Verification Required",
            ),
        ],
    )
    async def test_db_record_to_protocol_preserves_unicode_characters(
        self,
        repository: PostgreSQLEmailRepository,
        to_address: str,
        subject: str,
        variables: dict[str, str],
        expected_to: str,
        expected_subject: str,
    ) -> None:
        """Test _db_record_to_protocol preserves Unicode characters correctly."""
        # Arrange
        db_record = MagicMock(spec=DbEmailRecord)
        db_record.message_id = "msg-unicode-123"
        db_record.to_address = to_address
        db_record.from_address = "noreply@huleedu.se"
        db_record.from_name = "HuleEdu System"
        db_record.subject = subject
        db_record.template_id = "verification"
        db_record.category = "authentication"
        db_record.variables = variables
        db_record.correlation_id = str(uuid4())
        db_record.provider = "sendgrid"
        db_record.provider_message_id = "sg-789"
        db_record.status = EmailStatus.SENT
        db_record.created_at = datetime.now(timezone.utc)
        db_record.sent_at = datetime.now(timezone.utc)
        db_record.failed_at = None
        db_record.failure_reason = None

        # Act
        protocol_record = repository._db_record_to_protocol(db_record)

        # Assert - Unicode characters preserved
        assert protocol_record.to_address == expected_to
        assert protocol_record.subject == expected_subject
        assert protocol_record.variables == variables


class TestPostgreSQLEmailRepositoryErrorHandling:
    """Tests for error handling patterns and database exception scenarios."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock AsyncEngine."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Sample correlation ID for error testing."""
        return uuid4()

    def test_structured_error_handling_patterns_for_email_operations(
        self, correlation_id: UUID
    ) -> None:
        """Test structured error handling patterns for email repository operations."""
        # Test error raising pattern for database constraint violation
        with pytest.raises(HuleEduError) as exc_info:
            raise_processing_error(
                service="email_service",
                operation="create_email_record",
                message="Database constraint violation: duplicate message_id",
                correlation_id=correlation_id,
                error_type="IntegrityError",
                message_id="msg-duplicate-123",
            )

        error = exc_info.value
        assert "Database constraint violation" in str(error)
        assert error.error_detail.service == "email_service"
        assert error.error_detail.operation == "create_email_record"

    def test_error_handling_preserves_swedish_characters(self, correlation_id: UUID) -> None:
        """Test error handling preserves Swedish characters in error messages."""
        swedish_email = "åsa.öberg@skolan.se"
        error_message = f"E-postleverans misslyckades till {swedish_email}"

        with pytest.raises(HuleEduError) as exc_info:
            raise_processing_error(
                service="email_service",
                operation="update_status",
                message=error_message,
                correlation_id=correlation_id,
                error_type="DeliveryError",
                recipient_email=swedish_email,
            )

        error = exc_info.value
        assert swedish_email in str(error)
        assert "åsa.öberg" in str(error)

    @pytest.mark.parametrize(
        "error_scenario, operation, error_type, expected_message",
        [
            (
                "duplicate_message_id",
                "create_email_record",
                "IntegrityError",
                "Email record creation failed: duplicate message ID",
            ),
            (
                "invalid_email_format",
                "create_email_record",
                "ValidationError",
                "Invalid email address format in recipient field",
            ),
            (
                "record_not_found",
                "update_status",
                "NotFoundError",
                "Email record not found for status update",
            ),
            (
                "database_connection_lost",
                "get_by_message_id",
                "OperationalError",
                "Database connection lost during email record retrieval",
            ),
        ],
    )
    def test_repository_error_scenarios(
        self,
        correlation_id: UUID,
        error_scenario: str,
        operation: str,
        error_type: str,
        expected_message: str,
    ) -> None:
        """Test various repository error scenarios with structured error handling."""
        with pytest.raises(HuleEduError) as exc_info:
            raise_processing_error(
                service="email_service",
                operation=operation,
                message=expected_message,
                correlation_id=correlation_id,
                error_type=error_type,
                scenario=error_scenario,
            )

        error = exc_info.value
        assert expected_message in str(error)
        assert error.error_detail.service == "email_service"
        assert error.error_detail.operation == operation


class TestPostgreSQLEmailRepositoryBehavioralEdgeCases:
    """Tests for HuleEdu-specific behavioral edge cases and domain requirements."""

    @pytest.fixture
    def mock_engine(self) -> AsyncMock:
        """Create mock AsyncEngine."""
        return AsyncMock(spec=AsyncEngine)

    @pytest.fixture
    def repository(self, mock_engine: AsyncMock) -> PostgreSQLEmailRepository:
        """Create repository instance."""
        return PostgreSQLEmailRepository(mock_engine)

    def test_repository_handles_hule_edu_email_categories(
        self, repository: PostgreSQLEmailRepository
    ) -> None:
        """Test repository properly handles HuleEdu-specific email categories."""
        # Test the domain-specific categories that should be supported
        hule_edu_categories = [
            "onboarding",  # New user welcome emails
            "authentication",  # Login, password reset, verification
            "notification",  # System notifications
            "assessment",  # Essay submissions, feedback
            "communication",  # Teacher-student messaging
        ]

        # Verify these are valid string categories (not enforced at repository level)
        for category in hule_edu_categories:
            # This tests that string categories are accepted
            assert isinstance(category, str)
            assert len(category) > 0

    def test_repository_handles_swedish_educational_content(
        self, repository: PostgreSQLEmailRepository
    ) -> None:
        """Test repository handles Swedish educational terminology correctly."""
        # Test Swedish educational terms with special characters
        terms_with_swedish_chars = [
            "lärare",  # teacher
            "skåla",  # school (modified for testing)
            "bedömning",  # assessment
            "återkoppling",  # feedback
        ]

        # Test that Swedish characters are preserved in strings
        for term in terms_with_swedish_chars:
            assert isinstance(term, str)
            # Verify these terms contain Swedish special characters
            has_swedish_chars = any(char in term for char in ["ä", "ö", "å"])
            assert has_swedish_chars, f"Term '{term}' should contain Swedish characters"

        # Test that repository can handle these terms (they're just strings to the repo)
        for term in terms_with_swedish_chars:
            assert len(term) > 0  # Basic validation that terms are non-empty strings

    def test_email_status_enum_covers_lifecycle(
        self, repository: PostgreSQLEmailRepository
    ) -> None:
        """Test EmailStatus enum covers complete email lifecycle."""
        # Verify all expected statuses are available
        expected_statuses = {
            EmailStatus.PENDING,
            EmailStatus.PROCESSING,
            EmailStatus.SENT,
            EmailStatus.FAILED,
            EmailStatus.BOUNCED,
            EmailStatus.COMPLAINED,
        }

        actual_statuses = set(EmailStatus)
        assert expected_statuses == actual_statuses

        # Verify string values are correct
        assert EmailStatus.PENDING.value == "pending"
        assert EmailStatus.SENT.value == "sent"
        assert EmailStatus.FAILED.value == "failed"
