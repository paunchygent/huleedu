"""Integration tests for repository anchor flag handling."""

from __future__ import annotations

from uuid import uuid4

import pytest

from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import ProcessedEssay
from services.cj_assessment_service.tests.fixtures.database_fixtures import PostgresDataAccess


@pytest.mark.asyncio
async def test_create_or_update_sets_is_anchor_flag(
    postgres_data_access: PostgresDataAccess,
) -> None:
    """Repository should persist the is_anchor flag derived from metadata."""

    async with postgres_data_access.session() as session:
        batch = await postgres_data_access.create_new_cj_batch(
            session=session,
            bos_batch_id="anchor-flag-batch",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=2,
        )

        anchor = await postgres_data_access.create_or_update_cj_processed_essay(
            session=session,
            cj_batch_id=batch.id,
            els_essay_id="ANCHOR_SAMPLE",
            text_storage_id="storage-anchor",
            assessment_input_text="Anchor essay",
            processing_metadata={"is_anchor": True, "anchor_grade": "A"},
        )

        student = await postgres_data_access.create_or_update_cj_processed_essay(
            session=session,
            cj_batch_id=batch.id,
            els_essay_id="student-1",
            text_storage_id="storage-student",
            assessment_input_text="Student essay",
            processing_metadata={"is_anchor": False},
        )

        await session.flush()

        stored_anchor = await session.get(ProcessedEssay, anchor.els_essay_id)
        stored_student = await session.get(ProcessedEssay, student.els_essay_id)

        assert stored_anchor is not None
        assert stored_anchor.is_anchor is True
        assert stored_student is not None
        assert stored_student.is_anchor is False
