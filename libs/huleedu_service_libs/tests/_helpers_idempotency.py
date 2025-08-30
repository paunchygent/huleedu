from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Dict, List, Tuple
from uuid import uuid4

from aiokafka import ConsumerRecord


class HandlerCallTracker:
    """Track handler calls for test verification without mocking business logic."""

    def __init__(self) -> None:
        self.call_count = 0
        self.last_call_args: tuple = ()
        self.last_call_kwargs: dict = {}

    def reset(self) -> None:
        self.call_count = 0
        self.last_call_args = ()
        self.last_call_kwargs = {}


async def tracked_handler(msg: ConsumerRecord, tracker: HandlerCallTracker, *args, **kwargs) -> str:
    """Real handler that tracks calls for test verification."""
    tracker.call_count += 1
    tracker.last_call_args = (msg,) + args
    tracker.last_call_kwargs = kwargs
    return f"tracked_result_{msg.offset}"


class MockRedisClient:
    """Mock Redis client for idempotency tests with call capture and toggled failures."""

    def __init__(self) -> None:
        self.keys: Dict[str, str] = {}
        self.set_calls: List[Tuple[str, str, int | None]] = []
        self.setex_calls: List[Tuple[str, int, str]] = []
        self.delete_calls: List[str] = []
        self.get_calls: List[str] = []

        self.should_fail_get = False
        self.should_fail_set = False
        self.should_fail_setex = False
        self.should_fail_delete = False

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        self.set_calls.append((key, value, ttl_seconds))

        if self.should_fail_set:
            raise RuntimeError("Mock Redis SET failure")

        if key in self.keys:
            return False

        self.keys[key] = value
        return True

    async def delete_key(self, key: str) -> int:
        self.delete_calls.append(key)

        if self.should_fail_delete:
            raise RuntimeError("Mock Redis DELETE failure")

        if key in self.keys:
            del self.keys[key]
            return 1
        return 0

    async def get(self, key: str) -> str | None:
        self.get_calls.append(key)

        if self.should_fail_get:
            raise RuntimeError("Mock Redis GET failure")

        return self.keys.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        if self.should_fail_setex:
            raise RuntimeError("Mock Redis SETEX failure")

        self.keys[key] = value
        self.setex_calls.append((key, ttl_seconds, value))
        return True

    async def ping(self) -> bool:  # For protocol compatibility
        return True


def create_mock_kafka_message(
    event_data: dict,
    *,
    headers: dict[str, str] | None = None,
    topic: str = "test-topic",
    partition: int = 0,
    offset: int = 123,
    key: str = "test-key",
) -> ConsumerRecord:
    """Create a mock Kafka ConsumerRecord for testing.

    Ensures minimal envelope fields are present. Headers (if provided) are encoded to bytes.
    """
    # Ensure required fields exist
    if "event_type" not in event_data:
        event_data["event_type"] = "test.event.v1"
    if "event_id" not in event_data:
        event_data["event_id"] = str(uuid4())
    if "source_service" not in event_data:
        event_data["source_service"] = "test-service"
    if "event_timestamp" not in event_data:
        event_data["event_timestamp"] = datetime.now(UTC).isoformat()

    message_json = json.dumps(event_data)

    header_list: List[Tuple[str, bytes]] = []
    if headers:
        header_list = [(k, v.encode("utf-8")) for k, v in headers.items()]

    return ConsumerRecord(
        topic=topic,
        partition=partition,
        offset=offset,
        timestamp=int(datetime.now(UTC).timestamp() * 1000),
        timestamp_type=1,
        key=key.encode("utf-8"),
        value=message_json.encode("utf-8"),
        headers=header_list,
        checksum=None,
        serialized_key_size=len(key.encode("utf-8")),
        serialized_value_size=len(message_json),
    )
