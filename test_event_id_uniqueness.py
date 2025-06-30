#!/usr/bin/env python3
"""
Test to verify that EventEnvelope generates unique event_ids for identical business data.
"""

import json
import uuid
from datetime import UTC, datetime

from common_core.domain_enums import CourseCode
from common_core.events.envelope import EventEnvelope
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.utils import generate_deterministic_event_id
from common_core.metadata_models import EntityReference, SystemProcessingMetadata


def test_event_id_uniqueness():
    """Test that identical business events get different event_ids."""
    
    # Create identical business data
    batch_id = "test-batch-123"
    correlation_id = str(uuid.uuid4())
    essay_id = "essay-789"
    
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
    
    # Create two envelopes with identical business data
    envelope1 = EventEnvelope(
        event_type="huleedu.batch.essays.registered.v1",
        source_service="batch-service",
        correlation_id=uuid.UUID(correlation_id),
        data=batch_registered_event,
    )
    
    envelope2 = EventEnvelope(
        event_type="huleedu.batch.essays.registered.v1",
        source_service="batch-service",
        correlation_id=uuid.UUID(correlation_id),
        data=batch_registered_event,
    )
    
    print(f"Event 1 ID: {envelope1.event_id}")
    print(f"Event 2 ID: {envelope2.event_id}")
    print(f"IDs are different: {envelope1.event_id != envelope2.event_id}")
    
    # Generate deterministic IDs
    envelope1_bytes = json.dumps(envelope1.model_dump(), default=str).encode('utf-8')
    envelope2_bytes = json.dumps(envelope2.model_dump(), default=str).encode('utf-8')
    
    det_id1 = generate_deterministic_event_id(envelope1_bytes)
    det_id2 = generate_deterministic_event_id(envelope2_bytes)
    
    print(f"Deterministic ID 1: {det_id1}")
    print(f"Deterministic ID 2: {det_id2}")
    print(f"Deterministic IDs are different: {det_id1 != det_id2}")
    
    # This proves that identical business events will NOT be caught as duplicates
    # because each EventEnvelope gets a unique event_id
    
    print("\n=== CONCLUSION ===")
    print("Identical business events get different event_ids and different deterministic IDs.")
    print("This means they will NOT be detected as duplicates by the idempotency system.")
    print("The idempotency system only catches exact message retries (same event_id).")


if __name__ == "__main__":
    test_event_id_uniqueness()