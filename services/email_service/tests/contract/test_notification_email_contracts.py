"""
Notification Email Request Event Contract Testing for Email Service.

This module provides comprehensive contract tests for NotificationEmailRequestedV1 events
to ensure proper serialization, template variable validation, and Swedish character
handling in the HuleEdu platform's notification system.

Following ULTRATHINK methodology for notification event schema validation.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from common_core.emailing_models import NotificationEmailRequestedV1
from pydantic import ValidationError


class TestNotificationEmailRequestedV1Contracts:
    """Contract tests for NotificationEmailRequestedV1 event schema and validation."""

    def test_notification_email_requested_required_fields_contract(self) -> None:
        """Contract test: NotificationEmailRequestedV1 must have all required fields."""
        # Arrange
        correlation_id = str(uuid4())

        # Act - Create NotificationEmailRequestedV1 with all required fields
        event = NotificationEmailRequestedV1(
            message_id="notification-001",
            template_id="welcome_teacher",
            to="teacher@school.se",
            variables={"teacher_name": "Anna Lindström", "school": "Björkskolan"},
            category="teacher_notification",
            correlation_id=correlation_id,
        )

        # Assert - All required fields present and correct types
        assert event.message_id == "notification-001"
        assert event.template_id == "welcome_teacher"
        assert event.to == "teacher@school.se"
        assert event.variables == {"teacher_name": "Anna Lindström", "school": "Björkskolan"}
        assert event.category == "teacher_notification"
        assert event.correlation_id == correlation_id

    @pytest.mark.parametrize(
        "template_variables, expected_variables",
        [
            # Empty variables (default)
            ({}, {}),
            # Swedish educational context variables with special characters
            (
                {"student_name": "Åsa Öhman", "class": "7A", "subject": "Matematik"},
                {"student_name": "Åsa Öhman", "class": "7A", "subject": "Matematik"},
            ),
            (
                {"teacher_name": "Erik Ångström", "school_name": "Älvsjö Grundskola"},
                {"teacher_name": "Erik Ångström", "school_name": "Älvsjö Grundskola"},
            ),
            # Complex template variables
            (
                {
                    "assignment_title": "Språkanalys: Årstider på svenska",
                    "due_date": "2024-09-15",
                    "instructions": "Skriv en uppsats om höstens färger i naturen",
                    "teacher_email": "svenska.lärare@skola.se",
                },
                {
                    "assignment_title": "Språkanalys: Årstider på svenska",
                    "due_date": "2024-09-15",
                    "instructions": "Skriv en uppsats om höstens färger i naturen",
                    "teacher_email": "svenska.lärare@skola.se",
                },
            ),
            # Password reset context
            (
                {
                    "reset_token": "abc123xyz789",
                    "user_name": "Märta Öberg",
                    "expires_in": "24 timmar",
                },
                {
                    "reset_token": "abc123xyz789",
                    "user_name": "Märta Öberg",
                    "expires_in": "24 timmar",
                },
            ),
        ],
    )
    def test_notification_email_template_variables_swedish_contract(
        self, template_variables: dict[str, str], expected_variables: dict[str, str]
    ) -> None:
        """Contract: template variables with Swedish characters.

        Ensures NotificationEmailRequestedV1 preserves åäö characters.
        """
        correlation_id = str(uuid4())

        # Act
        event = NotificationEmailRequestedV1(
            message_id="swedish-vars-test",
            template_id="test_template",
            to="test@example.se",
            variables=template_variables,
            category="system",
            correlation_id=correlation_id,
        )

        # Assert - Template variables preserved including Swedish characters
        assert event.variables == expected_variables

    @pytest.mark.parametrize(
        "category",
        [
            "verification",
            "password_reset",
            "receipt",
            "teacher_notification",
            "system",
        ],
    )
    def test_notification_email_category_enum_contract(self, category: str) -> None:
        """Contract test: NotificationEmailRequestedV1 category enum constraint validation."""
        correlation_id = str(uuid4())

        # Act
        event = NotificationEmailRequestedV1(
            message_id="category-test",
            template_id="test_template",
            to="test@example.com",
            variables={},
            category=category,  # type: ignore[arg-type] # testing literal constraint
            correlation_id=correlation_id,
        )

        # Assert - Category accepted and preserved
        assert event.category == category

    def test_notification_email_category_invalid_contract(self) -> None:
        """Contract test: NotificationEmailRequestedV1 must reject invalid categories."""
        correlation_id = str(uuid4())

        # Act & Assert - Invalid category should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            NotificationEmailRequestedV1(
                message_id="invalid-category-test",
                template_id="test_template",
                to="test@example.com",
                variables={},
                category="invalid_category",  # type: ignore[arg-type] # intentionally invalid
                correlation_id=correlation_id,
            )

        # Assert - Validation error contains category constraint information
        error_details = str(exc_info.value)
        assert "category" in error_details.lower()

    @pytest.mark.parametrize(
        "email_address",
        [
            # Valid Swedish educational email addresses
            "student@skola.se",
            "lärare.matematik@grundskola.se",
            "anna.öhman@högstadiet.se",
            "erik.ångström@gymnasium.se",
            "test+tag@universitetet.se",
            # International formats
            "teacher@international-school.edu",
            "admin@school.org",
        ],
    )
    def test_notification_email_emailstr_validation_contract(self, email_address: str) -> None:
        """Contract test: NotificationEmailRequestedV1 EmailStr field validation."""
        correlation_id = str(uuid4())

        # Act
        event = NotificationEmailRequestedV1(
            message_id="email-validation-test",
            template_id="test_template",
            to=email_address,
            variables={},
            category="system",
            correlation_id=correlation_id,
        )

        # Assert - Email address validated and preserved
        assert event.to == email_address

    def test_notification_email_variable_dict_serialization_contract(self) -> None:
        """Contract test: NotificationEmailRequestedV1 variables dict JSON serialization."""
        # Arrange - Complex variables with Swedish characters
        correlation_id = str(uuid4())
        complex_variables = {
            "student_name": "Åse Öhrn",
            "assignment_title": "Naturvetenskap - Årstidernas påverkan",
            "teacher_comment": "Bra arbete! Fortsätt så här.",
            "grade": "VG",
            "submission_date": "2024-08-23",
            "school_year": "2024/2025",
        }

        event = NotificationEmailRequestedV1(
            message_id="dict-serialization-test",
            template_id="assignment_feedback",
            to="student@school.se",
            variables=complex_variables,
            category="teacher_notification",
            correlation_id=correlation_id,
        )

        # Act - JSON round-trip serialization
        json_str = event.model_dump_json()
        json_dict = json.loads(json_str)
        deserialized = NotificationEmailRequestedV1.model_validate(json_dict)

        # Assert - Variables dictionary perfectly preserved
        assert deserialized.variables == complex_variables
        assert deserialized.variables["student_name"] == "Åse Öhrn"
        assert deserialized.variables["assignment_title"] == "Naturvetenskap - Årstidernas påverkan"
        assert deserialized == event
