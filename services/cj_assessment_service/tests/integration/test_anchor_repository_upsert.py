"""Integration tests for repository-level anchor upsert behavior.

Validates that PostgreSQLAnchorRepository.upsert_anchor_reference uses
INSERT .. ON CONFLICT DO UPDATE semantics keyed on
(assignment_id, anchor_label, grade_scale), allowing multiple anchors with
the same grade but different labels while returning the anchor ID via
RETURNING so callers can reuse the same anchor across registrations.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_db import AnchorEssayReference
from services.cj_assessment_service.tests.fixtures.database_fixtures import PostgresDataAccess


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upsert_anchor_reference_idempotent_and_updates_storage_id(
    postgres_data_access: PostgresDataAccess,
) -> None:
    """Upserting the same assignment/grade/scale reuses ID and updates storage.

    This test runs against a real PostgreSQL backend using the
    postgres_repository fixture and ensures that the ON CONFLICT DO UPDATE
    logic behaves as expected.
    """

    async with postgres_data_access.session() as session:
        assert isinstance(session, AsyncSession)

        # First upsert creates a new anchor for this (assignment_id, anchor_label, scale)
        anchor_id_first = await postgres_data_access.upsert_anchor_reference(
            session,
            assignment_id="repo-upsert-assignment-1",
            anchor_label="A1",
            grade="A",
            grade_scale="swedish_8_anchor",
            text_storage_id="storage-first",
        )

        # Second upsert with same triple but different storage_id should reuse ID
        anchor_id_second = await postgres_data_access.upsert_anchor_reference(
            session,
            assignment_id="repo-upsert-assignment-1",
            anchor_label="A1",
            grade="A",
            grade_scale="swedish_8_anchor",
            text_storage_id="storage-second",
        )

        assert anchor_id_first == anchor_id_second

        # Verify there is exactly one row and text_storage_id was updated
        result = await session.execute(
            select(AnchorEssayReference).where(
                AnchorEssayReference.assignment_id == "repo-upsert-assignment-1",
                AnchorEssayReference.grade == "A",
                AnchorEssayReference.grade_scale == "swedish_8_anchor",
            )
        )
        anchors = list(result.scalars().all())
        assert len(anchors) == 1
        assert anchors[0].id == anchor_id_first
        assert anchors[0].text_storage_id == "storage-second"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_anchor_labels_can_share_the_same_grade(
    postgres_data_access: PostgresDataAccess,
) -> None:
    """Different anchor labels with the same grade co-exist for an assignment."""

    async with postgres_data_access.session() as session:
        assert isinstance(session, AsyncSession)

        anchor_a = await postgres_data_access.upsert_anchor_reference(
            session,
            assignment_id="repo-upsert-assignment-2",
            anchor_label="Anchor-A",
            grade="A",
            grade_scale="swedish_8_anchor",
            text_storage_id="storage-anchor-a",
        )

        anchor_b = await postgres_data_access.upsert_anchor_reference(
            session,
            assignment_id="repo-upsert-assignment-2",
            anchor_label="Anchor-B",
            grade="A",
            grade_scale="swedish_8_anchor",
            text_storage_id="storage-anchor-b",
        )

        assert anchor_a != anchor_b

        result = await session.execute(
            select(AnchorEssayReference).where(
                AnchorEssayReference.assignment_id == "repo-upsert-assignment-2",
                AnchorEssayReference.grade == "A",
                AnchorEssayReference.grade_scale == "swedish_8_anchor",
            )
        )
        anchors = list(result.scalars().all())
        assert {anchor.anchor_label for anchor in anchors} == {"Anchor-A", "Anchor-B"}
