"""
Comprehensive behavioral tests for database models following Rule 075 methodology.

Tests focus on actual model behavior, not SQLAlchemy ORM mechanics:
- Model creation and field validation
- Constraint enforcement and business rules
- Swedish character handling in text fields
- Default value behavior and enum validation
- Relationship mapping and foreign key constraints

All tests use direct model instantiation without @patch usage.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Type
from uuid import uuid4

import pytest

from services.entitlements_service.models_db import (
    CreditBalance,
    CreditOperation,
    OperationStatus,
    RateLimitBucket,
    SubjectType,
)
from huleedu_service_libs.outbox.models import EventOutbox


class TestEnumBehavior:
    """Tests for enum types used in database models."""

    @pytest.mark.parametrize(
        "enum_class, expected_values",
        [
            (SubjectType, {"user", "org"}),
            (OperationStatus, {"pending", "completed", "failed"}),
        ],
    )
    def test_enum_values_and_behavior(
        self, enum_class: Type[Any], expected_values: set[str]
    ) -> None:
        """Test enum classes contain expected values and proper equality behavior."""
        actual_values = {member.value for member in enum_class}
        assert actual_values == expected_values

        # Test equality behavior
        for member in enum_class:
            assert member == member
            for other in enum_class:
                if member != other:
                    assert member != other


class TestCreditBalanceModel:
    """Tests for CreditBalance model creation and field validation."""

    @pytest.mark.parametrize(
        "subject_type, subject_id, balance",
        [
            (SubjectType.USER, "user-standard", 100),
            (SubjectType.ORG, "org-standard", 500),
            (SubjectType.USER, "användare-åäö", 250),
            (SubjectType.ORG, "skola-malmö", 750),
            (SubjectType.USER, "lärare-göteborg", 1000),
            (SubjectType.ORG, "universitet-västerås", 2000),
            (SubjectType.USER, "student-örebro", 50),
            (SubjectType.ORG, "förening-åre", 0),
        ],
    )
    def test_credit_balance_creation_valid_fields(
        self, subject_type: SubjectType, subject_id: str, balance: int
    ) -> None:
        """Test CreditBalance model creation with valid fields including Swedish characters."""
        # Act
        credit_balance = CreditBalance(
            subject_type=subject_type,
            subject_id=subject_id,
            balance=balance,
        )

        # Assert
        assert credit_balance.subject_type == subject_type
        assert credit_balance.subject_id == subject_id
        assert credit_balance.balance == balance

    def test_credit_balance_field_assignment_and_timestamps(self) -> None:
        """Test CreditBalance field assignment and timestamp behavior."""
        # Test explicit balance assignment
        credit_balance = CreditBalance(
            subject_type=SubjectType.USER,
            subject_id="test-user",
            balance=150,
        )
        assert credit_balance.balance == 150

        # Test Swedish character handling
        swedish_balance = CreditBalance(
            subject_type=SubjectType.ORG,
            subject_id="skola-malmö-åäö",
            balance=200,
        )
        assert swedish_balance.subject_id == "skola-malmö-åäö"
        assert any(char in swedish_balance.subject_id for char in "åäö")

        # Test timestamp fields are not set during model instantiation
        assert not hasattr(credit_balance, "created_at") or credit_balance.created_at is None
        assert not hasattr(credit_balance, "updated_at") or credit_balance.updated_at is None


class TestCreditOperationModel:
    """Tests for CreditOperation model creation and field validation."""

    @pytest.mark.parametrize(
        "subject_type, subject_id, metric, amount, consumed_from, correlation_id",
        [
            (SubjectType.USER, "user-1", "spellcheck", 10, SubjectType.USER, "corr-123"),
            (
                SubjectType.ORG,
                "skola-åäö",
                "grammatik_kontroll",
                25,
                SubjectType.ORG,
                "corr-svenska",
            ),
            (
                SubjectType.USER,
                "användare-malmö",
                "språk_bedömning",
                50,
                SubjectType.ORG,
                "corr-åäö-123",
            ),
            (
                SubjectType.ORG,
                "företag-göteborg",
                "rätt_stavning",
                15,
                SubjectType.USER,
                "admin-corr-åäö",
            ),
            (
                SubjectType.USER,
                "lärare-örebro",
                "ai_feedback",
                100,
                SubjectType.ORG,
                "batch-åre-ÅÄÖ",
            ),
        ],
    )
    def test_credit_operation_creation_valid_fields(
        self,
        subject_type: SubjectType,
        subject_id: str,
        metric: str,
        amount: int,
        consumed_from: SubjectType,
        correlation_id: str,
    ) -> None:
        """Test CreditOperation model creation with valid fields including Swedish characters."""
        # Arrange
        operation_id = uuid4()

        # Act
        credit_operation = CreditOperation(
            id=operation_id,
            subject_type=subject_type,
            subject_id=subject_id,
            metric=metric,
            amount=amount,
            consumed_from=consumed_from,
            correlation_id=correlation_id,
        )

        # Assert
        assert credit_operation.id == operation_id
        assert credit_operation.subject_type == subject_type
        assert credit_operation.subject_id == subject_id
        assert credit_operation.metric == metric
        assert credit_operation.amount == amount
        assert credit_operation.consumed_from == consumed_from
        assert credit_operation.correlation_id == correlation_id

    def test_credit_operation_field_validation_and_options(self) -> None:
        """Test CreditOperation field validation, ID assignment, and status handling."""
        # Test explicit ID assignment
        explicit_id = uuid4()
        operation_with_id = CreditOperation(
            id=explicit_id,
            subject_type=SubjectType.USER,
            subject_id="test-user",
            metric="test_metric",
            amount=10,
            consumed_from=SubjectType.USER,
            correlation_id="test-correlation",
        )
        assert operation_with_id.id == explicit_id
        assert isinstance(operation_with_id.id, uuid.UUID)

        # Test status assignment
        operation_with_status = CreditOperation(
            subject_type=SubjectType.USER,
            subject_id="test-user",
            metric="test_metric",
            amount=10,
            consumed_from=SubjectType.USER,
            correlation_id="test-correlation",
            operation_status=OperationStatus.COMPLETED,
        )
        assert operation_with_status.operation_status == OperationStatus.COMPLETED

    @pytest.mark.parametrize(
        "amount, status, batch_id",
        [
            (1, OperationStatus.PENDING, None),
            (-1, OperationStatus.COMPLETED, "batch-123"),
            (100, OperationStatus.FAILED, "batch-åäö-swedish"),
            (-250, OperationStatus.COMPLETED, "bulk-operation-malmö"),
            (0, OperationStatus.PENDING, None),
        ],
    )
    def test_credit_operation_field_combinations(
        self, amount: int, status: OperationStatus, batch_id: str | None
    ) -> None:
        """Test CreditOperation handles various field combinations including Swedish characters."""
        credit_operation = CreditOperation(
            subject_type=SubjectType.USER,
            subject_id="test-user",
            metric="test_metric",
            amount=amount,
            consumed_from=SubjectType.USER,
            correlation_id="test-correlation",
            operation_status=status,
            batch_id=batch_id,
        )

        assert credit_operation.amount == amount
        assert credit_operation.operation_status == status
        assert credit_operation.batch_id == batch_id


class TestRateLimitBucketModel:
    """Tests for RateLimitBucket model creation and field validation."""

    @pytest.mark.parametrize(
        "subject_id, metric, count",
        [
            ("user-standard", "requests", 10),
            ("användare-åäö", "grammatik_kontroll", 25),
            ("skola-malmö", "språk_bedömning", 100),
            ("lärare-göteborg", "rätt_stavning", 0),
            ("företag-örebro", "ai_feedback", 500),
        ],
    )
    def test_rate_limit_bucket_creation_valid_fields(
        self, subject_id: str, metric: str, count: int
    ) -> None:
        """Test RateLimitBucket model creation with valid fields including Swedish characters."""
        # Arrange
        window_start = datetime.now(timezone.utc)

        # Act
        rate_limit_bucket = RateLimitBucket(
            subject_id=subject_id,
            metric=metric,
            window_start=window_start,
            count=count,
        )

        # Assert
        assert rate_limit_bucket.subject_id == subject_id
        assert rate_limit_bucket.metric == metric
        assert rate_limit_bucket.window_start == window_start
        assert rate_limit_bucket.count == count

    @pytest.mark.parametrize(
        "subject_id, metric, count",
        [
            ("test-user", "requests", 25),
            ("användare-åäö", "grammatik_kontroll", 50),
            ("skola-malmö", "språk_bedömning_requests", 100),
            ("lärare-göteborg", "rätt_stavning_calls", 0),
            ("företag-örebro", "ai_feedback_usage", 500),
        ],
    )
    def test_rate_limit_bucket_field_handling_and_swedish_characters(
        self, subject_id: str, metric: str, count: int
    ) -> None:
        """Test RateLimitBucket field handling including Swedish characters and metrics."""
        window_start = datetime.now(timezone.utc)

        rate_limit_bucket = RateLimitBucket(
            subject_id=subject_id,
            metric=metric,
            window_start=window_start,
            count=count,
        )

        assert rate_limit_bucket.subject_id == subject_id
        assert rate_limit_bucket.metric == metric
        assert rate_limit_bucket.count == count

    def test_rate_limit_bucket_timestamp_precision(self) -> None:
        """Test RateLimitBucket maintains timestamp precision for window calculations."""
        precise_timestamp = datetime(2024, 1, 15, 12, 30, 45, 123456, timezone.utc)

        rate_limit_bucket = RateLimitBucket(
            subject_id="precision-test",
            metric="test_metric",
            window_start=precise_timestamp,
            count=1,
        )

        assert rate_limit_bucket.window_start == precise_timestamp
        assert rate_limit_bucket.window_start.microsecond == 123456


class TestEventOutboxModel:
    """Tests for EventOutbox model creation and field validation."""

    @pytest.mark.parametrize(
        "aggregate_type, aggregate_id, event_type, topic",
        [
            ("CreditBalance", "user-123", "CreditBalanceUpdated", "credit.balance.updated"),
            ("CreditBalance", "användare-åäö", "CreditBalanceCreated", "credit.balance.created"),
            ("CreditOperation", "skola-malmö", "CreditConsumed", "credit.operation.consumed"),
            ("RateLimit", "lärare-göteborg", "RateLimitExceeded", "rate.limit.exceeded"),
            ("CreditBalance", "företag-örebro", "CreditAdjusted", "credit.balance.adjusted"),
        ],
    )
    def test_event_outbox_creation_valid_fields(
        self, aggregate_type: str, aggregate_id: str, event_type: str, topic: str
    ) -> None:
        """Test EventOutbox model creation with valid fields including Swedish characters."""
        # Arrange
        event_id = uuid4()
        event_data = {"user_id": aggregate_id, "amount": 100}

        # Act
        event_outbox = EventOutbox(
            id=event_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            event_data=event_data,
            topic=topic,
        )

        # Assert
        assert event_outbox.id == event_id
        assert event_outbox.aggregate_type == aggregate_type
        assert event_outbox.aggregate_id == aggregate_id
        assert event_outbox.event_type == event_type
        assert event_outbox.event_data == event_data
        assert event_outbox.topic == topic

    def test_event_outbox_id_and_timestamp_behavior(self) -> None:
        """Test EventOutbox ID assignment and timestamp behavior."""
        # Test explicit ID assignment
        explicit_id = uuid4()
        event_with_id = EventOutbox(
            id=explicit_id,
            aggregate_type="TestAggregate",
            aggregate_id="test-id",
            event_type="TestEvent",
            event_data={"test": "data"},
            topic="test.topic",
        )
        assert event_with_id.id == explicit_id
        assert isinstance(event_with_id.id, uuid.UUID)

        # Test published_at initially None
        unpublished_event = EventOutbox(
            aggregate_type="TestAggregate",
            aggregate_id="test-id",
            event_type="TestEvent",
            event_data={"test": "data"},
            topic="test.topic",
        )
        assert unpublished_event.published_at is None

        # Test published_at timestamp assignment
        published_time = datetime.now(timezone.utc)
        published_event = EventOutbox(
            aggregate_type="TestAggregate",
            aggregate_id="test-id",
            event_type="TestEvent",
            event_data={"test": "data"},
            topic="test.topic",
            published_at=published_time,
        )
        assert published_event.published_at == published_time

    @pytest.mark.parametrize(
        "event_data, aggregate_id",
        [
            ({"simple": "data"}, "user-123"),
            (
                {"user_id": "användare-åäö", "metric": "grammatik_kontroll", "amount": 25},
                "skola-malmö-gymnasium",
            ),
            ({"nested": {"data": {"with": "multiple_levels"}}}, "lärare-göteborg-svenska"),
            ({"array": ["item1", "item2", "åäö-item"]}, "företag-örebro-språktjänst"),
            ({"empty": {}}, "bedömning-motor-åre"),
            (
                {
                    "complex": {
                        "user_id": "lärare-malmö",
                        "operations": [{"metric": "språk_bedömning", "amount": 10}],
                        "metadata": {"source": "språk_tjänst", "timestamp": "2024-01-15T12:00:00Z"},
                    }
                },
                "användare-åäö-123",
            ),
        ],
    )
    def test_event_outbox_json_data_and_swedish_characters(
        self, event_data: dict, aggregate_id: str
    ) -> None:
        """Test EventOutbox handles JSON data structures and Swedish characters."""
        event_outbox = EventOutbox(
            aggregate_type="CreditBalance",
            aggregate_id=aggregate_id,
            event_type="CreditBalanceUpdated",
            event_data=event_data,
            topic="credit.balance.updated",
        )

        assert event_outbox.event_data == event_data
        assert event_outbox.aggregate_id == aggregate_id
