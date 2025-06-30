#!/usr/bin/env python3
"""
Trace the E2E test execution to find where it stops.
"""

import asyncio
import aiohttp
import uuid
import json
import time
from pathlib import Path

async def trace_e2e_test():
    """Trace each step of the E2E test to find where it fails."""
    
    print("🔍 Tracing E2E Test Execution")
    print("=" * 50)
    
    # Step 1: Load test essays
    print("\n1️⃣ Loading test essays...")
    test_essays_dir = Path("test_uploads/real_test_batch")
    if not test_essays_dir.exists():
        print("❌ Test essays directory not found")
        return
    
    essay_files = list(test_essays_dir.glob("*.txt"))[:3]  # Just 3 for testing
    print(f"✅ Found {len(essay_files)} test essays")
    
    # Step 2: Create batch
    print("\n2️⃣ Creating batch...")
    batch_id = None
    correlation_id = str(uuid.uuid4())
    
    async with aiohttp.ClientSession() as session:
        batch_request = {
            "course_code": "ENG5",
            "expected_essay_count": len(essay_files),
            "essay_instructions": "Test batch",
            "user_id": "test_user_123",
            "enable_cj_assessment": True
        }
        
        headers = {
            "X-Correlation-ID": correlation_id,
            "Authorization": "Bearer test_token"
        }
        
        try:
            async with session.post(
                "http://localhost:5001/v1/batches/register",
                json=batch_request,
                headers=headers
            ) as response:
                if response.status == 202:
                    result = await response.json()
                    batch_id = result["batch_id"]
                    actual_correlation_id = result["correlation_id"]
                    print(f"✅ Batch created: {batch_id}")
                    print(f"   Request correlation ID: {correlation_id}")
                    print(f"   Actual correlation ID: {actual_correlation_id}")
                else:
                    print(f"❌ Batch creation failed: {response.status}")
                    return
        except Exception as e:
            print(f"❌ Error creating batch: {e}")
            return
    
    # Step 3: Monitor Kafka events
    print("\n3️⃣ Setting up Kafka monitoring...")
    from aiokafka import AIOKafkaConsumer
    
    topics = [
        "huleedu.batch.essays.registered.v1",
        "huleedu.file.essay.content.provisioned.v1",
        "huleedu.els.batch.essays.ready.v1",
        "huleedu.batch.spellcheck.initiate.command.v1"
    ]
    
    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers="localhost:9093",
        group_id=f"trace_{uuid.uuid4().hex[:8]}",
        auto_offset_reset="earliest",
        enable_auto_commit=False
    )
    
    await consumer.start()
    print("✅ Kafka consumer started")
    
    # Step 4: Upload files
    print("\n4️⃣ Uploading files...")
    
    # Create multipart form data
    from aiohttp import FormData
    
    form_data = FormData()
    form_data.add_field("batch_id", batch_id)
    
    for essay_file in essay_files:
        with open(essay_file, 'rb') as f:
            form_data.add_field(
                'files',
                f.read(),
                filename=essay_file.name,
                content_type='text/plain'
            )
    
    # Create new session for file upload
    async with aiohttp.ClientSession() as upload_session:
        try:
            async with upload_session.post(
                "http://localhost:7001/v1/files/batch",
                data=form_data,
                headers={"Authorization": "Bearer test_token"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ Files uploaded successfully")
                    print(f"   Response: {result}")
                else:
                    text = await response.text()
                    print(f"❌ File upload failed: {response.status} - {text}")
                    await consumer.stop()
                    return
        except Exception as e:
            print(f"❌ Error uploading files: {e}")
            await consumer.stop()
            return
    
    # Step 5: Monitor events
    print("\n5️⃣ Monitoring pipeline events (30 seconds)...")
    
    events_seen = []
    start_time = time.time()
    timeout = 30
    
    try:
        while (time.time() - start_time) < timeout:
            records = await consumer.getmany(timeout_ms=1000)
            
            for topic_partition, messages in records.items():
                for msg in messages:
                    try:
                        event = json.loads(msg.value.decode('utf-8'))
                        event_type = event.get("event_type", "unknown")
                        event_batch_id = event.get("data", {}).get("batch_id")
                        
                        if event_batch_id == batch_id:
                            elapsed = time.time() - start_time
                            events_seen.append({
                                "time": elapsed,
                                "topic": msg.topic,
                                "event_type": event_type
                            })
                            print(f"   📨 +{elapsed:.1f}s: {event_type}")
                            
                            # Check for BatchEssaysReady
                            if "batch.essays.ready" in event_type:
                                print("   ✅ BatchEssaysReady received - essays are ready for processing")
                                
                    except Exception as e:
                        print(f"   ⚠️ Error parsing message: {e}")
            
            # Print status every 5 seconds
            elapsed = time.time() - start_time
            if int(elapsed) % 5 == 0 and int(elapsed) > 0:
                print(f"   ⏳ {int(elapsed)}s elapsed, {len(events_seen)} events captured")
                
    finally:
        await consumer.stop()
    
    # Step 6: Analyze results
    print(f"\n6️⃣ Analysis:")
    print(f"   Total events captured: {len(events_seen)}")
    
    expected_events = [
        "batch.essays.registered",
        "essay.content.provisioned",
        "batch.essays.ready",
        "batch.spellcheck.initiate"
    ]
    
    for expected in expected_events:
        found = any(expected in e["event_type"] for e in events_seen)
        if found:
            print(f"   ✅ {expected}")
        else:
            print(f"   ❌ {expected} - MISSING")
            print(f"      ^ Pipeline likely stopped here")
            break
    
    print("\n" + "=" * 50)
    print("📊 Summary:")
    print(f"   Batch ID: {batch_id}")
    print(f"   Files uploaded: {len(essay_files)}")
    print(f"   Events captured: {len(events_seen)}")
    
    if events_seen:
        print("\n   Event Timeline:")
        for event in events_seen:
            print(f"   +{event['time']:.1f}s: {event['event_type']}")


if __name__ == "__main__":
    asyncio.run(trace_e2e_test())