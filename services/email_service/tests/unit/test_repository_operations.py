"""
Unit tests for PostgreSQLEmailRepository email operations.

Tests focus on record creation, status updates, and query operations
with comprehensive Swedish character support following Rule 075 methodology.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from services.email_service.implementations.repository_impl import PostgreSQLEmailRepository
from services.email_service.models_db import EmailRecord as DbEmailRecord
from services.email_service.models_db import EmailStatus
from services.email_service.protocols import EmailRecord


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

        # Mock query result
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

        # Mock query result
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
        session.execute = AsyncMock()
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
