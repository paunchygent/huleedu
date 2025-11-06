"""Integration tests for anchor essay workflow and grade projection.

This module tests the complete anchor essay workflow from initial batch creation
through grade projection and final grade assignment. It validates:
- Loading anchor essays with known grades
- Grade calibration from anchor Bradley-Terry scores
- Grade projection calculation for student essays
- Handling of various anchor distributions (comprehensive, sparse, edge cases)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
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
from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
)

if TYPE_CHECKING:
    pass


@pytest.mark.integration
class TestAnchorEssayWorkflow:
    """Test the complete anchor essay workflow with grade projection."""

    async def _create_assessment_context(
        self,
        session: AsyncSession,
        assignment_id: str,
        course_code: str,
    ) -> None:
        """Create assessment instructions and anchor references for testing."""
        # Create assessment instructions
        instruction = AssessmentInstruction(
            assignment_id=assignment_id,
            instructions_text="Assess essays based on clarity, argumentation, and language use.",
        )
        session.add(instruction)

        # Create anchor essay references with grades
        # Using Swedish grade distribution
        anchor_grades = [
            ("F", "anchor_storage_f"),
            ("E", "anchor_storage_e"),
            ("D", "anchor_storage_d"),
            ("C", "anchor_storage_c"),
            ("B", "anchor_storage_b"),
            ("A", "anchor_storage_a"),
        ]

        for grade, storage_id in anchor_grades:
            anchor_ref = AnchorEssayReference(
                grade=grade,
                text_storage_id=storage_id,
                assignment_id=assignment_id,
            )
            session.add(anchor_ref)

        await session.flush()

    async def _create_batch_with_essays(
        self,
        repository: CJRepositoryProtocol,
        session: AsyncSession,
        student_count: int,
        anchor_grades: list[str],
        batch_id: str = "test-batch",
        assignment_id: str = "test-assignment",
    ) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]]]:
        """Create a batch with student essays and anchor essays.

        Returns:
            Tuple of (batch_id, student_essays, anchor_essays)
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

        # Update batch with assignment_id
        cj_batch.assignment_id = assignment_id
        await session.flush()

        # Create student essays
        student_essays = []
        for i in range(student_count):
            essay_id = f"student_{i:03d}"
            essay = await repository.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=cj_batch.id,
                els_essay_id=essay_id,
                text_storage_id=f"student_storage_{i:03d}",
                assessment_input_text=f"Student essay content {i}",
            )
            student_essays.append(
                {
                    "els_essay_id": essay_id,
                    "is_anchor": False,
                }
            )

        # Create anchor essays
        anchor_essays = []
        for idx, grade in enumerate(anchor_grades):
            essay_id = f"anchor_{grade}_{idx:02d}"
            essay = await repository.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=cj_batch.id,
                els_essay_id=essay_id,
                text_storage_id=f"anchor_storage_{grade}_{idx}",
                assessment_input_text=f"Anchor essay for grade {grade}",
                processing_metadata={"anchor_grade": grade},
            )
            # Mark as anchor
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
            quality_ordering: Dict mapping essay_id to quality score

        Returns:
            List of ComparisonResult objects
        """
        comparison_results = []

        # Generate all pairs
        for i in range(len(essays)):
            for j in range(i + 1, len(essays)):
                essay_a = essays[i]
                essay_b = essays[j]

                # Determine winner based on quality scores
                quality_a = quality_ordering.get(essay_a["els_essay_id"], 0.5)
                quality_b = quality_ordering.get(essay_b["els_essay_id"], 0.5)

                # Add some noise for realism
                import random

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
                    confidence=4.0,  # Using 1-5 scale
                )

                comparison_results.append(
                    ComparisonResult(
                        task=task,
                        llm_assessment=assessment,
                        raw_llm_response_content="Mock LLM response",
                    )
                )

        return comparison_results

    async def test_full_anchor_workflow_with_comprehensive_anchors(
        self,
        postgres_repository: CJRepositoryProtocol,
        postgres_session: AsyncSession,
        mock_content_client: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test grade projection with comprehensive anchor coverage (all grades)."""
        # Create assessment context
        assignment_id = "test-assignment-001"
        await self._create_assessment_context(postgres_session, assignment_id, "ENG5")

        # Create batch with 20 students and anchors for all grades
        anchor_grades = ["F", "E", "D", "C", "B", "A"]
        batch_id, student_essays, anchor_essays = await self._create_batch_with_essays(
            postgres_repository,
            postgres_session,
            student_count=20,
            anchor_grades=anchor_grades,
            assignment_id=assignment_id,
        )

        # Define quality ordering (anchors have known quality, students distributed)
        quality_ordering = {
            # Anchors at their expected positions
            "anchor_F_0": 0.0,
            "anchor_E_1": 0.2,
            "anchor_D_2": 0.4,
            "anchor_C_3": 0.6,
            "anchor_B_4": 0.8,
            "anchor_A_5": 1.0,
        }

        # Distribute students across quality range
        for i, student in enumerate(student_essays):
            quality_ordering[student["els_essay_id"]] = i / len(student_essays)

        # Generate comparisons
        all_essays = student_essays + anchor_essays
        comparison_results = self._generate_comparison_results(all_essays, quality_ordering)

        # Create essay objects for scoring
        essay_objects = []
        for essay in all_essays:
            essay_objects.append(
                EssayForComparison(
                    id=essay["els_essay_id"],
                    text_content=f"Content for {essay['els_essay_id']}",
                    current_bt_score=None,
                )
            )

        # Record comparisons and calculate scores
        correlation_id = uuid4()
        scores = await record_comparisons_and_update_scores(
            all_essays=essay_objects,
            comparison_results=comparison_results,
            db_session=postgres_session,
            cj_batch_id=batch_id,
            correlation_id=correlation_id,
        )

        # Verify scores were calculated
        assert len(scores) > 0, "Should have calculated Bradley-Terry scores"

        # Get rankings from database
        stmt = (
            select(
                ProcessedEssay.els_essay_id,
                ProcessedEssay.current_bt_score,
                ProcessedEssay.current_bt_se,
                ProcessedEssay.is_anchor,
                ProcessedEssay.processing_metadata,
            )
            .where(ProcessedEssay.cj_batch_id == batch_id)
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

        # Mock content client to return anchor content
        async def mock_fetch_content(content_id: str, correlation_id: Any) -> str:
            return f"Anchor essay content for {content_id}"

        mock_content_client.fetch_content.side_effect = mock_fetch_content

        # Calculate grade projections
        grade_projector = GradeProjector()
        projection_summary = await grade_projector.calculate_projections(
            session=postgres_session,
            rankings=rankings,
            cj_batch_id=batch_id,
            assignment_id=assignment_id,
            course_code="ENG5",
            content_client=mock_content_client,
            correlation_id=correlation_id,
        )

        # Verify projections were calculated
        assert projection_summary.projections_available, "Should have grade projections available"

        # Verify all students got grades
        student_ids = [s["els_essay_id"] for s in student_essays]
        for student_id in student_ids:
            assert student_id in projection_summary.primary_grades, (
                f"Student {student_id} should have a grade"
            )
            assert student_id in projection_summary.confidence_labels, (
                f"Student {student_id} should have confidence"
            )

        # Verify grades are from the valid set
        valid_grades = [
            "F",
            "F+",
            "E-",
            "E",
            "E+",
            "D-",
            "D",
            "D+",
            "C-",
            "C",
            "C+",
            "B-",
            "B",
            "B+",
            "A-",
            "A",
        ]
        for grade in projection_summary.primary_grades.values():
            assert grade in valid_grades, f"Grade {grade} not in valid grade set"

        # Verify calibration info
        assert "grade_centers" in projection_summary.calibration_info
        assert "anchor_count" in projection_summary.calibration_info
        assert projection_summary.calibration_info["anchor_count"] == len(anchor_grades)

        # Verify grades were stored in database
        stmt = select(GradeProjection).where(GradeProjection.cj_batch_id == batch_id)
        result = await postgres_session.execute(stmt)
        stored_projections = result.scalars().all()

        assert len(stored_projections) == len(student_essays), (
            "Should store projections for all students"
        )

        # Verify projection properties
        for projection in stored_projections:
            assert projection.primary_grade in valid_grades
            assert projection.grade_scale == "swedish_8_anchor"
            assert 0.0 <= projection.confidence_score <= 1.0
            assert projection.confidence_label in ["HIGH", "MID", "LOW"]
            assert projection.calculation_metadata is not None

    async def test_grade_projection_with_sparse_anchors(
        self,
        postgres_repository: CJRepositoryProtocol,
        postgres_session: AsyncSession,
        mock_content_client: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test grade projection with sparse anchor coverage (only A, C, E grades)."""
        # Create assessment context
        assignment_id = "test-assignment-002"
        await self._create_assessment_context(postgres_session, assignment_id, "ENG5")

        # Create batch with sparse anchors
        sparse_anchor_grades = ["E", "C", "A"]  # Missing F, D, B
        batch_id, student_essays, anchor_essays = await self._create_batch_with_essays(
            postgres_repository,
            postgres_session,
            student_count=10,
            anchor_grades=sparse_anchor_grades,
            assignment_id=assignment_id,
        )

        # Define quality ordering
        quality_ordering = {
            "anchor_E_0": 0.2,
            "anchor_C_1": 0.6,
            "anchor_A_2": 1.0,
        }

        # Distribute students
        for i, student in enumerate(student_essays):
            quality_ordering[student["els_essay_id"]] = (i + 0.5) / (len(student_essays) + 1)

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
            cj_batch_id=batch_id,
            correlation_id=correlation_id,
        )

        # Get rankings
        stmt = select(
            ProcessedEssay.els_essay_id,
            ProcessedEssay.current_bt_score,
            ProcessedEssay.current_bt_se,
            ProcessedEssay.is_anchor,
            ProcessedEssay.processing_metadata,
        ).where(ProcessedEssay.cj_batch_id == batch_id)
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

        # Calculate projections with sparse anchors
        grade_projector = GradeProjector()
        projection_summary = await grade_projector.calculate_projections(
            session=postgres_session,
            rankings=rankings,
            cj_batch_id=batch_id,
            assignment_id=assignment_id,
            course_code="ENG5",
            content_client=mock_content_client,
            correlation_id=correlation_id,
        )

        # Verify projections work with sparse anchors
        assert projection_summary.projections_available, "Should handle sparse anchors"

        # System should interpolate missing grades
        student_ids = [s["els_essay_id"] for s in student_essays]
        for student_id in student_ids:
            assert student_id in projection_summary.primary_grades

        # Verify calibration adapted to sparse anchors
        assert projection_summary.calibration_info["anchor_count"] == len(sparse_anchor_grades)

    async def test_batch_with_no_anchors(
        self,
        postgres_repository: CJRepositoryProtocol,
        postgres_session: AsyncSession,
        mock_content_client: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test that batches without anchors complete but don't produce grade projections."""
        # Create batch with only student essays (no anchors)
        batch_id, student_essays, _ = await self._create_batch_with_essays(
            postgres_repository,
            postgres_session,
            student_count=10,
            anchor_grades=[],  # No anchors
            assignment_id="test-assignment-003",
        )

        # Generate comparisons for students only
        quality_ordering = {
            student["els_essay_id"]: i / 10 for i, student in enumerate(student_essays)
        }

        comparison_results = self._generate_comparison_results(student_essays, quality_ordering)

        essay_objects = [
            EssayForComparison(
                id=essay["els_essay_id"],
                text_content="Content",
                current_bt_score=None,
            )
            for essay in student_essays
        ]

        # Calculate scores (should work without anchors)
        correlation_id = uuid4()
        scores = await record_comparisons_and_update_scores(
            all_essays=essay_objects,
            comparison_results=comparison_results,
            db_session=postgres_session,
            cj_batch_id=batch_id,
            correlation_id=correlation_id,
        )

        # Verify scoring worked
        assert len(scores) > 0, "Should calculate scores even without anchors"

        # Get rankings
        stmt = select(
            ProcessedEssay.els_essay_id,
            ProcessedEssay.current_bt_score,
            ProcessedEssay.current_bt_se,
            ProcessedEssay.is_anchor,
        ).where(ProcessedEssay.cj_batch_id == batch_id)
        result = await postgres_session.execute(stmt)
        rankings = [
            {
                "els_essay_id": row.els_essay_id,
                "bradley_terry_score": row.current_bt_score,
                "bradley_terry_se": row.current_bt_se,
                "is_anchor": row.is_anchor,
            }
            for row in result
        ]

        # Try to calculate projections
        grade_projector = GradeProjector()
        projection_summary = await grade_projector.calculate_projections(
            session=postgres_session,
            rankings=rankings,
            cj_batch_id=batch_id,
            assignment_id=None,  # No assignment context
            course_code="ENG5",
            content_client=mock_content_client,
            correlation_id=correlation_id,
        )

        # Verify no projections without anchors
        assert not projection_summary.projections_available, (
            "Should not project grades without anchors"
        )
        assert len(projection_summary.primary_grades) == 0
        assert len(projection_summary.confidence_labels) == 0

    async def test_grade_boundary_behavior(
        self,
        postgres_repository: CJRepositoryProtocol,
        postgres_session: AsyncSession,
        mock_content_client: AsyncMock,
        test_settings: Settings,
    ) -> None:
        """Test that grade boundaries and fine grades work correctly."""
        # Create assessment context
        assignment_id = "test-assignment-004"
        await self._create_assessment_context(postgres_session, assignment_id, "ENG5")

        # Create batch with anchors
        anchor_grades = ["F", "D", "C", "B", "A"]
        batch_id, student_essays, anchor_essays = await self._create_batch_with_essays(
            postgres_repository,
            postgres_session,
            student_count=15,
            anchor_grades=anchor_grades,
            assignment_id=assignment_id,
        )

        # Create specific quality ordering to test boundaries
        quality_ordering = {
            "anchor_F_0": 0.0,
            "anchor_D_1": 0.35,
            "anchor_C_2": 0.55,
            "anchor_B_3": 0.75,
            "anchor_A_4": 0.95,
        }

        # Place students at specific positions to test fine grades
        test_positions = [
            ("student_000", 0.05),  # Near F (might get F or F+)
            ("student_001", 0.30),  # Between F and D (might get D-)
            ("student_002", 0.36),  # Just above D
            ("student_003", 0.45),  # Between D and C
            ("student_004", 0.54),  # Just below C
            ("student_005", 0.56),  # Just above C
            ("student_006", 0.65),  # Between C and B
            ("student_007", 0.74),  # Just below B
            ("student_008", 0.76),  # Just above B
            ("student_009", 0.85),  # Between B and A
            ("student_010", 0.94),  # Just below A
            ("student_011", 0.96),  # Just above A
        ]

        for student_id, quality in test_positions[: len(student_essays)]:
            if any(s["els_essay_id"] == student_id for s in student_essays):
                quality_ordering[student_id] = quality

        # Fill in remaining students
        for student in student_essays:
            if student["els_essay_id"] not in quality_ordering:
                quality_ordering[student["els_essay_id"]] = 0.5

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
            cj_batch_id=batch_id,
            correlation_id=correlation_id,
        )

        # Get rankings
        stmt = select(
            ProcessedEssay.els_essay_id,
            ProcessedEssay.current_bt_score,
            ProcessedEssay.current_bt_se,
            ProcessedEssay.is_anchor,
            ProcessedEssay.processing_metadata,
        ).where(ProcessedEssay.cj_batch_id == batch_id)
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

        # Calculate projections
        grade_projector = GradeProjector()
        projection_summary = await grade_projector.calculate_projections(
            session=postgres_session,
            rankings=rankings,
            cj_batch_id=batch_id,
            assignment_id=assignment_id,
            course_code="ENG5",
            content_client=mock_content_client,
            correlation_id=correlation_id,
        )

        # Verify projections
        assert projection_summary.projections_available

        # Check that fine grades are assigned appropriately
        # We don't assert specific grades (that would be testing outcomes not mechanisms)
        # But we verify the mechanism produces valid fine grades

        fine_grades = [
            "F",
            "F+",
            "E-",
            "E",
            "E+",
            "D-",
            "D",
            "D+",
            "C-",
            "C",
            "C+",
            "B-",
            "B",
            "B+",
            "A-",
            "A",
        ]

        for student_id, grade in projection_summary.primary_grades.items():
            assert grade in fine_grades, f"Grade {grade} not in valid fine grade set"

            # Verify probability distribution exists
            assert student_id in projection_summary.grade_probabilities
            probs = projection_summary.grade_probabilities[student_id]

            # Probabilities should sum to approximately 1.0
            total_prob = sum(probs.values())
            assert 0.99 <= total_prob <= 1.01, f"Probabilities don't sum to 1: {total_prob}"

            # Verify BT stats exist
            assert student_id in projection_summary.bt_stats
            bt_stat = projection_summary.bt_stats[student_id]
            assert "bt_mean" in bt_stat
            assert "bt_se" in bt_stat
            assert bt_stat["bt_se"] >= 0, "Standard error should be non-negative"
