#!/usr/bin/env python3
"""
Diagnostic script to trace the exact failure point in the E2E test.

This script runs a simplified version of the E2E test with detailed logging
at each step to identify where the pipeline stops.
"""

import asyncio
import json
import uuid
import time
from datetime import UTC, datetime
from pathlib import Path

import redis.asyncio as redis
from aiokafka import AIOKafkaConsumer

# Test configuration
KAFKA_BOOTSTRAP_SERVERS = "localhost:9093"
TOPICS_TO_MONITOR = [
    "huleedu.batch.essays.registered.v1",
    "huleedu.file.essay.content.provisioned.v1",
    "huleedu.els.batch.essays.ready.v1",
    "huleedu.batch.spellcheck.initiate.command.v1",
    "huleedu.spellcheck.completed.v1",
    "huleedu.batch.cj_assessment.initiate.command.v1",
    "huleedu.cj_assessment.completed.v1",
    "huleedu.els.batch.phase.outcome.v1",
    "huleedu.client.pipeline.request.v1",
]


async def monitor_kafka_events(test_batch_id: str, test_correlation_id: str, duration: int = 60):
    """Monitor Kafka events for a specific batch and correlation ID."""

    print(f"🔍 Monitoring Kafka events for:")
    print(f"   Batch ID: {test_batch_id}")
    print(f"   Correlation ID: {test_correlation_id}")
    print(f"   Duration: {duration} seconds")
    print(f"   Timeout: {duration} seconds")
    print()

    # Create consumer with unique group ID
    consumer = AIOKafkaConsumer(
        *TOPICS_TO_MONITOR,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=f"diagnostic_{uuid.uuid4().hex[:8]}",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda m: m.decode("utf-8") if m else None,
    )

    events_captured = []
    start_time = time.time()

    try:
        await consumer.start()
        print("✅ Kafka consumer started")

        while (time.time() - start_time) < duration:
            # Poll for messages with timeout
            try:
                records = await consumer.getmany(timeout_ms=1000)

                for topic_partition, messages in records.items():
                    for msg in messages:
                        try:
                            event_data = json.loads(msg.value) if msg.value else {}

                            # Extract key fields
                            event_type = event_data.get("event_type", "unknown")
                            event_id = event_data.get("event_id", "unknown")
                            correlation_id = event_data.get("correlation_id", "")
                            data = event_data.get("data", {})

                            # Check if this event is related to our test
                            batch_id = data.get("batch_id", "")

                            if batch_id == test_batch_id or correlation_id == test_correlation_id:
                                event_info = {
                                    "timestamp": time.time() - start_time,
                                    "topic": msg.topic,
                                    "event_type": event_type,
                                    "event_id": event_id,
                                    "correlation_id": correlation_id,
                                    "batch_id": batch_id,
                                    "offset": msg.offset,
                                    "data_keys": list(data.keys()),
                                }

                                events_captured.append(event_info)

                                print(f"\n📨 Event captured at +{event_info['timestamp']:.1f}s:")
                                print(f"   Topic: {msg.topic}")
                                print(f"   Event Type: {event_type}")
                                print(f"   Batch ID: {batch_id}")
                                print(f"   Correlation ID: {correlation_id}")
                                print(f"   Data Keys: {event_info['data_keys']}")

                        except Exception as e:
                            print(f"⚠️  Error parsing message: {e}")

            except asyncio.TimeoutError:
                # No messages in this interval
                elapsed = time.time() - start_time
                if int(elapsed) % 10 == 0:  # Print every 10 seconds
                    print(f"⏳ Waiting for events... ({int(elapsed)}s elapsed)")

    except Exception as e:
        print(f"❌ Consumer error: {e}")
    finally:
        await consumer.stop()
        print(f"\n✅ Monitoring completed. Captured {len(events_captured)} related events.")

    return events_captured


async def check_service_health():
    """Check if all required services are running."""
    import httpx

    services = {
        "Batch Orchestrator": "http://localhost:5001/health",
        "Essay Lifecycle API": "http://localhost:6001/health",
        "File Service": "http://localhost:7001/health",
        "Content Service": "http://localhost:8001/health",
        "API Gateway": "http://localhost:8080/health",
        "Spell Checker": "Not HTTP (Kafka worker)",
        "CJ Assessment": "Not HTTP (Kafka worker)",
    }

    print("🏥 Checking service health:")

    async with httpx.AsyncClient() as client:
        for name, url in services.items():
            if url.startswith("http"):
                try:
                    response = await client.get(url, timeout=5.0)
                    if response.status_code == 200:
                        print(f"   ✅ {name}: Healthy")
                    else:
                        print(f"   ❌ {name}: Unhealthy (status {response.status_code})")
                except Exception as e:
                    print(f"   ❌ {name}: Not reachable ({type(e).__name__})")
            else:
                print(f"   ℹ️  {name}: {url}")
    print()


async def check_redis_state():
    """Check Redis for any existing keys."""
    redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)

    try:
        all_keys = await redis_client.keys("*")
        print(f"📊 Redis state: {len(all_keys)} keys found")

        if all_keys:
            print("   Sample keys:")
            for key in all_keys[:5]:
                print(f"   - {key}")
            if len(all_keys) > 5:
                print(f"   ... and {len(all_keys) - 5} more")
    finally:
        await redis_client.aclose()
    print()


async def analyze_event_flow(events):
    """Analyze the captured events to identify issues."""
    print("\n🔎 Event Flow Analysis:")
    print("=" * 50)

    if not events:
        print("❌ No events captured - pipeline never started")
        return

    # Expected event flow
    expected_flow = [
        ("Batch Registration", "huleedu.batch.essays.registered.v1"),
        ("Content Provisioning", "huleedu.file.essay.content.provisioned.v1"),
        ("Essays Ready", "huleedu.els.batch.essays.ready.v1"),
        ("Spellcheck Command", "huleedu.batch.spellcheck.initiate.command.v1"),
        ("Spellcheck Results", "huleedu.spellcheck.completed.v1"),
        ("Phase Outcome", "huleedu.els.batch.phase.outcome.v1"),
        ("CJ Assessment Command", "huleedu.batch.cj_assessment.initiate.command.v1"),
        ("CJ Assessment Results", "huleedu.cj_assessment.completed.v1"),
        ("Final Phase Outcome", "huleedu.els.batch.phase.outcome.v1"),
    ]

    # Check which steps completed
    topics_seen = {event["topic"] for event in events}

    for step_name, expected_topic in expected_flow:
        if expected_topic in topics_seen:
            event_count = sum(1 for e in events if e["topic"] == expected_topic)
            print(f"✅ {step_name}: {event_count} event(s)")
        else:
            print(f"❌ {step_name}: MISSING")
            print(f"   ⚠️  Pipeline likely failed before this step")
            break

    # Show event timeline
    print("\n📅 Event Timeline:")
    for event in sorted(events, key=lambda x: x["timestamp"]):
        print(f"   +{event['timestamp']:5.1f}s: {event['topic'].split('.')[-2]}")

    # Check for duplicate events (idempotency issues)
    print("\n🔍 Checking for duplicate events:")
    event_ids = [e["event_id"] for e in events]
    unique_ids = set(event_ids)
    if len(event_ids) != len(unique_ids):
        print(f"   ⚠️  Found {len(event_ids) - len(unique_ids)} duplicate events!")
    else:
        print("   ✅ No duplicate events found")


async def main():
    """Run the diagnostic process."""
    import sys

    # Parse command line arguments
    timeout = 60  # default
    if len(sys.argv) > 1 and sys.argv[1].startswith("--timeout="):
        try:
            timeout = int(sys.argv[1].split("=")[1])
        except:
            print("⚠️  Invalid timeout value, using default 60 seconds")

    print("🔬 E2E Pipeline Diagnostic Tool")
    print("=" * 50)
    print(f"⏱️  Timeout: {timeout} seconds")
    print()

    # Step 1: Check prerequisites
    await check_service_health()
    await check_redis_state()

    # Step 2: Generate test identifiers
    test_batch_id = str(uuid.uuid4())
    test_correlation_id = str(uuid.uuid4())

    print(f"🆔 Test Identifiers:")
    print(f"   Batch ID: {test_batch_id}")
    print(f"   Correlation ID: {test_correlation_id}")
    print()

    # Step 3: Monitor events
    print("📡 Starting event monitoring...")
    print("   (Run your E2E test now with these IDs)")
    print()

    events = await monitor_kafka_events(test_batch_id, test_correlation_id, duration=timeout)

    # Step 4: Analyze results
    await analyze_event_flow(events)

    print("\n✅ Diagnostic complete")


if __name__ == "__main__":
    asyncio.run(main())
