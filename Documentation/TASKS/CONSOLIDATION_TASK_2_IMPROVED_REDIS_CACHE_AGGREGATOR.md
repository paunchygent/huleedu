# Consolidation Task 2: Implementing Active Cache Invalidation ✅ COMPLETED

**Status: COMPLETED** - Active cache invalidation using Redis SETs has been successfully implemented in the Result Aggregator Service.

**Implementation Evidence:**
- `services/result_aggregator_service/implementations/cache_manager_impl.py:100-106` - Redis pipeline-based cache setting with SET tracking
- `services/result_aggregator_service/implementations/cache_manager_impl.py:130-159` - Active invalidation using Redis SET operations
- `services/result_aggregator_service/implementations/event_processor_impl.py:64` - Cache invalidation triggered on BatchEssaysRegistered events
- `services/result_aggregator_service/di.py` - CacheManagerProtocol injected into EventProcessorImpl
- `services/libs/huleedu_service_libs/redis_set_operations.py` - Redis SET operations abstraction
- No KEYS or SCAN operations used (performance-optimized)

Original Objective: Research the current TTL-based cache invalidation weakness and formulate a plan to implement a highly performant, active invalidation strategy using Redis SETs for indexing user-specific cache keys.

Key Architectural Principles (Rules to Apply)
****: Focus on Service Autonomy and how RAS manages its own read-model caching.

****: Understand how consuming events is the trigger for cache invalidation.

****: Review how dependencies like the Redis client are injected and used.

Primary Files for Analysis (The Caching Implementation)
services/result_aggregator_service/implementations/cache_manager_impl.py:

Analyze the set_user_batches_json method to understand how list-based caches are currently written.

Analyze the invalidate_user_batches method and its comment explaining the current limitation.

services/result_aggregator_service/implementations/event_processor_impl.py:

Analyze the process_batch_registered method. This is the primary trigger point where invalidation should occur. Note its current dependencies.

services/result_aggregator_service/di.py: Understand how CacheManagerProtocol and EventProcessorProtocol are instantiated and what dependencies they receive.

services/libs/huleedu_service_libs/redis_client.py: Review the available methods on the RedisClient to confirm it supports SADD, SMEMBERS, and pipeline transactions.

Reference Files (Data Contracts)
common_core/src/common_core/events/batch_coordination_events.py: Examine the BatchEssaysRegistered event model to confirm that user_id is available to the consumer.

Analysis Questions to Answer
Why is a KEYS or SCAN operation in Redis not a suitable solution for invalidating the user batch list cache?

Explain step-by-step how using a Redis SET as an index solves the problem of not knowing which cache keys to invalidate when a BatchEssaysRegistered event for a specific user_id is consumed.

What changes are required in di.py for the EventProcessorImpl to be able to call the invalidate_user_batches method on the CacheManagerImpl?

Why is it important to use a Redis PIPELINE when updating both the cache data and the tracking set in set_user_batches_json?
The challenge is to implement an active invalidation strategy that is both performant and architecturally sound, avoiding expensive KEYS or SCAN operations in Redis which are unsuitable for production.

The Solution: Active Invalidation via Redis Sets
The most scalable and efficient solution is to maintain an index of cache keys for each user. We will use a Redis SET for this purpose. For each user, we will store a set whose members are the cache keys of all their batch-list queries.

When an event occurs that changes a user's set of batches (like a new batch being registered), we can use the user_id from the event to find this index set, retrieve all related cache keys, and delete them in a single, atomic operation.

Here is the detailed, step-by-step implementation plan to refactor the caching logic.

Step 1: Enhance CacheManagerImpl to Track User Cache Keys
First, we will modify set_user_batches_json to not only cache the data but also to record the cache key in a user-specific index set.

File to Modify: services/result_aggregator_service/implementations/cache_manager_impl.py

Current set_user_batches_json Method:

```Python

# services/result_aggregator_service/implementations/cache_manager_impl.py

# ... existing code

    async def set_user_batches_json(
        self, user_id: str, limit: int, offset: int, status: Optional[str], data_json: str, ttl: int
    ) -> None:
        """Cache user batches list as JSON string."""
        try:
            cache_key = self._build_user_batches_key(user_id, limit, offset, status)
            await self.redis.setex(cache_key, ttl, data_json)

            logger.debug("Cached user batches", user_id=user_id, ttl=ttl, cache_key=cache_key)
        except Exception as e:
            logger.warning(
                "Failed to cache user batches",
                user_id=user_id,
                error=str(e),
            )

# ... existing code

```

Proposed set_user_batches_json Method:
We will use a Redis PIPELINE to atomically perform both the SETEX for the data and the SADD for the index.

```Python
# services/result_aggregator_service/implementations/cache_manager_impl.py

# ... existing code

    async def set_user_batches_json(
        self, user_id: str, limit: int, offset: int, status: Optional[str], data_json: str, ttl: int
    ) -> None:
        """Cache user batches list and track the key in a user-specific index set."""
        try:
            cache_key = self._build_user_batches_key(user_id, limit, offset, status)
            user_tracking_key = f"ras:user_cache_keys:{user_id}"

            # Use a Redis pipeline for atomicity
            async with self.redis.client.pipeline() as pipe:
                # 1. Cache the actual data with a TTL
                pipe.setex(cache_key, ttl, data_json)
                # 2. Add the cache key to the user's tracking set
                pipe.sadd(user_tracking_key, cache_key)
                # 3. Set a TTL on the tracking set itself to prevent it from growing indefinitely
                pipe.expire(user_tracking_key, ttl)
                # Execute both commands
                await pipe.execute()

            logger.debug(
                "Cached user batches and tracked key",
                user_id=user_id,
                cache_key=cache_key,
                tracking_key=user_tracking_key,
            )
        except Exception as e:
            logger.warning(
                "Failed to cache user batches with tracking",
                user_id=user_id,
                error=str(e),
            )

# ... existing code

```Python

Step 2: Implement Active Invalidation in CacheManagerImpl
Next, we will replace the no-op invalidate_user_batches method with a functional implementation that uses our new index set.

File to Modify: services/result_aggregator_service/implementations/cache_manager_impl.py

Current invalidate_user_batches Method:

```Python

# services/result_aggregator_service/implementations/cache_manager_impl.py

# ... existing code

    async def invalidate_user_batches(self, user_id: str) -> None:
        """Invalidate all cached user batch lists."""
        # ... logs a warning and does nothing ...

# ... existing code

```

Proposed invalidate_user_batches Method:
This implementation will fetch all keys from the user's tracking set and delete them, including the tracking set itself.

```Python

# services/result_aggregator_service/implementations/cache_manager_impl.py

# ... existing code

    async def invalidate_user_batches(self, user_id: str) -> None:
        """Actively invalidate all cached batch lists for a specific user."""
        user_tracking_key = f"ras:user_cache_keys:{user_id}"
        try:
            # Retrieve all cache keys associated with the user
            keys_to_delete = await self.redis.client.smembers(user_tracking_key)
            if not keys_to_delete:
                logger.debug(f"No active user batch caches to invalidate for user {user_id}")
                return

            # Add the tracking key itself to the list of keys to be deleted
            keys_to_delete.add(user_tracking_key)

            # Delete all keys in a single atomic operation
            await self.redis.client.delete(*keys_to_delete)

            logger.info(f"Successfully invalidated {len(keys_to_delete)} cache entries for user {user_id}")

        except Exception as e:
            logger.warning(
                f"Failed to invalidate user batches cache for user {user_id}",
                error=str(e),
            )

# ... existing code

```

Step 3: Trigger Invalidation from the Event Processor
Finally, we must trigger this new invalidation logic when a relevant event occurs. The BatchEssaysRegistered event is the primary trigger, as it signifies the creation of a new batch that should appear in the user's list.

File to Modify: services/result_aggregator_service/implementations/event_processor_impl.py

Proposed change in process_batch_registered Method:
We will add a call to self.cache_manager.invalidate_user_batches() after successfully creating the batch record. Note: This requires injecting the CacheManagerProtocol into the EventProcessorImpl.

```Python

# services/result_aggregator_service/implementations/event_processor_impl.py

# ... imports

from ..protocols import (
    BatchRepositoryProtocol,
    EventProcessorProtocol,
    CacheManagerProtocol, # Add this import
)

class EventProcessorImpl(EventProcessorProtocol):
    def __init__(
        self,
        batch_repository: BatchRepositoryProtocol,
        cache_manager: CacheManagerProtocol, # Add cache_manager
    ):
        self.batch_repository = batch_repository
        self.cache_manager = cache_manager # Store it

    async def process_batch_registered(
        self, envelope: "EventEnvelope[BatchEssaysRegistered]", data: "BatchEssaysRegistered"
    ) -> None:
        try:
            # ... existing logic to create the batch record in the database ...
            await self.batch_repository.create_batch(
                batch_id=data.batch_id,
                user_id=data.user_id,
                # ... other fields ...
            )

            # --- NEW INVALIDATION LOGIC ---
            # After successfully creating the batch, invalidate the user's cache.
            await self.cache_manager.invalidate_user_batches(data.user_id)
            # --- END NEW LOGIC ---

            logger.info("Created initial batch record and invalidated user cache", batch_id=data.batch_id)

        except Exception as e:
            logger.error("Failed to process batch registration", batch_id=data.batch_id, error=str(e))
            raise

# ... rest of the file

```

File to Modify: services/result_aggregator_service/di.py

To support the change above, we must update the DI provider to inject the CacheManagerProtocol into the EventProcessorImpl.

```Python

# services/result_aggregator_service/di.py

# ... imports

from .protocols import (
    # ...
    CacheManagerProtocol,
    EventProcessorProtocol,
    # ...
)

class ServiceProvider(Provider):
    # ... existing provides ...

    @provide
    def provide_event_processor(
        self,
        batch_repository: BatchRepositoryProtocol,
        cache_manager: CacheManagerProtocol, # Add cache_manager
    ) -> EventProcessorProtocol:
        """Provide event processor implementation."""
        # Inject the new dependency
        return EventProcessorImpl(batch_repository, cache_manager)
    # ... rest of the file ...

```

By implementing these changes, we create a system that is both highly performant for reads and provides immediate consistency for writes, leading to a significantly better and more intuitive user experience without compromising scalability.
