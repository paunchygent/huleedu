#!/usr/bin/env python3
"""
Isolated test of the core ELS batch registration and content processing flow.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime

from aiokafka import AIOKafkaProducer
from common_core.domain_enums import CourseCode
from common_core.events.envelope import EventEnvelope
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.file_events import EssayContentProvisionedV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata


async def test_isolated_flow():
    """Test the isolated ELS batch registration and content processing flow."""
    
    # Create unique IDs for this test
    batch_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    essay_id = str(uuid.uuid4())
    text_storage_id = str(uuid.uuid4())
    
    print(f"🔬 Testing isolated flow with batch_id: {batch_id}")
    print(f"🔗 Using correlation_id: {correlation_id}")
    
    # Create Kafka producer
    producer = AIOKafkaProducer(
        bootstrap_servers='localhost:9093',
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
    )
    
    try:
        await producer.start()
        
        # Step 1: Send BatchEssaysRegistered event
        print("\n📝 Step 1: Sending BatchEssaysRegistered event...")
        
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
        
        envelope1 = EventEnvelope(
            event_type="huleedu.batch.essays.registered.v1",
            source_service="batch-service",
            correlation_id=uuid.UUID(correlation_id),
            data=batch_registered_event,
        )
        
        await producer.send(
            "huleedu.batch.essays.registered.v1",
            envelope1.model_dump()
        )
        
        print(f"✅ Sent BatchEssaysRegistered event_id: {envelope1.event_id}")
        
        # Let's also send the same event again to test idempotency
        print("\n🔁 Sending IDENTICAL BatchEssaysRegistered event again...")
        await producer.send(
            "huleedu.batch.essays.registered.v1",
            envelope1.model_dump()
        )
        print(f"✅ Sent IDENTICAL BatchEssaysRegistered event_id: {envelope1.event_id}")
        
        # Wait a moment for processing
        await asyncio.sleep(2)
        
        # Step 2: Send EssayContentProvisionedV1 event
        print("\n📄 Step 2: Sending EssayContentProvisionedV1 event...")
        
        content_provisioned_event = EssayContentProvisionedV1(
            batch_id=batch_id,
            original_file_name="test_essay.txt",
            raw_file_storage_id=str(uuid.uuid4()),
            text_storage_id=text_storage_id,
            file_size_bytes=1000,
            content_md5_hash="abcd1234",
            correlation_id=uuid.UUID(correlation_id),
            timestamp=datetime.now(UTC),
        )
        
        envelope2 = EventEnvelope(
            event_type="huleedu.file.essay.content.provisioned.v1",
            source_service="file-service",
            correlation_id=uuid.UUID(correlation_id),
            data=content_provisioned_event,
        )
        
        await producer.send(
            "huleedu.file.essay.content.provisioned.v1",
            envelope2.model_dump()
        )
        
        print(f"✅ Sent EssayContentProvisionedV1 event_id: {envelope2.event_id}")
        
        # Wait for processing
        await asyncio.sleep(3)
        
        print("\n🔍 Check ELS logs to see if:")
        print("1. BatchEssaysRegistered was processed (batch expectation created)")
        print("2. EssayContentProvisionedV1 was assigned to slot (not marked as excess)")
        print("3. BatchEssaysReady event was published")
        
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(test_isolated_flow())