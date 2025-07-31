"""
Simplified Race Condition Debug Test

This test proves that the order of BatchEssaysRegistered vs EssayContentProvisioned events
determines whether essays are assigned to slots or marked as excess content.

Uses minimal infrastructure to isolate the specific race condition.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Dict, List, Optional
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.envelope import EventEnvelope
from common_core.events.file_events import EssayContentProvisionedV1
from huleedu_service_libs.logging_utils import create_service_logger
from redis.asyncio import Redis

logger = create_service_logger("test.race_condition_simplified")


class SimulatedELS:
    """Minimal simulation of ELS batch and essay handling logic."""
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.events_processed = []
        self.outcomes = []
    
    async def process_batch_essays_registered(self, event: BatchEssaysRegistered) -> None:
        """Process batch registration - creates slots for essays."""
        batch_id = event.batch_id
        expected_count = event.expected_essay_count
        
        # Create available slots in Redis (simulating ELS behavior)
        for i in range(expected_count):
            await self.redis.sadd(f"batch:{batch_id}:available_slots", f"slot_{i}")
        
        # Store batch metadata
        await self.redis.hset(f"batch:{batch_id}:metadata", mapping={
            "expected_count": str(expected_count),
            "status": "registered",
            "correlation_id": str(event.metadata.correlation_id) if hasattr(event.metadata, 'correlation_id') else "",
        })
        
        self.events_processed.append(("BatchEssaysRegistered", batch_id))
        logger.info(f"✅ Registered batch {batch_id} with {expected_count} slots")
    
    async def process_essay_content_provisioned(self, event: EssayContentProvisionedV1) -> str:
        """
        Process essay content - tries to assign to slot.
        Returns: "assigned" or "excess_content"
        """
        batch_id = event.batch_id
        text_storage_id = event.text_storage_id
        
        # Check if batch exists
        batch_exists = await self.redis.exists(f"batch:{batch_id}:metadata")
        if not batch_exists:
            # Batch not registered yet - essay becomes excess content
            self.events_processed.append(("EssayContentProvisioned", f"{text_storage_id} -> EXCESS (no batch)"))
            self.outcomes.append({
                "essay": text_storage_id,
                "result": "excess_content",
                "reason": "batch_not_registered",
            })
            logger.warning(f"❌ Essay {text_storage_id} marked as EXCESS - batch {batch_id} not registered")
            return "excess_content"
        
        # Try to assign to available slot
        slot = await self.redis.spop(f"batch:{batch_id}:available_slots")
        if slot:
            # Successfully assigned
            await self.redis.hset(f"batch:{batch_id}:assignments", text_storage_id, slot.decode())
            self.events_processed.append(("EssayContentProvisioned", f"{text_storage_id} -> ASSIGNED"))
            self.outcomes.append({
                "essay": text_storage_id,
                "result": "assigned",
                "slot": slot.decode(),
            })
            logger.info(f"✅ Essay {text_storage_id} assigned to {slot.decode()}")
            
            # Check if batch is complete
            assigned_count = await self.redis.hlen(f"batch:{batch_id}:assignments")
            expected_count = int((await self.redis.hget(f"batch:{batch_id}:metadata", "expected_count")).decode())
            
            if assigned_count == expected_count:
                logger.info(f"🎉 Batch {batch_id} COMPLETE - would publish BatchEssaysReady")
                self.outcomes.append({
                    "batch": batch_id,
                    "result": "batch_ready",
                    "essay_count": assigned_count,
                })
            
            return "assigned"
        else:
            # No slots available - excess content
            self.events_processed.append(("EssayContentProvisioned", f"{text_storage_id} -> EXCESS (no slots)"))
            self.outcomes.append({
                "essay": text_storage_id,
                "result": "excess_content",
                "reason": "no_slots_available",
            })
            logger.warning(f"❌ Essay {text_storage_id} marked as EXCESS - no slots available")
            return "excess_content"


class TestRaceConditionSimplified:
    """Simplified test focusing on the core race condition."""
    
    @pytest.fixture
    async def redis_client(self):
        """Create Redis client for testing."""
        # Use Redis on localhost (requires Redis running)
        redis = Redis(host="localhost", port=6379, decode_responses=False)
        
        # Clean up any test data
        await redis.flushdb()
        
        yield redis
        
        await redis.close()
    
    @pytest.mark.asyncio
    async def test_correct_order_success(self, redis_client: Redis):
        """Test: BatchEssaysRegistered BEFORE EssayContentProvisioned = SUCCESS"""
        logger.info("\n" + "="*80)
        logger.info("TEST 1: CORRECT ORDER (Batch Registration → Essay Content)")
        logger.info("="*80)
        
        # Setup
        batch_id = str(uuid4())
        correlation_id = str(uuid4())
        els = SimulatedELS(redis_client)
        
        # Step 1: Process BatchEssaysRegistered FIRST
        batch_event = BatchEssaysRegisteredV1(
            batch_id=batch_id,
            expected_count=2,
            correlation_id=correlation_id,
        )
        await els.process_batch_essays_registered(batch_event)
        
        # Step 2: Process EssayContentProvisioned events AFTER
        for i in range(2):
            essay_event = EssayContentProvisionedV1(
                batch_id=batch_id,
                text_storage_id=f"storage_{i}",
                original_file_name=f"essay_{i}.txt",
                correlation_id=correlation_id,
            )
            await els.process_essay_content_provisioned(essay_event)
        
        # Verify results
        logger.info(f"\nEvent processing order: {els.events_processed}")
        logger.info(f"Outcomes: {json.dumps(els.outcomes, indent=2)}")
        
        # Assertions
        excess_count = sum(1 for o in els.outcomes if o.get("result") == "excess_content")
        assigned_count = sum(1 for o in els.outcomes if o.get("result") == "assigned")
        batch_ready = any(o.get("result") == "batch_ready" for o in els.outcomes)
        
        assert excess_count == 0, "Should have NO excess content"
        assert assigned_count == 2, "All essays should be assigned"
        assert batch_ready, "Batch should be ready"
        
        logger.info("\n✅ SUCCESS: All essays assigned, BatchEssaysReady would be published")
    
    @pytest.mark.asyncio
    async def test_race_condition_failure(self, redis_client: Redis):
        """Test: EssayContentProvisioned BEFORE BatchEssaysRegistered = FAILURE"""
        logger.info("\n" + "="*80)
        logger.info("TEST 2: RACE CONDITION (Essay Content → Batch Registration)")
        logger.info("="*80)
        
        # Setup
        batch_id = str(uuid4())
        correlation_id = str(uuid4())
        els = SimulatedELS(redis_client)
        
        # Step 1: Process EssayContentProvisioned events FIRST (RACE CONDITION)
        for i in range(2):
            essay_event = EssayContentProvisionedV1(
                batch_id=batch_id,
                text_storage_id=f"storage_{i}",
                original_file_name=f"essay_{i}.txt",
                correlation_id=correlation_id,
            )
            await els.process_essay_content_provisioned(essay_event)
        
        # Step 2: Process BatchEssaysRegistered AFTER (TOO LATE)
        batch_event = BatchEssaysRegisteredV1(
            batch_id=batch_id,
            expected_count=2,
            correlation_id=correlation_id,
        )
        await els.process_batch_essays_registered(batch_event)
        
        # Verify results
        logger.info(f"\nEvent processing order: {els.events_processed}")
        logger.info(f"Outcomes: {json.dumps(els.outcomes, indent=2)}")
        
        # Assertions
        excess_count = sum(1 for o in els.outcomes if o.get("result") == "excess_content")
        assigned_count = sum(1 for o in els.outcomes if o.get("result") == "assigned")
        batch_ready = any(o.get("result") == "batch_ready" for o in els.outcomes)
        
        assert excess_count == 2, "All essays should be excess content"
        assert assigned_count == 0, "No essays should be assigned"
        assert not batch_ready, "Batch should NOT be ready"
        
        logger.info("\n❌ FAILURE: All essays marked as excess content, NO BatchEssaysReady")
    
    @pytest.mark.asyncio
    async def test_partial_race_condition(self, redis_client: Redis):
        """Test: Mixed timing - some essays before, some after batch registration"""
        logger.info("\n" + "="*80)
        logger.info("TEST 3: PARTIAL RACE CONDITION (Mixed Timing)")
        logger.info("="*80)
        
        # Setup
        batch_id = str(uuid4())
        correlation_id = str(uuid4())
        els = SimulatedELS(redis_client)
        
        # Step 1: First essay arrives BEFORE batch registration
        essay_event_1 = EssayContentProvisionedV1(
            batch_id=batch_id,
            text_storage_id="storage_0",
            original_file_name="essay_0.txt",
            correlation_id=correlation_id,
        )
        await els.process_essay_content_provisioned(essay_event_1)
        
        # Step 2: Batch registration
        batch_event = BatchEssaysRegisteredV1(
            batch_id=batch_id,
            expected_count=2,
            correlation_id=correlation_id,
        )
        await els.process_batch_essays_registered(batch_event)
        
        # Step 3: Second essay arrives AFTER batch registration  
        essay_event_2 = EssayContentProvisionedV1(
            batch_id=batch_id,
            text_storage_id="storage_1",
            original_file_name="essay_1.txt",
            correlation_id=correlation_id,
        )
        await els.process_essay_content_provisioned(essay_event_2)
        
        # Verify results
        logger.info(f"\nEvent processing order: {els.events_processed}")
        logger.info(f"Outcomes: {json.dumps(els.outcomes, indent=2)}")
        
        # Assertions
        excess_count = sum(1 for o in els.outcomes if o.get("result") == "excess_content")
        assigned_count = sum(1 for o in els.outcomes if o.get("result") == "assigned")
        
        assert excess_count == 1, "First essay should be excess content"
        assert assigned_count == 1, "Second essay should be assigned"
        
        logger.info("\n⚠️ PARTIAL FAILURE: Only essays arriving after batch registration are assigned")
    
    @pytest.mark.asyncio
    async def test_relay_worker_delay_simulation(self, redis_client: Redis):
        """Test: Simulate actual relay worker delays that cause the race condition"""
        logger.info("\n" + "="*80)
        logger.info("TEST 4: RELAY WORKER DELAY SIMULATION")
        logger.info("="*80)
        
        # Setup
        batch_id = str(uuid4())
        correlation_id = str(uuid4())
        els = SimulatedELS(redis_client)
        
        # Simulate events being stored in outbox at nearly the same time
        batch_stored_time = 1000.0  # milliseconds
        essay1_stored_time = 1000.1
        essay2_stored_time = 1000.2
        
        # Simulate relay worker processing with different delays
        bos_relay_delay = 2.0  # BOS relay worker is slower
        file_relay_delay = 0.5  # File service relay worker is faster
        
        # Calculate when events would be published to Kafka
        batch_published_time = batch_stored_time + bos_relay_delay
        essay1_published_time = essay1_stored_time + file_relay_delay
        essay2_published_time = essay2_stored_time + file_relay_delay
        
        logger.info(f"Batch stored at {batch_stored_time}ms, published at {batch_published_time}ms")
        logger.info(f"Essay 1 stored at {essay1_stored_time}ms, published at {essay1_published_time}ms")
        logger.info(f"Essay 2 stored at {essay2_stored_time}ms, published at {essay2_published_time}ms")
        
        # Process events in publication order
        events = [
            (essay1_published_time, "essay", EssayContentProvisionedV1(
                batch_id=batch_id,
                text_storage_id="storage_0",
                original_file_name="essay_0.txt",
                correlation_id=correlation_id,
            )),
            (essay2_published_time, "essay", EssayContentProvisionedV1(
                batch_id=batch_id,
                text_storage_id="storage_1",
                original_file_name="essay_1.txt",
                correlation_id=correlation_id,
            )),
            (batch_published_time, "batch", BatchEssaysRegisteredV1(
                batch_id=batch_id,
                expected_count=2,
                correlation_id=correlation_id,
            )),
        ]
        
        # Sort by publication time
        events.sort(key=lambda x: x[0])
        
        logger.info(f"\nActual processing order due to relay worker delays:")
        for pub_time, event_type, event in events:
            logger.info(f"  {pub_time}ms: {event_type}")
            if event_type == "batch":
                await els.process_batch_essays_registered(event)
            else:
                await els.process_essay_content_provisioned(event)
        
        # Verify results  
        logger.info(f"\nOutcomes: {json.dumps(els.outcomes, indent=2)}")
        
        excess_count = sum(1 for o in els.outcomes if o.get("result") == "excess_content")
        assert excess_count == 2, "Both essays become excess content due to relay worker delays"
        
        logger.info("\n💡 INSIGHT: Even tiny relay worker delays can cause race conditions!")


if __name__ == "__main__":
    import sys
    pytest.main([__file__, "-v", "-s", "--tb=short"])