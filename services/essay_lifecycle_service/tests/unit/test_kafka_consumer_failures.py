"""
Critical Kafka consumer failure tests for Essay Lifecycle Service.

Tests the 3 most critical failure modes that impact production:
1. Malformed JSON deserialization
2. Unknown event type handling
3. Processing exceptions

Simple, focused tests without overengineering.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiokafka import ConsumerRecord
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.file_events import EssayContentProvisionedV1

from services.essay_lifecycle_service.batch_command_handlers import (
    _deserialize_message,
    process_single_message,
)
from services.essay_lifecycle_service.protocols import (
    BatchCommandHandler,
    BatchCoordinationHandler,
    ServiceResultHandler,
)


class TestKafkaConsumerFailures:
    """Critical Kafka consumer failure scenarios."""

    def test_malformed_json_fails_gracefully(self) -> None:
        """Malformed JSON should return None, not crash."""
        bad_message = ConsumerRecord(
            topic="test",
            partition=0,
            offset=1,
            timestamp=None,
            timestamp_type=None,
            key=None,
            value=b'{"bad": json}',
            checksum=None,
            serialized_key_size=None,
            serialized_value_size=None,
            headers=[],
        )

        result = _deserialize_message(bad_message)
        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_event_type_returns_false(self) -> None:
        """Unknown event types should be rejected gracefully."""
        # Create envelope with unknown event type but valid structure
        envelope_data = {
            "event_id": str(uuid4()),
            "event_type": "unknown.event.v1",  # Not in routing table
            "event_timestamp": datetime.now(UTC).isoformat(),
            "source_service": "test",
            "correlation_id": str(uuid4()),
            "data": {"test": "data"},
        }

        message = ConsumerRecord(
            topic="test",
            partition=0,
            offset=1,
            timestamp=None,
            timestamp_type=None,
            key=None,
            value=json.dumps(envelope_data).encode("utf-8"),
            checksum=None,
            serialized_key_size=None,
            serialized_value_size=None,
            headers=[],
        )

        result = await process_single_message(
            msg=message,
            batch_coordination_handler=AsyncMock(spec=BatchCoordinationHandler),
            batch_command_handler=AsyncMock(spec=BatchCommandHandler),
            service_result_handler=AsyncMock(spec=ServiceResultHandler),
            tracer=None,
            confirm_idempotency=None,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_processing_exception_returns_false(self) -> None:
        """Processing exceptions should return False, not crash."""
        mock_handler = AsyncMock(spec=BatchCoordinationHandler)
        mock_handler.handle_essay_content_provisioned.side_effect = Exception("Test error")

        # Use real event structure that will trigger the handler
        event_data = EssayContentProvisionedV1(
            entity_id="test_batch",
            file_upload_id="test-file-upload-kafka-failure",
            text_storage_id="test_storage",
            raw_file_storage_id="raw_storage",
            original_file_name="test.txt",
            file_size_bytes=1000,
            content_md5_hash="testhash123",
        )

        envelope: EventEnvelope[EssayContentProvisionedV1] = EventEnvelope(
            event_id=uuid4(),
            event_type=topic_name(ProcessingEvent.ESSAY_CONTENT_PROVISIONED),
            event_timestamp=datetime.now(UTC),
            source_service="content_service",
            correlation_id=uuid4(),
            data=event_data,
        )

        message = ConsumerRecord(
            topic="test",
            partition=0,
            offset=1,
            timestamp=None,
            timestamp_type=None,
            key=None,
            value=envelope.model_dump_json().encode("utf-8"),
            checksum=None,
            serialized_key_size=None,
            serialized_value_size=None,
            headers=[],
        )

        result = await process_single_message(
            msg=message,
            batch_coordination_handler=mock_handler,
            batch_command_handler=AsyncMock(spec=BatchCommandHandler),
            service_result_handler=AsyncMock(spec=ServiceResultHandler),
            tracer=None,
            confirm_idempotency=None,
        )

        assert result is False
