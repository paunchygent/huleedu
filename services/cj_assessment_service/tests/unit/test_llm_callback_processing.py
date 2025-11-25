"""Unit tests for LLM callback processing in CJ Assessment Service."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from aiokafka import ConsumerRecord
from common_core import LLMProviderType
from common_core.domain_enums import EssayComparisonWinner
from common_core.error_enums import ErrorCode
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1
from common_core.models.error_models import ErrorDetail
from huleedu_service_libs.error_handling import create_error_detail_with_context

from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.event_processor import process_llm_result
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
    SessionProviderProtocol,
)


@pytest.fixture
def mock_grade_projector_local() -> AsyncMock:
    """Create mock grade projector for testing."""
    return AsyncMock(spec=GradeProjector)


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.LLM_PROVIDER_CALLBACK_TOPIC = "llm-provider-callbacks"
    settings.PARALLEL_COMPARISONS_PER_ASSESSMENT = 3
    return settings


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Create mock event publisher protocol."""
    return AsyncMock(spec=CJEventPublisherProtocol)


@pytest.fixture
def mock_llm_interaction() -> AsyncMock:
    """Create mock LLM interaction protocol."""
    return AsyncMock(spec=LLMInteractionProtocol)


@pytest.fixture
def mock_session_provider() -> AsyncMock:
    """Create mock session provider protocol."""
    return AsyncMock(spec=SessionProviderProtocol)


@pytest.fixture
def mock_batch_repository() -> AsyncMock:
    """Create mock batch repository protocol."""
    return AsyncMock(spec=CJBatchRepositoryProtocol)


@pytest.fixture
def mock_essay_repository() -> AsyncMock:
    """Create mock essay repository protocol."""
    return AsyncMock(spec=CJEssayRepositoryProtocol)


@pytest.fixture
def mock_comparison_repository() -> AsyncMock:
    """Create mock comparison repository protocol."""
    return AsyncMock(spec=CJComparisonRepositoryProtocol)


def create_llm_callback_message(
    request_id: str,
    correlation_id: str,
    is_error: bool = False,
    winner: str | None = "Essay A",
    justification: str | None = "Better structure",
    confidence: float = 4.5,
    error_detail: ErrorDetail | None = None,
    request_metadata: dict[str, Any] | None = None,
) -> ConsumerRecord:
    """Create a mock Kafka message with LLM callback data."""
    # Create the LLM comparison result
    correlation_uuid = UUID(correlation_id) if isinstance(correlation_id, str) else correlation_id
    now = datetime.now(UTC)

    if is_error:
        result = LLMComparisonResultV1(
            request_id=request_id,
            correlation_id=correlation_uuid,
            error_detail=error_detail
            or create_error_detail_with_context(
                error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
                message="LLM provider failed",
                service="llm_provider_service",
                operation="generate_comparison",
                correlation_id=uuid4(),
            ),
            winner=None,
            justification=None,
            confidence=None,
            provider=LLMProviderType.ANTHROPIC,
            model="claude-3-haiku",
            response_time_ms=1500,
            cost_estimate=0.001,
            requested_at=now,
            completed_at=now,
            trace_id=None,
            request_metadata=request_metadata or {},
        )
    else:
        winner_enum = EssayComparisonWinner.ESSAY_A
        if winner == "Essay A":
            winner_enum = EssayComparisonWinner.ESSAY_A
        else:
            winner_enum = EssayComparisonWinner.ESSAY_B
        result = LLMComparisonResultV1(
            request_id=request_id,
            correlation_id=correlation_uuid,
            winner=winner_enum,
            justification=justification,
            confidence=confidence,
            provider=LLMProviderType.ANTHROPIC,
            model="claude-3-haiku",
            response_time_ms=1500,
            cost_estimate=0.001,
            requested_at=now,
            completed_at=now,
            trace_id=None,
            error_detail=None,
            request_metadata=request_metadata or {},
        )

    # Wrap in event envelope
    envelope: EventEnvelope[LLMComparisonResultV1] = EventEnvelope(
        event_type="llm_comparison_result_v1",
        event_timestamp=datetime.now(UTC),
        source_service="llm_provider_service",
        correlation_id=uuid4(),
        data=result,
    )

    # Create Kafka message
    return ConsumerRecord(
        topic="llm-provider-callbacks",
        partition=0,
        offset=100,
        timestamp=int(datetime.now(UTC).timestamp() * 1000),
        timestamp_type=0,
        key=None,
        value=envelope.model_dump_json().encode(),
        checksum=None,
        serialized_key_size=0,
        serialized_value_size=len(envelope.model_dump_json()),
        headers=[],
    )


class TestLLMCallbackProcessing:
    """Test cases for processing LLM comparison callbacks."""

    @patch(
        "services.cj_assessment_service.message_handlers.llm_callback_handler.continue_cj_assessment_workflow"
    )
    async def test_process_llm_result_success(
        self,
        mock_continue_workflow: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
        mock_llm_interaction: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_essay_repository: AsyncMock,
        mock_comparison_repository: AsyncMock,
        mock_grade_projector_local: AsyncMock,
    ) -> None:
        """Test successful processing of LLM comparison result."""
        # Arrange
        request_id = str(uuid4())
        correlation_id = str(uuid4())

        # Create success callback message
        msg = create_llm_callback_message(
            request_id=request_id,
            correlation_id=correlation_id,
            is_error=False,
            winner="Essay A",
            justification="Clear and concise",
            confidence=4.8,
        )

        # Act
        # Create mock content client
        mock_content_client = AsyncMock(spec=ContentClientProtocol)

        result = await process_llm_result(
            msg=msg,
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            essay_repository=mock_essay_repository,
            comparison_repository=mock_comparison_repository,
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            event_publisher=mock_event_publisher,
            content_client=mock_content_client,
            llm_interaction=mock_llm_interaction,
            settings_obj=mock_settings,
            grade_projector=mock_grade_projector_local,
            tracer=None,
        )

        # Assert
        assert result is True

        # Verify workflow was called with correct data
        mock_continue_workflow.assert_called_once()
        call_args = mock_continue_workflow.call_args[1]

        comparison_result = call_args["comparison_result"]
        assert comparison_result.request_id == request_id
        assert comparison_result.is_error is False
        assert comparison_result.winner == "Essay A"
        assert comparison_result.justification == "Clear and concise"
        assert comparison_result.confidence == 4.8

    @patch(
        "services.cj_assessment_service.message_handlers.llm_callback_handler.continue_cj_assessment_workflow"
    )
    async def test_process_llm_result_error_callback(
        self,
        mock_continue_workflow: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
        mock_llm_interaction: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_essay_repository: AsyncMock,
        mock_comparison_repository: AsyncMock,
        mock_grade_projector_local: AsyncMock,
    ) -> None:
        """Test processing of error callback from LLM provider."""
        # Arrange
        request_id = str(uuid4())
        correlation_id = str(uuid4())

        # Create error callback message
        msg = create_llm_callback_message(
            request_id=request_id,
            correlation_id=correlation_id,
            is_error=True,
        )

        # Act
        # Create mock content client
        mock_content_client = AsyncMock(spec=ContentClientProtocol)

        result = await process_llm_result(
            msg=msg,
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            essay_repository=mock_essay_repository,
            comparison_repository=mock_comparison_repository,
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            event_publisher=mock_event_publisher,
            content_client=mock_content_client,
            llm_interaction=mock_llm_interaction,
            settings_obj=mock_settings,
            grade_projector=mock_grade_projector_local,
            tracer=None,
        )

        # Assert
        assert result is True

        # Verify workflow was called with error data
        mock_continue_workflow.assert_called_once()
        call_args = mock_continue_workflow.call_args[1]

        comparison_result = call_args["comparison_result"]
        assert comparison_result.request_id == request_id
        assert comparison_result.is_error is True
        assert comparison_result.error_detail is not None

    @patch(
        "services.cj_assessment_service.message_handlers.llm_callback_handler.continue_cj_assessment_workflow"
    )
    async def test_process_llm_result_preserves_request_metadata(
        self,
        mock_continue_workflow: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
        mock_llm_interaction: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_essay_repository: AsyncMock,
        mock_comparison_repository: AsyncMock,
        mock_grade_projector_local: AsyncMock,
    ) -> None:
        """Ensure additive metadata is available to downstream workflow logic."""
        request_metadata = {
            "essay_a_id": "essay-a",
            "essay_b_id": "essay-b",
            "cj_llm_batching_mode": "per_request",
        }
        msg = create_llm_callback_message(
            request_id=str(uuid4()),
            correlation_id=str(uuid4()),
            request_metadata=request_metadata,
        )

        mock_content_client = AsyncMock(spec=ContentClientProtocol)
        await process_llm_result(
            msg=msg,
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            essay_repository=mock_essay_repository,
            comparison_repository=mock_comparison_repository,
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            event_publisher=mock_event_publisher,
            content_client=mock_content_client,
            llm_interaction=mock_llm_interaction,
            settings_obj=mock_settings,
            grade_projector=mock_grade_projector_local,
            tracer=None,
        )

        comparison_result = mock_continue_workflow.call_args[1]["comparison_result"]
        assert comparison_result.request_metadata == request_metadata

    @patch(
        "services.cj_assessment_service.message_handlers.llm_callback_handler.continue_cj_assessment_workflow"
    )
    async def test_process_llm_result_invalid_message(
        self,
        mock_continue_workflow: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
        mock_llm_interaction: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_essay_repository: AsyncMock,
        mock_comparison_repository: AsyncMock,
        mock_grade_projector_local: AsyncMock,
    ) -> None:
        """Test handling of invalid callback messages."""
        # Create invalid message (not proper JSON)
        msg = ConsumerRecord(
            topic="llm-provider-callbacks",
            partition=0,
            offset=100,
            timestamp=int(datetime.now(UTC).timestamp() * 1000),
            timestamp_type=0,
            key=None,
            value=b"invalid json data",
            checksum=None,
            serialized_key_size=0,
            serialized_value_size=17,
            headers=[],
        )

        # Act
        # Create mock content client
        mock_content_client = AsyncMock(spec=ContentClientProtocol)

        result = await process_llm_result(
            msg=msg,
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            essay_repository=mock_essay_repository,
            comparison_repository=mock_comparison_repository,
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            event_publisher=mock_event_publisher,
            content_client=mock_content_client,
            llm_interaction=mock_llm_interaction,
            settings_obj=mock_settings,
            grade_projector=mock_grade_projector_local,
            tracer=None,
        )

        # Assert
        assert result is True  # Still acknowledge to prevent reprocessing

        # Verify workflow was not called
        mock_continue_workflow.assert_not_called()

    @patch(
        "services.cj_assessment_service.message_handlers.llm_callback_handler.continue_cj_assessment_workflow"
    )
    async def test_process_llm_result_workflow_error(
        self,
        mock_continue_workflow: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
        mock_llm_interaction: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_essay_repository: AsyncMock,
        mock_comparison_repository: AsyncMock,
        mock_grade_projector_local: AsyncMock,
    ) -> None:
        """Test handling when workflow processing fails."""
        # Arrange
        request_id = str(uuid4())
        correlation_id = str(uuid4())

        # Mock workflow error
        mock_continue_workflow.side_effect = Exception("Database connection failed")

        # Create callback message
        msg = create_llm_callback_message(
            request_id=request_id,
            correlation_id=correlation_id,
            is_error=False,
        )

        # Act
        # Create mock content client
        mock_content_client = AsyncMock(spec=ContentClientProtocol)

        result = await process_llm_result(
            msg=msg,
            session_provider=mock_session_provider,
            batch_repository=mock_batch_repository,
            essay_repository=mock_essay_repository,
            comparison_repository=mock_comparison_repository,
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            event_publisher=mock_event_publisher,
            content_client=mock_content_client,
            llm_interaction=mock_llm_interaction,
            settings_obj=mock_settings,
            grade_projector=mock_grade_projector_local,
            tracer=None,
        )

        # Assert
        assert result is True  # Still acknowledge to prevent reprocessing
        mock_continue_workflow.assert_called_once()

    @patch(
        "services.cj_assessment_service.message_handlers.llm_callback_handler.continue_cj_assessment_workflow"
    )
    async def test_process_llm_result_multiple_callbacks(
        self,
        mock_continue_workflow: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_settings: Settings,
        mock_llm_interaction: AsyncMock,
        mock_session_provider: AsyncMock,
        mock_batch_repository: AsyncMock,
        mock_essay_repository: AsyncMock,
        mock_comparison_repository: AsyncMock,
        mock_grade_projector_local: AsyncMock,
    ) -> None:
        """Test processing multiple callbacks in sequence."""
        # Arrange
        request_ids = [str(uuid4()) for _ in range(3)]

        # Process multiple callbacks
        # Create mock content client
        mock_content_client = AsyncMock(spec=ContentClientProtocol)

        for i, request_id in enumerate(request_ids):
            msg = create_llm_callback_message(
                request_id=request_id,
                correlation_id=str(uuid4()),
                is_error=False,
                winner=f"Essay {'A' if i % 2 == 0 else 'B'}",
                confidence=4.0 + i * 0.5,
            )

            result = await process_llm_result(
                msg=msg,
                session_provider=mock_session_provider,
                batch_repository=mock_batch_repository,
                essay_repository=mock_essay_repository,
                comparison_repository=mock_comparison_repository,
                instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
                event_publisher=mock_event_publisher,
                content_client=mock_content_client,
                llm_interaction=mock_llm_interaction,
                settings_obj=mock_settings,
                grade_projector=mock_grade_projector_local,
                tracer=None,
            )

            assert result is True

        # Verify all callbacks were processed
        assert mock_continue_workflow.call_count == 3
