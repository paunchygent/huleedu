"""Unit tests for anchor grade mapping fallbacks."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from services.cj_assessment_service.cj_core_logic.context_builder import AssessmentContext
from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.models_db import AnchorEssayReference


def _build_context() -> AssessmentContext:
    # Create actual AnchorEssayReference instances instead of SimpleNamespace
    anchor1 = AnchorEssayReference(
        id=1,
        anchor_label="anchor-b",
        grade="B",
        grade_scale="swedish_8_anchor",
        text_storage_id="storage-1",
        assignment_id="test-assignment",
        created_at=datetime.now(timezone.utc),
    )
    anchor2 = AnchorEssayReference(
        id=2,
        anchor_label="anchor-a",
        grade="A",
        grade_scale="swedish_8_anchor",
        text_storage_id="storage-2",
        assignment_id="test-assignment",
        created_at=datetime.now(timezone.utc),
    )

    return AssessmentContext(
        assessment_instructions="Use anchors",
        anchor_essay_refs=[anchor1, anchor2],
        anchor_contents={},
        context_source="assignment",
        grade_scale="swedish_8_anchor",
    )


def test_map_anchor_grade_prefers_metadata_grade() -> None:
    projector = GradeProjector()
    anchors = [
        {
            "els_essay_id": "anchor-1",
            "anchor_grade": "C",
            "processing_metadata": {"text_storage_id": "storage-1"},
        }
    ]

    result = projector._map_anchor_grades(anchors, _build_context())

    assert result == {"anchor-1": "C"}


def test_map_anchor_grade_falls_back_to_context_storage_match() -> None:
    projector = GradeProjector()
    anchors = [
        {
            "els_essay_id": "anchor-2",
            # No anchor_grade provided
            "text_storage_id": "storage-2",
            "processing_metadata": {"anchor_ref_id": "2"},
        }
    ]

    result = projector._map_anchor_grades(anchors, _build_context())

    assert result == {"anchor-2": "A"}


def test_map_anchor_grade_warns_when_unresolved(monkeypatch: pytest.MonkeyPatch) -> None:
    projector = GradeProjector()
    mock_logger = MagicMock()
    projector.logger = mock_logger

    anchors = [
        {
            "els_essay_id": "anchor-3",
            "processing_metadata": {},
        }
    ]

    result = projector._map_anchor_grades(anchors, _build_context())

    assert result == {}
    mock_logger.warning.assert_called_once()
    _, kwargs = mock_logger.warning.call_args
    assert kwargs["extra"]["essay_id"] == "anchor-3"
