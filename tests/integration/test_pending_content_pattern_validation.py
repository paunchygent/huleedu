"""
Test suite to validate the Pending Content Pattern solution for race condition fix.

This test proves that the pending content pattern can solve the race condition
where EssayContentProvisioned events arrive before BatchEssaysRegistered events.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.file_events import EssayContentProvisionedV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from huleedu_service_libs.logging_utils import create_service_logger
from redis.asyncio import Redis

logger = create_service_logger("test.pending_content_pattern")


class PendingContentManager:
    """
    Manages pending content that arrives before batch registration.
    This is the core component that enables the race condition fix.
    """
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.logger = create_service_logger("pending_content_manager")
    
    async def store_pending_content(
        self, 
        batch_id: str, 
        text_storage_id: str,
        content_metadata: dict
    ) -> None:
        """Store content as pending until batch registration arrives."""
        # Add to batch-specific pending set
        pending_key = f"pending_content:{batch_id}"
        
        # Store metadata as JSON
        metadata_with_storage = {
            **content_metadata,
            "text_storage_id": text_storage_id,
            "stored_at": datetime.now(UTC).isoformat()
        }
        
        await self.redis.sadd(pending_key, json.dumps(metadata_with_storage))
        
        # Add to global index for monitoring/cleanup
        index_key = "pending_content:index"
        score = datetime.now(UTC).timestamp()
        await self.redis.zadd(index_key, {batch_id: score})
        
        # Set TTL on pending content (24 hours)
        await self.redis.expire(pending_key, 86400)
        
        self.logger.info(
            f"Stored pending content for batch {batch_id}: {text_storage_id}"
        )
    
    async def get_pending_content(self, batch_id: str) -> List[dict]:
        """Retrieve all pending content for a batch."""
        pending_key = f"pending_content:{batch_id}"
        
        # Get all pending content items
        pending_items = await self.redis.smembers(pending_key)
        
        if not pending_items:
            return []
        
        # Parse JSON metadata
        content_list = []
        for item in pending_items:
            try:
                metadata = json.loads(item)
                content_list.append(metadata)
            except json.JSONDecodeError:
                self.logger.error(f"Failed to parse pending content: {item}")
        
        return content_list
    
    async def remove_pending_content(
        self, 
        batch_id: str, 
        text_storage_id: str
    ) -> bool:
        """Remove specific pending content after it's been processed."""
        pending_key = f"pending_content:{batch_id}"
        
        # Find and remove the specific item
        pending_items = await self.redis.smembers(pending_key)
        
        for item in pending_items:
            try:
                metadata = json.loads(item)
                if metadata.get("text_storage_id") == text_storage_id:
                    await self.redis.srem(pending_key, item)
                    
                    # Clean up index if batch has no more pending content
                    remaining = await self.redis.scard(pending_key)
                    if remaining == 0:
                        await self.redis.zrem("pending_content:index", batch_id)
                        await self.redis.delete(pending_key)
                    
                    return True
            except json.JSONDecodeError:
                continue
        
        return False
    
    async def clear_all_pending(self, batch_id: str) -> None:
        """Clear all pending content for a batch."""
        pending_key = f"pending_content:{batch_id}"
        await self.redis.delete(pending_key)
        await self.redis.zrem("pending_content:index", batch_id)


class EnhancedBatchTracker:
    """
    Enhanced batch tracker that handles both registered batches and pending content.
    This simulates the enhanced ELS batch tracker with pending content support.
    """
    
    def __init__(self, redis_client: Redis, pending_manager: PendingContentManager):
        self.redis = redis_client
        self.pending_manager = pending_manager
        self.logger = create_service_logger("enhanced_batch_tracker")
        self.events_processed = []
        self.outcomes = []
    
    async def register_batch(
        self, 
        event: BatchEssaysRegistered,
        correlation_id: UUID
    ) -> None:
        """Register batch and reconcile any pending content."""
        batch_id = event.batch_id
        
        # Register batch slots
        for i, essay_id in enumerate(event.essay_ids):
            await self.redis.sadd(f"batch:{batch_id}:available_slots", essay_id)
        
        # Store batch metadata
        await self.redis.hset(f"batch:{batch_id}:metadata", mapping={
            "expected_count": str(event.expected_essay_count),
            "status": "registered",
            "correlation_id": str(correlation_id),
            "course_code": event.course_code.value,
        })
        
        self.events_processed.append(("BatchEssaysRegistered", batch_id))
        self.logger.info(f"✅ Registered batch {batch_id} with {event.expected_essay_count} slots")
        
        # NEW: Check for and process pending content
        pending_content = await self.pending_manager.get_pending_content(batch_id)
        
        if pending_content:
            self.logger.info(
                f"Found {len(pending_content)} pending content items for batch {batch_id}"
            )
            
            # Process each pending content item
            for content in pending_content:
                await self._process_pending_content(batch_id, content)
    
    async def _process_pending_content(
        self, 
        batch_id: str, 
        content_metadata: dict
    ) -> None:
        """Process a single pending content item."""
        text_storage_id = content_metadata["text_storage_id"]
        
        # Try to assign to slot
        slot = await self.redis.spop(f"batch:{batch_id}:available_slots")
        
        if slot:
            # Successfully assigned
            await self.redis.hset(
                f"batch:{batch_id}:assignments", 
                slot.decode(), 
                text_storage_id
            )
            
            # Remove from pending
            await self.pending_manager.remove_pending_content(batch_id, text_storage_id)
            
            self.events_processed.append(
                ("PendingContentReconciled", f"{text_storage_id} -> ASSIGNED to {slot.decode()}")
            )
            self.outcomes.append({
                "essay": text_storage_id,
                "result": "reconciled_and_assigned",
                "slot": slot.decode(),
                "was_pending": True
            })
            
            self.logger.info(
                f"✅ Reconciled pending content {text_storage_id} -> assigned to {slot.decode()}"
            )
            
            # Check if batch is complete
            await self._check_batch_completion(batch_id)
        else:
            # Still no slots - remains as excess
            self.logger.warning(
                f"❌ No slots available for pending content {text_storage_id}"
            )
    
    async def process_essay_content(
        self, 
        event: EssayContentProvisionedV1
    ) -> str:
        """
        Process essay content - either assign to slot or store as pending.
        Returns: "assigned", "pending", or "excess_content"
        """
        batch_id = event.batch_id
        text_storage_id = event.text_storage_id
        
        # Check if batch exists
        batch_exists = await self.redis.exists(f"batch:{batch_id}:metadata")
        
        if not batch_exists:
            # NEW: Store as pending instead of marking as excess
            content_metadata = {
                "original_file_name": event.original_file_name,
                "file_upload_id": event.file_upload_id,
                "file_size_bytes": event.file_size_bytes,
                "correlation_id": str(event.correlation_id),
            }
            
            await self.pending_manager.store_pending_content(
                batch_id, 
                text_storage_id,
                content_metadata
            )
            
            self.events_processed.append(
                ("EssayContentProvisioned", f"{text_storage_id} -> PENDING")
            )
            self.outcomes.append({
                "essay": text_storage_id,
                "result": "pending",
                "reason": "batch_not_registered_yet"
            })
            
            self.logger.info(
                f"📋 Essay {text_storage_id} stored as PENDING - batch {batch_id} not registered yet"
            )
            return "pending"
        
        # Batch exists - try normal assignment
        slot = await self.redis.spop(f"batch:{batch_id}:available_slots")
        
        if slot:
            # Successfully assigned
            await self.redis.hset(
                f"batch:{batch_id}:assignments", 
                slot.decode(), 
                text_storage_id
            )
            
            self.events_processed.append(
                ("EssayContentProvisioned", f"{text_storage_id} -> ASSIGNED to {slot.decode()}")
            )
            self.outcomes.append({
                "essay": text_storage_id,
                "result": "assigned",
                "slot": slot.decode()
            })
            
            self.logger.info(f"✅ Essay {text_storage_id} assigned to {slot.decode()}")
            
            # Check if batch is complete
            await self._check_batch_completion(batch_id)
            
            return "assigned"
        else:
            # No slots available - true excess content
            self.events_processed.append(
                ("EssayContentProvisioned", f"{text_storage_id} -> EXCESS (no slots)")
            )
            self.outcomes.append({
                "essay": text_storage_id,
                "result": "excess_content",
                "reason": "no_slots_available"
            })
            
            self.logger.warning(f"❌ Essay {text_storage_id} marked as EXCESS - no slots available")
            return "excess_content"
    
    async def _check_batch_completion(self, batch_id: str) -> None:
        """Check if batch is complete and log the event."""
        assigned_count = await self.redis.hlen(f"batch:{batch_id}:assignments")
        expected_count = int(
            (await self.redis.hget(f"batch:{batch_id}:metadata", "expected_count")).decode()
        )
        
        if assigned_count == expected_count:
            self.logger.info(f"🎉 Batch {batch_id} COMPLETE - would publish BatchEssaysReady")
            self.outcomes.append({
                "batch": batch_id,
                "result": "batch_ready",
                "essay_count": assigned_count
            })


class TestPendingContentPattern:
    """Test suite validating the pending content pattern solution."""
    
    @pytest.fixture
    async def redis_client(self):
        """Create Redis client for testing."""
        redis = Redis(host="localhost", port=6379, decode_responses=False)
        await redis.flushdb()
        yield redis
        await redis.aclose()
    
    @pytest.fixture
    def pending_manager(self, redis_client):
        """Create pending content manager."""
        return PendingContentManager(redis_client)
    
    @pytest.fixture
    def batch_tracker(self, redis_client, pending_manager):
        """Create enhanced batch tracker."""
        return EnhancedBatchTracker(redis_client, pending_manager)
    
    def create_batch_event(self, batch_id: str, expected_count: int = 2) -> BatchEssaysRegistered:
        """Helper to create a BatchEssaysRegistered event."""
        return BatchEssaysRegistered(
            batch_id=batch_id,
            expected_essay_count=expected_count,
            essay_ids=[f"essay_{i}" for i in range(expected_count)],
            course_code=CourseCode.ENG5,
            essay_instructions="Test instructions",
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                ),
                timestamp=datetime.now(UTC),
            ),
        )
    
    def create_essay_event(self, batch_id: str, index: int) -> EssayContentProvisionedV1:
        """Helper to create an EssayContentProvisionedV1 event."""
        return EssayContentProvisionedV1(
            batch_id=batch_id,
            text_storage_id=f"storage_{index}",
            original_file_name=f"essay_{index}.txt",
            file_upload_id=f"upload_{index}",
            raw_file_storage_id=f"raw_storage_{index}",
            file_size_bytes=1000,
            correlation_id=uuid4(),
        )
    
    @pytest.mark.asyncio
    async def test_race_condition_fixed_with_pending_pattern(
        self, batch_tracker: EnhancedBatchTracker
    ):
        """Test: Essays arriving before batch are stored as pending and later reconciled."""
        logger.info("\n" + "="*80)
        logger.info("TEST: PENDING CONTENT PATTERN - Race Condition Fix")
        logger.info("="*80)
        
        batch_id = str(uuid4())
        correlation_id = uuid4()
        
        # Step 1: Essays arrive BEFORE batch registration
        for i in range(2):
            essay_event = self.create_essay_event(batch_id, i)
            result = await batch_tracker.process_essay_content(essay_event)
            assert result == "pending", f"Essay {i} should be pending"
        
        # Verify essays are pending, not excess
        pending_outcomes = [o for o in batch_tracker.outcomes if o.get("result") == "pending"]
        assert len(pending_outcomes) == 2, "Both essays should be pending"
        
        # Step 2: Batch registration arrives and reconciles pending content
        batch_event = self.create_batch_event(batch_id, expected_count=2)
        await batch_tracker.register_batch(batch_event, correlation_id)
        
        # Verify outcomes
        logger.info(f"\nEvent processing order: {batch_tracker.events_processed}")
        logger.info(f"Outcomes: {json.dumps(batch_tracker.outcomes, indent=2)}")
        
        # Check reconciliation happened
        reconciled = [o for o in batch_tracker.outcomes if o.get("result") == "reconciled_and_assigned"]
        assert len(reconciled) == 2, "Both pending essays should be reconciled"
        
        # Check batch is ready
        batch_ready = any(o.get("result") == "batch_ready" for o in batch_tracker.outcomes)
        assert batch_ready, "Batch should be ready after reconciliation"
        
        logger.info("\n✅ SUCCESS: Pending content pattern fixes the race condition!")
    
    @pytest.mark.asyncio
    async def test_mixed_timing_with_pending_pattern(
        self, batch_tracker: EnhancedBatchTracker
    ):
        """Test: Mix of essays before and after batch registration."""
        logger.info("\n" + "="*80)
        logger.info("TEST: MIXED TIMING - Some Pending, Some Direct")
        logger.info("="*80)
        
        batch_id = str(uuid4())
        correlation_id = uuid4()
        
        # Step 1: First essay arrives early (becomes pending)
        essay_event_1 = self.create_essay_event(batch_id, 0)
        result1 = await batch_tracker.process_essay_content(essay_event_1)
        assert result1 == "pending"
        
        # Step 2: Batch registration (reconciles pending)
        batch_event = self.create_batch_event(batch_id, expected_count=3)
        await batch_tracker.register_batch(batch_event, correlation_id)
        
        # Step 3: More essays arrive after registration
        essay_event_2 = self.create_essay_event(batch_id, 1)
        result2 = await batch_tracker.process_essay_content(essay_event_2)
        assert result2 == "assigned"
        
        essay_event_3 = self.create_essay_event(batch_id, 2)
        result3 = await batch_tracker.process_essay_content(essay_event_3)
        assert result3 == "assigned"
        
        # Verify outcomes
        logger.info(f"\nOutcomes: {json.dumps(batch_tracker.outcomes, indent=2)}")
        
        # One reconciled, two directly assigned
        reconciled = [o for o in batch_tracker.outcomes if o.get("was_pending") == True]
        direct_assigned = [o for o in batch_tracker.outcomes if o.get("result") == "assigned" and not o.get("was_pending")]
        
        assert len(reconciled) == 1, "One essay should be reconciled from pending"
        assert len(direct_assigned) == 2, "Two essays should be directly assigned"
        
        logger.info("\n✅ SUCCESS: Mixed timing handled correctly!")
    
    @pytest.mark.asyncio
    async def test_excess_content_still_handled(
        self, batch_tracker: EnhancedBatchTracker
    ):
        """Test: True excess content (more essays than slots) is still detected."""
        logger.info("\n" + "="*80)
        logger.info("TEST: EXCESS CONTENT - More Essays Than Slots")
        logger.info("="*80)
        
        batch_id = str(uuid4())
        correlation_id = uuid4()
        
        # Register batch with 2 slots
        batch_event = self.create_batch_event(batch_id, expected_count=2)
        await batch_tracker.register_batch(batch_event, correlation_id)
        
        # Send 3 essays (one more than slots)
        for i in range(3):
            essay_event = self.create_essay_event(batch_id, i)
            await batch_tracker.process_essay_content(essay_event)
        
        # Verify outcomes
        logger.info(f"\nOutcomes: {json.dumps(batch_tracker.outcomes, indent=2)}")
        
        assigned = [o for o in batch_tracker.outcomes if o.get("result") == "assigned"]
        excess = [o for o in batch_tracker.outcomes if o.get("result") == "excess_content"]
        
        assert len(assigned) == 2, "Two essays should be assigned"
        assert len(excess) == 1, "One essay should be excess content"
        
        logger.info("\n✅ SUCCESS: True excess content still detected correctly!")
    
    @pytest.mark.asyncio
    async def test_pending_content_cleanup(
        self, pending_manager: PendingContentManager, redis_client: Redis
    ):
        """Test: Pending content is properly cleaned up after reconciliation."""
        logger.info("\n" + "="*80)
        logger.info("TEST: PENDING CONTENT CLEANUP")
        logger.info("="*80)
        
        batch_id = str(uuid4())
        
        # Store pending content
        await pending_manager.store_pending_content(
            batch_id, 
            "storage_1",
            {"original_file_name": "test.txt"}
        )
        
        # Verify it exists
        pending = await pending_manager.get_pending_content(batch_id)
        assert len(pending) == 1
        
        # Remove it
        removed = await pending_manager.remove_pending_content(batch_id, "storage_1")
        assert removed == True
        
        # Verify it's gone
        pending_after = await pending_manager.get_pending_content(batch_id)
        assert len(pending_after) == 0
        
        # Verify Redis keys are cleaned up
        pending_key = f"pending_content:{batch_id}"
        exists = await redis_client.exists(pending_key)
        assert exists == 0, "Pending content key should be deleted"
        
        logger.info("\n✅ SUCCESS: Pending content properly cleaned up!")


if __name__ == "__main__":
    import sys
    pytest.main([__file__, "-v", "-s", "--tb=short"])