#!/usr/bin/env python3
"""
Event generator for distributed testing of Essay Lifecycle Service.

Generates concurrent content provisioning events to test race condition prevention
and distributed coordination under load.
"""

import asyncio
import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

import httpx
from kafka import KafkaProducer
from pydantic import BaseModel


class ContentProvisionedEvent(BaseModel):
    """Model for EssayContentProvisionedV1 event data."""
    
    essay_id: str
    batch_id: str
    text_storage_id: str
    original_file_name: str
    file_size_bytes: int
    content_md5_hash: str
    status: str = "UPLOADED"


class EventEnvelope(BaseModel):
    """Standard event envelope for Kafka messages."""
    
    event_id: str
    event_type: str
    event_timestamp: str
    source_service: str
    correlation_id: str
    data: Dict[str, Any]


class DistributedTestEventGenerator:
    """Generates events for distributed testing scenarios."""
    
    def __init__(self) -> None:
        self.kafka_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
        self.els_url = os.getenv("ELS_LOAD_BALANCER_URL", "http://nginx_load_balancer")
        self.concurrent_events = int(os.getenv("CONCURRENT_EVENTS", "20"))
        self.test_duration = int(os.getenv("TEST_DURATION_SECONDS", "60"))
        
        # Initialize Kafka producer
        self.producer = KafkaProducer(
            bootstrap_servers=[self.kafka_servers],
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all',  # Wait for all replicas
            retries=3,
            max_in_flight_requests_per_connection=1,  # Ensure ordering
        )
        
        # HTTP client for API calls
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
    
    def generate_content_event(self, batch_id: str, essay_id: str) -> EventEnvelope:
        """Generate a content provisioned event for testing."""
        
        # Create unique content metadata
        content_data = ContentProvisionedEvent(
            essay_id=essay_id,
            batch_id=batch_id,
            text_storage_id=f"text_{uuid4().hex[:8]}",
            original_file_name=f"essay_{essay_id}_{random.randint(1, 1000)}.txt",
            file_size_bytes=random.randint(1000, 50000),
            content_md5_hash=uuid4().hex,
        )
        
        # Wrap in event envelope
        return EventEnvelope(
            event_id=str(uuid4()),
            event_type="EssayContentProvisionedV1",
            event_timestamp=datetime.now(timezone.utc).isoformat(),
            source_service="distributed_test_generator",
            correlation_id=str(uuid4()),
            data=content_data.model_dump(),
        )
    
    async def send_kafka_event(self, topic: str, event: EventEnvelope) -> None:
        """Send event to Kafka topic."""
        try:
            future = self.producer.send(topic, value=event.model_dump())
            # Wait for send to complete
            future.get(timeout=10)
            print(f"✅ Sent event {event.event_id} to topic {topic}")
        except Exception as e:
            print(f"❌ Failed to send event {event.event_id}: {e}")
    
    async def create_test_batch_via_api(self, batch_id: str, essay_count: int) -> bool:
        """Create a test batch via ELS API."""
        try:
            batch_data = {
                "batch_id": batch_id,
                "expected_essay_count": essay_count,
                "essay_ids": [f"essay_{i:03d}" for i in range(essay_count)],
                "course_code": "ENG5",
                "essay_instructions": "Distributed test essay",
                "user_id": "test_user_distributed",
            }
            
            response = await self.http_client.post(
                f"{self.els_url}/api/v1/batches",
                json=batch_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 201:
                print(f"✅ Created batch {batch_id} with {essay_count} essays")
                return True
            else:
                print(f"❌ Failed to create batch {batch_id}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Failed to create batch {batch_id}: {e}")
            return False
    
    async def test_concurrent_race_conditions(self) -> None:
        """Test scenario: Multiple identical events for race condition prevention."""
        
        print("🚀 Starting concurrent race condition test...")
        
        # Create test batch
        batch_id = f"race_test_{uuid4().hex[:8]}"
        essay_count = 5
        
        if not await self.create_test_batch_via_api(batch_id, essay_count):
            return
        
        # Wait for batch creation to propagate
        await asyncio.sleep(2)
        
        # Generate identical events for the same content to test race conditions
        target_essay = "essay_001"
        identical_events = []
        
        for i in range(self.concurrent_events):
            # Create IDENTICAL events (same text_storage_id, different event_id)
            event = self.generate_content_event(batch_id, target_essay)
            # Make text_storage_id identical to test race conditions
            event.data["text_storage_id"] = "identical_content_12345"
            identical_events.append(event)
        
        print(f"📤 Sending {len(identical_events)} identical events concurrently...")
        
        # Send all events concurrently
        start_time = time.time()
        tasks = [
            self.send_kafka_event("essay_content_provisioned", event)
            for event in identical_events
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        duration = time.time() - start_time
        print(f"⏱️  Sent {len(identical_events)} events in {duration:.2f}s")
        
        # Wait for processing
        await asyncio.sleep(5)
        
        # Check batch status to verify only one assignment occurred
        await self.check_batch_status(batch_id)
    
    async def test_distributed_coordination(self) -> None:
        """Test scenario: Multiple batches across different instances."""
        
        print("🌐 Starting distributed coordination test...")
        
        # Create multiple batches simultaneously
        batch_count = 3
        essays_per_batch = 4
        
        batch_creation_tasks = []
        for i in range(batch_count):
            batch_id = f"distributed_test_{i}_{uuid4().hex[:8]}"
            task = self.create_test_batch_via_api(batch_id, essays_per_batch)
            batch_creation_tasks.append((batch_id, task))
        
        # Create all batches concurrently
        batch_results = []
        for batch_id, task in batch_creation_tasks:
            result = await task
            if result:
                batch_results.append(batch_id)
        
        print(f"✅ Created {len(batch_results)} batches successfully")
        
        # Wait for batch creation to propagate
        await asyncio.sleep(3)
        
        # Generate content events for all batches concurrently
        all_events = []
        for batch_id in batch_results:
            for essay_idx in range(essays_per_batch):
                essay_id = f"essay_{essay_idx:03d}"
                event = self.generate_content_event(batch_id, essay_id)
                all_events.append(event)
        
        print(f"📤 Sending {len(all_events)} content events across {len(batch_results)} batches...")
        
        # Send all events concurrently
        start_time = time.time()
        tasks = [
            self.send_kafka_event("essay_content_provisioned", event)
            for event in all_events
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        duration = time.time() - start_time
        print(f"⏱️  Sent {len(all_events)} events in {duration:.2f}s")
        
        # Wait for processing
        await asyncio.sleep(10)
        
        # Check status of all batches
        for batch_id in batch_results:
            await self.check_batch_status(batch_id)
    
    async def test_performance_load(self) -> None:
        """Test scenario: High load for performance validation."""
        
        print("⚡ Starting performance load test...")
        
        # Create larger batch for load testing
        batch_id = f"load_test_{uuid4().hex[:8]}"
        essay_count = 20
        
        if not await self.create_test_batch_via_api(batch_id, essay_count):
            return
        
        await asyncio.sleep(2)
        
        # Generate events at high rate
        events = []
        for essay_idx in range(essay_count):
            essay_id = f"essay_{essay_idx:03d}"
            event = self.generate_content_event(batch_id, essay_id)
            events.append(event)
        
        print(f"📤 Sending {len(events)} events for load testing...")
        
        # Send in waves to test sustained load
        wave_size = 5
        waves = [events[i:i + wave_size] for i in range(0, len(events), wave_size)]
        
        total_start = time.time()
        
        for wave_idx, wave in enumerate(waves):
            wave_start = time.time()
            
            tasks = [
                self.send_kafka_event("essay_content_provisioned", event)
                for event in wave
            ]
            
            await asyncio.gather(*tasks, return_exceptions=True)
            
            wave_duration = time.time() - wave_start
            print(f"📊 Wave {wave_idx + 1}/{len(waves)}: {len(wave)} events in {wave_duration:.2f}s")
            
            # Small delay between waves
            await asyncio.sleep(1)
        
        total_duration = time.time() - total_start
        throughput = len(events) / total_duration
        print(f"🏁 Load test complete: {len(events)} events in {total_duration:.2f}s ({throughput:.1f} events/s)")
        
        # Wait for processing
        await asyncio.sleep(15)
        await self.check_batch_status(batch_id)
    
    async def check_batch_status(self, batch_id: str) -> None:
        """Check batch status via API."""
        try:
            response = await self.http_client.get(f"{self.els_url}/api/v1/batches/{batch_id}/status")
            
            if response.status_code == 200:
                status = response.json()
                print(f"📊 Batch {batch_id} status:")
                print(f"   - Total essays: {status.get('total_essays', 'unknown')}")
                print(f"   - Status breakdown: {status.get('status_summary', {})}")
                print(f"   - Ready for processing: {status.get('ready_for_processing', False)}")
            else:
                print(f"❌ Failed to get status for batch {batch_id}: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error checking batch {batch_id} status: {e}")
    
    async def run_test_suite(self) -> None:
        """Run complete distributed test suite."""
        
        print("🎯 Starting distributed test suite...")
        print(f"   - Kafka servers: {self.kafka_servers}")
        print(f"   - ELS URL: {self.els_url}")
        print(f"   - Concurrent events: {self.concurrent_events}")
        print(f"   - Test duration: {self.test_duration}s")
        print()
        
        try:
            # Test 1: Race condition prevention
            await self.test_concurrent_race_conditions()
            await asyncio.sleep(5)
            
            # Test 2: Distributed coordination
            await self.test_distributed_coordination()
            await asyncio.sleep(5)
            
            # Test 3: Performance load
            await self.test_performance_load()
            
            print("✅ All distributed tests completed successfully!")
            
        except Exception as e:
            print(f"❌ Test suite failed: {e}")
            raise
        finally:
            await self.http_client.aclose()
            self.producer.close()


async def main() -> None:
    """Main entry point for event generator."""
    
    generator = DistributedTestEventGenerator()
    await generator.run_test_suite()


if __name__ == "__main__":
    asyncio.run(main())