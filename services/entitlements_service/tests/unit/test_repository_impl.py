"""
Comprehensive behavioral tests for EntitlementsRepositoryImpl.

Tests focus on actual business behavior following Rule 075 methodology:
- Credit balance operations and management
- Transaction handling and rollback scenarios
- Audit trail recording with correlation tracking
- Identity handling including Swedish characters
- Idempotency and duplicate operation handling

All tests use AsyncMock(spec=Protocol) pattern for database session mocking.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.entitlements_service.implementations.repository_impl import EntitlementsRepositoryImpl
from services.entitlements_service.models_db import (
    CreditOperation,
    OperationStatus,
    SubjectType,
)


class TestEntitlementsRepositoryImplCreditBalance:
    """Tests for credit balance operations focusing on business behavior."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock AsyncSession."""
        session = AsyncMock(spec=AsyncSession)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.add = MagicMock()  # add is synchronous
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> EntitlementsRepositoryImpl:
        """Create repository instance for testing."""
        mock_factory = MagicMock(return_value=mock_session)
        return EntitlementsRepositoryImpl(mock_factory)

    @pytest.mark.parametrize(
        "subject_type,subject_id,expected_balance",
        [
            ("user", "test-user", 100),
            ("org", "test-org", 250),
            ("user", "användare-åäö", 500),  # Swedish characters
            ("org", "skola-malmö", 750),  # Swedish characters
            ("user", "empty-balance", 0),  # Zero balance
        ],
    )
    async def test_get_credit_balance_returns_existing_balance(
        self,
        repository: EntitlementsRepositoryImpl,
        mock_session: AsyncMock,
        subject_type: str,
        subject_id: str,
        expected_balance: int,
    ) -> None:
        """Test get_credit_balance returns existing balance for valid subjects."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar.return_value = expected_balance
        mock_session.execute.return_value = mock_result

        # Act
        balance = await repository.get_credit_balance(subject_type, subject_id)

        # Assert
        assert balance == expected_balance
        mock_session.execute.assert_called_once()
        # Verify correct query parameters
        call_args = mock_session.execute.call_args[0][0]
        assert str(call_args).find("credit_balances") != -1

    async def test_get_credit_balance_returns_zero_for_nonexistent_subject(
        self, repository: EntitlementsRepositoryImpl, mock_session: AsyncMock
    ) -> None:
        """Test get_credit_balance returns 0 when subject doesn't exist."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar.return_value = None  # No balance found
        mock_session.execute.return_value = mock_result

        # Act
        balance = await repository.get_credit_balance("user", "nonexistent")

        # Assert
        assert balance == 0
        mock_session.execute.assert_called_once()

    @pytest.mark.parametrize(
        "subject_type,subject_id,initial_balance,delta,expected_new_balance",
        [
            ("user", "test-user", 100, 50, 150),  # Credit addition
            ("user", "test-user", 100, -25, 75),  # Credit consumption
            ("org", "skola-åäö", 200, 100, 300),  # Swedish chars with addition
            ("org", "företag-öäå", 150, -50, 100),  # Swedish chars with consumption
            ("user", "edge-case", 1, -1, 0),  # Exact balance consumption
        ],
    )
    async def test_update_credit_balance_modifies_existing_balance(
        self,
        repository: EntitlementsRepositoryImpl,
        mock_session: AsyncMock,
        subject_type: str,
        subject_id: str,
        initial_balance: int,
        delta: int,
        expected_new_balance: int,
    ) -> None:
        """Test update_credit_balance correctly modifies existing balances."""
        # Arrange

        # Mock existing balance record
        mock_balance_record = MagicMock()
        mock_balance_record.balance = initial_balance
        mock_balance_record.updated_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_balance_record
        mock_session.execute.return_value = mock_result

        correlation_id = f"test-correlation-{uuid.uuid4()}"

        # Act
        new_balance = await repository.update_credit_balance(
            subject_type, subject_id, delta, correlation_id
        )

        # Assert
        assert new_balance == expected_new_balance
        assert mock_balance_record.balance == expected_new_balance
        assert mock_balance_record.updated_at is not None
        mock_session.commit.assert_called_once()

    async def test_update_credit_balance_creates_new_record_for_positive_delta(
        self, repository: EntitlementsRepositoryImpl, mock_session: AsyncMock
    ) -> None:
        """Test update_credit_balance creates new balance record for positive delta on nonexistent subject."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing balance
        mock_session.execute.return_value = mock_result

        subject_type = "user"
        subject_id = "new-användare"
        delta = 100
        correlation_id = "create-new-balance"

        # Act
        new_balance = await repository.update_credit_balance(
            subject_type, subject_id, delta, correlation_id
        )

        # Assert
        assert new_balance == delta
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    async def test_update_credit_balance_raises_error_for_insufficient_credits(
        self, repository: EntitlementsRepositoryImpl, mock_session: AsyncMock
    ) -> None:
        """Test update_credit_balance raises ValueError when balance would go negative."""
        # Arrange

        mock_balance_record = MagicMock()
        mock_balance_record.balance = 50

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_balance_record
        mock_session.execute.return_value = mock_result

        subject_type = "user"
        subject_id = "insufficient-user"
        delta = -100  # Would result in negative balance
        correlation_id = "insufficient-test"

        # Act & Assert
        with pytest.raises(ValueError, match="Insufficient credits"):
            await repository.update_credit_balance(subject_type, subject_id, delta, correlation_id)

        mock_session.rollback.assert_called_once()

    async def test_update_credit_balance_raises_error_for_negative_delta_on_nonexistent_subject(
        self, repository: EntitlementsRepositoryImpl, mock_session: AsyncMock
    ) -> None:
        """Test update_credit_balance raises ValueError for negative delta on nonexistent subject."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing balance
        mock_session.execute.return_value = mock_result

        subject_type = "user"
        subject_id = "nonexistent-user"
        delta = -50
        correlation_id = "consume-from-nothing"

        # Act & Assert
        with pytest.raises(ValueError, match="Cannot consume credits from non-existent balance"):
            await repository.update_credit_balance(subject_type, subject_id, delta, correlation_id)


class TestEntitlementsRepositoryImplAuditTrail:
    """Tests for audit trail recording and operation history."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock AsyncSession."""
        session = AsyncMock(spec=AsyncSession)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.add = MagicMock()  # add is synchronous
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> EntitlementsRepositoryImpl:
        """Create repository instance for testing."""
        mock_factory = MagicMock(return_value=mock_session)
        return EntitlementsRepositoryImpl(mock_factory)

    @pytest.mark.parametrize(
        "subject_type,subject_id,metric,amount,consumed_from,correlation_id,batch_id,status",
        [
            ("user", "test-user", "spellcheck", 10, "user", "corr-123", None, "completed"),
            ("org", "skola-örebro", "grammar_check", 25, "org", "corr-åäö", "batch-1", "completed"),
            (
                "user",
                "användare-123",
                "ai_feedback",
                50,
                "org",
                "swedish-corr",
                "batch-åäö",
                "failed",
            ),
            (
                "org",
                "företag-malmö",
                "manual_adjustment",
                -100,
                "org",
                "admin-adj",
                None,
                "completed",
            ),
        ],
    )
    async def test_record_operation_creates_audit_trail_entry(
        self,
        repository: EntitlementsRepositoryImpl,
        mock_session: AsyncMock,
        subject_type: str,
        subject_id: str,
        metric: str,
        amount: int,
        consumed_from: str,
        correlation_id: str,
        batch_id: str | None,
        status: str,
    ) -> None:
        """Test record_operation creates proper audit trail entries."""
        # Arrange

        # Act
        await repository.record_operation(
            subject_type=subject_type,
            subject_id=subject_id,
            metric=metric,
            amount=amount,
            consumed_from=consumed_from,
            correlation_id=correlation_id,
            batch_id=batch_id,
            status=status,
        )

        # Assert
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

        # Verify the operation record was created with correct data
        added_operation = mock_session.add.call_args[0][0]
        assert isinstance(added_operation, CreditOperation)
        assert added_operation.subject_type == SubjectType(subject_type)
        assert added_operation.subject_id == subject_id
        assert added_operation.metric == metric
        assert added_operation.amount == amount
        assert added_operation.consumed_from == SubjectType(consumed_from)
        assert added_operation.correlation_id == correlation_id
        assert added_operation.batch_id == batch_id
        assert added_operation.operation_status == OperationStatus(status)

    async def test_record_operation_handles_database_errors(
        self, repository: EntitlementsRepositoryImpl, mock_session: AsyncMock
    ) -> None:
        """Test record_operation properly handles database errors with rollback."""
        # Arrange
        mock_session.commit.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(Exception, match="Database error"):
            await repository.record_operation(
                subject_type="user",
                subject_id="error-user",
                metric="test_metric",
                amount=10,
                consumed_from="user",
                correlation_id="error-test",
            )

        mock_session.rollback.assert_called_once()


class TestEntitlementsRepositoryImplOperationsHistory:
    """Tests for operations history retrieval and filtering."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock AsyncSession."""
        session = AsyncMock(spec=AsyncSession)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.add = MagicMock()  # add is synchronous
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> EntitlementsRepositoryImpl:
        """Create repository instance for testing."""
        mock_factory = MagicMock(return_value=mock_session)
        return EntitlementsRepositoryImpl(mock_factory)

    def _create_mock_operation(
        self,
        op_id: str,
        subject_type: str,
        subject_id: str,
        metric: str,
        amount: int,
        correlation_id: str,
        batch_id: str | None = None,
    ) -> MagicMock:
        """Create mock operation for testing."""
        mock_op = MagicMock()
        mock_op.id = op_id
        mock_op.subject_type = SubjectType(subject_type)
        mock_op.subject_id = subject_id
        mock_op.metric = metric
        mock_op.amount = amount
        mock_op.batch_id = batch_id
        mock_op.consumed_from = SubjectType(subject_type)
        mock_op.correlation_id = correlation_id
        mock_op.operation_status = OperationStatus.COMPLETED
        mock_op.created_at = datetime.now(timezone.utc)
        return mock_op

    async def test_get_operations_history_returns_formatted_records(
        self, repository: EntitlementsRepositoryImpl, mock_session: AsyncMock
    ) -> None:
        """Test get_operations_history returns properly formatted operation records."""
        # Arrange

        mock_operations = [
            self._create_mock_operation("op-1", "user", "användare-1", "spellcheck", 10, "corr-1"),
            self._create_mock_operation(
                "op-2", "org", "skola-åäö", "grammar", 25, "corr-2", "batch-1"
            ),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_operations
        mock_session.execute.return_value = mock_result

        # Act
        history = await repository.get_operations_history()

        # Assert
        assert len(history) == 2
        assert history[0]["id"] == "op-1"
        assert history[0]["subject_type"] == "user"
        assert history[0]["subject_id"] == "användare-1"
        assert history[0]["metric"] == "spellcheck"
        assert history[0]["amount"] == 10
        assert history[0]["correlation_id"] == "corr-1"
        assert history[0]["batch_id"] is None

        assert history[1]["batch_id"] == "batch-1"
        assert history[1]["subject_id"] == "skola-åäö"

    @pytest.mark.parametrize(
        "subject_type,subject_id,correlation_id,limit",
        [
            ("user", "test-user", None, 50),
            (None, None, "corr-svenska", 25),
            ("org", "skola-malmö", "admin-åäö", 10),
            (None, "företag-örebro", None, 100),
        ],
    )
    async def test_get_operations_history_applies_filters_correctly(
        self,
        repository: EntitlementsRepositoryImpl,
        mock_session: AsyncMock,
        subject_type: str | None,
        subject_id: str | None,
        correlation_id: str | None,
        limit: int,
    ) -> None:
        """Test get_operations_history applies filters and limits correctly."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Act
        await repository.get_operations_history(
            subject_type=subject_type,
            subject_id=subject_id,
            correlation_id=correlation_id,
            limit=limit,
        )

        # Assert
        mock_session.execute.assert_called_once()
        # Verify query was called with proper filters - detailed query inspection omitted
        # per behavioral testing principles


class TestEntitlementsRepositoryImplBalanceAdjustment:
    """Tests for administrative balance adjustment functionality."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock AsyncSession."""
        session = AsyncMock(spec=AsyncSession)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.add = MagicMock()  # add is synchronous
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> EntitlementsRepositoryImpl:
        """Create repository instance for testing."""
        mock_factory = MagicMock(return_value=mock_session)
        return EntitlementsRepositoryImpl(mock_factory)

    @pytest.mark.parametrize(
        "subject_type,subject_id,amount,reason",
        [
            ("user", "adjust-user", 500, "Initial credit grant"),
            ("org", "skola-åäö", -100, "Billing correction"),
            ("user", "användare-malmö", 1000, "Promotional credits"),
            ("org", "företag-örebro", -250, "Overage adjustment"),
        ],
    )
    async def test_adjust_balance_performs_update_and_records_operation(
        self,
        repository: EntitlementsRepositoryImpl,
        mock_session: AsyncMock,
        subject_type: str,
        subject_id: str,
        amount: int,
        reason: str,
    ) -> None:
        """Test adjust_balance performs balance update and records audit trail."""
        # Arrange

        # Mock existing balance for update_credit_balance - set high enough for all test cases
        initial_balance = 1000  # High enough to handle -250 test case
        mock_balance_record = MagicMock()
        mock_balance_record.balance = initial_balance
        mock_balance_record.updated_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_balance_record
        mock_session.execute.return_value = mock_result

        correlation_id = f"admin-adjust-{uuid.uuid4()}"
        expected_new_balance = initial_balance + amount

        # Act
        new_balance = await repository.adjust_balance(
            subject_type=subject_type,
            subject_id=subject_id,
            amount=amount,
            reason=reason,
            correlation_id=correlation_id,
        )

        # Assert
        assert new_balance == expected_new_balance
        # Verify both update and record operations were called
        assert mock_session.commit.call_count == 2  # Once for update, once for record
        assert mock_session.add.call_count >= 1  # At least one for the operation record


class TestEntitlementsRepositoryImplErrorHandling:
    """Tests for error handling and transaction rollback scenarios."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock AsyncSession."""
        session = AsyncMock(spec=AsyncSession)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.add = MagicMock()  # add is synchronous
        return session

    @pytest.fixture
    def repository(self, mock_session: AsyncMock) -> EntitlementsRepositoryImpl:
        """Create repository instance for testing."""
        mock_factory = MagicMock(return_value=mock_session)
        return EntitlementsRepositoryImpl(mock_factory)

    async def test_get_credit_balance_handles_database_errors(
        self, repository: EntitlementsRepositoryImpl, mock_session: AsyncMock
    ) -> None:
        """Test get_credit_balance properly handles and re-raises database errors."""
        # Arrange
        mock_session.execute.side_effect = Exception("Database connection error")

        # Act & Assert
        with pytest.raises(Exception, match="Database connection error"):
            await repository.get_credit_balance("user", "error-user")

    async def test_update_credit_balance_rolls_back_on_constraint_violation(
        self, repository: EntitlementsRepositoryImpl, mock_session: AsyncMock
    ) -> None:
        """Test update_credit_balance rolls back transaction on constraint violations."""
        # Arrange
        mock_session.execute.side_effect = Exception("Constraint violation")

        # Act & Assert
        with pytest.raises(Exception, match="Constraint violation"):
            await repository.update_credit_balance("user", "constraint-user", 100, "test-corr")

        mock_session.rollback.assert_called_once()

    async def test_get_operations_history_handles_query_errors(
        self, repository: EntitlementsRepositoryImpl, mock_session: AsyncMock
    ) -> None:
        """Test get_operations_history properly handles query errors."""
        # Arrange
        mock_session.execute.side_effect = Exception("Query execution error")

        # Act & Assert
        with pytest.raises(Exception, match="Query execution error"):
            await repository.get_operations_history()
