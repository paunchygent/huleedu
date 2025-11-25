"""Tests for Comparison Repository - New comparison query methods."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.implementations.batch_repository import (
    PostgreSQLCJBatchRepository,
)
from services.cj_assessment_service.implementations.comparison_repository import (
    PostgreSQLCJComparisonRepository,
)
from services.cj_assessment_service.implementations.essay_repository import (
    PostgreSQLCJEssayRepository,
)
from services.cj_assessment_service.models_db import ComparisonPair


class TestGetComparisonPairsForBatch:
    """Tests for get_comparison_pairs_for_batch method."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_all_pair_ids_for_batch(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_essay_repository: PostgreSQLCJEssayRepository,
        postgres_comparison_repository: PostgreSQLCJComparisonRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test returns all pair IDs for a batch."""

        # Create batch
        batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="pairs-batch",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=3,
        )

        # Create essays
        essay_1 = await postgres_essay_repository.create_or_update_cj_processed_essay(
            session=postgres_session,
            cj_batch_id=batch.id,
            els_essay_id="essay-1",
            text_storage_id="storage-1",
            assessment_input_text="Essay 1 text",
        )

        essay_2 = await postgres_essay_repository.create_or_update_cj_processed_essay(
            session=postgres_session,
            cj_batch_id=batch.id,
            els_essay_id="essay-2",
            text_storage_id="storage-2",
            assessment_input_text="Essay 2 text",
        )

        essay_3 = await postgres_essay_repository.create_or_update_cj_processed_essay(
            session=postgres_session,
            cj_batch_id=batch.id,
            els_essay_id="essay-3",
            text_storage_id="storage-3",
            assessment_input_text="Essay 3 text",
        )

        # Create comparison pairs
        pair_1 = ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id=essay_1.els_essay_id,
            essay_b_els_id=essay_2.els_essay_id,
            prompt_text="Compare these essays",
            winner="essay_a",
            confidence=4.0,
            justification="Essay A is better",
        )
        pair_2 = ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id=essay_1.els_essay_id,
            essay_b_els_id=essay_3.els_essay_id,
            prompt_text="Compare these essays",
            winner="essay_b",
            confidence=3.5,
            justification="Essay B is better",
        )
        pair_3 = ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id=essay_2.els_essay_id,
            essay_b_els_id=essay_3.els_essay_id,
            prompt_text="Compare these essays",
            winner="essay_a",
            confidence=4.5,
            justification="Essay A is better",
        )

        postgres_session.add_all([pair_1, pair_2, pair_3])
        await postgres_session.flush()

        # Get comparison pairs
        pairs = await postgres_comparison_repository.get_comparison_pairs_for_batch(
            session=postgres_session,
            batch_id=batch.id,
        )

        # Should return all 3 pairs
        assert len(pairs) == 3
        # Check tuple format
        assert all(isinstance(p, tuple) and len(p) == 2 for p in pairs)
        # Check all pairs are present
        pair_set = set(pairs)
        assert ("essay-1", "essay-2") in pair_set
        assert ("essay-1", "essay-3") in pair_set
        assert ("essay-2", "essay-3") in pair_set

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_empty_list_for_batch_with_no_comparisons(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_comparison_repository: PostgreSQLCJComparisonRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test returns empty list for batch with no comparisons."""

        # Create batch with no comparisons
        batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="empty-pairs-batch",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )
        await postgres_session.flush()

        # Get comparison pairs
        pairs = await postgres_comparison_repository.get_comparison_pairs_for_batch(
            session=postgres_session,
            batch_id=batch.id,
        )

        # Should return empty list
        assert pairs == []

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_correct_tuple_format(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_essay_repository: PostgreSQLCJEssayRepository,
        postgres_comparison_repository: PostgreSQLCJComparisonRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test returns correct tuple format (essay_a_id, essay_b_id)."""

        # Create batch
        batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="tuple-format-batch",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=2,
        )

        # Create essays
        essay_a = await postgres_essay_repository.create_or_update_cj_processed_essay(
            session=postgres_session,
            cj_batch_id=batch.id,
            els_essay_id="essay-a-id",
            text_storage_id="storage-a",
            assessment_input_text="Essay A text",
        )

        essay_b = await postgres_essay_repository.create_or_update_cj_processed_essay(
            session=postgres_session,
            cj_batch_id=batch.id,
            els_essay_id="essay-b-id",
            text_storage_id="storage-b",
            assessment_input_text="Essay B text",
        )

        # Create comparison pair
        pair = ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id=essay_a.els_essay_id,
            essay_b_els_id=essay_b.els_essay_id,
            prompt_text="Compare",
            winner="essay_a",
            confidence=4.0,
        )
        postgres_session.add(pair)
        await postgres_session.flush()

        # Get comparison pairs
        pairs = await postgres_comparison_repository.get_comparison_pairs_for_batch(
            session=postgres_session,
            batch_id=batch.id,
        )

        # Should return correct tuple format
        assert len(pairs) == 1
        assert pairs[0] == ("essay-a-id", "essay-b-id")


class TestGetValidComparisonsForBatch:
    """Tests for get_valid_comparisons_for_batch method."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_only_comparisons_without_errors(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_essay_repository: PostgreSQLCJEssayRepository,
        postgres_comparison_repository: PostgreSQLCJComparisonRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test returns only comparisons where error_code is None."""

        # Create batch
        batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="valid-comparisons-batch",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=3,
        )

        # Create essays
        essay_1 = await postgres_essay_repository.create_or_update_cj_processed_essay(
            session=postgres_session,
            cj_batch_id=batch.id,
            els_essay_id="essay-1",
            text_storage_id="storage-1",
            assessment_input_text="Essay 1",
        )

        essay_2 = await postgres_essay_repository.create_or_update_cj_processed_essay(
            session=postgres_session,
            cj_batch_id=batch.id,
            els_essay_id="essay-2",
            text_storage_id="storage-2",
            assessment_input_text="Essay 2",
        )

        essay_3 = await postgres_essay_repository.create_or_update_cj_processed_essay(
            session=postgres_session,
            cj_batch_id=batch.id,
            els_essay_id="essay-3",
            text_storage_id="storage-3",
            assessment_input_text="Essay 3",
        )

        # Create valid comparison (no error)
        valid_pair = ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id=essay_1.els_essay_id,
            essay_b_els_id=essay_2.els_essay_id,
            prompt_text="Compare",
            winner="essay_a",
            confidence=4.0,
            error_code=None,
        )

        # Create comparison with error
        error_pair = ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id=essay_1.els_essay_id,
            essay_b_els_id=essay_3.els_essay_id,
            prompt_text="Compare",
            winner=None,
            confidence=None,
            error_code="LLM_PROVIDER_ERROR",
            error_correlation_id=uuid4(),
            error_timestamp=datetime.now(UTC),
            error_service="llm_provider_service",
            error_details={"message": "Rate limit exceeded"},
        )

        # Create another valid comparison
        valid_pair_2 = ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id=essay_2.els_essay_id,
            essay_b_els_id=essay_3.els_essay_id,
            prompt_text="Compare",
            winner="essay_b",
            confidence=3.5,
            error_code=None,
        )

        postgres_session.add_all([valid_pair, error_pair, valid_pair_2])
        await postgres_session.flush()

        # Get valid comparisons
        valid_comparisons = await postgres_comparison_repository.get_valid_comparisons_for_batch(
            session=postgres_session,
            batch_id=batch.id,
        )

        # Should return only the 2 valid comparisons
        assert len(valid_comparisons) == 2
        # Verify they are ComparisonPair objects
        assert all(isinstance(c, ComparisonPair) for c in valid_comparisons)
        # Verify none have error codes
        assert all(c.error_code is None for c in valid_comparisons)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_excludes_comparisons_with_errors(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_essay_repository: PostgreSQLCJEssayRepository,
        postgres_comparison_repository: PostgreSQLCJComparisonRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test excludes comparisons with errors."""

        # Create batch
        batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="error-exclusion-batch",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=2,
        )

        # Create essays
        essay_1 = await postgres_essay_repository.create_or_update_cj_processed_essay(
            session=postgres_session,
            cj_batch_id=batch.id,
            els_essay_id="essay-err-1",
            text_storage_id="storage-err-1",
            assessment_input_text="Essay 1",
        )

        essay_2 = await postgres_essay_repository.create_or_update_cj_processed_essay(
            session=postgres_session,
            cj_batch_id=batch.id,
            els_essay_id="essay-err-2",
            text_storage_id="storage-err-2",
            assessment_input_text="Essay 2",
        )

        # Create only error comparisons
        error_pair_1 = ComparisonPair(
            cj_batch_id=batch.id,
            essay_a_els_id=essay_1.els_essay_id,
            essay_b_els_id=essay_2.els_essay_id,
            prompt_text="Compare",
            error_code="TIMEOUT_ERROR",
            error_correlation_id=uuid4(),
            error_timestamp=datetime.now(UTC),
            error_service="llm_provider_service",
        )

        postgres_session.add(error_pair_1)
        await postgres_session.flush()

        # Get valid comparisons
        valid_comparisons = await postgres_comparison_repository.get_valid_comparisons_for_batch(
            session=postgres_session,
            batch_id=batch.id,
        )

        # Should return empty list (no valid comparisons)
        assert len(valid_comparisons) == 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_empty_list_for_batch_with_no_comparisons(
        self,
        postgres_batch_repository: PostgreSQLCJBatchRepository,
        postgres_comparison_repository: PostgreSQLCJComparisonRepository,
        postgres_session: AsyncSession,
    ) -> None:
        """Test returns empty list for batch with no comparisons."""

        # Create batch with no comparisons
        batch = await postgres_batch_repository.create_new_cj_batch(
            session=postgres_session,
            bos_batch_id="no-comparisons-batch",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=10,
        )
        await postgres_session.flush()

        # Get valid comparisons
        valid_comparisons = await postgres_comparison_repository.get_valid_comparisons_for_batch(
            session=postgres_session,
            batch_id=batch.id,
        )

        # Should return empty list
        assert valid_comparisons == []
