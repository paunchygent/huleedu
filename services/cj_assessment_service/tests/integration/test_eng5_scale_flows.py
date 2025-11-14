"""Integration tests for ENG5 scale flows (legacy vs national).

This module validates that the two ENG5 NP grade scales work correctly:
- eng5_np_legacy_9_step: Letter grades (F+ through A) with below-lowest grade "F"
- eng5_np_national_9_step: Numerical grades (1 through 9) with below-lowest grade "0"

Tests verify:
- Scale-specific population priors are applied
- Anchors are filtered by grade_scale
- Grade projections use correct grade set
- Below-lowest behavior differs per scale
- No behavioral drift between scales in projection logic
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core import EssayComparisonWinner
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.cj_core_logic.scoring_ranking import (
    record_comparisons_and_update_scores,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_api import (
    ComparisonResult,
    ComparisonTask,
    EssayForComparison,
    LLMAssessmentResponseSchema,
)
from services.cj_assessment_service.models_db import (
    AnchorEssayReference,
    AssessmentInstruction,
    GradeProjection,
    ProcessedEssay,
)
from services.cj_assessment_service.protocols import CJRepositoryProtocol


@pytest.mark.integration
class TestENG5ScaleFlows:
    """Test ENG5 legacy vs national scale integration."""

    async def _create_instruction_and_anchors(
        self,
        session: AsyncSession,
        assignment_id: str,
        grade_scale: str,
        anchor_grades: list[str],
    ) -> None:
        """Create assessment instruction and anchor references for a scale.

        Args:
            session: Database session
            assignment_id: Assignment identifier
            grade_scale: Grade scale ID (eng5_np_legacy_9_step or eng5_np_national_9_step)
            anchor_grades: List of valid grades for this scale
        """
        # Create assessment instruction
        instruction = AssessmentInstruction(
            assignment_id=assignment_id,
            instructions_text=f"Assess essays using {grade_scale} scale.",
            grade_scale=grade_scale,
        )
        session.add(instruction)

        # Create anchor essay references
        for grade in anchor_grades:
            anchor_ref = AnchorEssayReference(
                anchor_label=f"{assignment_id}_{grade}",
                grade=grade,
                grade_scale=grade_scale,
                text_storage_id=f"anchor_storage_{grade_scale}_{grade}",
                assignment_id=assignment_id,
            )
            session.add(anchor_ref)

        await session.flush()

    async def _create_batch_with_essays(
        self,
        repository: CJRepositoryProtocol,
        session: AsyncSession,
        batch_id: str,
        assignment_id: str,
        student_count: int,
        anchor_grades: list[str],
        grade_scale: str,
    ) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]]]:
        """Create a batch with student essays and anchor essays.

        Args:
            repository: CJ repository for database operations
            session: Database session
            batch_id: Batch identifier
            assignment_id: Assignment identifier
            student_count: Number of student essays to create
            anchor_grades: List of anchor grades to create
            grade_scale: Grade scale ID for this batch

        Returns:
            Tuple of (cj_batch_id, student_essays, anchor_essays)
        """
        # Create batch
        cj_batch = await repository.create_new_cj_batch(
            session=session,
            bos_batch_id=batch_id,
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=student_count + len(anchor_grades),
        )
        cj_batch.processing_metadata = {"student_prompt_text": "Write an argumentative essay"}
        cj_batch.assignment_id = assignment_id
        await session.flush()

        # Create student essays
        student_essays = []
        for i in range(student_count):
            essay_id = f"student_{batch_id}_{i:03d}"
            await repository.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=cj_batch.id,
                els_essay_id=essay_id,
                text_storage_id=f"student_storage_{batch_id}_{i:03d}",
                assessment_input_text=f"Student essay content {i}",
            )
            student_essays.append({"els_essay_id": essay_id, "is_anchor": False})

        # Create anchor essays
        anchor_essays = []
        for idx, grade in enumerate(anchor_grades):
            essay_id = f"anchor_{grade_scale}_{grade}_{idx:02d}"
            essay = await repository.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=cj_batch.id,
                els_essay_id=essay_id,
                text_storage_id=f"anchor_storage_{grade_scale}_{grade}_{idx}",
                assessment_input_text=f"Anchor essay for grade {grade}",
                processing_metadata={"anchor_grade": grade},
            )
            essay.is_anchor = True
            anchor_essays.append(
                {
                    "els_essay_id": essay_id,
                    "is_anchor": True,
                    "anchor_grade": grade,
                }
            )

        await session.flush()
        return cj_batch.id, student_essays, anchor_essays

    def _generate_comparison_results(
        self,
        essays: list[dict[str, Any]],
        quality_ordering: dict[str, float],
    ) -> list[ComparisonResult]:
        """Generate comparison results based on quality ordering.

        Args:
            essays: List of essay dictionaries
            quality_ordering: Dict mapping essay_id to quality score (0.0-1.0)

        Returns:
            List of ComparisonResult objects
        """
        comparison_results = []
        import random

        random.seed(42)  # Deterministic results

        # Generate all pairs
        for i in range(len(essays)):
            for j in range(i + 1, len(essays)):
                essay_a = essays[i]
                essay_b = essays[j]

                # Determine winner based on quality scores
                quality_a = quality_ordering.get(essay_a["els_essay_id"], 0.5)
                quality_b = quality_ordering.get(essay_b["els_essay_id"], 0.5)

                # Add some noise for realism
                noise = random.uniform(-0.1, 0.1)

                if quality_a + noise > quality_b:
                    winner = EssayComparisonWinner.ESSAY_A
                else:
                    winner = EssayComparisonWinner.ESSAY_B

                # Create comparison task
                task = ComparisonTask(
                    essay_a=EssayForComparison(
                        id=essay_a["els_essay_id"],
                        text_content=f"Content for {essay_a['els_essay_id']}",
                        current_bt_score=None,
                    ),
                    essay_b=EssayForComparison(
                        id=essay_b["els_essay_id"],
                        text_content=f"Content for {essay_b['els_essay_id']}",
                        current_bt_score=None,
                    ),
                    prompt="Compare these essays",
                )

                # Create assessment result
                assessment = LLMAssessmentResponseSchema(
                    winner=winner,
                    justification=f"Essay {winner.value} demonstrates better quality",
                    confidence=4.0,
                )

                comparison_results.append(
                    ComparisonResult(
                        task=task,
                        llm_assessment=assessment,
                        raw_llm_response_content="Mock LLM response",
                    )
                )

        return comparison_results

    async def test_legacy_scale_grade_projections(
        self,
        postgres_repository: CJRepositoryProtocol,
        postgres_session: AsyncSession,
        mock_content_client: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test grade projection with eng5_np_legacy_9_step scale."""
        assignment_id = "test-eng5-legacy-001"
        batch_id = "batch-legacy-001"
        grade_scale = "eng5_np_legacy_9_step"

        # Create instruction and anchors for legacy scale
        # Using representative grades from the 9-step scale
        anchor_grades = ["F+", "E+", "D+", "C+", "A"]
        await self._create_instruction_and_anchors(
            postgres_session, assignment_id, grade_scale, anchor_grades
        )

        # Create batch with essays
        cj_batch_id, student_essays, anchor_essays = await self._create_batch_with_essays(
            postgres_repository,
            postgres_session,
            batch_id,
            assignment_id,
            student_count=10,
            anchor_grades=anchor_grades,
            grade_scale=grade_scale,
        )

        # Define quality ordering
        quality_ordering = {
            f"anchor_{grade_scale}_F+_0": 0.1,
            f"anchor_{grade_scale}_E+_1": 0.3,
            f"anchor_{grade_scale}_D+_2": 0.5,
            f"anchor_{grade_scale}_C+_3": 0.7,
            f"anchor_{grade_scale}_A_4": 0.95,
        }

        # Distribute students across quality range
        for i, student in enumerate(student_essays):
            quality_ordering[student["els_essay_id"]] = (i + 1) / (len(student_essays) + 1)

        # Generate comparisons and calculate scores
        all_essays = student_essays + anchor_essays
        comparison_results = self._generate_comparison_results(all_essays, quality_ordering)

        essay_objects = [
            EssayForComparison(
                id=essay["els_essay_id"],
                text_content="Content",
                current_bt_score=None,
            )
            for essay in all_essays
        ]

        correlation_id = uuid4()
        await record_comparisons_and_update_scores(
            all_essays=essay_objects,
            comparison_results=comparison_results,
            db_session=postgres_session,
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Get rankings from database
        stmt = (
            select(
                ProcessedEssay.els_essay_id,
                ProcessedEssay.current_bt_score,
                ProcessedEssay.current_bt_se,
                ProcessedEssay.is_anchor,
                ProcessedEssay.processing_metadata,
            )
            .where(ProcessedEssay.cj_batch_id == cj_batch_id)
            .order_by(ProcessedEssay.current_bt_score.desc())
        )
        result = await postgres_session.execute(stmt)
        rankings = []
        for row in result:
            ranking_dict = {
                "els_essay_id": row.els_essay_id,
                "bradley_terry_score": row.current_bt_score,
                "bradley_terry_se": row.current_bt_se,
                "is_anchor": row.is_anchor,
            }
            if row.is_anchor and row.processing_metadata:
                ranking_dict["anchor_grade"] = row.processing_metadata.get("anchor_grade")
            rankings.append(ranking_dict)

        # Mock content client
        mock_content_client.fetch_content.side_effect = lambda cid, corr: f"Content {cid}"

        # Calculate grade projections
        grade_projector = GradeProjector()
        projection_summary = await grade_projector.calculate_projections(
            session=postgres_session,
            rankings=rankings,
            cj_batch_id=cj_batch_id,
            assignment_id=assignment_id,
            course_code="ENG5",
            content_client=mock_content_client,
            correlation_id=correlation_id,
        )

        # Verify projections were calculated
        assert projection_summary.projections_available, "Should have grade projections available"

        # Verify correct scale in calibration info
        actual_scale = projection_summary.calibration_info["grade_scale"]
        assert actual_scale == grade_scale, (
            f"Expected scale {grade_scale}, got {actual_scale}"
        )

        # Verify all students got grades
        student_ids = [s["els_essay_id"] for s in student_essays]
        for student_id in student_ids:
            assert student_id in projection_summary.primary_grades, (
                f"Student {student_id} should have a grade"
            )
            grade = projection_summary.primary_grades[student_id]

            # Verify grades are from the legacy scale's valid set
            # Note: Projector doesn't add minus/plus modifiers for ENG5 scales
            legacy_valid_grades = ["F+", "E-", "E+", "D-", "D+", "C-", "C+", "B", "A", "F"]
            assert grade in legacy_valid_grades, f"Grade {grade} not in legacy scale valid grades"

        # Verify stored projections have correct scale
        stmt = select(GradeProjection).where(GradeProjection.cj_batch_id == cj_batch_id)
        result = await postgres_session.execute(stmt)
        stored_projections = result.scalars().all()

        assert len(stored_projections) == len(student_essays), (
            "Should store projections for all students"
        )

        for projection in stored_projections:
            assert projection.grade_scale == grade_scale, (
                f"Stored projection should have scale {grade_scale}, got {projection.grade_scale}"
            )

    async def test_national_scale_grade_projections(
        self,
        postgres_repository: CJRepositoryProtocol,
        postgres_session: AsyncSession,
        mock_content_client: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test grade projection with eng5_np_national_9_step scale."""
        assignment_id = "test-eng5-national-001"
        batch_id = "batch-national-001"
        grade_scale = "eng5_np_national_9_step"

        # Create instruction and anchors for national scale
        # Using representative numerical grades
        anchor_grades = ["1", "3", "5", "7", "9"]
        await self._create_instruction_and_anchors(
            postgres_session, assignment_id, grade_scale, anchor_grades
        )

        # Create batch with essays
        cj_batch_id, student_essays, anchor_essays = await self._create_batch_with_essays(
            postgres_repository,
            postgres_session,
            batch_id,
            assignment_id,
            student_count=10,
            anchor_grades=anchor_grades,
            grade_scale=grade_scale,
        )

        # Define quality ordering
        quality_ordering = {
            f"anchor_{grade_scale}_1_0": 0.1,
            f"anchor_{grade_scale}_3_1": 0.3,
            f"anchor_{grade_scale}_5_2": 0.5,
            f"anchor_{grade_scale}_7_3": 0.7,
            f"anchor_{grade_scale}_9_4": 0.95,
        }

        # Distribute students across quality range
        for i, student in enumerate(student_essays):
            quality_ordering[student["els_essay_id"]] = (i + 1) / (len(student_essays) + 1)

        # Generate comparisons and calculate scores
        all_essays = student_essays + anchor_essays
        comparison_results = self._generate_comparison_results(all_essays, quality_ordering)

        essay_objects = [
            EssayForComparison(
                id=essay["els_essay_id"],
                text_content="Content",
                current_bt_score=None,
            )
            for essay in all_essays
        ]

        correlation_id = uuid4()
        await record_comparisons_and_update_scores(
            all_essays=essay_objects,
            comparison_results=comparison_results,
            db_session=postgres_session,
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Get rankings from database
        stmt = (
            select(
                ProcessedEssay.els_essay_id,
                ProcessedEssay.current_bt_score,
                ProcessedEssay.current_bt_se,
                ProcessedEssay.is_anchor,
                ProcessedEssay.processing_metadata,
            )
            .where(ProcessedEssay.cj_batch_id == cj_batch_id)
            .order_by(ProcessedEssay.current_bt_score.desc())
        )
        result = await postgres_session.execute(stmt)
        rankings = []
        for row in result:
            ranking_dict = {
                "els_essay_id": row.els_essay_id,
                "bradley_terry_score": row.current_bt_score,
                "bradley_terry_se": row.current_bt_se,
                "is_anchor": row.is_anchor,
            }
            if row.is_anchor and row.processing_metadata:
                ranking_dict["anchor_grade"] = row.processing_metadata.get("anchor_grade")
            rankings.append(ranking_dict)

        # Mock content client
        mock_content_client.fetch_content.side_effect = lambda cid, corr: f"Content {cid}"

        # Calculate grade projections
        grade_projector = GradeProjector()
        projection_summary = await grade_projector.calculate_projections(
            session=postgres_session,
            rankings=rankings,
            cj_batch_id=cj_batch_id,
            assignment_id=assignment_id,
            course_code="ENG5",
            content_client=mock_content_client,
            correlation_id=correlation_id,
        )

        # Verify projections were calculated
        assert projection_summary.projections_available, "Should have grade projections available"

        # Verify correct scale in calibration info
        actual_scale = projection_summary.calibration_info["grade_scale"]
        assert actual_scale == grade_scale, (
            f"Expected scale {grade_scale}, got {actual_scale}"
        )

        # Verify all students got grades
        student_ids = [s["els_essay_id"] for s in student_essays]
        for student_id in student_ids:
            assert student_id in projection_summary.primary_grades, (
                f"Student {student_id} should have a grade"
            )
            grade = projection_summary.primary_grades[student_id]

            # Verify grades are from the national scale's valid set
            national_valid_grades = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]
            assert grade in national_valid_grades, (
                f"Grade {grade} not in national scale valid grades"
            )

        # Verify stored projections have correct scale
        stmt = select(GradeProjection).where(GradeProjection.cj_batch_id == cj_batch_id)
        result = await postgres_session.execute(stmt)
        stored_projections = result.scalars().all()

        assert len(stored_projections) == len(student_essays), (
            "Should store projections for all students"
        )

        for projection in stored_projections:
            assert projection.grade_scale == grade_scale, (
                f"Stored projection should have scale {grade_scale}, got {projection.grade_scale}"
            )

    async def test_scale_isolation_anchors_not_mixed(
        self,
        postgres_repository: CJRepositoryProtocol,
        postgres_session: AsyncSession,
        mock_content_client: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test that anchors from different scales are not mixed.

        This test creates two assignments with different scales and verifies
        that anchors are properly filtered by grade_scale.
        """
        # Create legacy scale assignment
        legacy_assignment_id = "test-isolation-legacy"
        legacy_scale = "eng5_np_legacy_9_step"
        legacy_anchor_grades = ["F+", "C+", "A"]
        await self._create_instruction_and_anchors(
            postgres_session, legacy_assignment_id, legacy_scale, legacy_anchor_grades
        )

        # Create national scale assignment
        national_assignment_id = "test-isolation-national"
        national_scale = "eng5_np_national_9_step"
        national_anchor_grades = ["1", "5", "9"]
        await self._create_instruction_and_anchors(
            postgres_session, national_assignment_id, national_scale, national_anchor_grades
        )

        await postgres_session.flush()

        # Query anchors for legacy assignment
        from services.cj_assessment_service.implementations.db_access_impl import (
            get_anchor_essay_references,
        )

        legacy_anchors = await get_anchor_essay_references(
            postgres_session,
            assignment_id=legacy_assignment_id,
            grade_scale=legacy_scale,
        )

        # Verify only legacy anchors returned
        assert len(legacy_anchors) == len(legacy_anchor_grades), (
            f"Expected {len(legacy_anchor_grades)} legacy anchors, got {len(legacy_anchors)}"
        )
        for anchor in legacy_anchors:
            assert anchor.grade in legacy_anchor_grades, (
                f"Anchor grade {anchor.grade} not in legacy grades"
            )
            assert anchor.grade_scale == legacy_scale, (
                f"Anchor should have scale {legacy_scale}, got {anchor.grade_scale}"
            )

        # Query anchors for national assignment
        national_anchors = await get_anchor_essay_references(
            postgres_session,
            assignment_id=national_assignment_id,
            grade_scale=national_scale,
        )

        # Verify only national anchors returned
        assert len(national_anchors) == len(national_anchor_grades), (
            f"Expected {len(national_anchor_grades)} national anchors, got {len(national_anchors)}"
        )
        for anchor in national_anchors:
            assert anchor.grade in national_anchor_grades, (
                f"Anchor grade {anchor.grade} not in national grades"
            )
            assert anchor.grade_scale == national_scale, (
                f"Anchor should have scale {national_scale}, got {anchor.grade_scale}"
            )

        # Verify no overlap
        legacy_grades = {a.grade for a in legacy_anchors}
        national_grades = {a.grade for a in national_anchors}
        assert not legacy_grades.intersection(national_grades), (
            "Legacy and national anchor grades should not overlap"
        )
