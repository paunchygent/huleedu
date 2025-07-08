"""
Queue domain models for type-safe queue operations.

This module contains value objects and type definitions for queue-specific
operations, providing type safety and domain alignment for queue implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NewType

# Type-safe identifiers
QueueItemId = NewType('QueueItemId', str)
PriorityScore = NewType('PriorityScore', float)


@dataclass(frozen=True)
class QueueItem:
    """
    Value object representing a queue item with its priority.
    
    Provides type-safe representation of queue items retrieved from Redis
    sorted sets with scores.
    """
    item_id: QueueItemId
    priority: PriorityScore
    
    @classmethod
    def from_redis_tuple(cls, redis_tuple: tuple[str, float]) -> QueueItem:
        """
        Create QueueItem from Redis zrange result with scores.
        
        Args:
            redis_tuple: Tuple of (item_id, score) from Redis zrange withscores=True
            
        Returns:
            QueueItem with type-safe identifiers
        """
        item_id, score = redis_tuple
        return cls(
            item_id=QueueItemId(item_id),
            priority=PriorityScore(score)
        )