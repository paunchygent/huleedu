"""
Redis Test Manager for E2E Idempotency Testing

Provides comprehensive Redis mocking capabilities for cross-service idempotency validation.
Supports multiple services connecting to the same mock Redis instance to test
idempotency behavior across service boundaries.

Key Features:
- Cross-service Redis key tracking
- Redis failure simulation
- Connection state management
- Idempotency key lifecycle monitoring
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Tuple

from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("test.redis_manager")


class RedisKeyTracker:
    """Tracks Redis keys across multiple services for E2E validation."""

    def __init__(self) -> None:
        self.keys: Dict[str, str] = {}
        self.set_calls: List[Tuple[str, str, str, int]] = []  # (service, key, value, ttl)
        self.delete_calls: List[Tuple[str, str]] = []  # (service, key)
        self.get_calls: List[Tuple[str, str]] = []  # (service, key)
        self.service_connections: Set[str] = set()

    def add_service_connection(self, service_name: str) -> None:
        """Track that a service has connected to Redis."""
        self.service_connections.add(service_name)
        logger.info(f"Service {service_name} connected to Redis mock")

    def remove_service_connection(self, service_name: str) -> None:
        """Track that a service has disconnected from Redis."""
        self.service_connections.discard(service_name)
        logger.info(f"Service {service_name} disconnected from Redis mock")

    def get_keys_by_service(self, service_name: str) -> List[str]:
        """Get all keys accessed by a specific service."""
        keys = []
        # Extract keys from set_calls (service, key, value, ttl)
        keys.extend([key for service, key, _, _ in self.set_calls if service == service_name])
        # Extract keys from delete_calls (service, key)
        keys.extend([key for service, key in self.delete_calls if service == service_name])
        # Extract keys from get_calls (service, key)
        keys.extend([key for service, key in self.get_calls if service == service_name])
        return keys

    def get_cross_service_keys(self) -> Dict[str, List[str]]:
        """Get keys that were accessed by multiple services."""
        key_services: Dict[str, List[str]] = {}

        # Process set_calls (service, key, value, ttl)
        for service, key, _, _ in self.set_calls:
            if key not in key_services:
                key_services[key] = []
            if service not in key_services[key]:
                key_services[key].append(service)

        # Process delete_calls (service, key)
        for service, key in self.delete_calls:
            if key not in key_services:
                key_services[key] = []
            if service not in key_services[key]:
                key_services[key].append(service)

        # Process get_calls (service, key)
        for service, key in self.get_calls:
            if key not in key_services:
                key_services[key] = []
            if service not in key_services[key]:
                key_services[key].append(service)

        return {key: services for key, services in key_services.items() if len(services) > 1}


class MockRedisClient:
    """Mock Redis client for individual service connections."""

    def __init__(
        self, service_name: str, key_tracker: RedisKeyTracker, fail_mode: Optional[str] = None
    ) -> None:
        self.service_name = service_name
        self.key_tracker = key_tracker
        self.fail_mode = fail_mode  # "set", "delete", "get", "all", None
        self.is_connected = True

        # Track this service connection
        self.key_tracker.add_service_connection(service_name)

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """Mock SETNX operation with failure simulation."""
        # Always track the call
        self.key_tracker.set_calls.append((self.service_name, key, value, ttl_seconds or 0))

        # Simulate connection failures
        if not self.is_connected or self.fail_mode in ("set", "all"):
            raise Exception(f"Redis connection failed for {self.service_name}")

        # Check if key already exists
        if key in self.key_tracker.keys:
            logger.info(f"[{self.service_name}] Key {key} already exists (duplicate)")
            return False  # Key already exists (duplicate)

        # Set the key
        self.key_tracker.keys[key] = value
        logger.info(f"[{self.service_name}] Set key {key} with TTL {ttl_seconds or 'none'}")
        return True  # Key set successfully (first time)

    async def delete_key(self, key: str) -> int:
        """Mock DELETE operation with failure simulation."""
        # Always track the call
        self.key_tracker.delete_calls.append((self.service_name, key))

        # Simulate connection failures
        if not self.is_connected or self.fail_mode in ("delete", "all"):
            raise Exception(f"Redis delete failed for {self.service_name}")

        # Delete the key if it exists
        if key in self.key_tracker.keys:
            del self.key_tracker.keys[key]
            logger.info(f"[{self.service_name}] Deleted key {key}")
            return 1
        else:
            logger.info(f"[{self.service_name}] Key {key} not found for deletion")
            return 0

    async def get_key(self, key: str) -> Optional[str]:
        """Mock GET operation with failure simulation."""
        # Always track the call
        self.key_tracker.get_calls.append((self.service_name, key))

        # Simulate connection failures
        if not self.is_connected or self.fail_mode in ("get", "all"):
            raise Exception(f"Redis get failed for {self.service_name}")

        value = self.key_tracker.keys.get(key)
        logger.info(f"[{self.service_name}] Get key {key} = {value}")
        return value

    def disconnect(self) -> None:
        """Simulate Redis disconnection."""
        self.is_connected = False
        self.key_tracker.remove_service_connection(self.service_name)
        logger.info(f"[{self.service_name}] Disconnected from Redis")

    def reconnect(self) -> None:
        """Simulate Redis reconnection."""
        self.is_connected = True
        self.key_tracker.add_service_connection(self.service_name)
        logger.info(f"[{self.service_name}] Reconnected to Redis")


class RedisTestManager:
    """
    Manages Redis connections for E2E idempotency testing.

    Provides a single Redis mock instance that multiple services can connect to,
    enabling cross-service idempotency validation.
    """

    def __init__(self) -> None:
        self.key_tracker = RedisKeyTracker()
        self.service_clients: Dict[str, MockRedisClient] = {}
        self._cleanup_tasks: List[asyncio.Task] = []

    def create_service_client(
        self, service_name: str, fail_mode: Optional[str] = None
    ) -> MockRedisClient:
        """
        Create a Redis client for a specific service.

        Args:
            service_name: Name of the service (e.g., "batch_orchestrator_service")
            fail_mode: Optional failure mode ("set", "delete", "get", "all", None)

        Returns:
            MockRedisClient configured for the service
        """
        client = MockRedisClient(service_name, self.key_tracker, fail_mode)
        self.service_clients[service_name] = client
        return client

    def get_service_client(self, service_name: str) -> Optional[MockRedisClient]:
        """Get existing Redis client for a service."""
        return self.service_clients.get(service_name)

    def simulate_redis_outage(self) -> None:
        """Simulate Redis outage for all services."""
        logger.warning("Simulating Redis outage for all services")
        for client in self.service_clients.values():
            client.disconnect()

    def restore_redis_connectivity(self) -> None:
        """Restore Redis connectivity for all services."""
        logger.info("Restoring Redis connectivity for all services")
        for client in self.service_clients.values():
            client.reconnect()

    def get_idempotency_stats(self) -> Dict[str, Any]:
        """Get comprehensive idempotency statistics."""
        return {
            "total_keys": len(self.key_tracker.keys),
            "active_keys": list(self.key_tracker.keys.keys()),
            "total_set_calls": len(self.key_tracker.set_calls),
            "total_delete_calls": len(self.key_tracker.delete_calls),
            "total_get_calls": len(self.key_tracker.get_calls),
            "connected_services": list(self.key_tracker.service_connections),
            "cross_service_keys": self.key_tracker.get_cross_service_keys(),
            "set_calls_by_service": {
                service: len([call for call in self.key_tracker.set_calls if call[0] == service])
                for service in self.key_tracker.service_connections
            },
            "delete_calls_by_service": {
                service: len([call for call in self.key_tracker.delete_calls if call[0] == service])
                for service in self.key_tracker.service_connections
            },
        }

    def clear_all_keys(self) -> None:
        """Clear all Redis keys and call history."""
        self.key_tracker.keys.clear()
        self.key_tracker.set_calls.clear()
        self.key_tracker.delete_calls.clear()
        self.key_tracker.get_calls.clear()
        logger.info("Cleared all Redis keys and call history")

    @asynccontextmanager
    async def redis_context(self, services: List[str]) -> AsyncIterator[Dict[str, MockRedisClient]]:
        """
        Context manager for Redis clients across multiple services.

        Args:
            services: List of service names to create clients for

        Yields:
            Dictionary mapping service names to MockRedisClient instances
        """
        clients = {}

        try:
            # Create clients for all services
            for service_name in services:
                clients[service_name] = self.create_service_client(service_name)

            logger.info(f"Created Redis clients for services: {services}")
            yield clients

        finally:
            # Cleanup clients
            for service_name in services:
                if service_name in self.service_clients:
                    self.service_clients[service_name].disconnect()
                    del self.service_clients[service_name]

            logger.info(f"Cleaned up Redis clients for services: {services}")


# Convenience functions for test usage
async def create_cross_service_redis_test(services: List[str]) -> RedisTestManager:
    """Create a Redis test manager for cross-service testing."""
    manager = RedisTestManager()
    logger.info(f"Created cross-service Redis test manager for: {services}")
    return manager


def create_deterministic_event_test_data() -> List[Dict[str, Any]]:
    """Create test events with identical data payloads for deterministic ID testing."""
    base_data = {
        "batch_id": "test-batch-123",
        "essays": [
            {"essay_id": "essay-1", "text_storage_id": "storage-1"},
            {"essay_id": "essay-2", "text_storage_id": "storage-2"},
        ],
        "metadata": {
            "entity": {"entity_type": "batch", "entity_id": "test-batch-123"},
            "timestamp": "2024-01-15T10:00:00Z",
        },
    }

    # Create multiple events with same data but different envelope metadata
    events = []
    for i in range(3):
        event = {
            "event_id": str(uuid.uuid4()),  # Different envelope metadata
            "event_type": "huleedu.test.event.v1",
            "event_timestamp": f"2024-01-15T10:0{i}:00Z",  # Different timestamps
            "source_service": "test_service",
            "correlation_id": str(uuid.uuid4()),  # Different correlation IDs
            "data": base_data,  # SAME DATA - should produce same deterministic ID
        }
        events.append(event)

    return events
