"""Unit tests for BatchProcessor module."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from common_core import EssayComparisonWinner
from common_core.status_enums import CJBatchStateEnum
from services.cj_assessment_service.cj_core_logic.batch_processor import (
    BatchConfigOverrides,
    BatchProcessor,
    BatchSubmissionResult,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.exceptions import (
    AssessmentProcessingError,
    DatabaseOperationError,
)
from services.cj_assessment_service.models_api import (
    ComparisonResult,
    ComparisonTask,
    EssayForComparison,
    LLMAssessmentResponseSchema,
)
from services.cj_assessment_service.models_db import CJBatchState
from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
    LLMInteractionProtocol,
)


class TestBatchProcessor:
    """Test cases for BatchProcessor class."""

    @pytest.fixture
    def mock_database(self) -> AsyncMock:
        """Create mock database protocol."""
        mock_db = AsyncMock(spec=CJRepositoryProtocol)
        mock_session = AsyncMock()
        mock_db.session.return_value.__aenter__.return_value = mock_session
        mock_db.session.return_value.__aexit__.return_value = None
        return mock_db

    @pytest.fixture
    def mock_llm_interaction(self) -> AsyncMock:
        """Create mock LLM interaction protocol."""
        return AsyncMock(spec=LLMInteractionProtocol)

    @pytest.fixture
    def settings(self) -> Settings:
        """Create settings for testing."""
        return Settings(DEFAULT_BATCH_SIZE=50)

    @pytest.fixture
    def batch_processor(
        self,
        mock_database: AsyncMock,
        mock_llm_interaction: AsyncMock,
        settings: Settings,
    ) -> BatchProcessor:
        """Create BatchProcessor instance for testing."""
        return BatchProcessor(
            database=mock_database,
            llm_interaction=mock_llm_interaction,
            settings=settings,
        )

    @pytest.fixture
    def sample_comparison_tasks(self) -> list[ComparisonTask]:
        """Create sample comparison tasks."""
        return [
            ComparisonTask(
                essay_a=EssayForComparison(
                    id="essay_a_1",
                    text_content="Sample essay A content",
                    current_bt_score=0.0,
                ),
                essay_b=EssayForComparison(
                    id="essay_b_1",
                    text_content="Sample essay B content",
                    current_bt_score=0.0,
                ),
                prompt="Compare these essays",
            ),
            ComparisonTask(
                essay_a=EssayForComparison(
                    id="essay_a_2",
                    text_content="Sample essay A2 content",
                    current_bt_score=0.0,
                ),
                essay_b=EssayForComparison(
                    id="essay_b_2",
                    text_content="Sample essay B2 content",
                    current_bt_score=0.0,
                ),
                prompt="Compare these essays",
            ),
        ]

    @pytest.fixture
    def sample_comparison_results(
        self, sample_comparison_tasks: list[ComparisonTask]
    ) -> list[ComparisonResult]:
        """Create sample comparison results."""
        return [
            ComparisonResult(
                task=sample_comparison_tasks[0],
                llm_assessment=LLMAssessmentResponseSchema(
                    winner=EssayComparisonWinner.ESSAY_A,
                    justification="Essay A is better",
                    confidence=4.0,
                ),
            ),
            ComparisonResult(
                task=sample_comparison_tasks[1],
                llm_assessment=LLMAssessmentResponseSchema(
                    winner=EssayComparisonWinner.ESSAY_B,
                    justification="Essay B is better",
                    confidence=3.0,
                ),
            ),
        ]

    @pytest.fixture
    def sample_batch_state(self) -> CJBatchState:
        """Create sample batch state."""
        batch_state = CJBatchState()
        batch_state.batch_id = 1
        batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        batch_state.total_comparisons = 100
        batch_state.submitted_comparisons = 50
        batch_state.completed_comparisons = 40
        batch_state.failed_comparisons = 5
        batch_state.completion_threshold_pct = 95
        return batch_state

    async def test_submit_comparison_batch_success(
        self,
        batch_processor: BatchProcessor,
        sample_comparison_tasks: list[ComparisonTask],
        sample_comparison_results: list[ComparisonResult],
        mock_llm_interaction: AsyncMock,
    ) -> None:
        """Test successful batch submission."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()
        mock_llm_interaction.perform_comparisons.return_value = sample_comparison_results

        # Act
        result = await batch_processor.submit_comparison_batch(
            cj_batch_id=cj_batch_id,
            comparison_tasks=sample_comparison_tasks,
            correlation_id=correlation_id,
        )

        # Assert
        assert isinstance(result, BatchSubmissionResult)
        assert result.batch_id == cj_batch_id
        assert result.total_submitted == len(sample_comparison_tasks)
        assert result.all_submitted is True
        assert result.correlation_id == correlation_id
        assert isinstance(result.submitted_at, datetime)

        # Verify LLM interaction was called
        mock_llm_interaction.perform_comparisons.assert_called_once()

    async def test_submit_comparison_batch_with_config_overrides(
        self,
        batch_processor: BatchProcessor,
        sample_comparison_tasks: list[ComparisonTask],
        sample_comparison_results: list[ComparisonResult],
        mock_llm_interaction: AsyncMock,
    ) -> None:
        """Test batch submission with configuration overrides."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()
        config_overrides = BatchConfigOverrides(
            batch_size=10,
            max_concurrent_batches=2,
            partial_completion_threshold=0.8,
        )
        mock_llm_interaction.perform_comparisons.return_value = sample_comparison_results

        # Act
        result = await batch_processor.submit_comparison_batch(
            cj_batch_id=cj_batch_id,
            comparison_tasks=sample_comparison_tasks,
            correlation_id=correlation_id,
            config_overrides=config_overrides,
        )

        # Assert
        assert result.total_submitted == len(sample_comparison_tasks)
        assert result.all_submitted is True

    async def test_submit_comparison_batch_empty_tasks(
        self,
        batch_processor: BatchProcessor,
    ) -> None:
        """Test batch submission with empty task list."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()
        empty_tasks: list[ComparisonTask] = []

        # Act & Assert
        with pytest.raises(AssessmentProcessingError) as exc_info:
            await batch_processor.submit_comparison_batch(
                cj_batch_id=cj_batch_id,
                comparison_tasks=empty_tasks,
                correlation_id=correlation_id,
            )

        assert "No comparison tasks provided" in str(exc_info.value)
        assert exc_info.value.correlation_id == correlation_id

    async def test_submit_comparison_batch_llm_failure(
        self,
        batch_processor: BatchProcessor,
        sample_comparison_tasks: list[ComparisonTask],
        mock_llm_interaction: AsyncMock,
    ) -> None:
        """Test batch submission with LLM failure."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()
        mock_llm_interaction.perform_comparisons.side_effect = Exception("LLM failure")

        # Act & Assert
        with pytest.raises(AssessmentProcessingError) as exc_info:
            await batch_processor.submit_comparison_batch(
                cj_batch_id=cj_batch_id,
                comparison_tasks=sample_comparison_tasks,
                correlation_id=correlation_id,
            )

        assert "Batch submission failed" in str(exc_info.value)
        assert exc_info.value.correlation_id == correlation_id

    async def test_check_batch_completion_completed_state(
        self,
        batch_processor: BatchProcessor,
        sample_batch_state: CJBatchState,
    ) -> None:
        """Test batch completion check for completed state."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()
        sample_batch_state.state = CJBatchStateEnum.COMPLETED

        # Act
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_processor.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = sample_batch_state
            is_complete = await batch_processor.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

        # Assert
        assert is_complete is True

    async def test_check_batch_completion_threshold_reached(
        self,
        batch_processor: BatchProcessor,
        sample_batch_state: CJBatchState,
    ) -> None:
        """Test batch completion check with threshold reached."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()
        sample_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        sample_batch_state.total_comparisons = 100
        sample_batch_state.completed_comparisons = 96  # 96% completion

        # Act
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_processor.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = sample_batch_state
            is_complete = await batch_processor.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

        # Assert
        assert is_complete is True

    async def test_check_batch_completion_threshold_not_reached(
        self,
        batch_processor: BatchProcessor,
        sample_batch_state: CJBatchState,
    ) -> None:
        """Test batch completion check with threshold not reached."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()
        sample_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        sample_batch_state.total_comparisons = 100
        sample_batch_state.completed_comparisons = 90  # 90% completion

        # Act
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_processor.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = sample_batch_state
            is_complete = await batch_processor.check_batch_completion(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

        # Assert
        assert is_complete is False

    async def test_check_batch_completion_batch_not_found(
        self,
        batch_processor: BatchProcessor,
    ) -> None:
        """Test batch completion check with batch not found."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()

        # Act & Assert
        with patch(
            "services.cj_assessment_service.cj_core_logic.batch_processor.get_batch_state",
            new_callable=AsyncMock,
        ) as mock_get_batch_state:
            mock_get_batch_state.return_value = None
            with pytest.raises(DatabaseOperationError) as exc_info:
                await batch_processor.check_batch_completion(
                    cj_batch_id=cj_batch_id,
                    correlation_id=correlation_id,
                )

            assert "Batch state not found" in str(exc_info.value)
            assert exc_info.value.correlation_id == correlation_id

    async def test_handle_batch_submission_with_request_data(
        self,
        batch_processor: BatchProcessor,
        sample_comparison_tasks: list[ComparisonTask],
        sample_comparison_results: list[ComparisonResult],
        mock_llm_interaction: AsyncMock,
    ) -> None:
        """Test batch submission handling with request data."""
        # Arrange
        cj_batch_id = 1
        correlation_id = uuid4()
        request_data = {
            "batch_config_overrides": {
                "batch_size": 25,
                "partial_completion_threshold": 0.9,
            },
            "llm_config_overrides": Mock(
                model_override="gpt-4",
                temperature_override=0.2,
                max_tokens_override=1000,
            ),
        }
        mock_llm_interaction.perform_comparisons.return_value = sample_comparison_results

        # Act
        result = await batch_processor.handle_batch_submission(
            cj_batch_id=cj_batch_id,
            comparison_tasks=sample_comparison_tasks,
            correlation_id=correlation_id,
            request_data=request_data,
        )

        # Assert
        assert isinstance(result, BatchSubmissionResult)
        assert result.batch_id == cj_batch_id
        assert result.total_submitted == len(sample_comparison_tasks)

        # Verify LLM interaction was called with overrides
        mock_llm_interaction.perform_comparisons.assert_called_once()
        call_args = mock_llm_interaction.perform_comparisons.call_args
        assert call_args.kwargs["model_override"] == "gpt-4"
        assert call_args.kwargs["temperature_override"] == 0.2
        assert call_args.kwargs["max_tokens_override"] == 1000

    # Note: Tests for _get_effective_batch_size, _get_effective_threshold, and _submit_batch_chunk
    # have been removed as these methods were extracted to separate modules during refactoring.


class TestBatchConfigOverrides:
    """Test cases for BatchConfigOverrides model."""

    def test_valid_config_overrides(self) -> None:
        """Test valid configuration overrides."""
        config = BatchConfigOverrides(
            batch_size=100,
            max_concurrent_batches=3,
            partial_completion_threshold=0.85,
        )

        assert config.batch_size == 100
        assert config.max_concurrent_batches == 3
        assert config.partial_completion_threshold == 0.85

    def test_invalid_batch_size(self) -> None:
        """Test invalid batch size validation."""
        with pytest.raises(ValueError):
            BatchConfigOverrides(batch_size=5)  # Below minimum

        with pytest.raises(ValueError):
            BatchConfigOverrides(batch_size=300)  # Above maximum

    def test_invalid_max_concurrent_batches(self) -> None:
        """Test invalid max concurrent batches validation."""
        with pytest.raises(ValueError):
            BatchConfigOverrides(max_concurrent_batches=0)  # Below minimum

        with pytest.raises(ValueError):
            BatchConfigOverrides(max_concurrent_batches=10)  # Above maximum

    def test_invalid_partial_completion_threshold(self) -> None:
        """Test invalid partial completion threshold validation."""
        with pytest.raises(ValueError):
            BatchConfigOverrides(partial_completion_threshold=0.3)  # Below minimum

        with pytest.raises(ValueError):
            BatchConfigOverrides(partial_completion_threshold=1.5)  # Above maximum

    def test_optional_fields(self) -> None:
        """Test optional fields default to None."""
        config = BatchConfigOverrides()

        assert config.batch_size is None
        assert config.max_concurrent_batches is None
        assert config.partial_completion_threshold is None


class TestBatchSubmissionResult:
    """Test cases for BatchSubmissionResult model."""

    def test_batch_submission_result_creation(self) -> None:
        """Test creation of BatchSubmissionResult."""
        batch_id = 1
        total_submitted = 50
        submitted_at = datetime.now()
        all_submitted = True
        correlation_id = uuid4()

        result = BatchSubmissionResult(
            batch_id=batch_id,
            total_submitted=total_submitted,
            submitted_at=submitted_at,
            all_submitted=all_submitted,
            correlation_id=correlation_id,
        )

        assert result.batch_id == batch_id
        assert result.total_submitted == total_submitted
        assert result.submitted_at == submitted_at
        assert result.all_submitted == all_submitted
        assert result.correlation_id == correlation_id

    def test_batch_submission_result_serialization(self) -> None:
        """Test serialization of BatchSubmissionResult."""
        result = BatchSubmissionResult(
            batch_id=1,
            total_submitted=50,
            submitted_at=datetime.now(),
            all_submitted=True,
            correlation_id=uuid4(),
        )

        # Should be able to serialize to dict
        result_dict = result.model_dump()
        assert "batch_id" in result_dict
        assert "total_submitted" in result_dict
        assert "submitted_at" in result_dict
        assert "all_submitted" in result_dict
        assert "correlation_id" in result_dict
