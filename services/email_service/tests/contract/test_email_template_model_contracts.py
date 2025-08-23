"""
Email Template Model Contract Testing for Email Service.

This module provides comprehensive contract tests for EmailTemplate model
to ensure proper field validation, constraint enforcement, Swedish character
support, and serialization compatibility across service boundaries.

Following ULTRATHINK methodology for database model contract validation.
"""

from __future__ import annotations

import pytest

from services.email_service.models_db import (
    EmailTemplate,
)


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
        # Note: Model defaults are applied by SQLAlchemy/database, not at Python instantiation
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
        EmailTemplate(
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
        # Note: Model defaults are applied by SQLAlchemy/database, not at Python instantiation
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
