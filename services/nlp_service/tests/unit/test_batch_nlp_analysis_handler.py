"""Unit tests for BatchNlpAnalysisHandler."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import aiohttp
import pytest
from aiokafka import ConsumerRecord
from common_core.domain_enums import ContentType
from common_core.error_enums import ErrorCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.nlp_events import (
    BatchNlpProcessingRequestedV2,
    GrammarAnalysis,
    NlpMetrics,
)
from common_core.events.spellcheck_models import SpellcheckMetricsV1
from common_core.models.error_models import ErrorDetail
from common_core.metadata_models import EssayProcessingInputRefV1, StorageReferenceMetadata
from huleedu_nlp_shared.feature_pipeline.feature_context import FeatureContext
from huleedu_nlp_shared.feature_pipeline.protocols import FeaturePipelineResult
from huleedu_service_libs.error_handling import HuleEduError

from services.nlp_service.command_handlers.batch_nlp_analysis_handler import (
    BatchNlpAnalysisHandler,
)
from services.nlp_service.metrics import get_metrics


@pytest.mark.asyncio
async def test_batch_nlp_analysis_handler_passes_prompt_text_to_pipeline_and_publisher() -> None:
    """Ensure hydrated prompt text flows into feature pipeline and published events."""

    # Arrange mocks
    content_client = AsyncMock()
    prompt_text = "Compare themes of resilience and hope in the essay."
    prompt_storage_id = "prompt-abc123"
    content_client.fetch_content = AsyncMock(
        side_effect=[prompt_text, "Sample essay content for analysis."]
    )

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

    command_data = BatchNlpProcessingRequestedV2(
        event_name=ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED_V2,
        batch_id=batch_id,
        entity_type="batch",
        entity_id=batch_id,
        essays_to_process=[
            EssayProcessingInputRefV1(essay_id=essay_id, text_storage_id="storage-1")
        ],
        language="en",
        student_prompt_ref=StorageReferenceMetadata(
            references={
                ContentType.STUDENT_PROMPT_TEXT: {
                    "storage_id": prompt_storage_id,
                    "path": "",
                }
            }
        ),
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
        prompt_text=prompt_text,
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
    assert content_client.fetch_content.await_count == 2
    first_call = content_client.fetch_content.await_args_list[0]
    assert first_call.kwargs["storage_id"] == prompt_storage_id

    feature_pipeline.extract_features.assert_awaited_once()
    assert feature_pipeline.extract_features.await_args.kwargs["prompt_text"] == prompt_text
    assert feature_pipeline.extract_features.await_args.kwargs["prompt_id"] == prompt_storage_id
    event_publisher.publish_essay_nlp_completed.assert_awaited_once()
    publish_kwargs = event_publisher.publish_essay_nlp_completed.await_args.kwargs
    assert publish_kwargs["prompt_text"] == prompt_text
    assert publish_kwargs["prompt_storage_id"] == prompt_storage_id


@pytest.mark.asyncio
async def test_batch_nlp_analysis_handler_records_metric_on_prompt_fetch_failure() -> None:
    """Ensure prompt fetch failures increment the dedicated Prometheus counter."""

    # Arrange
    prompt_storage_id = "prompt-missing"
    error_detail = ErrorDetail(
        error_code=ErrorCode.CONTENT_SERVICE_ERROR,
        message="Prompt fetch failed",
        correlation_id=uuid4(),
        timestamp=datetime.now(UTC),
        service="nlp_service",
        operation="fetch_content",
        details={},
    )
    content_client = AsyncMock()
    content_client.fetch_content = AsyncMock(
        side_effect=[HuleEduError(error_detail), "Essay body text."]
    )

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

    batch_id = "batch-789"
    essay_id = "essay-999"

    command_data = BatchNlpProcessingRequestedV2(
        event_name=ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED_V2,
        batch_id=batch_id,
        entity_type="batch",
        entity_id=batch_id,
        essays_to_process=[
            EssayProcessingInputRefV1(essay_id=essay_id, text_storage_id="storage-essay")
        ],
        language="en",
        student_prompt_ref=StorageReferenceMetadata(
            references={
                ContentType.STUDENT_PROMPT_TEXT: {
                    "storage_id": prompt_storage_id,
                    "path": "",
                }
            }
        ),
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
        normalized_text="Essay body text.",
        spellcheck_metrics=spellcheck_metrics,
        prompt_text=None,
        essay_id=essay_id,
        batch_id=batch_id,
        language="en",
    )
    feature_context.nlp_metrics = NlpMetrics(
        word_count=120,
        sentence_count=6,
        avg_sentence_length=20.0,
        language_detected="en",
        processing_time_ms=900,
    )
    feature_context.grammar_analysis = GrammarAnalysis(
        error_count=0,
        errors=[],
        language="en",
        processing_time_ms=350,
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
    # First fetch attempts prompt text and fails with HuleEduError
    assert content_client.fetch_content.await_count == 2
    first_call = content_client.fetch_content.await_args_list[0]
    assert first_call.kwargs["storage_id"] == prompt_storage_id

    feature_pipeline.extract_features.assert_awaited_once()
    assert feature_pipeline.extract_features.await_args.kwargs["prompt_text"] is None
    assert feature_pipeline.extract_features.await_args.kwargs["prompt_id"] == prompt_storage_id

    publish_kwargs = event_publisher.publish_essay_nlp_completed.await_args.kwargs
    assert publish_kwargs["prompt_text"] is None
    assert publish_kwargs["prompt_storage_id"] == prompt_storage_id

    counter = get_metrics()["prompt_fetch_failures"]
    assert counter.labels(reason="content_service_error")._value.get() == 1
