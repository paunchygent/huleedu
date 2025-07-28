"""
Shared test utilities for testing idempotency with realistic patterns.
"""

import asyncio
import json
from typing import Any, Callable, Optional, Tuple
from unittest.mock import AsyncMock

from aiokafka import ConsumerRecord


class AsyncConfirmationTestHelper:
    """Helper for testing async confirmation patterns in idempotency."""
    
    def __init__(self):
        self.processing_started = asyncio.Event()
        self.processing_complete = asyncio.Event()
        self.confirmation_allowed = asyncio.Event()
        self.confirmation_complete = asyncio.Event()
        self.processing_error: Optional[Exception] = None
        self.processing_result: Any = None
        self.confirmed = False
        
    async def process_with_controlled_confirmation(
        self,
        process_func: Callable,
        msg: ConsumerRecord,
        confirm_idempotency: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Process a message with controlled confirmation timing.
        
        This simulates the real-world pattern where:
        1. Processing starts
        2. Business logic executes (possibly with DB transaction)
        3. Confirmation happens after transaction commit
        """
        try:
            self.processing_started.set()
            
            # Execute business logic
            result = await process_func(msg, *args, **kwargs)
            # If process_func returns None, return True to indicate success
            self.processing_result = result if result is not None else True
            self.processing_complete.set()
            
            # Wait for test to allow confirmation
            await self.confirmation_allowed.wait()
            
            # Simulate potential delay or failure before confirmation
            await confirm_idempotency()
            self.confirmed = True
            self.confirmation_complete.set()
            
            return self.processing_result
            
        except Exception as e:
            self.processing_error = e
            self.processing_complete.set()
            raise
    
    async def wait_for_processing_started(self, timeout: float = 1.0):
        """Wait for processing to start."""
        await asyncio.wait_for(self.processing_started.wait(), timeout)
    
    async def wait_for_processing_complete(self, timeout: float = 1.0):
        """Wait for processing to complete (but before confirmation)."""
        await asyncio.wait_for(self.processing_complete.wait(), timeout)
    
    def allow_confirmation(self):
        """Allow the confirmation to proceed."""
        self.confirmation_allowed.set()
    
    async def wait_for_confirmation(self, timeout: float = 1.0):
        """Wait for confirmation to complete."""
        await asyncio.wait_for(self.confirmation_complete.wait(), timeout)


def create_test_message(
    event_id: str = "test-123",
    event_type: str = "test.event.v1",
    data: Optional[dict] = None
) -> ConsumerRecord:
    """Create a test Kafka message."""
    event_data = {
        "event_id": event_id,
        "event_type": event_type,
        "event_timestamp": "2024-01-01T12:00:00Z",
        "source_service": "test_service",
        "correlation_id": "corr-123",
        "data": data or {"test": "data"}
    }
    
    return ConsumerRecord(
        topic="test-topic",
        partition=0,
        offset=100,
        timestamp=None,
        timestamp_type=None,
        key=None,
        value=json.dumps(event_data).encode(),
        checksum=None,
        serialized_key_size=None,
        serialized_value_size=None,
        headers=[],
    )