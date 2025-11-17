"""Unit tests for BatchRetryProcessor module."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from common_core import LLMBatchingMode, LLMProviderType
from huleedu_service_libs.error_handling import HuleEduError

from services.cj_assessment_service.cj_core_logic.batch_retry_processor import (
    BatchRetryProcessor,
)
from services.cj_assessment_service.cj_core_logic.batch_submission import (
    BatchSubmissionResult,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import (
    ComparisonTask,
    EssayForComparison,
)
from services.cj_assessment_service.protocols import (
    BatchProcessorProtocol,
    CJRepositoryProtocol,
    LLMInteractionProtocol,
)

# Import shared fixtures (includes mock_get_batch_state)
pytest_plugins = ["services.cj_assessment_service.tests.unit.conftest_pool"]
pytestmark = pytest.mark.usefixtures("mock_get_batch_state")


class TestBatchRetryProcessor:
    """Test cases for BatchRetryProcessor class."""

    @pytest.fixture
    def mock_settings(self) -> Settings:
        """Create mock settings."""
        mock_settings = Mock(spec=Settings)
        mock_settings.ENABLE_FAILED_COMPARISON_RETRY = True
        mock_settings.ENABLE_LLM_BATCHING_METADATA_HINTS = True
        mock_settings.DEFAULT_LLM_PROVIDER = LLMProviderType.OPENAI
        mock_settings.LLM_BATCHING_MODE = LLMBatchingMode.PER_REQUEST
        mock_settings.LLM_BATCH_API_ALLOWED_PROVIDERS = [LLMProviderType.OPENAI]
        return mock_settings

    @pytest.fixture
    def mock_database(self) -> AsyncMock:
        """Create mock database protocol."""
        mock_db = AsyncMock(spec=CJRepositoryProtocol)
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = AsyncMock()
        session_cm.__aexit__.return_value = AsyncMock()
        mock_db.session.return_value = session_cm
        return mock_db

    @pytest.fixture
    def mock_llm_interaction(self) -> AsyncMock:
        """Create mock LLM interaction protocol."""
        return AsyncMock(spec=LLMInteractionProtocol)

    @pytest.fixture
    def mock_pool_manager(self) -> AsyncMock:
        """Create mock pool manager."""
        from services.cj_assessment_service.cj_core_logic.batch_pool_manager import (
            BatchPoolManager,
        )

        return AsyncMock(spec=BatchPoolManager)

    @pytest.fixture
    def mock_batch_submitter(self) -> AsyncMock:
        """Create mock batch submitter protocol."""
        return AsyncMock(spec=BatchProcessorProtocol)

    @pytest.fixture
    def retry_processor(
        self,
        mock_database: AsyncMock,
        mock_llm_interaction: AsyncMock,
        mock_settings: Settings,
        mock_pool_manager: AsyncMock,
        mock_batch_submitter: AsyncMock,
    ) -> BatchRetryProcessor:
        """Create BatchRetryProcessor instance for testing."""
        return BatchRetryProcessor(
            database=mock_database,
            llm_interaction=mock_llm_interaction,
            settings=mock_settings,
            pool_manager=mock_pool_manager,
            batch_submitter=mock_batch_submitter,
        )

    @pytest.fixture
    def sample_comparison_task(self) -> ComparisonTask:
        """Create sample comparison task."""
        return ComparisonTask(
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
        )

    async def test_submit_retry_batch_success(
        self,
        retry_processor: BatchRetryProcessor,
        mock_pool_manager: AsyncMock,
        mock_batch_submitter: AsyncMock,
        sample_comparison_task: ComparisonTask,
    ) -> None:
        """Test successful retry batch submission."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()
        retry_tasks = [sample_comparison_task]

        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=1,
            submitted_at=datetime.now(),
            all_submitted=True,
            correlation_id=correlation_id,
        )

        mock_pool_manager.form_retry_batch.return_value = retry_tasks
        mock_batch_submitter.submit_comparison_batch.return_value = submission_result

        # Mock metrics
        with patch(
            "services.cj_assessment_service.metrics.get_business_metrics"
        ) as mock_get_metrics:
            mock_metric = Mock()
            mock_get_metrics.return_value = {"cj_retry_batches_submitted_total": mock_metric}

            # Act
            result = await retry_processor.submit_retry_batch(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert
            assert result is not None
            assert result.batch_id == cj_batch_id
            assert result.total_submitted == 1
            assert result.correlation_id == correlation_id

            # Verify method calls
            mock_pool_manager.form_retry_batch.assert_called_once_with(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
                force_retry_all=False,
            )
            mock_batch_submitter.submit_comparison_batch.assert_called_once()
            call_kwargs = mock_batch_submitter.submit_comparison_batch.call_args.kwargs
            assert call_kwargs["cj_batch_id"] == cj_batch_id
            assert call_kwargs["metadata_context"]["cj_batch_id"] == str(cj_batch_id)
            assert call_kwargs["metadata_context"]["cj_request_type"] == "cj_retry"

            # Verify metrics
            mock_metric.inc.assert_called_once()

    async def test_submit_retry_batch_uses_persisted_overrides(
        self,
        retry_processor: BatchRetryProcessor,
        mock_pool_manager: AsyncMock,
        mock_batch_submitter: AsyncMock,
        mock_get_batch_state: AsyncMock,
        sample_comparison_task: ComparisonTask,
    ) -> None:
        """Ensure retry submits reuse persisted LLM overrides when they exist."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()
        retry_tasks = [sample_comparison_task]

        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=1,
            submitted_at=datetime.now(),
            all_submitted=True,
            correlation_id=correlation_id,
        )

        overrides_metadata = {
            "model_override": "persisted-model",
            "temperature_override": 0.2,
            "max_tokens_override": 1500,
            "system_prompt_override": "Persisted system prompt",
            "provider_override": "anthropic",
        }

        mock_pool_manager.form_retry_batch.return_value = retry_tasks
        mock_batch_submitter.submit_comparison_batch.return_value = submission_result
        mock_get_batch_state.return_value = SimpleNamespace(
            processing_metadata={
                "llm_overrides": overrides_metadata,
                "original_request": {"cj_source": "eng5_runner"},
            }
        )

        # Mock metrics
        with patch(
            "services.cj_assessment_service.metrics.get_business_metrics"
        ) as mock_get_metrics:
            mock_metric = Mock()
            mock_get_metrics.return_value = {"cj_retry_batches_submitted_total": mock_metric}

            # Act
            result = await retry_processor.submit_retry_batch(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert
            assert result is not None
            call_args = mock_batch_submitter.submit_comparison_batch.call_args
            assert call_args[1]["model_override"] == overrides_metadata["model_override"]
            assert (
                call_args[1]["temperature_override"] == overrides_metadata["temperature_override"]
            )
            assert call_args[1]["max_tokens_override"] == overrides_metadata["max_tokens_override"]
            assert (
                call_args[1]["system_prompt_override"]
                == overrides_metadata["system_prompt_override"]
            )
            assert call_args[1]["provider_override"] == overrides_metadata["provider_override"]
            metadata_context = call_args[1]["metadata_context"]
            assert metadata_context["cj_source"] == "eng5_runner"
            assert metadata_context["cj_request_type"] == "cj_retry"

    async def test_submit_retry_batch_disabled(
        self,
        retry_processor: BatchRetryProcessor,
        mock_settings: Settings,
    ) -> None:
        """Test retry batch submission when retry is disabled."""
        # Arrange
        mock_settings.ENABLE_FAILED_COMPARISON_RETRY = False
        cj_batch_id = 123
        correlation_id = uuid4()

        # Act
        result = await retry_processor.submit_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is None

    async def test_submit_retry_batch_no_tasks(
        self,
        retry_processor: BatchRetryProcessor,
        mock_pool_manager: AsyncMock,
    ) -> None:
        """Test retry batch submission when no tasks are available."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        mock_pool_manager.form_retry_batch.return_value = None

        # Act
        result = await retry_processor.submit_retry_batch(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is None
        mock_pool_manager.form_retry_batch.assert_called_once()

    async def test_submit_retry_batch_with_overrides(
        self,
        retry_processor: BatchRetryProcessor,
        mock_pool_manager: AsyncMock,
        mock_batch_submitter: AsyncMock,
        sample_comparison_task: ComparisonTask,
    ) -> None:
        """Test retry batch submission with model overrides."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()
        model_override = "test-model"
        temperature_override = 0.7
        max_tokens_override = 1000
        retry_tasks = [sample_comparison_task]

        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=1,
            submitted_at=datetime.now(),
            all_submitted=True,
            correlation_id=correlation_id,
        )

        mock_pool_manager.form_retry_batch.return_value = retry_tasks
        mock_batch_submitter.submit_comparison_batch.return_value = submission_result

        # Mock metrics
        with patch(
            "services.cj_assessment_service.metrics.get_business_metrics"
        ) as mock_get_metrics:
            mock_metric = Mock()
            mock_get_metrics.return_value = {"cj_retry_batches_submitted_total": mock_metric}

            # Act
            result = await retry_processor.submit_retry_batch(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
                model_override=model_override,
                temperature_override=temperature_override,
                max_tokens_override=max_tokens_override,
                provider_override="openai",
            )

            # Assert
            assert result is not None
            mock_batch_submitter.submit_comparison_batch.assert_called_once()

            # Verify overrides were passed
            call_args = mock_batch_submitter.submit_comparison_batch.call_args
            assert call_args[1]["model_override"] == model_override
            assert call_args[1]["temperature_override"] == temperature_override
            assert call_args[1]["max_tokens_override"] == max_tokens_override
            assert call_args[1]["system_prompt_override"] is None
            assert call_args[1]["provider_override"] == "openai"

    async def test_submit_retry_batch_force_retry_all(
        self,
        retry_processor: BatchRetryProcessor,
        mock_pool_manager: AsyncMock,
        mock_batch_submitter: AsyncMock,
        sample_comparison_task: ComparisonTask,
    ) -> None:
        """Test retry batch submission with force_retry_all=True."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()
        retry_tasks = [sample_comparison_task] * 3  # Multiple tasks

        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=3,
            submitted_at=datetime.now(),
            all_submitted=True,
            correlation_id=correlation_id,
        )

        mock_pool_manager.form_retry_batch.return_value = retry_tasks
        mock_batch_submitter.submit_comparison_batch.return_value = submission_result

        # Mock metrics
        with patch(
            "services.cj_assessment_service.metrics.get_business_metrics"
        ) as mock_get_metrics:
            mock_metric = Mock()
            mock_get_metrics.return_value = {"cj_retry_batches_submitted_total": mock_metric}

            # Act
            result = await retry_processor.submit_retry_batch(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
                force_retry_all=True,
            )

            # Assert
            assert result is not None
            assert result.total_submitted == 3

            # Verify force_retry_all was passed
            mock_pool_manager.form_retry_batch.assert_called_once_with(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
                force_retry_all=True,
            )

    async def test_submit_retry_batch_form_retry_failure(
        self,
        retry_processor: BatchRetryProcessor,
        mock_pool_manager: AsyncMock,
    ) -> None:
        """Test retry batch submission when form_retry_batch fails."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        mock_pool_manager.form_retry_batch.side_effect = Exception("Pool formation failed")

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await retry_processor.submit_retry_batch(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

        assert "Failed to submit retry batch" in str(exc_info.value)
        assert exc_info.value.correlation_id == str(correlation_id)
        assert exc_info.value.error_detail.details["batch_id"] == str(cj_batch_id)
        assert exc_info.value.error_detail.details["processing_stage"] == "retry_batch_submission"

    async def test_submit_retry_batch_submission_failure(
        self,
        retry_processor: BatchRetryProcessor,
        mock_pool_manager: AsyncMock,
        mock_batch_submitter: AsyncMock,
        sample_comparison_task: ComparisonTask,
    ) -> None:
        """Test retry batch submission when submission fails."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()
        retry_tasks = [sample_comparison_task]

        mock_pool_manager.form_retry_batch.return_value = retry_tasks
        mock_batch_submitter.submit_comparison_batch.side_effect = Exception("Submission failed")

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await retry_processor.submit_retry_batch(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

        assert "Failed to submit retry batch" in str(exc_info.value)
        assert exc_info.value.correlation_id == str(correlation_id)
        assert exc_info.value.error_detail.details["batch_id"] == str(cj_batch_id)

    async def test_process_remaining_failed_comparisons_success(
        self,
        retry_processor: BatchRetryProcessor,
        mock_pool_manager: AsyncMock,
        mock_batch_submitter: AsyncMock,
        sample_comparison_task: ComparisonTask,
    ) -> None:
        """Test processing remaining failed comparisons successfully."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()
        retry_tasks = [sample_comparison_task] * 2

        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=2,
            submitted_at=datetime.now(),
            all_submitted=True,
            correlation_id=correlation_id,
        )

        mock_pool_manager.form_retry_batch.return_value = retry_tasks
        mock_batch_submitter.submit_comparison_batch.return_value = submission_result

        # Mock metrics
        with patch(
            "services.cj_assessment_service.metrics.get_business_metrics"
        ) as mock_get_metrics:
            mock_metric = Mock()
            mock_get_metrics.return_value = {"cj_retry_batches_submitted_total": mock_metric}

            # Act
            result = await retry_processor.process_remaining_failed_comparisons(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert
            assert result is not None
            assert result.total_submitted == 2

            # Verify force_retry_all=True was used
            mock_pool_manager.form_retry_batch.assert_called_once_with(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
                force_retry_all=True,
            )

    async def test_process_remaining_failed_comparisons_with_overrides(
        self,
        retry_processor: BatchRetryProcessor,
        mock_pool_manager: AsyncMock,
        mock_batch_submitter: AsyncMock,
        sample_comparison_task: ComparisonTask,
    ) -> None:
        """Test processing remaining failed comparisons with model overrides."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()
        model_override = "end-of-batch-model"
        temperature_override = 0.3
        max_tokens_override = 500
        retry_tasks = [sample_comparison_task]

        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=1,
            submitted_at=datetime.now(),
            all_submitted=True,
            correlation_id=correlation_id,
        )

        mock_pool_manager.form_retry_batch.return_value = retry_tasks
        mock_batch_submitter.submit_comparison_batch.return_value = submission_result

        # Mock metrics
        with patch(
            "services.cj_assessment_service.metrics.get_business_metrics"
        ) as mock_get_metrics:
            mock_metric = Mock()
            mock_get_metrics.return_value = {"cj_retry_batches_submitted_total": mock_metric}

            # Act
            result = await retry_processor.process_remaining_failed_comparisons(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
                model_override=model_override,
                temperature_override=temperature_override,
                max_tokens_override=max_tokens_override,
                provider_override="anthropic",
            )

            # Assert
            assert result is not None

            # Verify overrides were passed through
            call_args = mock_batch_submitter.submit_comparison_batch.call_args
            assert call_args[1]["model_override"] == model_override
            assert call_args[1]["temperature_override"] == temperature_override
            assert call_args[1]["max_tokens_override"] == max_tokens_override
            assert call_args[1]["provider_override"] == "anthropic"

    async def test_process_remaining_failed_comparisons_no_failures(
        self,
        retry_processor: BatchRetryProcessor,
        mock_pool_manager: AsyncMock,
    ) -> None:
        """Test processing remaining failed comparisons when no failures remain."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        mock_pool_manager.form_retry_batch.return_value = None

        # Act
        result = await retry_processor.process_remaining_failed_comparisons(
            cj_batch_id=cj_batch_id,
            correlation_id=correlation_id,
        )

        # Assert
        assert result is None

    async def test_process_remaining_failed_comparisons_failure(
        self,
        retry_processor: BatchRetryProcessor,
        mock_pool_manager: AsyncMock,
    ) -> None:
        """Test processing remaining failed comparisons when operation fails."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        mock_pool_manager.form_retry_batch.side_effect = Exception(
            "Failed to form end-of-batch retry"
        )

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await retry_processor.process_remaining_failed_comparisons(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

        assert "Failed to process remaining failed comparisons" in str(exc_info.value)
        assert exc_info.value.correlation_id == str(correlation_id)
        assert exc_info.value.error_detail.details["batch_id"] == str(cj_batch_id)
        assert (
            exc_info.value.error_detail.details["processing_stage"]
            == "end_of_batch_retry_processing"
        )

    async def test_end_of_batch_fairness_scenario(
        self,
        retry_processor: BatchRetryProcessor,
        mock_pool_manager: AsyncMock,
        mock_batch_submitter: AsyncMock,
        sample_comparison_task: ComparisonTask,
    ) -> None:
        """Test end-of-batch fairness processing workflow."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()

        # Simulate 3 remaining failures at end of batch
        retry_tasks = [sample_comparison_task] * 3

        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=3,
            submitted_at=datetime.now(),
            all_submitted=True,
            correlation_id=correlation_id,
        )

        mock_pool_manager.form_retry_batch.return_value = retry_tasks
        mock_batch_submitter.submit_comparison_batch.return_value = submission_result

        # Mock metrics
        with patch(
            "services.cj_assessment_service.metrics.get_business_metrics"
        ) as mock_get_metrics:
            mock_metric = Mock()
            mock_get_metrics.return_value = {"cj_retry_batches_submitted_total": mock_metric}

            # Act - Simulate end-of-batch processing
            result = await retry_processor.process_remaining_failed_comparisons(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert
            assert result is not None
            assert result.total_submitted == 3
            assert result.all_submitted is True

            # Verify force_retry_all=True was used for fairness
            mock_pool_manager.form_retry_batch.assert_called_once_with(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
                force_retry_all=True,  # KEY: Ensures fairness processing
            )

            # Verify metrics were updated
            mock_metric.inc.assert_called_once()

    async def test_retry_batch_submission_result_validation(
        self,
        retry_processor: BatchRetryProcessor,
        mock_pool_manager: AsyncMock,
        mock_batch_submitter: AsyncMock,
        sample_comparison_task: ComparisonTask,
    ) -> None:
        """Test validation of retry batch submission result fields."""
        # Arrange
        cj_batch_id = 123
        correlation_id = uuid4()
        retry_tasks = [sample_comparison_task]

        # Create result with specific timestamp
        submitted_at = datetime.now()
        submission_result = BatchSubmissionResult(
            batch_id=cj_batch_id,
            total_submitted=1,
            submitted_at=submitted_at,
            all_submitted=True,
            correlation_id=correlation_id,
        )

        mock_pool_manager.form_retry_batch.return_value = retry_tasks
        mock_batch_submitter.submit_comparison_batch.return_value = submission_result

        # Mock metrics
        with patch(
            "services.cj_assessment_service.metrics.get_business_metrics"
        ) as mock_get_metrics:
            mock_metric = Mock()
            mock_get_metrics.return_value = {"cj_retry_batches_submitted_total": mock_metric}

            # Act
            result = await retry_processor.submit_retry_batch(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )

            # Assert all result fields
            assert result is not None
            assert result.batch_id == cj_batch_id
            assert result.total_submitted == 1
            assert result.submitted_at == submitted_at
            assert result.all_submitted is True
            assert result.correlation_id == correlation_id
