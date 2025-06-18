"""
Batch state repository implementations for BCS.

Provides Redis-cached and PostgreSQL persistent storage options for essay processing
state management, optimized for frequent BOS polling during pipeline resolution.

Follows established patterns from ELS state_store.py and BOS postgres repository.
"""

from __future__ import annotations

# Re-export the separated implementations
from services.batch_conductor_service.implementations.postgres_batch_state_repository import (
    PostgreSQLBatchStateRepositoryImpl,
)
from services.batch_conductor_service.implementations.redis_batch_state_repository import (
    RedisCachedBatchStateRepositoryImpl,
)

__all__ = ["RedisCachedBatchStateRepositoryImpl", "PostgreSQLBatchStateRepositoryImpl"]
