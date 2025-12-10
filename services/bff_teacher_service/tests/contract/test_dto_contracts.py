"""
BFF Teacher DTO Contract Testing.

Validates TeacherBatchItemV1 and TeacherDashboardResponseV1 DTOs
for proper serialization, field validation, and frontend contract compliance.

Following ULTRATHINK methodology for DTO schema validation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_core.status_enums import BatchClientStatus

from services.bff_teacher_service.dto.teacher_v1 import (
    TeacherBatchItemV1,
    TeacherDashboardResponseV1,
)


class TestTeacherBatchItemV1Contract:
    """Contract tests for TeacherBatchItemV1 DTO."""

    def test_required_fields_contract(self) -> None:
        """Contract: TeacherBatchItemV1 must have all required fields."""
        # Arrange
        batch_id = str(uuid4())
        created_at = datetime.now(UTC)

        # Act - Create with minimum required fields
        item = TeacherBatchItemV1(
            batch_id=batch_id,
            status=BatchClientStatus.PROCESSING,
            created_at=created_at,
        )

        # Assert - Required fields present with correct types
        assert item.batch_id == batch_id
        assert item.status == BatchClientStatus.PROCESSING
        assert item.created_at == created_at
        # Defaults applied
        assert item.title == "Untitled Batch"
        assert item.class_name is None
        assert item.total_essays == 0
        assert item.completed_essays == 0

    @pytest.mark.parametrize("status", list(BatchClientStatus))
    def test_all_status_values_contract(self, status: BatchClientStatus) -> None:
        """Contract: All BatchClientStatus enum values must be accepted."""
        # Act
        item = TeacherBatchItemV1(
            batch_id=str(uuid4()),
            status=status,
            created_at=datetime.now(UTC),
        )

        # Assert
        assert item.status == status
        assert item.status.value in [
            "pending_content",
            "ready",
            "processing",
            "completed_successfully",
            "completed_with_failures",
            "failed",
            "cancelled",
        ]

    def test_class_name_nullable_contract(self) -> None:
        """Contract: class_name can be null (batch without class association)."""
        # Act - Explicit null
        item_null = TeacherBatchItemV1(
            batch_id=str(uuid4()),
            class_name=None,
            status=BatchClientStatus.READY,
            created_at=datetime.now(UTC),
        )

        # Act - With class name
        item_with_class = TeacherBatchItemV1(
            batch_id=str(uuid4()),
            class_name="Class 9A - English",
            status=BatchClientStatus.READY,
            created_at=datetime.now(UTC),
        )

        # Assert
        assert item_null.class_name is None
        assert item_with_class.class_name == "Class 9A - English"

    def test_datetime_serialization_contract(self) -> None:
        """Contract: created_at must serialize with timezone info (ISO 8601)."""
        # Arrange - Create with timezone-aware datetime
        created_at = datetime.now(UTC)
        item = TeacherBatchItemV1(
            batch_id=str(uuid4()),
            status=BatchClientStatus.PROCESSING,
            created_at=created_at,
        )

        # Act - Serialize to JSON
        json_str = item.model_dump_json()
        parsed = json.loads(json_str)

        # Assert - ISO format with timezone
        assert "created_at" in parsed
        # Should end with Z (UTC) or have offset
        assert parsed["created_at"].endswith("Z") or "+" in parsed["created_at"]

        # Assert - Round-trip preservation
        deserialized = TeacherBatchItemV1.model_validate_json(json_str)
        assert deserialized.created_at == created_at

    def test_json_roundtrip_contract(self) -> None:
        """Contract: TeacherBatchItemV1 must serialize/deserialize perfectly via JSON."""
        # Arrange
        original = TeacherBatchItemV1(
            batch_id=str(uuid4()),
            title="Hamlet Essay Analysis",
            class_name="Class 9A",
            status=BatchClientStatus.COMPLETED_SUCCESSFULLY,
            total_essays=25,
            completed_essays=25,
            created_at=datetime.now(UTC),
        )

        # Act - Full JSON round-trip
        json_str = original.model_dump_json()
        json_dict = json.loads(json_str)
        deserialized = TeacherBatchItemV1.model_validate(json_dict)

        # Assert - Perfect round-trip
        assert deserialized == original
        assert deserialized.batch_id == original.batch_id
        assert deserialized.title == original.title
        assert deserialized.class_name == original.class_name
        assert deserialized.status == original.status
        assert deserialized.total_essays == original.total_essays
        assert deserialized.completed_essays == original.completed_essays
        assert deserialized.created_at == original.created_at

    def test_default_title_contract(self) -> None:
        """Contract: title defaults to 'Untitled Batch' when not provided."""
        # Act - Without title
        item = TeacherBatchItemV1(
            batch_id=str(uuid4()),
            status=BatchClientStatus.PENDING_CONTENT,
            created_at=datetime.now(UTC),
        )

        # Assert
        assert item.title == "Untitled Batch"

    @pytest.mark.parametrize(
        "title, class_name",
        [
            # Swedish characters
            ("Uppsats om Astrid Lindgren", "Klass 9Å - Svenska"),
            ("Övning i grammatik", "Årskurs 8Ö"),
            # Special characters
            ("Essay #1: Analysis", "Class A/B"),
            ("Test & Practice", None),
            # Long title
            ("A" * 200, "Class"),
        ],
    )
    def test_string_field_preservation_contract(self, title: str, class_name: str | None) -> None:
        """Contract: String fields must preserve exact content including special chars."""
        # Act
        item = TeacherBatchItemV1(
            batch_id=str(uuid4()),
            title=title,
            class_name=class_name,
            status=BatchClientStatus.READY,
            created_at=datetime.now(UTC),
        )

        # Assert - Direct preservation
        assert item.title == title
        assert item.class_name == class_name

        # Assert - JSON round-trip preservation
        json_str = item.model_dump_json()
        deserialized = TeacherBatchItemV1.model_validate_json(json_str)
        assert deserialized.title == title
        assert deserialized.class_name == class_name


class TestTeacherDashboardResponseV1Contract:
    """Contract tests for TeacherDashboardResponseV1 DTO."""

    def test_empty_batches_valid_contract(self) -> None:
        """Contract: Empty batches list is valid (new user with no batches)."""
        # Act
        response = TeacherDashboardResponseV1(
            batches=[],
            total_count=0,
        )

        # Assert
        assert response.batches == []
        assert response.total_count == 0

    def test_pagination_fields_present_contract(self) -> None:
        """Contract: Response must include pagination metadata."""
        # Act
        response = TeacherDashboardResponseV1(
            batches=[],
            total_count=100,
            limit=20,
            offset=40,
        )

        # Assert - Pagination fields present in serialized output
        json_dict = response.model_dump()
        assert "total_count" in json_dict
        assert "limit" in json_dict
        assert "offset" in json_dict
        assert json_dict["total_count"] == 100
        assert json_dict["limit"] == 20
        assert json_dict["offset"] == 40

    def test_batches_list_type_contract(self) -> None:
        """Contract: batches must be a list of TeacherBatchItemV1."""
        # Arrange
        batch_item = TeacherBatchItemV1(
            batch_id=str(uuid4()),
            title="Test Batch",
            class_name="Class A",
            status=BatchClientStatus.READY,
            total_essays=10,
            completed_essays=0,
            created_at=datetime.now(UTC),
        )

        # Act
        response = TeacherDashboardResponseV1(
            batches=[batch_item],
            total_count=1,
        )

        # Assert
        assert len(response.batches) == 1
        assert isinstance(response.batches[0], TeacherBatchItemV1)
        assert response.batches[0].batch_id == batch_item.batch_id

    def test_json_roundtrip_contract(self) -> None:
        """Contract: TeacherDashboardResponseV1 must serialize/deserialize perfectly."""
        # Arrange
        batch_items = [
            TeacherBatchItemV1(
                batch_id=str(uuid4()),
                title=f"Batch {i}",
                class_name=f"Class {chr(65 + i)}",
                status=BatchClientStatus.PROCESSING,
                total_essays=10 + i,
                completed_essays=i,
                created_at=datetime.now(UTC),
            )
            for i in range(3)
        ]

        original = TeacherDashboardResponseV1(
            batches=batch_items,
            total_count=50,
            limit=3,
            offset=10,
        )

        # Act - Full JSON round-trip
        json_str = original.model_dump_json()
        json_dict = json.loads(json_str)
        deserialized = TeacherDashboardResponseV1.model_validate(json_dict)

        # Assert
        assert deserialized.total_count == original.total_count
        assert deserialized.limit == original.limit
        assert deserialized.offset == original.offset
        assert len(deserialized.batches) == len(original.batches)
        for i, batch in enumerate(deserialized.batches):
            assert batch.batch_id == original.batches[i].batch_id
            assert batch.title == original.batches[i].title

    def test_default_values_contract(self) -> None:
        """Contract: Default values applied correctly (limit=20, offset=0, batches=[])."""
        # Act - Minimal construction
        response = TeacherDashboardResponseV1()

        # Assert - Defaults
        assert response.batches == []
        assert response.total_count == 0
        assert response.limit == 20
        assert response.offset == 0

    def test_multiple_batches_with_mixed_statuses_contract(self) -> None:
        """Contract: Response can contain batches with different statuses."""
        # Arrange - One batch per status
        statuses = [
            BatchClientStatus.PENDING_CONTENT,
            BatchClientStatus.READY,
            BatchClientStatus.PROCESSING,
            BatchClientStatus.COMPLETED_SUCCESSFULLY,
            BatchClientStatus.COMPLETED_WITH_FAILURES,
            BatchClientStatus.FAILED,
            BatchClientStatus.CANCELLED,
        ]

        batches = [
            TeacherBatchItemV1(
                batch_id=str(uuid4()),
                title=f"Batch {status.value}",
                status=status,
                created_at=datetime.now(UTC),
            )
            for status in statuses
        ]

        # Act
        response = TeacherDashboardResponseV1(
            batches=batches,
            total_count=len(batches),
        )

        # Assert
        assert len(response.batches) == 7
        response_statuses = {b.status for b in response.batches}
        assert response_statuses == set(statuses)

        # Assert - JSON round-trip
        json_str = response.model_dump_json()
        deserialized = TeacherDashboardResponseV1.model_validate_json(json_str)
        assert len(deserialized.batches) == 7
