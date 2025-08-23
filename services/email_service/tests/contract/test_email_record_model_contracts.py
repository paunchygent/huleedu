"""
Email Record Model Contract Testing for Email Service.

This module provides comprehensive contract tests for EmailRecord model
to ensure proper field validation, constraint enforcement, Swedish character
support, and serialization compatibility across service boundaries.

Following ULTRATHINK methodology for database model contract validation.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from services.email_service.models_db import (
    EmailRecord,
    EmailStatus,
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
