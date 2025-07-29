"""
Robust synchronization utilities for distributed tests.

Replaces brittle sleep-based waits with proper state verification
and polling mechanisms with timeouts.
"""

import asyncio
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar('T')


class SyncTimeout(Exception):
    """Raised when synchronization timeout is exceeded."""
    pass


async def wait_for_condition(
    condition_func: Callable[[], Awaitable[bool]],
    timeout_seconds: float = 5.0,
    poll_interval: float = 0.01,
    description: str = "condition",
) -> None:
    """
    Wait for a condition to become true with proper timeout handling.
    
    Args:
        condition_func: Async function that returns True when condition is met
        timeout_seconds: Maximum time to wait
        poll_interval: How frequently to check the condition
        description: Description for error messages
    """
    start_time = asyncio.get_event_loop().time()
    
    while True:
        if await condition_func():
            return
            
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= timeout_seconds:
            raise SyncTimeout(f"Timeout waiting for {description} after {elapsed:.2f}s")
            
        await asyncio.sleep(poll_interval)


async def wait_for_value(
    value_func: Callable[[], Awaitable[T]], 
    expected_value: T,
    timeout_seconds: float = 5.0,
    poll_interval: float = 0.01,
    description: str = "value",
) -> T:
    """
    Wait for a function to return a specific value.
    
    Returns the actual value when condition is met.
    """
    async def condition() -> bool:
        actual = await value_func()
        return actual == expected_value
    
    await wait_for_condition(condition, timeout_seconds, poll_interval, description)
    return expected_value


async def wait_for_redis_state(
    redis_client: Any,
    key: str,
    expected_state: str | int | None = None,
    timeout_seconds: float = 5.0,
    description: str = "Redis state",
) -> Any:
    """
    Wait for specific Redis key state.
    
    Args:
        redis_client: Redis client instance
        key: Redis key to check
        expected_state: Expected value (None means key should exist)
        timeout_seconds: Maximum wait time
        description: Description for errors
    """
    async def check_state() -> bool:
        if expected_state is None:
            # Just check if key exists
            return await redis_client.exists(key) > 0
        else:
            # Check for specific value
            actual = await redis_client.get(key)
            return actual == expected_state
    
    await wait_for_condition(check_state, timeout_seconds, 0.01, description)


async def wait_for_batch_ready(
    repository: Any,
    batch_id: str, 
    expected_count: int,
    timeout_seconds: float = 10.0,
) -> None:
    """
    Wait for batch to have the expected number of ready essays.
    
    This replaces brittle sleep waits for "batch completion processing".
    """
    async def batch_is_ready() -> bool:
        from common_core.status_enums import EssayStatus
        
        batch_status = await repository.get_batch_status_summary(batch_id)
        ready_count = batch_status.get(EssayStatus.READY_FOR_PROCESSING, 0)
        return ready_count == expected_count
    
    await wait_for_condition(
        batch_is_ready, 
        timeout_seconds, 
        0.05,  # Check every 50ms for batch state
        f"batch {batch_id} to have {expected_count} ready essays"
    )


async def wait_for_event_publication(
    event_publisher: Any,
    event_type: str,
    expected_count: int = 1,
    timeout_seconds: float = 5.0,
) -> None:
    """
    Wait for specific events to be published.
    
    Replaces timing-based waits for event processing.
    """
    async def events_published() -> bool:
        matching_events = [
            event for event in event_publisher.published_events 
            if event[0] == event_type
        ]
        return len(matching_events) >= expected_count
    
    await wait_for_condition(
        events_published,
        timeout_seconds,
        0.01,
        f"{expected_count} {event_type} events to be published"
    )