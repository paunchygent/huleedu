#!/usr/bin/env python3
"""
Test the minimal flow to see where it breaks.
Just monitor Kafka to see what events are flowing.
"""

import asyncio
import json
import time
from aiokafka import AIOKafkaConsumer

async def monitor_all_events():
    """Monitor ALL Kafka events to see what's happening."""
    
    print("🔍 Monitoring ALL Kafka Events")
    print("=" * 50)
    
    # Monitor ALL topics
    topics = [
        "huleedu.batch.essays.registered.v1",
        "huleedu.file.essay.content.provisioned.v1",
        "huleedu.els.batch.essays.ready.v1",
        "huleedu.batch.spellcheck.initiate.command.v1",
        "huleedu.spellcheck.completed.v1",
        "huleedu.essay.spellcheck.completed.v1",
        "huleedu.batch.cj_assessment.initiate.command.v1",
        "huleedu.cj_assessment.completed.v1",
        "huleedu.els.batch.phase.outcome.v1",
        "huleedu.els.excess.content.provisioned.v1"
    ]
    
    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers="localhost:9093",
        group_id="monitor_all",
        auto_offset_reset="latest",  # Only new events
        enable_auto_commit=False
    )
    
    await consumer.start()
    print("✅ Monitoring started (showing only NEW events)")
    print("\n👉 NOW RUN THE E2E TEST in another terminal:")
    print("   python test_redis_isolation.py")
    print("\n📡 Waiting for events...\n")
    
    start_time = time.time()
    event_count = 0
    
    try:
        while True:
            records = await consumer.getmany(timeout_ms=1000)
            
            for topic_partition, messages in records.items():
                for msg in messages:
                    event_count += 1
                    elapsed = time.time() - start_time
                    
                    try:
                        event = json.loads(msg.value.decode('utf-8'))
                        event_type = event.get("event_type", "unknown")
                        batch_id = event.get("data", {}).get("batch_id", "N/A")
                        correlation_id = event.get("correlation_id", "N/A")
                        
                        print(f"📨 [{event_count}] +{elapsed:.1f}s: {event_type}")
                        print(f"   Topic: {msg.topic}")
                        print(f"   Batch ID: {batch_id}")
                        print(f"   Correlation ID: {correlation_id}")
                        
                        # Special checks
                        if "ready" in event_type.lower():
                            print("   ⚡ This is a READY event - pipeline should continue!")
                        if "excess" in event_type.lower():
                            print("   ⚠️  EXCESS content - no slots available!")
                            
                        print()
                        
                    except Exception as e:
                        print(f"⚠️  Error parsing event: {e}")
                        print()
            
            # Status update every 10 seconds
            elapsed = time.time() - start_time
            if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                print(f"⏳ {int(elapsed)}s elapsed, {event_count} events captured\n")
                
    except KeyboardInterrupt:
        print("\n\n🛑 Monitoring stopped")
        print(f"📊 Total events captured: {event_count}")
    finally:
        await consumer.stop()


if __name__ == "__main__":
    print("Press Ctrl+C to stop monitoring\n")
    asyncio.run(monitor_all_events())