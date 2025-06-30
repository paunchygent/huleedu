#!/usr/bin/env python3
"""
Debug the deterministic ID generation for events.
"""

import json
import uuid
from datetime import UTC, datetime

from common_core.domain_enums import CourseCode
from common_core.events.envelope import EventEnvelope
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.utils import generate_deterministic_event_id
from common_core.metadata_models import EntityReference, SystemProcessingMetadata


def debug_deterministic_id():
    """Debug what deterministic ID is generated for a BatchEssaysRegistered event."""

    # Create the same type of event as in my isolated test
    batch_id = "8f06e7eb-8ec0-429a-95e7-23ed603b6275"
    correlation_id = "c735e913-6efe-4c93-b32d-ef1a51f73553"
    essay_id = str(uuid.uuid4())

    batch_registered_event = BatchEssaysRegistered(
        batch_id=batch_id,
        expected_essay_count=1,
        essay_ids=[essay_id],
        metadata=SystemProcessingMetadata(
            entity=EntityReference(entity_id=batch_id, entity_type="batch"),
            timestamp=datetime.now(UTC),
        ),
        course_code=CourseCode.ENG5,
        essay_instructions="Test essay instructions",
        user_id="test_user_123",
    )

    envelope = EventEnvelope(
        event_type="huleedu.batch.essays.registered.v1",
        source_service="batch-service",
        correlation_id=uuid.UUID(correlation_id),
        data=batch_registered_event,
    )

    # Serialize the envelope as Kafka would
    envelope_dict = envelope.model_dump()
    envelope_json = json.dumps(envelope_dict, default=str)
    envelope_bytes = envelope_json.encode("utf-8")

    print(f"Event ID in envelope: {envelope.event_id}")
    print(f"Batch ID: {batch_id}")
    print(f"Correlation ID: {correlation_id}")

    # Generate deterministic ID
    deterministic_id = generate_deterministic_event_id(envelope_bytes)
    print(f"Generated deterministic ID: {deterministic_id}")

    # Check if this matches the Redis key from the logs
    expected_key = "27b745cabb1d96d1dc578e7dde579ab9b736b2177a3caa7ed57865ab4a70cdbb"
    print(f"Expected key from logs: {expected_key}")
    print(f"IDs match: {deterministic_id == expected_key}")

    # Let's also examine the envelope structure
    print(f"\nEnvelope structure:")
    print(json.dumps(envelope_dict, indent=2, default=str))

    # Test what happens if we parse the JSON
    parsed = json.loads(envelope_json)
    print(f"\nParsed event_id: {parsed.get('event_id')}")
    print(f"Parsed data type: {type(parsed.get('event_id'))}")


if __name__ == "__main__":
    debug_deterministic_id()
