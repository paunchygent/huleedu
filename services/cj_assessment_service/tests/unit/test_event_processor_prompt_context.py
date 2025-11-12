"""Focused tests for prompt hydration behaviour in the CJ event processor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from aiokafka import ConsumerRecord
from common_core.error_enums import ErrorCode
from common_core.events.cj_assessment_events import ELS_CJAssessmentRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.models.error_models import ErrorDetail

from services.cj_assessment_service.event_processor import (
    _hydrate_prompt_text,
    process_single_message,
)
from services.cj_assessment_service.models_api import PromptHydrationFailure
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)


class DummyCounter:
    """Minimal counter replacement supporting inc() and labels()."""

    def __init__(self) -> None:
        self.count = 0
        self.labels_calls: list[dict[str, str]] = []

    def inc(self) -> None:
        self.count += 1

    def labels(self, **labels: str) -> "DummyCounter":
        self.labels_calls.append(labels)
        return self


def _create_consumer_record(envelope_data: dict[str, Any]) -> ConsumerRecord:
    """Helper to build ConsumerRecord for process_single_message tests."""
    import json

    json_bytes = json.dumps(envelope_data).encode("utf-8")
    return ConsumerRecord(
        topic="test-topic",
        partition=0,
        offset=0,
        timestamp=int(datetime.now(UTC).timestamp() * 1000),
        timestamp_type=0,
        key=None,
        value=json_bytes,
        checksum=None,
        serialized_key_size=len(json_bytes),
        serialized_value_size=len(json_bytes),
        headers=[],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "case",
        "storage_id",
        "fetch_result",
        "fetch_side_effect",
        "expected_ok",
        "expected_value",
        "expected_reason",
    ),
    [
        ("no_storage", None, None, None, True, "", None),
        ("success", "storage-1", "Prompt body", None, True, "Prompt body", None),
        ("empty", "storage-2", "", None, False, None, "empty_content"),
        (
            "content_error",
            "storage-3",
            None,
            ErrorDetail(
                error_code=ErrorCode.CONTENT_SERVICE_ERROR,
                message="content failure",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="test",
                operation="hydrate",
                details={},
            ),
            False,
            None,
            "content_service_error",
        ),
        ("unexpected", "storage-4", None, RuntimeError("boom"), False, None, "unexpected_error"),
    ],
)
async def test_hydrate_prompt_text_result_contract(
    case: str,
    storage_id: str | None,
    fetch_result: str | None,
    fetch_side_effect: Exception | ErrorDetail | None,
    expected_ok: bool,
    expected_value: str | None,
    expected_reason: str | None,
) -> None:
    """Validate Result behaviour and failure metrics for prompt hydration."""

    content_client = AsyncMock(spec=ContentClientProtocol)

    if isinstance(fetch_side_effect, ErrorDetail):
        from huleedu_service_libs.error_handling import HuleEduError

        content_client.fetch_content.side_effect = HuleEduError(fetch_side_effect)
    elif fetch_side_effect is not None:
        content_client.fetch_content.side_effect = fetch_side_effect
    elif fetch_result is not None:
        content_client.fetch_content.return_value = fetch_result

    failure_counter = DummyCounter()

    result = await _hydrate_prompt_text(
        storage_id=storage_id,
        content_client=content_client,
        correlation_id=uuid4(),
        log_extra={},
        prompt_failure_metric=failure_counter,
    )

    if expected_ok:
        assert result.is_ok
        assert result.value == expected_value
        assert failure_counter.count == 0
        assert not failure_counter.labels_calls
    else:
        assert result.is_err
        error = result.error
        assert isinstance(error, PromptHydrationFailure)
        assert error.reason == expected_reason
        assert failure_counter.count == 1
        assert failure_counter.labels_calls == [{"reason": expected_reason}]


@pytest.mark.asyncio
async def test_process_message_increments_prompt_success_metric(
    cj_assessment_request_data_with_overrides: ELS_CJAssessmentRequestV1,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful prompt hydration should increment success metric exactly once."""

    from services.cj_assessment_service.tests.unit.mocks import MockDatabase

    # Arrange request data with explicit assignment and storage ID
    event_data = cj_assessment_request_data_with_overrides.model_copy(
        update={
            "assignment_id": "assignment-909",
            "student_prompt_ref": cj_assessment_request_data_with_overrides.student_prompt_ref,
        }
    )

    envelope: EventEnvelope[ELS_CJAssessmentRequestV1] = EventEnvelope(
        event_id=uuid4(),
        event_type="els.cj_assessment.requested.v1",
        event_timestamp=datetime.now(UTC),
        source_service="essay_lifecycle_service",
        correlation_id=uuid4(),
        data=event_data,
    )

    kafka_msg = _create_consumer_record(envelope.model_dump(mode="json"))

    repository = MockDatabase()
    content_client = AsyncMock(spec=ContentClientProtocol)
    content_client.fetch_content.return_value = "Prompt body"
    event_publisher = AsyncMock(spec=CJEventPublisherProtocol)
    llm_interaction = AsyncMock(spec=LLMInteractionProtocol)
    workflow_mock = AsyncMock(return_value=Mock(rankings=[], batch_id="1"))

    monkeypatch.setattr(
        "services.cj_assessment_service.event_processor.run_cj_assessment_workflow",
        workflow_mock,
    )

    success_counter = DummyCounter()
    failure_counter = DummyCounter()

    monkeypatch.setattr(
        "services.cj_assessment_service.event_processor.get_business_metrics",
        lambda: {
            "cj_comparisons_made": None,
            "cj_assessment_duration_seconds": None,
            "kafka_queue_latency_seconds": None,
            "prompt_fetch_failures": failure_counter,
            "prompt_fetch_success": success_counter,
        },
    )

    settings = Mock(
        MAX_PAIRWISE_COMPARISONS=100,
        CJ_ASSESSMENT_FAILED_TOPIC="cj_assessment.failed.v1",
        SERVICE_NAME="cj_assessment_service",
    )

    # Act
    await process_single_message(
        msg=kafka_msg,
        database=repository,
        content_client=content_client,
        event_publisher=event_publisher,
        llm_interaction=llm_interaction,
        settings_obj=settings,
    )

    # Assert - Hydration success recorded, failure untouched
    assert success_counter.count == 1
    assert failure_counter.count == 0

    converted_request_data = workflow_mock.call_args.kwargs["request_data"]
    assert converted_request_data["assignment_id"] == "assignment-909"
    assert converted_request_data["student_prompt_text"] == "Prompt body"
