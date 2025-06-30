#!/usr/bin/env python3
"""
Test the most basic pipeline flow directly without the complex E2E test.
"""

import asyncio
import aiohttp
import uuid
import json
from datetime import UTC, datetime

async def test_basic_flow():
    """Test the most basic batch registration and file upload flow."""
    
    batch_id = None
    correlation_id = str(uuid.uuid4())
    
    print("🧪 Testing Basic Pipeline Flow")
    print("=" * 50)
    
    # Step 1: Register a batch
    print("\n1️⃣ Registering batch...")
    async with aiohttp.ClientSession() as session:
        batch_request = {
            "course_code": "ENG5",
            "expected_essay_count": 1,
            "essay_instructions": "Basic test",
            "user_id": "test_user",
            "enable_cj_assessment": False  # Keep it simple
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
                    batch_id = result.get("batch_id")
                    print(f"✅ Batch registered: {batch_id}")
                else:
                    text = await response.text()
                    print(f"❌ Batch registration failed: {response.status} - {text}")
                    return
        except Exception as e:
            print(f"❌ Error registering batch: {e}")
            return
    
    # Step 2: Check if batch exists in ELS
    print("\n2️⃣ Checking ELS database...")
    import subprocess
    
    cmd = [
        "docker", "exec", "-i", "huleedu_essay_lifecycle_db",
        "psql", "-U", "huleedu_user", "-d", "essay_lifecycle",
        "-t", "-c", f"SELECT COUNT(*) FROM essay_states WHERE batch_id = '{batch_id}';"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        count = int(result.stdout.strip())
        if count > 0:
            print(f"✅ Found {count} essays in ELS for batch {batch_id}")
        else:
            print(f"❌ No essays found in ELS for batch {batch_id}")
            print("   This means BatchEssaysRegistered event was not processed by ELS")
    
    # Step 3: Check Kafka for events
    print("\n3️⃣ Checking Kafka for events...")
    from aiokafka import AIOKafkaConsumer
    
    consumer = AIOKafkaConsumer(
        "huleedu.batch.essays.registered.v1",
        bootstrap_servers="localhost:9093",
        group_id=f"test_{uuid.uuid4().hex[:8]}",
        auto_offset_reset="earliest",
        consumer_timeout_ms=5000
    )
    
    await consumer.start()
    
    try:
        event_found = False
        async for msg in consumer:
            try:
                if msg.value:
                    event = json.loads(msg.value.decode('utf-8'))
                    event_batch_id = event.get("data", {}).get("batch_id")
                    if event_batch_id == batch_id:
                        print(f"✅ Found BatchEssaysRegistered event in Kafka")
                        print(f"   Event ID: {event.get('event_id')}")
                        print(f"   Correlation ID: {event.get('correlation_id')}")
                        event_found = True
                        break
            except:
                pass
        
        if not event_found:
            print("❌ BatchEssaysRegistered event NOT found in Kafka")
            print("   This means BOS is not publishing the event")
            
    finally:
        await consumer.stop()
    
    print("\n" + "=" * 50)
    print("📊 Summary:")
    if batch_id:
        print(f"   Batch ID: {batch_id}")
        print(f"   Correlation ID: {correlation_id}")
    else:
        print("   ❌ Failed at batch registration")


if __name__ == "__main__":
    asyncio.run(test_basic_flow())