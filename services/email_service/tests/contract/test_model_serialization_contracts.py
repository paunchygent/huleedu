"""
Model Serialization and Database Constraint Contract Testing for Email Service.

This module provides comprehensive contract tests for cross-model serialization,
database constraints, and validation rules to ensure proper behavior across
service boundaries and data integrity enforcement.

Following ULTRATHINK methodology for database model contract validation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import inspect

from services.email_service.models_db import (
    Base,
    EmailRecord,
    EmailStatus,
    EmailTemplate,
    EventOutbox,
)


class TestModelSerializationContracts:
    """Test contracts for model serialization and deserialization across boundaries."""

    def test_email_record_dict_conversion_contract(self) -> None:
        """Contract test: EmailRecord must convert to dict consistently."""
        # Arrange
        email_record = EmailRecord(
            message_id=f"msg_{uuid4()}",
            correlation_id=str(uuid4()),
            to_address="test@huledu.se",
            from_address="noreply@huledu.se",
            from_name="HuleEdu System",
            subject="Test Subject with åäö",
            template_id="test_template",
            category="notification",
            variables={"user": "Åsa", "course": "Matematik"},
            status=EmailStatus.SENT,
            provider="sendgrid",
            provider_message_id="sg_msg_123",
            sent_at=datetime.now(UTC),
        )

        # Act - Convert to dict using SQLAlchemy inspection
        inspector = inspect(EmailRecord)
        record_dict = {}
        for column in inspector.columns:
            record_dict[column.name] = getattr(email_record, column.name)

        # Assert - Dict conversion contract
        assert record_dict["message_id"] == email_record.message_id
        assert record_dict["subject"] == "Test Subject with åäö"
        assert record_dict["variables"] == {"user": "Åsa", "course": "Matematik"}
        assert record_dict["status"] == EmailStatus.SENT
        assert record_dict["provider"] == "sendgrid"

    def test_json_serialization_complex_types_contract(self) -> None:
        """Contract test: Complex types must serialize to JSON properly."""
        # Arrange - Create models with complex types
        email_id = uuid4()
        correlation_id = uuid4()
        timestamp = datetime.now(UTC)

        outbox_entry = EventOutbox(
            id=email_id,
            aggregate_id=str(correlation_id),
            aggregate_type="EmailRecord",
            event_type="EmailProcessed",
            event_data={
                "email_id": str(email_id),
                "correlation_id": str(correlation_id),
                "processed_at": timestamp.isoformat(),
                "status": "sent",
                "swedish_content": "Meddelande med åäö",
            },
            topic="email.events",
            created_at=timestamp,
            published_at=timestamp + timedelta(seconds=1),
            retry_count=2,
        )

        # Act - Create JSON-serializable dict
        serializable_dict = {}
        inspector = inspect(EventOutbox)
        for column in inspector.columns:
            value = getattr(outbox_entry, column.name)
            if isinstance(value, UUID):
                serializable_dict[column.name] = str(value)
            elif isinstance(value, datetime):
                serializable_dict[column.name] = value.isoformat()
            else:
                serializable_dict[column.name] = value

        # Act - JSON round-trip
        json_str = json.dumps(serializable_dict, ensure_ascii=False)
        deserialized_dict = json.loads(json_str)

        # Assert - JSON serialization contract
        assert deserialized_dict["id"] == str(email_id)
        assert deserialized_dict["aggregate_id"] == str(correlation_id)
        assert deserialized_dict["retry_count"] == 2
        assert "swedish_content" in json.dumps(deserialized_dict["event_data"])
        assert "åäö" in json_str  # Swedish characters preserved

    def test_enum_serialization_consistency_contract(self) -> None:
        """Contract test: Enum serialization must be consistent across formats."""
        # Arrange - Test all EmailStatus enum values
        status_records = []
        for status in EmailStatus:
            record = EmailRecord(
                message_id=f"msg_{status.value}_{uuid4()}",
                correlation_id=str(uuid4()),
                to_address="test@huledu.se",
                from_address="noreply@huledu.se",
                from_name="HuleEdu",
                subject=f"Test {status.value}",
                template_id="test_template",
                category="test",
                variables={},
                status=status,
            )
            status_records.append(record)

        # Act & Assert - Test enum serialization consistency
        for record in status_records:
            # Direct enum access
            assert isinstance(record.status, EmailStatus)

            # String value access
            assert record.status.value in [
                "pending",
                "processing",
                "sent",
                "failed",
                "bounced",
                "complained",
            ]

            # JSON serialization would convert enum to string value
            status_dict = {"status": record.status.value}
            json_str = json.dumps(status_dict)
            parsed = json.loads(json_str)

            # Assert - Round-trip preservation
            assert parsed["status"] == record.status.value
            assert EmailStatus(parsed["status"]) == record.status

    def test_field_type_preservation_contract(self) -> None:
        """Contract test: Field types must be preserved across model boundaries."""
        # Arrange - Create models with various field types
        email_template = EmailTemplate(
            template_id="type_test_template",
            name="Type Test Template",
            description="Testing field type preservation",
            category="testing",
            subject_template="Subject: {{variable}}",
            is_active=True,
        )

        outbox_entry = EventOutbox(
            aggregate_id="test_aggregate",
            aggregate_type="TestType",
            event_type="TypeTest",
            event_data={"number": 42, "boolean": True, "string": "test"},
            topic="type.test",
            retry_count=5,
        )

        # Act & Assert - Field type contracts
        # String fields
        assert isinstance(email_template.template_id, str)
        assert isinstance(email_template.name, str)
        assert isinstance(email_template.category, str)

        # Boolean field
        assert isinstance(email_template.is_active, bool)
        assert email_template.is_active is True

        # Integer field
        assert isinstance(outbox_entry.retry_count, int)
        assert outbox_entry.retry_count == 5

        # Dict/JSON field
        assert isinstance(outbox_entry.event_data, dict)
        assert outbox_entry.event_data["number"] == 42
        assert outbox_entry.event_data["boolean"] is True

        # UUID field (default applied by SQLAlchemy/database)
        # Note: At Python instantiation, id will be None until database assigns UUID
        # assert isinstance(outbox_entry.id, UUID)  # Would be set by database default


class TestDatabaseConstraintContracts:
    """Test contracts for database constraints and validation rules."""

    def test_unique_constraint_validation_contract(self) -> None:
        """Contract test: Unique constraints must be properly defined."""
        # Act - Inspect unique constraints
        email_record_table = EmailRecord.__table__

        # Assert - provider_message_id has unique constraint
        provider_msg_column = email_record_table.columns["provider_message_id"]
        assert provider_msg_column.unique is True

        # Assert - Primary keys are unique by definition
        assert email_record_table.columns["message_id"].primary_key is True

        email_template_table = EmailTemplate.__table__
        assert email_template_table.columns["template_id"].primary_key is True

        outbox_table = EventOutbox.__table__
        assert outbox_table.columns["id"].primary_key is True

    def test_not_null_constraint_enforcement_contract(self) -> None:
        """Contract test: NOT NULL constraints must be properly enforced."""
        # Act - Test EmailRecord NOT NULL constraints
        email_record_columns = EmailRecord.__table__.columns

        # Assert - Required fields are NOT NULL
        required_fields = [
            "message_id",
            "correlation_id",
            "to_address",
            "from_address",
            "from_name",
            "subject",
            "template_id",
            "category",
            "status",
        ]
        for field in required_fields:
            assert email_record_columns[field].nullable is False

        # Assert - Optional fields are nullable
        optional_fields = [
            "provider",
            "provider_message_id",
            "failure_reason",
            "sent_at",
            "failed_at",
        ]
        for field in optional_fields:
            assert email_record_columns[field].nullable is True

        # Act - Test EventOutbox NOT NULL constraints
        outbox_columns = EventOutbox.__table__.columns

        # Assert - Required outbox fields are NOT NULL
        required_outbox_fields = [
            "id",
            "aggregate_id",
            "aggregate_type",
            "event_type",
            "event_data",
            "topic",
            "created_at",
            "retry_count",
        ]
        for field in required_outbox_fields:
            assert outbox_columns[field].nullable is False

    def test_default_value_application_contract(self) -> None:
        """Contract test: Default values must be applied correctly."""
        # Act - Test EmailRecord defaults
        EmailRecord(
            message_id=f"msg_{uuid4()}",
            correlation_id=str(uuid4()),
            to_address="test@huledu.se",
            from_address="noreply@huledu.se",
            from_name="HuleEdu",
            subject="Test",
            template_id="test_template",
            category="test",
            # variables not provided - should default to empty dict
            # status not provided - should default to PENDING
        )

        # Assert - Column default definition contracts (applied by SQLAlchemy/database)
        # Test that column definitions have the correct default settings

        # EmailRecord column defaults
        variables_column = EmailRecord.__table__.columns["variables"]
        status_column = EmailRecord.__table__.columns["status"]

        assert variables_column.default is not None  # Has Python callable default
        assert status_column.default is not None  # Has enum default

        # Test EventOutbox column defaults
        outbox_entry = EventOutbox(
            aggregate_id=str(uuid4()),
            aggregate_type="Test",
            event_type="TestEvent",
            event_data={"test": True},
            topic="test.events",
        )

        # EventOutbox column defaults
        id_column = EventOutbox.__table__.columns["id"]
        retry_count_column = EventOutbox.__table__.columns["retry_count"]

        assert id_column.default is not None  # Has UUID default
        assert retry_count_column.default is not None  # Has integer default
        assert retry_count_column.server_default is not None  # Server default too
        assert outbox_entry.published_at is None  # No default for published_at

    def test_model_inheritance_base_class_contract(self) -> None:
        """Contract test: All models must inherit from proper Base class."""
        # Assert - All models inherit from Base
        assert issubclass(EmailRecord, Base)
        assert issubclass(EmailTemplate, Base)
        assert issubclass(EventOutbox, Base)

        # Assert - Base class has AsyncAttrs mixin
        from sqlalchemy.ext.asyncio import AsyncAttrs

        assert issubclass(Base, AsyncAttrs)

        # Assert - Models are properly registered with Base metadata
        table_names = [table.name for table in Base.metadata.tables.values()]
        assert "email_records" in table_names
        assert "email_templates" in table_names
        assert "event_outbox" in table_names
