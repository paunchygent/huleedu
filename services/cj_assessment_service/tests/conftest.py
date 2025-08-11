"""
Pytest configuration and fixtures for CJ Assessment Service tests.

This module provides fixtures for testing the CJ assessment service
with dependency injection and mocked external dependencies.
"""

from __future__ import annotations

import json
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import aiohttp
import pytest
from aiokafka import AIOKafkaProducer, ConsumerRecord

# CRITICAL: Import ALL enum types FIRST
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name

# Import models that need rebuilding
from common_core.events.base_event_models import (
    BaseEventData,
    ProcessingUpdate,
)
from common_core.events.cj_assessment_events import (
    CJAssessmentCompletedV1,
    CJAssessmentFailedV1,
    ELS_CJAssessmentRequestV1,
    LLMConfigOverrides,
)
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)
from common_core.status_enums import ProcessingStage
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.tests.unit.mocks import MockDatabase, MockRedisClient

# NOW rebuild models with all types available
BaseEventData.model_rebuild(raise_errors=True)
ProcessingUpdate.model_rebuild(raise_errors=True)
LLMConfigOverrides.model_rebuild(raise_errors=True)
ELS_CJAssessmentRequestV1.model_rebuild(raise_errors=True)
CJAssessmentCompletedV1.model_rebuild(raise_errors=True)
CJAssessmentFailedV1.model_rebuild(raise_errors=True)
EventEnvelope.model_rebuild(raise_errors=True)
SystemProcessingMetadata.model_rebuild(raise_errors=True)
EssayProcessingInputRefV1.model_rebuild(raise_errors=True)


@pytest.fixture
def sample_batch_id() -> str:
    """Provide a sample batch ID for testing."""
    return str(uuid4())


@pytest.fixture
def sample_essay_id() -> str:
    """Provide a sample essay ID for testing."""
    return str(uuid4())


@pytest.fixture
def sample_storage_id() -> str:
    """Provide a sample storage ID for testing."""
    return str(uuid4())


@pytest.fixture
def sample_essay_text() -> str:
    """Provide sample essay text for testing."""
    return "This is a sample essay for comparative judgment analysis."


@pytest.fixture
def llm_config_overrides() -> LLMConfigOverrides:
    """Provide sample LLM configuration overrides."""
    return LLMConfigOverrides(
        model_override="gpt-4o",
        temperature_override=0.3,
        max_tokens_override=2000,
        provider_override="openai",
    )


@pytest.fixture
def llm_config_overrides_minimal() -> LLMConfigOverrides:
    """Provide minimal LLM configuration overrides with only model."""
    return LLMConfigOverrides(model_override="claude-sonnet-4-20250514")


@pytest.fixture
def sample_parent_id() -> str | None:
    """Provide a sample parent ID for testing."""
    return None


@pytest.fixture
def system_metadata(sample_batch_id: str, sample_parent_id: str | None) -> SystemProcessingMetadata:
    """Provide sample SystemProcessingMetadata."""
    return SystemProcessingMetadata(
        entity_id=sample_batch_id,
        entity_type="batch",
        parent_id=sample_parent_id,
        event=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED,
        processing_stage=ProcessingStage.PENDING,
    )


@pytest.fixture
def essay_processing_ref(sample_essay_id: str, sample_storage_id: str) -> EssayProcessingInputRefV1:
    """Provide sample EssayProcessingInputRefV1."""
    return EssayProcessingInputRefV1(essay_id=sample_essay_id, text_storage_id=sample_storage_id)


@pytest.fixture
def cj_assessment_request_data_with_overrides(
    sample_batch_id: str,
    sample_parent_id: str | None,
    system_metadata: SystemProcessingMetadata,
    essay_processing_ref: EssayProcessingInputRefV1,
    llm_config_overrides: LLMConfigOverrides,
) -> ELS_CJAssessmentRequestV1:
    """Provide ELS_CJAssessmentRequestV1 with LLM config overrides."""
    # Create multiple essays for comparison testing
    essay_ref_2 = EssayProcessingInputRefV1(
        essay_id=str(uuid4()),
        text_storage_id=str(uuid4()),
    )
    return ELS_CJAssessmentRequestV1(
        event_name=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED,
        entity_id=sample_batch_id,
        entity_type="batch",
        parent_id=sample_parent_id,
        system_metadata=system_metadata,
        essays_for_cj=[essay_processing_ref, essay_ref_2],  # Multiple essays for comparisons
        language="en",
        course_code=CourseCode.ENG5,
        essay_instructions="Compare the quality of these essays.",
        llm_config_overrides=llm_config_overrides,
    )


@pytest.fixture
def cj_assessment_request_data_no_overrides(
    sample_batch_id: str,
    sample_parent_id: str | None,
    system_metadata: SystemProcessingMetadata,
    essay_processing_ref: EssayProcessingInputRefV1,
) -> ELS_CJAssessmentRequestV1:
    """Provide ELS_CJAssessmentRequestV1 without LLM config overrides."""
    # Create multiple essays for comparison testing
    essay_ref_2 = EssayProcessingInputRefV1(
        essay_id=str(uuid4()),
        text_storage_id=str(uuid4()),
    )
    return ELS_CJAssessmentRequestV1(
        event_name=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED,
        entity_id=sample_batch_id,
        entity_type="batch",
        parent_id=sample_parent_id,
        system_metadata=system_metadata,
        essays_for_cj=[essay_processing_ref, essay_ref_2],  # Multiple essays for comparisons
        language="en",
        course_code=CourseCode.SV1,
        essay_instructions="Compare the quality of these essays.",
        llm_config_overrides=None,
    )


@pytest.fixture
def cj_request_envelope_with_overrides(
    cj_assessment_request_data_with_overrides: ELS_CJAssessmentRequestV1,
) -> EventEnvelope[ELS_CJAssessmentRequestV1]:
    """Provide EventEnvelope with LLM config overrides."""
    return EventEnvelope[ELS_CJAssessmentRequestV1](
        event_type="els.cj_assessment.requested.v1",
        source_service="essay-lifecycle-service",
        correlation_id=uuid4(),
        data=cj_assessment_request_data_with_overrides,
    )


@pytest.fixture
def cj_request_envelope_no_overrides(
    cj_assessment_request_data_no_overrides: ELS_CJAssessmentRequestV1,
) -> EventEnvelope[ELS_CJAssessmentRequestV1]:
    """Provide EventEnvelope without LLM config overrides."""
    return EventEnvelope[ELS_CJAssessmentRequestV1](
        event_type="els.cj_assessment.requested.v1",
        source_service="essay-lifecycle-service",
        correlation_id=uuid4(),
        data=cj_assessment_request_data_no_overrides,
    )


@pytest.fixture
def kafka_message_with_overrides(
    cj_request_envelope_with_overrides: EventEnvelope[ELS_CJAssessmentRequestV1],
    sample_batch_id: str,
) -> ConsumerRecord:
    """Provide Kafka ConsumerRecord with LLM config overrides."""
    message_value = json.dumps(cj_request_envelope_with_overrides.model_dump(mode="json")).encode(
        "utf-8",
    )

    record = MagicMock(spec=ConsumerRecord)
    record.topic = "els.cj_assessment.requested.v1"
    record.partition = 0
    record.offset = 123
    record.key = sample_batch_id.encode("utf-8")
    record.value = message_value

    return record


@pytest.fixture
def kafka_message_no_overrides(
    cj_request_envelope_no_overrides: EventEnvelope[ELS_CJAssessmentRequestV1],
    sample_batch_id: str,
) -> ConsumerRecord:
    """Provide Kafka ConsumerRecord without LLM config overrides."""
    message_value = json.dumps(cj_request_envelope_no_overrides.model_dump(mode="json")).encode(
        "utf-8",
    )

    record = MagicMock(spec=ConsumerRecord)
    record.topic = "els.cj_assessment.requested.v1"
    record.partition = 0
    record.offset = 123
    record.key = sample_batch_id.encode("utf-8")
    record.value = message_value

    return record


@pytest.fixture
def mock_producer() -> AsyncMock:
    """Provide a mock Kafka producer."""
    producer = AsyncMock(spec=AIOKafkaProducer)
    producer.send_and_wait = AsyncMock()
    return producer


@pytest.fixture
def mock_http_session() -> AsyncMock:
    """Provide a mock HTTP session."""
    session = AsyncMock(spec=aiohttp.ClientSession)
    return session


@pytest.fixture
def mock_settings() -> Settings:
    """Provide mock settings for testing."""
    settings = MagicMock()
    # Create a proper mock for the enum that has a value attribute
    provider_mock = MagicMock()
    provider_mock.value = "openai"
    settings.DEFAULT_LLM_PROVIDER = provider_mock
    settings.DEFAULT_LLM_MODEL = "gpt-4o-mini"
    settings.DEFAULT_LLM_MODEL_VERSION = "20240101"  # Add missing model version
    settings.DEFAULT_LLM_TEMPERATURE = 0.7  # Add missing default temperature
    settings.TEMPERATURE = 0.7
    settings.MAX_TOKENS_RESPONSE = 4000
    settings.system_prompt = "You are a helpful AI assistant."
    settings.llm_request_timeout_seconds = 30
    settings.MAX_PAIRWISE_COMPARISONS = 100
    # Add required Kafka and service configuration
    settings.CJ_ASSESSMENT_COMPLETED_TOPIC = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)
    settings.CJ_ASSESSMENT_FAILED_TOPIC = topic_name(ProcessingEvent.CJ_ASSESSMENT_FAILED)
    settings.ASSESSMENT_RESULT_TOPIC = "huleedu.assessment.results.v1"  # Add missing RAS topic
    settings.SERVICE_NAME = "cj-assessment-service"
    settings.LLM_PROVIDERS_CONFIG = {
        "openai": MagicMock(
            api_base="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            temperature=0.7,
            max_tokens=4000,
            api_key_env_var="OPENAI_API_KEY",
        ),
        "anthropic": MagicMock(
            api_base="https://api.anthropic.com",
            default_model="claude-3-haiku-20240307",
            temperature=0.7,
            max_tokens=4000,
            api_key_env_var="ANTHROPIC_API_KEY",
        ),
        "google": MagicMock(
            api_base="https://generativelanguage.googleapis.com/v1",
            default_model="gemini-1.5-flash",
            temperature=0.7,
            max_tokens=4000,
            api_key_env_var="GOOGLE_API_KEY",
        ),
        "openrouter": MagicMock(
            api_base="https://openrouter.ai/api/v1",
            default_model="mistralai/mistral-7b-instruct",
            temperature=0.7,
            max_tokens=4000,
            api_key_env_var="OPENROUTER_API_KEY",
        ),
    }
    # Add missing attributes for LLM interaction tests
    settings.max_concurrent_llm_requests = 10
    settings.llm_request_timeout_seconds = 30

    # Add failed pool configuration for retry logic tests
    settings.ENABLE_FAILED_COMPARISON_RETRY = True
    settings.FAILED_COMPARISON_RETRY_THRESHOLD = 5
    settings.MAX_RETRY_ATTEMPTS = 3
    settings.RETRY_BATCH_SIZE = 10

    return settings


@pytest.fixture
def sample_comparison_results() -> list[dict[str, Any]]:
    """Provide sample comparison results data."""
    return [
        {"els_essay_id": str(uuid4()), "rank": 1, "score": 0.85},
        {"els_essay_id": str(uuid4()), "rank": 2, "score": 0.72},
    ]


# --- Mock Protocol Implementations (for Idempotency Tests) ---


@pytest.fixture
def mock_redis_client() -> MockRedisClient:
    """Provide a mock Redis client for idempotency testing."""
    from services.cj_assessment_service.tests.unit.mocks import MockRedisClient

    return MockRedisClient()


@pytest.fixture
def mock_cj_repository() -> MockDatabase:
    """Provide a mock CJ repository for idempotency testing."""
    from services.cj_assessment_service.tests.unit.mocks import MockDatabase

    return MockDatabase()


@pytest.fixture
def opentelemetry_test_isolation() -> Generator[InMemorySpanExporter, None, None]:
    """
    Provide OpenTelemetry test isolation with InMemorySpanExporter.

    Works with existing TracerProvider by adding a test span processor
    with InMemorySpanExporter for collecting spans during tests.
    Cleans up after each test for proper isolation.
    """
    # Create an in-memory span exporter for test span collection
    span_exporter = InMemorySpanExporter()

    # Get the current tracer provider (may be already set by service initialization)
    current_provider = trace.get_tracer_provider()

    # If no provider is set yet, create one for tests
    if not hasattr(current_provider, "add_span_processor"):
        test_provider = TracerProvider()
        trace.set_tracer_provider(test_provider)
        current_provider = test_provider

    # Add our test span processor to the existing provider
    test_processor = SimpleSpanProcessor(span_exporter)
    current_provider.add_span_processor(test_processor)

    try:
        # Yield the exporter so tests can access recorded spans
        yield span_exporter
    finally:
        # Clean up: clear spans and remove our processor if possible
        span_exporter.clear()
        # Note: TracerProvider doesn't have remove_span_processor,
        # but clearing the exporter is sufficient for test isolation


# Import the database fixtures
from services.cj_assessment_service.tests.fixtures.database_fixtures import *  # noqa: F401,F403,E402
