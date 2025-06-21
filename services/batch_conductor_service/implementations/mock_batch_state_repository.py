"""
Mock implementation of BatchStateRepositoryProtocol for development/testing.

Simulates Redis atomic operations and TTL behavior without Redis infrastructure.
Follows the same pattern as BOS MockBatchRepositoryImpl.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from services.batch_conductor_service.protocols import BatchStateRepositoryProtocol


class MockBatchStateRepositoryImpl(BatchStateRepositoryProtocol):
    """
    In-memory mock implementation with atomic operation simulation.

    Simulates Redis behavior including:
    - TTL expiration
    - Atomic operations with locks
    - Idempotency handling
    - Cache invalidation patterns
    """

    def __init__(self):
        """Initialize in-memory storage with TTL tracking."""
        self.essay_states: dict[str, dict[str, Any]] = {}
        self.batch_summaries: dict[str, dict[str, Any]] = {}
        self.ttl_expiry: dict[str, datetime] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, key: str) -> asyncio.Lock:
        """Get or create lock for atomic operations (simulates Redis WATCH)."""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _is_expired(self, key: str) -> bool:
        """Check if key has expired based on TTL."""
        if key not in self.ttl_expiry:
            return False
        return datetime.utcnow() > self.ttl_expiry[key]

    async def record_essay_step_completion(
        self, batch_id: str, essay_id: str, step_name: str, metadata: dict | None = None
    ) -> bool:
        """Simulate atomic step completion with lock-based atomicity."""
        essay_key = f"bcs:essay_state:{batch_id}:{essay_id}"

        async with self._get_lock(essay_key):
            # Simulate Redis atomic behavior - clean up expired data
            if self._is_expired(essay_key):
                self.essay_states.pop(essay_key, None)

            essay_state = self.essay_states.get(essay_key, {
                "completed_steps": set[str](),
                "step_metadata": {},
                "created_at": datetime.utcnow().isoformat(),
                "last_updated": datetime.utcnow().isoformat(),
            })

            # Idempotency check
            if step_name in essay_state["completed_steps"]:
                return True

            # Update state
            essay_state["completed_steps"].add(step_name)
            essay_state["step_metadata"][step_name] = metadata or {}
            essay_state["last_updated"] = datetime.utcnow().isoformat()

            # Store with TTL (7 days like production)
            self.essay_states[essay_key] = essay_state
            self.ttl_expiry[essay_key] = datetime.utcnow() + timedelta(days=7)

            # Invalidate batch summary cache
            batch_summary_key = f"bcs:batch_summary:{batch_id}"
            self.batch_summaries.pop(batch_summary_key, None)
            self.ttl_expiry.pop(batch_summary_key, None)

            return True

    async def get_essay_completed_steps(self, batch_id: str, essay_id: str) -> set[str]:
        """Get all completed processing steps for an essay."""
        essay_key = f"bcs:essay_state:{batch_id}:{essay_id}"

        if self._is_expired(essay_key):
            self.essay_states.pop(essay_key, None)
            return set()

        essay_state = self.essay_states.get(essay_key)
        if not essay_state:
            return set()

        completed_steps = essay_state["completed_steps"]
        assert isinstance(completed_steps, set)
        return completed_steps.copy()

    async def get_batch_completion_summary(self, batch_id: str) -> dict[str, dict[str, int]]:
        """Get completion summary for all essays in a batch."""
        # Find all unique steps for this batch by scanning essay states
        all_steps = set()
        essay_count = 0

        for key, essay_state in self.essay_states.items():
            if key.startswith(f"bcs:essay_state:{batch_id}:") and not self._is_expired(key):
                essay_count += 1
                all_steps.update(essay_state["completed_steps"])

        # Build summary dict
        summary = {}

        for step_name in all_steps:
            completed_count = 0

            # Count essays that completed this step
            for key, essay_state in self.essay_states.items():
                if key.startswith(f"bcs:essay_state:{batch_id}:") and not self._is_expired(key):
                    if step_name in essay_state["completed_steps"]:
                        completed_count += 1

            summary[step_name] = {
                "completed": completed_count,
                "total": essay_count
            }

        return summary

    async def is_batch_step_complete(self, batch_id: str, step_name: str) -> bool:
        """Check if a processing step is complete for all essays in a batch."""
        essay_count = 0
        completed_count = 0

        for key, essay_state in self.essay_states.items():
            if key.startswith(f"bcs:essay_state:{batch_id}:") and not self._is_expired(key):
                essay_count += 1
                if step_name in essay_state["completed_steps"]:
                    completed_count += 1

        return essay_count > 0 and completed_count == essay_count

    async def cleanup_expired_data(self) -> int:
        """Clean up expired entries (simulate Redis TTL expiration)."""
        cleaned_count = 0
        current_time = datetime.utcnow()

        # Clean essay states
        expired_keys = [
            key for key, expiry in self.ttl_expiry.items()
            if current_time > expiry
        ]

        for key in expired_keys:
            self.essay_states.pop(key, None)
            self.batch_summaries.pop(key, None)
            self.ttl_expiry.pop(key, None)
            cleaned_count += 1

        return cleaned_count
