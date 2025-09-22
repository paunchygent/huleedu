"""Unit tests for BatchNlpAnalysisHandler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import aiohttp
import pytest
from aiokafka import ConsumerRecord
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.nlp_events import (
    BatchNlpProcessingRequestedV2,
    GrammarAnalysis,
    NlpMetrics,
)
from common_core.events.spellcheck_models import SpellcheckMetricsV1
from common_core.metadata_models import EssayProcessingInputRefV1
from huleedu_nlp_shared.feature_pipeline.feature_context import FeatureContext
from huleedu_nlp_shared.feature_pipeline.protocols import FeaturePipelineResult

from services.nlp_service.command_handlers.batch_nlp_analysis_handler import (
    BatchNlpAnalysisHandler,
)


@pytest.mark.asyncio
async def test_batch_nlp_analysis_handler_passes_prompt_text_to_pipeline_and_publisher() -> None:
    """Ensure essay instructions flow into feature pipeline and published events."""

    # Arrange mocks
    content_client = AsyncMock()
    content_client.fetch_content = AsyncMock(return_value="Sample essay content for analysis.")

    event_publisher = AsyncMock()
    event_publisher.publish_essay_nlp_completed = AsyncMock()
    event_publisher.publish_batch_nlp_analysis_completed = AsyncMock()

    outbox_repository = AsyncMock()
    feature_pipeline = AsyncMock()

    handler = BatchNlpAnalysisHandler(
        content_client=content_client,
        event_publisher=event_publisher,
        outbox_repository=outbox_repository,
        feature_pipeline=feature_pipeline,
        tracer=None,
    )

    batch_id = "batch-123"
    essay_id = "essay-456"
    instructions = "Compare themes of resilience and hope in the essay."

    command_data = BatchNlpProcessingRequestedV2(
        event_name=ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED_V2,
        batch_id=batch_id,
        entity_type="batch",
        entity_id=batch_id,
        essays_to_process=[
            EssayProcessingInputRefV1(essay_id=essay_id, text_storage_id="storage-1")
        ],
        language="en",
        essay_instructions=instructions,
    )

    envelope = EventEnvelope[BatchNlpProcessingRequestedV2](
        event_type=topic_name(ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED_V2),
        source_service="test-suite",
        correlation_id=uuid4(),
        data=command_data,
    )

    consumer_record = MagicMock(spec=ConsumerRecord)
    consumer_record.topic = envelope.event_type
    consumer_record.partition = 0
    consumer_record.offset = 0
    consumer_record.key = batch_id.encode()

    spellcheck_metrics = SpellcheckMetricsV1(
        total_corrections=0,
        l2_dictionary_corrections=0,
        spellchecker_corrections=0,
        word_count=120,
        correction_density=0.0,
    )

    feature_context = FeatureContext(
        normalized_text="Sample essay content for analysis.",
        spellcheck_metrics=spellcheck_metrics,
        prompt_text=instructions,
        essay_id=essay_id,
        batch_id=batch_id,
        language="en",
    )
    feature_context.nlp_metrics = NlpMetrics(
        word_count=120,
        sentence_count=6,
        avg_sentence_length=20.0,
        language_detected="en",
        processing_time_ms=1500,
    )
    feature_context.grammar_analysis = GrammarAnalysis(
        error_count=0,
        errors=[],
        language="en",
        processing_time_ms=500,
    )

    feature_pipeline.extract_features = AsyncMock(
        return_value=FeaturePipelineResult(features={}, context=feature_context)
    )

    http_session = AsyncMock(spec=aiohttp.ClientSession)

    # Act
    result = await handler.handle(
        msg=consumer_record,
        envelope=envelope,
        http_session=http_session,
        correlation_id=envelope.correlation_id,
        span=None,
    )

    # Assert
    assert result is True
    feature_pipeline.extract_features.assert_awaited_once()
    assert feature_pipeline.extract_features.await_args.kwargs["prompt_text"] == instructions
    event_publisher.publish_essay_nlp_completed.assert_awaited_once()
    assert (
        event_publisher.publish_essay_nlp_completed.await_args.kwargs["essay_instructions"]
        == instructions
    )
