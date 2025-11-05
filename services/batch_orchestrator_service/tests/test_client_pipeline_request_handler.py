"""Tests for ClientPipelineRequestHandler prompt metadata plumbing."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType, CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.client_commands import ClientBatchPipelineRequestV1, PipelinePromptPayload
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import StorageReferenceMetadata
from common_core.pipeline_models import PhaseName, PipelineExecutionStatus
from common_core.status_enums import BatchStatus
from unittest.mock import AsyncMock

from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations.client_pipeline_request_handler import (
    ClientPipelineRequestHandler,
)


class _StubCreditOutcome:
    """Simple stub returned by the credit guard AsyncMock."""

    def __init__(self) -> None:
        self.allowed = True
        self.required_credits = 0
        self.available_credits = 0
        self.denial_reason = None
        self.resource_breakdown: dict[str, int] = {}


def _make_kafka_message(envelope: EventEnvelope[Any]) -> Any:
    """Serialize an EventEnvelope to a fake Kafka message structure."""
    payload = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
    return SimpleNamespace(
        value=payload,
        topic=topic_name(ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST),
        partition=0,
        offset=0,
    )


@pytest.mark.asyncio
async def test_handle_client_request_passes_prompt_metadata() -> None:
    """BOS forwards prompt attachment metadata to BCS when teachers provide CMS prompts."""
    prompt_ref = StorageReferenceMetadata()
    prompt_ref.add_reference(ContentType.STUDENT_PROMPT_TEXT, "deadbeefcafefeed")

    request_payload = ClientBatchPipelineRequestV1(
        batch_id="batch-123",
        requested_pipeline=PhaseName.AI_FEEDBACK.value,
        user_id="teacher-42",
        is_retry=False,
        prompt_payload=PipelinePromptPayload(cms_prompt_ref=prompt_ref),
    )

    envelope = EventEnvelope[ClientBatchPipelineRequestV1](
        event_type=topic_name(ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST),
        source_service="api_gateway_service",
        correlation_id=uuid4(),
        data=request_payload.model_dump(mode="json"),
    )
    message = _make_kafka_message(envelope)

    registration_context = BatchRegistrationRequestV1(
        expected_essay_count=1,
        essay_ids=["essay-1"],
        course_code=CourseCode.ENG5,
        student_prompt_ref=None,
        user_id="teacher-42",
        org_id=None,
        class_id=None,
        enable_cj_assessment=False,
    )

    bcs_client = AsyncMock()
    bcs_client.resolve_pipeline.return_value = {"final_pipeline": [PhaseName.AI_FEEDBACK.value]}

    batch_repo = AsyncMock()
    batch_repo.get_batch_context.return_value = registration_context
    batch_repo.get_batch_by_id.return_value = {
        "status": BatchStatus.READY_FOR_PIPELINE_EXECUTION.value
    }
    batch_repo.get_processing_pipeline_state.side_effect = [None, None]
    batch_repo.save_processing_pipeline_state = AsyncMock()

    phase_coordinator = AsyncMock()
    entitlements_client = AsyncMock()

    credit_guard = AsyncMock()
    credit_guard.evaluate.return_value = _StubCreditOutcome()

    handler = ClientPipelineRequestHandler(
        bcs_client=bcs_client,
        batch_repo=batch_repo,
        phase_coordinator=phase_coordinator,
        entitlements_client=entitlements_client,
        credit_guard=credit_guard,
    )

    # Avoid touching notification and event publishing infrastructure.
    handler.notification_projector = None

    await handler.handle_client_pipeline_request(message)

    assert bcs_client.resolve_pipeline.await_count == 1
    resolve_args = bcs_client.resolve_pipeline.await_args.args
    assert resolve_args[0] == "batch-123"
    assert resolve_args[1] == PhaseName.AI_FEEDBACK
    assert resolve_args[2] == str(envelope.correlation_id)

    sent_metadata = resolve_args[3]
    assert sent_metadata == {"prompt_attached": True, "prompt_source": "cms"}

    # Ensure the context now holds the newly attached reference for downstream consumers.
    assert registration_context.student_prompt_ref is not None
    assert (
        registration_context.student_prompt_ref.references[ContentType.STUDENT_PROMPT_TEXT][
            "storage_id"
        ]
        == "deadbeefcafefeed"
    )


class _BlockingPipelineState:
    """Stub pipeline state with a non-final active phase to trigger guard clause."""

    def __init__(self) -> None:
        self.requested_pipelines = [PhaseName.SPELLCHECK.value, PhaseName.NLP.value]

    def get_pipeline(self, name: str) -> Any:
        if name == PhaseName.SPELLCHECK.value:
            return SimpleNamespace(status=PipelineExecutionStatus.IN_PROGRESS)
        if name == PhaseName.NLP.value:
            return SimpleNamespace(status=PipelineExecutionStatus.PENDING_DEPENDENCIES)
        return SimpleNamespace(status=PipelineExecutionStatus.REQUESTED_BY_USER)


@pytest.mark.asyncio
async def test_handle_client_request_skips_when_pipeline_active() -> None:
    """Handler returns early without calling BCS when a pipeline is already in flight."""
    request_payload = ClientBatchPipelineRequestV1(
        batch_id="batch-789",
        requested_pipeline=PhaseName.NLP.value,
        user_id="teacher-007",
        is_retry=False,
    )

    envelope = EventEnvelope[ClientBatchPipelineRequestV1](
        event_type=topic_name(ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST),
        source_service="api_gateway_service",
        correlation_id=uuid4(),
        data=request_payload.model_dump(mode="json"),
    )
    message = _make_kafka_message(envelope)

    registration_context = BatchRegistrationRequestV1(
        expected_essay_count=1,
        essay_ids=["essay-1"],
        course_code=CourseCode.ENG5,
        student_prompt_ref=None,
        user_id="teacher-007",
        org_id=None,
        class_id=None,
        enable_cj_assessment=False,
    )

    bcs_client = AsyncMock()
    batch_repo = AsyncMock()
    batch_repo.get_batch_context.return_value = registration_context
    batch_repo.get_batch_by_id.return_value = {
        "status": BatchStatus.READY_FOR_PIPELINE_EXECUTION.value
    }
    batch_repo.get_processing_pipeline_state.return_value = _BlockingPipelineState()

    phase_coordinator = AsyncMock()
    entitlements_client = AsyncMock()
    credit_guard = AsyncMock()

    handler = ClientPipelineRequestHandler(
        bcs_client=bcs_client,
        batch_repo=batch_repo,
        phase_coordinator=phase_coordinator,
        entitlements_client=entitlements_client,
        credit_guard=credit_guard,
    )

    await handler.handle_client_pipeline_request(message)

    bcs_client.resolve_pipeline.assert_not_awaited()
    phase_coordinator.initiate_resolved_pipeline.assert_not_awaited()
