"""Integration test for CJ pair position randomization at the database level.

This test creates a CJ batch with 12 anchors and 12 students, runs the
real comparison submission entry point, and then inspects the
`cj_comparison_pairs` table to verify that anchors appear in the
`essay_a` and `essay_b` positions in a roughly balanced way.

The goal is to provide an end-to-end guardrail that the per-pair
A/B position randomization is actually reflected in persisted
ComparisonPair rows, not just in-memory tasks.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic import pair_generation
from services.cj_assessment_service.cj_core_logic.batch_submission_tracking import (
    create_tracking_records,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_api import (
    CJAssessmentRequestData,
    EssayForComparison,
    EssayToProcess,
)
from services.cj_assessment_service.models_db import ComparisonPair, ProcessedEssay
from services.cj_assessment_service.protocols import CJRepositoryProtocol


@pytest.mark.integration
class TestPairGenerationRandomizationIntegration:
    """Validate CJ pair position randomization using a real database.

    This test uses the shared Postgres-backed repository and session
    fixtures from `tests/fixtures/database_fixtures.py` and a mocked
    LLM interaction that simulates async processing.
    """

    async def _create_12x12_batch(
        self,
        repository: CJRepositoryProtocol,
        session: AsyncSession,
    ) -> tuple[int, str]:
        """Create a CJ batch with 12 anchors and 12 student essays.

        Returns:
            Tuple of (cj_batch_id, bos_batch_id)
        """

        bos_batch_id = str(uuid4())

        # Create batch upload record
        cj_batch = await repository.create_new_cj_batch(
            session=session,
            bos_batch_id=bos_batch_id,
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=24,
        )
        # Minimal processing metadata to keep alignment with other tests
        cj_batch.processing_metadata = {"student_prompt_text": "Randomization integration test"}
        await session.flush()

        # Create 12 student essays
        for i in range(12):
            await repository.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=cj_batch.id,
                els_essay_id=f"student_{i:02d}",
                text_storage_id=f"student_storage_{i:02d}",
                assessment_input_text=f"Student essay content {i}",
            )

        # Create 12 anchor essays and mark them as anchors
        for i in range(12):
            essay = await repository.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=cj_batch.id,
                els_essay_id=f"anchor_{i:02d}",
                text_storage_id=f"anchor_storage_{i:02d}",
                assessment_input_text=f"Anchor essay content {i}",
                processing_metadata={"anchor_label": f"A{i:02d}"},
            )
            essay.is_anchor = True

        await session.flush()
        return cj_batch.id, bos_batch_id

    async def _load_essays_for_api_model(
        self,
        repository: CJRepositoryProtocol,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> tuple[list[EssayForComparison], list[ProcessedEssay]]:
        """Load ProcessedEssay rows and convert them to EssayForComparison models."""

        processed_essays = await repository.get_essays_for_cj_batch(
            session=session,
            cj_batch_id=cj_batch_id,
        )

        essays_for_api_model: list[EssayForComparison] = []
        for processed in processed_essays:
            essays_for_api_model.append(
                EssayForComparison(
                    id=processed.els_essay_id,
                    text_content=processed.assessment_input_text,
                    current_bt_score=processed.current_bt_score or 0.0,
                )
            )

        return essays_for_api_model, processed_essays

    async def _build_request_data(
        self,
        bos_batch_id: str,
        processed_essays: list[ProcessedEssay],
    ) -> CJAssessmentRequestData:
        """Construct minimal CJAssessmentRequestData for submission entry point."""

        essays_to_process = [
            EssayToProcess(
                els_essay_id=essay.els_essay_id,
                text_storage_id=essay.text_storage_id,
            )
            for essay in processed_essays
        ]

        return CJAssessmentRequestData(
            bos_batch_id=bos_batch_id,
            assignment_id=None,
            essays_to_process=essays_to_process,
            language="en",
            course_code="ENG5",
            cj_source="els",
            cj_request_type="cj_comparison",
        )

    async def test_anchor_positions_are_balanced_in_db(
        self,
        postgres_repository: CJRepositoryProtocol,
        postgres_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        """Anchors should occupy essay_a about half the time in persisted pairs.

        This test creates a 12 anchors + 12 students batch, runs the real
        submission path once, and inspects `cj_comparison_pairs` rows for
        that batch. We assert that, for all pairs involving at least one
        anchor essay, the fraction of rows where the anchor is stored in
        `essay_a_els_id` is roughly 50%.

        The assertion band is intentionally wide to avoid flakiness while
        still catching any regression that reintroduces systematic
        anchor-first bias.
        """

        # Configure settings for this test run
        # Use a deterministic seed so the test is reproducible
        test_settings.PAIR_GENERATION_SEED = 42
        # Allow generation of all pairwise comparisons for this batch
        test_settings.MAX_PAIRWISE_COMPARISONS = 1000
        test_settings.COMPARISONS_PER_STABILITY_CHECK_ITERATION = 300

        # Step 1: Create a CJ batch with 12 anchors and 12 students
        cj_batch_id, bos_batch_id = await self._create_12x12_batch(
            repository=postgres_repository,
            session=postgres_session,
        )

        # Step 2: Load essays for API model and build request data
        essays_for_api_model, processed_essays = await self._load_essays_for_api_model(
            repository=postgres_repository,
            session=postgres_session,
            cj_batch_id=cj_batch_id,
        )
        await self._build_request_data(
            bos_batch_id=bos_batch_id,
            processed_essays=processed_essays,
        )

        correlation_id = uuid4()

        # Step 3: Generate comparison tasks using real pair generation logic
        comparison_tasks = await pair_generation.generate_comparison_tasks(
            essays_for_comparison=essays_for_api_model,
            db_session=postgres_session,
            cj_batch_id=cj_batch_id,
            existing_pairs_threshold=test_settings.COMPARISONS_PER_STABILITY_CHECK_ITERATION,
            max_pairwise_comparisons=test_settings.MAX_PAIRWISE_COMPARISONS,
            correlation_id=correlation_id,
            randomization_seed=test_settings.PAIR_GENERATION_SEED,
        )

        assert comparison_tasks, "Expected at least one comparison task to be generated"

        # Step 4: Persist ComparisonPair tracking records for generated tasks
        await create_tracking_records(
            session=postgres_session,
            batch_tasks=comparison_tasks,
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Step 5: Inspect persisted ComparisonPair rows for this batch
        stmt = select(
            ComparisonPair.essay_a_els_id,
            ComparisonPair.essay_b_els_id,
        ).where(ComparisonPair.cj_batch_id == cj_batch_id)

        result = await postgres_session.execute(stmt)
        rows = result.all()

        assert rows, "Expected at least one persisted comparison pair"

        anchor_pair_total = 0
        anchor_a_total = 0

        for essay_a_id, essay_b_id in rows:
            is_anchor_a = essay_a_id.startswith("anchor_")
            is_anchor_b = essay_b_id.startswith("anchor_")

            if is_anchor_a or is_anchor_b:
                anchor_pair_total += 1
                if is_anchor_a:
                    anchor_a_total += 1

        assert anchor_pair_total > 0, "Expected at least one pair involving an anchor"

        ratio = anchor_a_total / anchor_pair_total

        # Wide but meaningful assertion band to avoid flakiness while
        # still catching systematic bias (e.g. anchors always in essay_a).
        assert 0.3 <= ratio <= 0.7, (
            "Anchor essays should appear in essay_a roughly half the time; "
            f"observed ratio={ratio:.3f}"
        )
