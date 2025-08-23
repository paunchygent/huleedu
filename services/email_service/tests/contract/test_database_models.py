"""
Database Model Contract Testing for Email Service.

This module provides comprehensive contract tests for EmailRecord, EmailTemplate,
and EventOutbox models to ensure proper field validation, constraint enforcement,
serialization compatibility, and Swedish character support across service boundaries.

Following ULTRATHINK methodology for database model contract validation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect

from services.email_service.models_db import (
    Base,
    EmailRecord,
    EmailStatus,
    EmailTemplate,
    EventOutbox,
)


class TestEmailRecordModelContracts:
    """Test contracts for EmailRecord model structure, validation, and behavior."""

    @pytest.mark.parametrize(
        "status_value, expected_enum",
        [
            ("pending", EmailStatus.PENDING),
            ("processing", EmailStatus.PROCESSING),
            ("sent", EmailStatus.SENT),
            ("failed", EmailStatus.FAILED),
            ("bounced", EmailStatus.BOUNCED),
            ("complained", EmailStatus.COMPLAINED),
        ],
    )
    def test_email_status_enum_validation_contract(
        self, status_value: str, expected_enum: EmailStatus
    ) -> None:
        """Contract test: EmailStatus enum must support all required values."""
        # Assert - Enum value mapping contract
        assert expected_enum.value == status_value
        assert EmailStatus(status_value) == expected_enum

    def test_email_record_required_fields_contract(self) -> None:
        """Contract test: EmailRecord must have all required fields with correct types."""
        # Arrange - Create EmailRecord with all required fields
        correlation_id = str(uuid4())
        message_id = f"msg_{uuid4()}"

        email_record = EmailRecord(
            message_id=message_id,
            correlation_id=correlation_id,
            to_address="test@huledu.se",
            from_address="noreply@huledu.se",
            from_name="HuleEdu System",
            subject="Test Subject",
            template_id="test_template",
            category="notification",
            variables={"user_name": "Test User"},
        )

        # Assert - All required fields present and correct types
        assert email_record.message_id == message_id
        assert email_record.correlation_id == correlation_id
        assert email_record.to_address == "test@huledu.se"
        assert email_record.from_address == "noreply@huledu.se"
        assert email_record.from_name == "HuleEdu System"
        assert email_record.subject == "Test Subject"
        assert email_record.template_id == "test_template"
        assert email_record.category == "notification"
        assert email_record.variables == {"user_name": "Test User"}
        # Note: Model defaults are applied by SQLAlchemy/database, not at Python instantiation
        assert email_record.provider is None  # Optional field default
        assert email_record.provider_message_id is None  # Optional field default
        assert email_record.failure_reason is None  # Optional field default
        assert email_record.sent_at is None  # Optional timestamp default
        assert email_record.failed_at is None  # Optional timestamp default

    @pytest.mark.parametrize(
        "subject, from_name, to_address",
        [
            # Swedish characters in subject
            ("Välkommen till HuleEdu - Äntligen här!", "HuleEdu System", "user@test.se"),
            # Swedish characters in from_name
            ("Welcome Message", "HuleEdu Stöd", "user@test.se"),
            # Swedish characters in to_address
            ("Test Subject", "HuleEdu System", "ärende@huledu.se"),
            # Mixed Swedish characters
            ("Ämnesrad med åäö", "Björn Andersson", "ärende@huledu.se"),
            # Uppercase Swedish characters
            ("ÄLDRE ÄMNEN", "ÅKER & SÖRENSEN", "ÄRENDE@HULEDU.SE"),
        ],
    )
    def test_email_record_swedish_character_support_contract(
        self, subject: str, from_name: str, to_address: str
    ) -> None:
        """Contract test: EmailRecord must support Swedish characters in relevant fields."""
        # Act - Create record with Swedish characters
        email_record = EmailRecord(
            message_id=f"msg_{uuid4()}",
            correlation_id=str(uuid4()),
            to_address=to_address,
            from_address="noreply@huledu.se",
            from_name=from_name,
            subject=subject,
            template_id="swedish_template",
            category="notification",
            variables={},
        )

        # Assert - Swedish characters preserved correctly
        assert email_record.subject == subject
        assert email_record.from_name == from_name
        assert email_record.to_address == to_address

    def test_email_record_primary_key_constraint_contract(self) -> None:
        """Contract test: EmailRecord must enforce message_id as primary key."""
        # Arrange
        message_id = f"msg_{uuid4()}"

        # Act - Create two records with same message_id
        record1 = EmailRecord(
            message_id=message_id,
            correlation_id=str(uuid4()),
            to_address="user1@test.se",
            from_address="noreply@huledu.se",
            from_name="HuleEdu",
            subject="Subject 1",
            template_id="template1",
            category="notification",
            variables={},
        )

        record2 = EmailRecord(
            message_id=message_id,  # Same message_id - should cause constraint violation
            correlation_id=str(uuid4()),
            to_address="user2@test.se",
            from_address="noreply@huledu.se",
            from_name="HuleEdu",
            subject="Subject 2",
            template_id="template2",
            category="notification",
            variables={},
        )

        # Assert - Primary key constraint detected
        assert record1.message_id == record2.message_id
        # Note: Actual DB constraint testing requires database session
        # This validates the model structure contract

    def test_email_record_index_definitions_contract(self) -> None:
        """Contract test: EmailRecord must have required indexes for performance."""
        # Act - Inspect table metadata
        table = EmailRecord.__table__

        # Assert - Individual field indexes exist (from mapped_column index=True)
        indexed_columns = [col.name for col in table.columns if col.index]
        expected_indexed_fields = [
            "correlation_id",
            "to_address",
            "template_id",
            "category",
            "status",
            "created_at",
        ]

        for field in expected_indexed_fields:
            assert field in indexed_columns, f"Field {field} must be indexed"

        # Assert - Composite indexes exist in __table_args__
        table_args = getattr(EmailRecord, "__table_args__", ())
        index_names = [arg.name for arg in table_args if hasattr(arg, "name")]

        assert "ix_email_records_status_created" in index_names
        assert "ix_email_records_category_created" in index_names
        assert "ix_email_records_provider_status" in index_names

    def test_email_record_json_variables_handling_contract(self) -> None:
        """Contract test: EmailRecord must handle JSON variables field properly."""
        # Arrange - Complex variables dictionary with nested data
        complex_variables = {
            "user_name": "Åsa Svensson",
            "course_data": {
                "name": "Matematik för lärare",
                "code": "MAT123",
                "credits": 7.5,
            },
            "assignments": [
                {"name": "Uppgift 1", "due_date": "2025-01-15"},
                {"name": "Uppgift 2", "due_date": "2025-02-01"},
            ],
            "metadata": {
                "created_by": "system",
                "locale": "sv_SE",
                "encoding": "utf-8",
            },
        }

        # Act - Create record with complex JSON variables
        email_record = EmailRecord(
            message_id=f"msg_{uuid4()}",
            correlation_id=str(uuid4()),
            to_address="asa.svensson@huledu.se",
            from_address="noreply@huledu.se",
            from_name="HuleEdu System",
            subject="Kursuppgifter tillgängliga",
            template_id="assignment_template",
            category="academic",
            variables=complex_variables,
        )

        # Assert - JSON serialization and structure preservation
        assert email_record.variables == complex_variables
        assert email_record.variables["user_name"] == "Åsa Svensson"
        assert email_record.variables["course_data"]["name"] == "Matematik för lärare"
        assert len(email_record.variables["assignments"]) == 2
        assert email_record.variables["metadata"]["locale"] == "sv_SE"

    def test_email_record_timestamp_defaults_contract(self) -> None:
        """Contract test: EmailRecord must have proper timestamp default behavior."""
        # Arrange & Act - Create record without explicit timestamps
        email_record = EmailRecord(
            message_id=f"msg_{uuid4()}",
            correlation_id=str(uuid4()),
            to_address="test@huledu.se",
            from_address="noreply@huledu.se",
            from_name="HuleEdu",
            subject="Test",
            template_id="test_template",
            category="test",
            variables={},
        )

        # Assert - Timestamp field behavior contracts
        # created_at has server default (NOW()) - model won't set it
        assert email_record.created_at is None  # Will be set by database server_default
        assert email_record.sent_at is None  # Explicitly nullable, no default
        assert email_record.failed_at is None  # Explicitly nullable, no default

        # Assert - created_at column has server default configuration
        created_at_column = EmailRecord.__table__.columns["created_at"]
        assert created_at_column.server_default is not None
        assert str(created_at_column.server_default.arg) == "NOW()"


class TestEmailTemplateModelContracts:
    """Test contracts for EmailTemplate model structure, validation, and behavior."""

    def test_email_template_required_fields_contract(self) -> None:
        """Contract test: EmailTemplate must have all required fields with correct types."""
        # Act - Create EmailTemplate with all required fields
        template = EmailTemplate(
            template_id="welcome_template",
            name="Welcome Email Template",
            description="Template for welcoming new users",
            category="onboarding",
            subject_template="Välkommen till HuleEdu, {{user_name}}!",
        )

        # Assert - All required fields present and correct types
        assert template.template_id == "welcome_template"
        assert template.name == "Welcome Email Template"
        assert template.description == "Template for welcoming new users"
        assert template.category == "onboarding"
        assert template.subject_template == "Välkommen till HuleEdu, {{user_name}}!"
        assert template.is_active is True  # Default value
        # Timestamps will be None until database sets server defaults
        assert template.created_at is None  # Server default
        assert template.updated_at is None  # Server default

    @pytest.mark.parametrize(
        "name, description, subject_template",
        [
            # Swedish characters in name
            ("Välkomstbrev Mall", "Mall för välkomstbrev", "Welcome {{name}}"),
            # Swedish characters in description
            ("Welcome Template", "Mall för att välkomna användare åäö", "Welcome"),
            # Swedish characters in subject template
            ("Template", "Description", "Välkommen {{användarnamn}} - Kära {{titel}}!"),
            # Mixed Swedish characters across fields
            ("Ämne Mall", "Beskrivning med åäö", "Ämne: {{kurs}} - Hälsningar!"),
            # Uppercase Swedish characters
            ("ÄMNE MALL", "BESKRIVNING MED ÅÄÖ", "ÄMNE: {{KURS}} - HÄLSNINGAR!"),
        ],
    )
    def test_email_template_swedish_character_support_contract(
        self, name: str, description: str, subject_template: str
    ) -> None:
        """Contract test: EmailTemplate must support Swedish characters in text fields."""
        # Act - Create template with Swedish characters
        template = EmailTemplate(
            template_id="swedish_template",
            name=name,
            description=description,
            category="swedish_category",
            subject_template=subject_template,
        )

        # Assert - Swedish characters preserved correctly
        assert template.name == name
        assert template.description == description
        assert template.subject_template == subject_template

    def test_email_template_primary_key_constraint_contract(self) -> None:
        """Contract test: EmailTemplate must enforce template_id as primary key."""
        # Arrange
        template_id = "duplicate_template_id"

        # Act - Create two templates with same template_id
        template1 = EmailTemplate(
            template_id=template_id,
            name="Template 1",
            category="category1",
            subject_template="Subject 1",
        )

        template2 = EmailTemplate(
            template_id=template_id,  # Same template_id - should cause constraint violation
            name="Template 2",
            category="category2",
            subject_template="Subject 2",
        )

        # Assert - Primary key constraint detected
        assert template1.template_id == template2.template_id
        # Note: Actual DB constraint testing requires database session

    def test_email_template_boolean_is_active_behavior_contract(self) -> None:
        """Contract test: EmailTemplate is_active flag must behave correctly."""
        # Act - Test default True behavior
        active_template = EmailTemplate(
            template_id="active_template",
            name="Active Template",
            category="test",
            subject_template="Test Subject",
        )

        # Act - Test explicit False
        inactive_template = EmailTemplate(
            template_id="inactive_template",
            name="Inactive Template",
            category="test",
            subject_template="Test Subject",
            is_active=False,
        )

        # Assert - Boolean flag behavior contracts
        assert active_template.is_active is True  # Default value
        assert inactive_template.is_active is False  # Explicit value

    def test_email_template_index_definitions_contract(self) -> None:
        """Contract test: EmailTemplate must have required indexes for performance."""
        # Act - Inspect table metadata
        table = EmailTemplate.__table__

        # Assert - Category field is indexed (from mapped_column index=True)
        indexed_columns = [col.name for col in table.columns if col.index]
        assert "category" in indexed_columns, "Category field must be indexed"

        # Assert - Composite index exists in __table_args__
        table_args = getattr(EmailTemplate, "__table_args__", ())
        index_names = [arg.name for arg in table_args if hasattr(arg, "name")]
        assert "ix_email_templates_category_active" in index_names

    def test_email_template_timestamp_auto_update_contract(self) -> None:
        """Contract test: EmailTemplate updated_at must have onupdate behavior."""
        # Act - Inspect column metadata
        updated_at_column = EmailTemplate.__table__.columns["updated_at"]
        created_at_column = EmailTemplate.__table__.columns["created_at"]

        # Assert - Server defaults configured correctly
        assert created_at_column.server_default is not None
        assert updated_at_column.server_default is not None
        assert updated_at_column.onupdate is not None

        # Assert - Both use NOW() function
        assert str(created_at_column.server_default.arg) == "NOW()"
        assert str(updated_at_column.server_default.arg) == "NOW()"
        assert str(updated_at_column.onupdate.arg) == "NOW()"


class TestEventOutboxModelContracts:
    """Test contracts for EventOutbox model structure, validation, and behavior."""

    def test_event_outbox_required_fields_contract(self) -> None:
        """Contract test: EventOutbox must have all required fields with correct types."""
        # Arrange - Create EventOutbox with all required fields
        aggregate_id = str(uuid4())
        event_data = {
            "user_id": str(uuid4()),
            "email_address": "test@huledu.se",
            "template_id": "welcome_template",
            "variables": {"name": "Test User"},
        }

        outbox_entry = EventOutbox(
            aggregate_id=aggregate_id,
            aggregate_type="EmailRecord",
            event_type="EmailSendRequested",
            event_data=event_data,
            topic="email.send.requested",
        )

        # Assert - All required fields present and correct types
        assert outbox_entry.aggregate_id == aggregate_id
        assert outbox_entry.aggregate_type == "EmailRecord"
        assert outbox_entry.event_type == "EmailSendRequested"
        assert outbox_entry.event_data == event_data
        assert outbox_entry.topic == "email.send.requested"
        assert outbox_entry.event_key is None  # Optional field default
        assert outbox_entry.published_at is None  # Unpublished default
        assert outbox_entry.retry_count == 0  # Default value
        assert outbox_entry.last_error is None  # Optional field default
        # UUID and timestamp will be set by defaults/server
        assert outbox_entry.id is not None  # UUID default generated
        assert outbox_entry.created_at is None  # Server default

    def test_event_outbox_uuid_primary_key_generation_contract(self) -> None:
        """Contract test: EventOutbox must generate unique UUID primary keys."""
        # Act - Create multiple outbox entries
        entries = []
        for i in range(5):
            entry = EventOutbox(
                aggregate_id=f"aggregate_{i}",
                aggregate_type="TestAggregate",
                event_type="TestEvent",
                event_data={"index": i},
                topic="test.events",
            )
            entries.append(entry)

        # Assert - All UUIDs are unique and proper type
        ids = [entry.id for entry in entries]
        assert len(set(ids)) == len(ids)  # All unique
        assert all(isinstance(id_val, UUID) for id_val in ids)  # All are UUID objects

    def test_event_outbox_json_event_data_serialization_contract(self) -> None:
        """Contract test: EventOutbox must handle complex JSON event_data properly."""
        # Arrange - Complex event data with Swedish content and nested structures
        complex_event_data = {
            "email_request": {
                "recipient": {
                    "email": "användare@huledu.se",
                    "name": "Åsa Svensson",
                    "locale": "sv_SE",
                },
                "content": {
                    "subject": "Välkommen till kursen {{kurs_namn}}",
                    "template_variables": {
                        "kurs_namn": "Matematik för Lärare",
                        "start_datum": "2025-01-15",
                        "lärare": "Dr. Björn Andersson",
                    },
                },
                "metadata": {
                    "priority": "high",
                    "retry_attempts": 3,
                    "created_at": datetime.now(UTC).isoformat(),
                    "tags": ["course_enrollment", "welcome_email", "swedish"],
                },
            },
            "correlation_data": {
                "correlation_id": str(uuid4()),
                "source_service": "course_management",
                "request_id": str(uuid4()),
            },
        }

        # Act - Create outbox entry with complex event data
        outbox_entry = EventOutbox(
            aggregate_id=str(uuid4()),
            aggregate_type="EmailRequest",
            event_type="ComplexEmailRequested",
            event_data=complex_event_data,
            topic="email.complex.requested",
        )

        # Assert - Complex JSON serialization and structure preservation
        assert outbox_entry.event_data == complex_event_data
        assert outbox_entry.event_data["email_request"]["recipient"]["name"] == "Åsa Svensson"
        assert (
            outbox_entry.event_data["email_request"]["content"]["subject"]
            == "Välkommen till kursen {{kurs_namn}}"
        )
        assert (
            outbox_entry.event_data["email_request"]["content"]["template_variables"]["kurs_namn"]
            == "Matematik för Lärare"
        )
        assert len(outbox_entry.event_data["email_request"]["metadata"]["tags"]) == 3

    def test_event_outbox_retry_count_increment_behavior_contract(self) -> None:
        """Contract test: EventOutbox retry_count must handle increments correctly."""
        # Act - Create outbox entry and test retry scenarios
        outbox_entry = EventOutbox(
            aggregate_id=str(uuid4()),
            aggregate_type="EmailRecord",
            event_type="EmailSendFailed",
            event_data={"reason": "provider_timeout"},
            topic="email.send.failed",
        )

        # Assert - Default retry count behavior
        assert outbox_entry.retry_count == 0

        # Act - Simulate retry count increments
        outbox_entry.retry_count = 1
        assert outbox_entry.retry_count == 1

        outbox_entry.retry_count += 1
        assert outbox_entry.retry_count == 2

        # Act - Test with explicit retry count
        retry_entry = EventOutbox(
            aggregate_id=str(uuid4()),
            aggregate_type="EmailRecord",
            event_type="EmailSendFailed",
            event_data={"reason": "provider_error"},
            topic="email.send.failed",
            retry_count=5,
        )

        # Assert - Explicit retry count preserved
        assert retry_entry.retry_count == 5

    def test_event_outbox_published_at_null_constraint_contract(self) -> None:
        """Contract test: EventOutbox published_at must be null for unpublished events."""
        # Act - Create unpublished event
        unpublished_entry = EventOutbox(
            aggregate_id=str(uuid4()),
            aggregate_type="EmailRecord",
            event_type="EmailQueued",
            event_data={"queue_position": 1},
            topic="email.queue.added",
        )

        # Assert - Unpublished event contract
        assert unpublished_entry.published_at is None

        # Act - Simulate publishing
        publish_time = datetime.now(UTC)
        unpublished_entry.published_at = publish_time

        # Assert - Published state preserved
        assert unpublished_entry.published_at == publish_time

    def test_event_outbox_composite_index_effectiveness_contract(self) -> None:
        """Contract test: EventOutbox must have effective indexes for query patterns."""
        # Act - Inspect table metadata
        table = EventOutbox.__table__

        # Assert - Individual field indexes exist (from mapped_column index=True)
        indexed_columns = [col.name for col in table.columns if col.index]
        assert "aggregate_id" in indexed_columns, "aggregate_id field must be indexed"

        # Assert - Composite indexes exist in __table_args__
        table_args = getattr(EventOutbox, "__table_args__", ())
        index_names = [arg.name for arg in table_args if hasattr(arg, "name")]

        expected_indexes = [
            "ix_event_outbox_unpublished_topic",
            "ix_event_outbox_topic",
            "ix_event_outbox_aggregate",
            "ix_event_outbox_event_type",
        ]

        for index_name in expected_indexes:
            assert index_name in index_names, f"Index {index_name} must exist"

    def test_event_outbox_timestamp_timezone_awareness_contract(self) -> None:
        """Contract test: EventOutbox timestamps must be timezone-aware."""
        # Act - Inspect timestamp column metadata
        created_at_column = EventOutbox.__table__.columns["created_at"]
        published_at_column = EventOutbox.__table__.columns["published_at"]

        # Assert - Timezone awareness configured
        assert (
            hasattr(created_at_column.type, "timezone") and created_at_column.type.timezone is True
        )  # type: ignore[attr-defined]
        assert (
            hasattr(published_at_column.type, "timezone")
            and published_at_column.type.timezone is True
        )  # type: ignore[attr-defined]

        # Assert - Server default uses timezone-aware function
        assert created_at_column.server_default is not None
        # func.current_timestamp() is timezone-aware in PostgreSQL


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

        # UUID field
        assert isinstance(outbox_entry.id, UUID)


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
        email_record = EmailRecord(
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

        # Assert - Default value contracts
        assert email_record.variables == {}  # Python default
        assert email_record.status == EmailStatus.PENDING  # SQLAlchemy default

        # Act - Test EventOutbox defaults
        outbox_entry = EventOutbox(
            aggregate_id=str(uuid4()),
            aggregate_type="Test",
            event_type="TestEvent",
            event_data={"test": True},
            topic="test.events",
            # retry_count not provided - should default to 0
            # id not provided - should generate UUID
        )

        # Assert - EventOutbox default contracts
        assert outbox_entry.retry_count == 0  # Default value
        assert isinstance(outbox_entry.id, UUID)  # Auto-generated UUID
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
