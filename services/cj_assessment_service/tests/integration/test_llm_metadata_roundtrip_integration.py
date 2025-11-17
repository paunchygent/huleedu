"""Integration test ensuring CJ ↔ LPS metadata round-trip contract stays intact."""

from __future__ import annotations

import json
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from aiokafka import ConsumerRecord
from common_core import (
    LLMBatchingMode,
    LLMComparisonRequest,
    LLMProviderType,
)
from common_core import (
    LLMConfigOverridesHTTP as ProviderOverrides,
)
from common_core.domain_enums import EssayComparisonWinner

from services.cj_assessment_service.config import Settings as CJSettings
from services.cj_assessment_service.event_processor import process_llm_result
from services.cj_assessment_service.models_api import (
    CJLLMComparisonMetadata,
    ComparisonTask,
    EssayForComparison,
)
from services.llm_provider_service.config import Settings as LPSSettings
from services.llm_provider_service.implementations.queue_processor_impl import QueueProcessorImpl
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.internal_models import LLMOrchestratorResponse
from services.llm_provider_service.queue_models import QueuedRequest


@pytest.mark.asyncio
async def test_metadata_roundtrip_from_cj_to_lps_and_back() -> None:
    """Ensure CJ metadata survives the full CJ → LPS → CJ callback loop."""
    # Build CJ comparison task and metadata
    task = ComparisonTask(
        essay_a=EssayForComparison(id="essay-a", text_content="Essay A"),
        essay_b=EssayForComparison(id="essay-b", text_content="Essay B"),
        prompt="Compare essays",
    )
    metadata_adapter = CJLLMComparisonMetadata.from_comparison_task(
        task,
        bos_batch_id="bos-001",
    ).with_additional_context(cj_llm_batching_mode="per_request")
    request_metadata = metadata_adapter.to_request_metadata()

    correlation_id = uuid4()
    queue_id = uuid4()
    callback_topic = "test.llm.callback"

    request = LLMComparisonRequest(
        user_prompt=task.prompt,
        callback_topic=callback_topic,
        correlation_id=correlation_id,
        metadata=request_metadata,
        llm_config_overrides=ProviderOverrides(system_prompt_override="CJ Prompt"),
    )
    queued_request = QueuedRequest(
        queue_id=queue_id,
        request_data=request,
        size_bytes=len(request.model_dump_json()),
        callback_topic=callback_topic,
        correlation_id=correlation_id,
    )

    orchestrator_response = LLMOrchestratorResponse(
        winner=EssayComparisonWinner.ESSAY_A,
        justification="Essay A wins",
        confidence=0.9,
        provider=LLMProviderType.OPENAI,
        model="gpt-4o",
        response_time_ms=1200,
        token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        cost_estimate=0.02,
        correlation_id=correlation_id,
        metadata={"prompt_sha256": "abc123"},
    )

    lps_settings = LPSSettings()
    lps_settings.QUEUE_POLL_INTERVAL_SECONDS = 0.1
    lps_settings.QUEUE_MAX_RETRIES = 3
    lps_settings.QUEUE_PROCESSING_MODE = LLMBatchingMode.PER_REQUEST
    queue_processor = QueueProcessorImpl(
        comparison_processor=AsyncMock(),
        queue_manager=AsyncMock(),
        event_publisher=AsyncMock(),
        trace_context_manager=TraceContextManagerImpl(),
        settings=lps_settings,
    )

    await queue_processor._publish_callback_event(queued_request, orchestrator_response)

    publish_mock = cast(AsyncMock, queue_processor.event_publisher.publish_to_topic)
    publish_call = publish_mock.call_args
    event_data = publish_call[1]["envelope"].data
    assert event_data.request_id == str(queue_id)
    assert event_data.request_metadata["essay_a_id"] == "essay-a"
    assert event_data.request_metadata["bos_batch_id"] == "bos-001"
    assert event_data.request_metadata["prompt_sha256"] == "abc123"

    envelope_json = json.dumps(publish_call[1]["envelope"].model_dump(mode="json"))
    message = ConsumerRecord(
        topic=callback_topic,
        partition=0,
        offset=0,
        timestamp=0,
        timestamp_type=0,
        key=None,
        value=envelope_json.encode("utf-8"),
        checksum=None,
        serialized_key_size=0,
        serialized_value_size=len(envelope_json),
        headers=[],
    )

    mock_database = AsyncMock()
    mock_event_publisher = AsyncMock()
    mock_content_client = AsyncMock()
    mock_llm_interaction = AsyncMock()
    settings = CJSettings()

    with patch(
        "services.cj_assessment_service.message_handlers.llm_callback_handler.continue_cj_assessment_workflow",
        new_callable=AsyncMock,
    ) as mock_continue:
        result = await process_llm_result(
            msg=message,
            database=mock_database,
            event_publisher=mock_event_publisher,
            content_client=mock_content_client,
            llm_interaction=mock_llm_interaction,
            settings_obj=settings,
            tracer=None,
        )

    assert result is True
    mock_continue.assert_awaited_once()
    comparison_result = mock_continue.call_args[1]["comparison_result"]
    assert comparison_result.request_metadata == event_data.request_metadata
