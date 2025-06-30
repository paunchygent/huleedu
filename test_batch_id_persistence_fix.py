#!/usr/bin/env python3
"""
Isolated test to verify the batch_id persistence fixes.

This test verifies that essays maintain their batch_id association 
throughout the entire pipeline, ensuring proper batch coordination.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime

import redis.asyncio as redis
from aiokafka import AIOKafkaProducer

from common_core.domain_enums import CourseCode
from common_core.events.envelope import EventEnvelope
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.file_events import EssayContentProvisionedV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata


async def clear_test_data():
    """Clear Redis and database for isolated testing."""
    print("🧹 Cleaning test environment...")
    
    # Clear ALL Redis keys (more thorough)
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    try:
        await redis_client.flushall()
        print("🗑️  Cleared ALL Redis keys")
    finally:
        await redis_client.aclose()


async def wait_for_database_update(batch_id: str, essay_ids: list[str], timeout: int = 10) -> bool:
    """Wait for essays to be created in database with correct batch_id."""
    import subprocess
    
    start_time = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start_time) < timeout:
        # Check if essays exist with correct batch_id
        cmd = [
            "docker", "exec", "huleedu_essay_lifecycle_db",
            "psql", "-U", "postgres", "-d", "essay_lifecycle",
            "-t", "-c", 
            f"SELECT COUNT(*) FROM essay_states WHERE batch_id = '{batch_id}' AND essay_id = ANY(ARRAY{essay_ids});"
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                count = int(result.stdout.strip())
                if count == len(essay_ids):
                    return True
        except Exception as e:
            print(f"⚠️ Database check error: {e}")
        
        await asyncio.sleep(0.5)
    
    return False


async def check_batch_id_in_database(batch_id: str, essay_ids: list[str]) -> dict:
    """Check batch_id persistence in database."""
    import subprocess
    
    cmd = [
        "docker", "exec", "huleedu_essay_lifecycle_db",
        "psql", "-U", "postgres", "-d", "essay_lifecycle",
        "-t", "-c", 
        f"""
        SELECT essay_id, 
               COALESCE(batch_id, 'NULL') as batch_id, 
               current_status 
        FROM essay_states 
        WHERE essay_id = ANY(ARRAY{essay_ids});
        """
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            results = {}
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 3:
                        essay_id, found_batch_id, status = parts[0], parts[1], parts[2]
                        results[essay_id] = {
                            'batch_id': found_batch_id if found_batch_id != 'NULL' else None,
                            'status': status
                        }
            return results
    except Exception as e:
        print(f"❌ Database query error: {e}")
    
    return {}


async def test_batch_id_persistence():
    """Test that batch_id is properly persisted throughout the pipeline."""
    
    print("🔬 Testing batch_id persistence fixes...")
    
    # Generate test data
    batch_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    essay_ids = [str(uuid.uuid4()) for _ in range(3)]
    
    print(f"📝 Test batch: {batch_id}")
    print(f"🔗 Correlation: {correlation_id}")
    print(f"📄 Essays: {essay_ids}")
    
    # Clear test environment
    await clear_test_data()
    
    # Create Kafka producer
    producer = AIOKafkaProducer(
        bootstrap_servers='localhost:9093',
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
    )
    
    try:
        await producer.start()
        
        print("\n🎯 Step 1: Send BatchEssaysRegistered event")
        
        # Create BatchEssaysRegistered event
        batch_registered_event = BatchEssaysRegistered(
            batch_id=batch_id,
            expected_essay_count=len(essay_ids),
            essay_ids=essay_ids,
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
        
        print(f"✅ Sent BatchEssaysRegistered with {len(essay_ids)} essays")
        
        # Wait for initial essay creation
        print("⏳ Waiting for initial essay creation...")
        await asyncio.sleep(5)
        
        # Check if essays were created with correct batch_id
        print("🔍 Checking initial essay creation...")
        essay_data = await check_batch_id_in_database(batch_id, essay_ids)
        
        initial_creation_success = True
        for essay_id in essay_ids:
            if essay_id in essay_data:
                found_batch_id = essay_data[essay_id]['batch_id']
                status = essay_data[essay_id]['status']
                print(f"📄 Essay {essay_id[:8]}... batch_id: {found_batch_id[:8] if found_batch_id else 'NULL'}... status: {status}")
                
                if found_batch_id != batch_id:
                    print(f"❌ INITIAL CREATION BUG: Essay {essay_id} has incorrect batch_id")
                    initial_creation_success = False
            else:
                print(f"❌ INITIAL CREATION BUG: Essay {essay_id} not found in database")
                initial_creation_success = False
        
        if initial_creation_success:
            print("✅ Initial essay creation: ALL essays have correct batch_id")
        else:
            print("❌ Initial essay creation: FAILED - batch_id persistence broken")
            return False
        
        print("\n🎯 Step 2: Send EssayContentProvisionedV1 events")
        
        # Send content provisioned events for each essay
        content_success = True
        for i, essay_id in enumerate(essay_ids):
            text_storage_id = str(uuid.uuid4())
            
            content_provisioned_event = EssayContentProvisionedV1(
                batch_id=batch_id,
                original_file_name=f"test_essay_{i+1}.txt",
                raw_file_storage_id=str(uuid.uuid4()),
                text_storage_id=text_storage_id,
                file_size_bytes=1000 + i,
                content_md5_hash=f"hash{i+1}",
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
        
        print(f"✅ Sent {len(essay_ids)} EssayContentProvisionedV1 events")
        
        # Wait for content processing
        print("⏳ Waiting for content processing...")
        await asyncio.sleep(5)
        
        # Check if essays still have correct batch_id after content processing
        print("🔍 Checking batch_id after content processing...")
        essay_data = await check_batch_id_in_database(batch_id, essay_ids)
        
        for essay_id in essay_ids:
            if essay_id in essay_data:
                found_batch_id = essay_data[essay_id]['batch_id']
                status = essay_data[essay_id]['status']
                print(f"📄 Essay {essay_id[:8]}... batch_id: {found_batch_id[:8] if found_batch_id else 'NULL'}... status: {status}")
                
                if found_batch_id != batch_id:
                    print(f"❌ CONTENT PROCESSING BUG: Essay {essay_id} lost batch_id during content processing")
                    content_success = False
            else:
                print(f"❌ CONTENT PROCESSING BUG: Essay {essay_id} not found after content processing")
                content_success = False
        
        if content_success:
            print("✅ Content processing: ALL essays maintain correct batch_id")
        else:
            print("❌ Content processing: FAILED - batch_id lost during updates")
            return False
        
        print("\n🎯 Overall Test Result:")
        if initial_creation_success and content_success:
            print("🎉 SUCCESS: batch_id persistence fixes are working correctly!")
            print("✅ Essays maintain batch association throughout the pipeline")
            return True
        else:
            print("❌ FAILURE: batch_id persistence issues remain")
            return False
            
    finally:
        await producer.stop()


async def main():
    """Run the isolated batch_id persistence test."""
    print("=" * 60)
    print("🔬 ISOLATED TEST: batch_id Persistence Fixes")
    print("=" * 60)
    
    success = await test_batch_id_persistence()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 TEST PASSED: batch_id persistence fixes are working!")
    else:
        print("❌ TEST FAILED: batch_id persistence issues remain")
    print("=" * 60)
    
    return success


if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)