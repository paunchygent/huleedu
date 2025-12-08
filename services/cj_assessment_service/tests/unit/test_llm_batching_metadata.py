"""Unit tests for CJ LLM batching metadata wiring.

Focus: preferred_bundle_size hints from CJ into LPS request metadata.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core import LLMBatchingMode

from services.cj_assessment_service.cj_core_logic import (
    comparison_batch_orchestrator as cbo,
)
from services.cj_assessment_service.cj_core_logic.comparison_request_normalizer import (
    ComparisonRequestNormalizer,
)
from services.cj_assessment_service.cj_core_logic.llm_batching_service import (
    BatchingModeService,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import (
    CJAssessmentRequestData,
    ComparisonTask,
    EssayForComparison,
    EssayToProcess,
)
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    LLMInteractionProtocol,
    PairMatchingStrategyProtocol,
    PairOrientationStrategyProtocol,
)
from services.cj_assessment_service.tests.unit.test_mocks.session_mocks import (
    MockSessionProvider,
)


@pytest.mark.asyncio
async def test_submit_initial_batch_sets_preferred_bundle_size_to_wave_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Initial batch metadata should include preferred_bundle_size == wave size."""

    settings = Settings()
    settings.LLM_BATCHING_MODE = LLMBatchingMode.SERIAL_BUNDLE
    settings.ENABLE_LLM_BATCHING_METADATA_HINTS = True

    session_provider = MockSessionProvider()
    batch_repository = AsyncMock(spec=CJBatchRepositoryProtocol)
    comparison_repository = AsyncMock(spec=CJComparisonRepositoryProtocol)
    instruction_repository = AsyncMock(spec=AssessmentInstructionRepositoryProtocol)
    llm_interaction = AsyncMock(spec=LLMInteractionProtocol)
    matching_strategy = AsyncMock(spec=PairMatchingStrategyProtocol)
    orientation_strategy = AsyncMock(spec=PairOrientationStrategyProtocol)

    batching_service = BatchingModeService(settings)
    orchestrator = cbo.ComparisonBatchOrchestrator(
        batch_repository=batch_repository,
        session_provider=session_provider,
        comparison_repository=comparison_repository,
        instruction_repository=instruction_repository,
        llm_interaction=llm_interaction,
        matching_strategy=matching_strategy,
        orientation_strategy=orientation_strategy,
        settings=settings,
        batching_service=batching_service,
        request_normalizer=ComparisonRequestNormalizer(settings),
    )

    essays_for_api_model = [
        EssayForComparison(id="essay-a", text_content="Essay A"),
        EssayForComparison(id="essay-b", text_content="Essay B"),
        EssayForComparison(id="essay-c", text_content="Essay C"),
        EssayForComparison(id="essay-d", text_content="Essay D"),
    ]

    # Simulate a single wave of comparison tasks for the batch.
    comparison_tasks = [
        ComparisonTask(
            essay_a=EssayForComparison(id=f"a-{i}", text_content="A"),
            essay_b=EssayForComparison(id=f"b-{i}", text_content="B"),
            prompt="Compare A and B",
        )
        for i in range(4)
    ]

    monkeypatch.setattr(
        cbo.pair_generation,
        "generate_comparison_tasks",
        AsyncMock(return_value=comparison_tasks),
    )
    monkeypatch.setattr(cbo, "merge_batch_processing_metadata", AsyncMock())

    captured_metadata: dict[str, Any] = {}

    class _DummyBatchProcessor:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - wiring
            pass

        async def submit_comparison_batch(self, *args: Any, **kwargs: Any) -> Any:
            nonlocal captured_metadata
            captured_metadata = dict(kwargs.get("metadata_context") or {})

            # Minimal submission result with attributes used by orchestrator logging.
            class _Result:
                def __init__(self, total: int) -> None:
                    self.total_submitted = total
                    self.all_submitted = True

            tasks = kwargs.get("comparison_tasks") or []
            return _Result(total=len(tasks))

    monkeypatch.setattr(cbo, "BatchProcessor", _DummyBatchProcessor)

    request_data = CJAssessmentRequestData(
        bos_batch_id="bos-test-123",
        assignment_id="assignment-1",
        essays_to_process=[
            EssayToProcess(els_essay_id="essay-a", text_storage_id="s1"),
            EssayToProcess(els_essay_id="essay-b", text_storage_id="s2"),
        ],
        language="en",
        course_code="eng5",
    )

    await orchestrator.submit_initial_batch(
        essays_for_api_model=essays_for_api_model,
        cj_batch_id=42,
        request_data=request_data,
        correlation_id=uuid4(),
        log_extra={},
    )

    # The preferred bundle size hint should match the number of comparison
    # tasks in this initial wave and respect the global cap of 64.
    assert captured_metadata["preferred_bundle_size"] == len(comparison_tasks)
    assert 1 <= captured_metadata["preferred_bundle_size"] <= 64
