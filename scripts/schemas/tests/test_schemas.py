"""Tests for frontmatter schemas."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from scripts.schemas.docs_schema import (
    DecisionFrontmatter,
    EpicFrontmatter,
    RunbookFrontmatter,
)
from scripts.schemas.docs_schema import (
    get_allowed_values as docs_get_allowed_values,
)
from scripts.schemas.rule_schema import (
    RuleFrontmatter,
)
from scripts.schemas.rule_schema import (
    get_allowed_values as rule_get_allowed_values,
)
from scripts.schemas.task_schema import (
    TaskFrontmatter,
)
from scripts.schemas.task_schema import (
    get_allowed_values as task_get_allowed_values,
)


class TestTaskFrontmatter:
    """Tests for TaskFrontmatter schema."""

    @pytest.fixture
    def valid_task_data(self) -> dict:
        """Return valid task frontmatter data."""
        return {
            "id": "test-task",
            "title": "Test Task",
            "status": "research",
            "priority": "medium",
            "domain": "infrastructure",
            "owner_team": "agents",
            "created": date(2025, 12, 1),
            "last_updated": date(2025, 12, 1),
        }

    @pytest.mark.parametrize(
        "status",
        ["research", "blocked", "in_progress", "paused", "completed", "archived"],
    )
    def test_accepts_valid_statuses(self, valid_task_data: dict, status: str) -> None:
        """Should accept all valid status values."""
        valid_task_data["status"] = status
        fm = TaskFrontmatter(**valid_task_data)
        assert fm.status.value == status

    @pytest.mark.parametrize(
        "priority",
        ["low", "medium", "high", "critical"],
    )
    def test_accepts_valid_priorities(self, valid_task_data: dict, priority: str) -> None:
        """Should accept all valid priority values."""
        valid_task_data["priority"] = priority
        fm = TaskFrontmatter(**valid_task_data)
        assert fm.priority.value == priority

    @pytest.mark.parametrize(
        "domain",
        [
            "assessment",
            "content",
            "identity",
            "frontend",
            "infrastructure",
            "security",
            "integrations",
            "architecture",
            "programs",
        ],
    )
    def test_accepts_valid_domains(self, valid_task_data: dict, domain: str) -> None:
        """Should accept all valid domain values."""
        valid_task_data["domain"] = domain
        fm = TaskFrontmatter(**valid_task_data)
        assert fm.domain.value == domain

    def test_rejects_invalid_status(self, valid_task_data: dict) -> None:
        """Should reject invalid status values."""
        valid_task_data["status"] = "invalid_status"
        with pytest.raises(ValidationError):
            TaskFrontmatter(**valid_task_data)

    def test_requires_mandatory_fields(self) -> None:
        """Should require all mandatory fields."""
        with pytest.raises(ValidationError) as exc_info:
            TaskFrontmatter(id="test", title="Test")
        errors = exc_info.value.errors()
        missing_fields = {e["loc"][0] for e in errors if e["type"] == "missing"}
        assert "status" in missing_fields
        assert "priority" in missing_fields
        assert "domain" in missing_fields

    def test_allows_extra_fields(self, valid_task_data: dict) -> None:
        """Should allow extra fields (tolerant parsing)."""
        valid_task_data["extra_field"] = "extra_value"
        fm = TaskFrontmatter(**valid_task_data)
        assert fm.id == "test-task"

    def test_optional_fields_default_correctly(self, valid_task_data: dict) -> None:
        """Should set correct defaults for optional fields."""
        fm = TaskFrontmatter(**valid_task_data)
        assert fm.service == ""
        assert fm.owner == ""
        assert fm.program == ""
        assert fm.related == []
        assert fm.labels == []


class TestRuleFrontmatter:
    """Tests for RuleFrontmatter schema."""

    @pytest.fixture
    def valid_rule_data(self) -> dict:
        """Return valid rule frontmatter data."""
        return {
            "id": "020-architectural-mandates",
            "type": "architecture",
            "created": date(2025, 6, 1),
            "last_updated": date(2025, 11, 20),
            "scope": "all",
        }

    @pytest.mark.parametrize(
        "rule_type",
        [
            "service",
            "architecture",
            "implementation",
            "workflow",
            "testing",
            "observability",
            "standards",
            "operational",
            "library",
        ],
    )
    def test_accepts_valid_types(self, valid_rule_data: dict, rule_type: str) -> None:
        """Should accept all valid type values."""
        valid_rule_data["type"] = rule_type
        if rule_type == "service":
            valid_rule_data["service_name"] = "test_service"
        fm = RuleFrontmatter(**valid_rule_data)
        assert fm.type == rule_type

    @pytest.mark.parametrize(
        "scope",
        [
            "all",
            "backend",
            "frontend",
            "infrastructure",
            "cross-service",
            "testing",
            "documentation",
        ],
    )
    def test_accepts_valid_scopes(self, valid_rule_data: dict, scope: str) -> None:
        """Should accept all valid scope values."""
        valid_rule_data["scope"] = scope
        fm = RuleFrontmatter(**valid_rule_data)
        assert fm.scope == scope

    def test_rejects_invalid_id_format(self, valid_rule_data: dict) -> None:
        """Should reject IDs with invalid format."""
        valid_rule_data["id"] = "invalid_id"
        with pytest.raises(ValidationError):
            RuleFrontmatter(**valid_rule_data)

    def test_accepts_sub_rule_id_with_parent(self) -> None:
        """Should accept sub-rule ID when parent_rule is provided."""
        data = {
            "id": "020.7-cj-assessment-service",
            "type": "service",
            "created": date(2025, 6, 1),
            "last_updated": date(2025, 11, 20),
            "scope": "backend",
            "parent_rule": "020-architectural-mandates",
            "service_name": "cj_assessment_service",
        }
        fm = RuleFrontmatter(**data)
        assert fm.id == "020.7-cj-assessment-service"

    def test_rejects_sub_rule_without_parent(self) -> None:
        """Should reject sub-rule ID when parent_rule is missing."""
        data = {
            "id": "020.7-cj-assessment-service",
            "type": "architecture",
            "created": date(2025, 6, 1),
            "last_updated": date(2025, 11, 20),
            "scope": "backend",
        }
        with pytest.raises(ValidationError) as exc_info:
            RuleFrontmatter(**data)
        assert "must have parent_rule field" in str(exc_info.value)

    def test_service_type_requires_service_name(self, valid_rule_data: dict) -> None:
        """Should reject service type without service_name."""
        valid_rule_data["type"] = "service"
        with pytest.raises(ValidationError) as exc_info:
            RuleFrontmatter(**valid_rule_data)
        assert "must have service_name field" in str(exc_info.value)

    def test_last_updated_must_be_after_created(self, valid_rule_data: dict) -> None:
        """Should reject last_updated before created."""
        valid_rule_data["created"] = date(2025, 12, 1)
        valid_rule_data["last_updated"] = date(2025, 1, 1)
        with pytest.raises(ValidationError) as exc_info:
            RuleFrontmatter(**valid_rule_data)
        assert "cannot be before created" in str(exc_info.value)


class TestRunbookFrontmatter:
    """Tests for RunbookFrontmatter schema."""

    @pytest.fixture
    def valid_runbook_data(self) -> dict:
        """Return valid runbook frontmatter data."""
        return {
            "service": "essay_lifecycle_service",
            "severity": "high",
            "last_reviewed": date(2025, 11, 15),
        }

    @pytest.mark.parametrize("severity", ["low", "medium", "high", "critical"])
    def test_accepts_valid_severities(self, valid_runbook_data: dict, severity: str) -> None:
        """Should accept all valid severity values."""
        valid_runbook_data["severity"] = severity
        fm = RunbookFrontmatter(**valid_runbook_data)
        assert fm.severity == severity

    def test_default_type_is_runbook(self, valid_runbook_data: dict) -> None:
        """Should default type to 'runbook'."""
        fm = RunbookFrontmatter(**valid_runbook_data)
        assert fm.type == "runbook"

    def test_rejects_invalid_severity(self, valid_runbook_data: dict) -> None:
        """Should reject invalid severity values."""
        valid_runbook_data["severity"] = "extreme"
        with pytest.raises(ValidationError):
            RunbookFrontmatter(**valid_runbook_data)


class TestDecisionFrontmatter:
    """Tests for DecisionFrontmatter schema."""

    @pytest.fixture
    def valid_decision_data(self) -> dict:
        """Return valid decision frontmatter data."""
        return {
            "id": "0019",
            "status": "accepted",
            "created": date(2025, 11, 1),
            "last_updated": date(2025, 12, 1),
        }

    @pytest.mark.parametrize("status", ["proposed", "accepted", "superseded", "rejected"])
    def test_accepts_valid_statuses(self, valid_decision_data: dict, status: str) -> None:
        """Should accept all valid status values."""
        valid_decision_data["status"] = status
        fm = DecisionFrontmatter(**valid_decision_data)
        assert fm.status == status

    def test_default_type_is_decision(self, valid_decision_data: dict) -> None:
        """Should default type to 'decision'."""
        fm = DecisionFrontmatter(**valid_decision_data)
        assert fm.type == "decision"

    def test_rejects_invalid_id_format(self, valid_decision_data: dict) -> None:
        """Should reject ID not matching 4-digit pattern."""
        valid_decision_data["id"] = "19"  # too short
        with pytest.raises(ValidationError):
            DecisionFrontmatter(**valid_decision_data)


class TestEpicFrontmatter:
    """Tests for EpicFrontmatter schema."""

    @pytest.fixture
    def valid_epic_data(self) -> dict:
        """Return valid epic frontmatter data."""
        return {
            "id": "EPIC-007",
            "title": "Dev Tooling Script Consolidation",
            "status": "draft",
            "created": date(2025, 12, 1),
            "last_updated": date(2025, 12, 1),
        }

    @pytest.mark.parametrize("status", ["draft", "active", "completed", "cancelled"])
    def test_accepts_valid_statuses(self, valid_epic_data: dict, status: str) -> None:
        """Should accept all valid status values."""
        valid_epic_data["status"] = status
        fm = EpicFrontmatter(**valid_epic_data)
        assert fm.status == status

    def test_default_type_is_epic(self, valid_epic_data: dict) -> None:
        """Should default type to 'epic'."""
        fm = EpicFrontmatter(**valid_epic_data)
        assert fm.type == "epic"

    def test_rejects_invalid_id_format(self, valid_epic_data: dict) -> None:
        """Should reject ID not matching EPIC-NNN pattern."""
        valid_epic_data["id"] = "EPIC-7"  # too short
        with pytest.raises(ValidationError):
            EpicFrontmatter(**valid_epic_data)

    def test_optional_fields_default_to_none(self, valid_epic_data: dict) -> None:
        """Should default optional fields to None."""
        fm = EpicFrontmatter(**valid_epic_data)
        assert fm.phase is None
        assert fm.sprint_target is None


class TestGetAllowedValues:
    """Tests for get_allowed_values() helpers."""

    def test_task_get_allowed_values(self) -> None:
        """Should return correct allowed values for task schema."""
        values = task_get_allowed_values()
        assert "status" in values
        assert "priority" in values
        assert "domain" in values
        assert "type" in values
        assert "research" in values["status"]
        assert "critical" in values["priority"]

    def test_rule_get_allowed_values(self) -> None:
        """Should return correct allowed values for rule schema."""
        values = rule_get_allowed_values()
        assert "type" in values
        assert "scope" in values
        assert "architecture" in values["type"]
        assert "backend" in values["scope"]

    def test_docs_get_allowed_values(self) -> None:
        """Should return correct allowed values for docs schema."""
        values = docs_get_allowed_values()
        assert "runbook_severity" in values
        assert "decision_status" in values
        assert "epic_status" in values
        assert "critical" in values["runbook_severity"]
        assert "accepted" in values["decision_status"]
        assert "draft" in values["epic_status"]
