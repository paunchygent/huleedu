# Comprehensive Refactor Plan: Splitting Large Service Files

## Executive Summary

This plan details the complete refactor strategy to split the two largest service files (`redis_batch_coordinator.py` at 1,082 lines and `event_publisher.py` at 1,035 lines) into sub-400 LoC modules while maintaining architectural integrity and zero breaking changes.

## Phase 1: RedisBatchCoordinator Refactor (1,082 → 5 Modules)

### Module Breakdown

#### **Module 1: `redis_scripts.py`** (~150 LoC)

**Purpose:** Centralize all Lua scripts and Redis key naming utilities

```python
# Location: services/essay_lifecycle_service/implementations/redis_scripts.py
- ATOMIC_ASSIGN_SCRIPT constant
- ATOMIC_RETURN_SCRIPT constant  
- Redis key naming functions (_get_available_slots_key, _get_assignments_key, etc.)
- Script loading utilities
```

#### **Module 2: `batch_slot_manager.py`** (~280 LoC)

**Purpose:** Handle atomic slot assignment and return operations

```python
# Location: services/essay_lifecycle_service/implementations/batch_slot_manager.py
- assign_slot_atomic() method
- return_slot() method  
- Slot availability queries
- Content-to-slot mapping operations
```

#### **Module 3: `batch_state_tracker.py`** (~320 LoC)

**Purpose:** Manage batch metadata and state queries

```python
# Location: services/essay_lifecycle_service/implementations/batch_state_tracker.py
- get_batch_status() method
- get_batch_metadata() method
- list_active_batch_ids() method
- Batch existence and completion checks
```

#### **Module 4: `batch_timeout_manager.py`** (~280 LoC)

**Purpose:** Handle batch lifecycle and cleanup

```python
# Location: services/essay_lifecycle_service/implementations/batch_timeout_manager.py
- handle_batch_timeout() method
- cleanup_batch() method
- Timeout configuration and TTL management
- Batch expiration handling
```

#### **Module 5: `batch_coordinator.py`** (~350 LoC)

**Purpose:** Main coordinator facade implementing protocols

```python
# Location: services/essay_lifecycle_service/implementations/batch_coordinator.py
- Implements BatchEssayTracker protocol
- Coordinates between specialized modules
- Maintains backward compatibility
- Dependency injection integration
```

## Phase 2: EventPublisher Refactor (1,035 → 6 Modules)

### Module Breakdown

#### **Module 1: `event_types.py`** (~120 LoC)

**Purpose:** Event schemas and topic mappings

```python
# Location: services/essay_lifecycle_service/implementations/event_types.py
- Event type constants
- Topic mapping utilities
- Event validation schemas
- Serialization helpers
```

#### **Module 2: `redis_event_publisher.py`** (~280 LoC)

**Purpose:** Redis-specific event publishing

```python
# Location: services/essay_lifecycle_service/implementations/redis_event_publisher.py
- publish_status_update() for Redis
- Real-time UI notification events
- Redis key management for events
- Status broadcasting utilities
```

#### **Module 3: `kafka_event_publisher.py`** (~320 LoC)

**Purpose:** Kafka event publishing logic

```python
# Location: services/essay_lifecycle_service/implementations/kafka_event_publisher.py
- Direct Kafka publishing
- Topic routing and key generation
- Error handling and retry logic
- Kafka-specific serialization
```

#### **Module 4: `outbox_publisher.py`** (~280 LoC)

**Purpose:** Transactional outbox pattern

```python
# Location: services/essay_lifecycle_service/implementations/outbox_publisher.py
- _publish_to_outbox() method
- Outbox event storage
- Relay worker notification
- Transactional event handling
```

#### **Module 5: `batch_event_publisher.py`** (~300 LoC)

**Purpose:** Batch-specific event coordination

```python
# Location: services/essay_lifecycle_service/implementations/batch_event_publisher.py
- publish_batch_phase_progress() method
- publish_batch_phase_concluded() method
- publish_batch_essays_ready() method
- Batch completion event coordination
```

#### **Module 6: `default_event_publisher.py`** (~320 LoC)

**Purpose:** Main publisher facade implementing protocols

```python
# Location: services/essay_lifecycle_service/implementations/default_event_publisher.py
- Implements EventPublisher protocol
- Coordinates between specialized publishers
- Event routing and delegation
- Protocol contract maintenance
```

## Phase 3: Migration Strategy

### Step 1: Create New Modules (Week 1)

- Create all new module files with extracted functionality
- Maintain original files for backward compatibility
- No breaking changes to existing interfaces

### Step 2: Update DI Containers (Week 2)

```python
# Update DI providers in affected files:
# services/essay_lifecycle_service/di.py
# services/llm_provider_service/di.py  
# services/batch_orchestrator_service/di.py
# services/spellchecker_service/di.py
# services/cj_assessment_service/di.py
# services/file_service/di.py

# Example change:
from services.essay_lifecycle_service.implementations.batch_coordinator import BatchCoordinator
# instead of:
# from services.essay_lifecycle_service.implementations.redis_batch_coordinator import RedisBatchCoordinator
```

### Step 3: Update Test Infrastructure (Week 3)

- Update all test fixtures and mocks
- Update test import statements
- Run comprehensive test suite
- Validate integration tests

### Step 4: Protocol Verification (Week 4)

- Ensure all protocol contracts remain unchanged
- Verify backward compatibility
- Update any direct class references to protocol types
- Final validation testing

### Step 5: Cleanup (Week 5)

- Remove original large files
- Update documentation
- Final codebase verification
- Performance testing

## Impact Analysis Summary

### Files Directly Affected

- **8 DI container files** requiring import updates
- **12+ test files** requiring fixture/mock updates
- **5 protocol interfaces** requiring verification
- **Multiple service integration points**

### Risk Mitigation

- **Zero breaking changes** during migration
- **Maintained protocol contracts** throughout
- **Comprehensive test coverage** at each phase
- **Rollback strategy** for each phase

## Implementation Checklist

### Pre-Implementation

- [ ] Approve module boundaries and naming
- [ ] Create migration branch
- [ ] Set up comprehensive test environment

### RedisBatchCoordinator

- [ ] Create `redis_scripts.py`
- [ ] Create `batch_slot_manager.py`
- [ ] Create `batch_state_tracker.py`
- [ ] Create `batch_timeout_manager.py`
- [ ] Create `batch_coordinator.py`
- [ ] Update DI containers
- [ ] Update tests
- [ ] Validate functionality

### EventPublisher

- [ ] Create `event_types.py`
- [ ] Create `redis_event_publisher.py`
- [ ] Create `kafka_event_publisher.py`
- [ ] Create `outbox_publisher.py`
- [ ] Create `batch_event_publisher.py`
- [ ] Create `default_event_publisher.py`
- [ ] Update DI containers
- [ ] Update tests
- [ ] Validate functionality

### Final Validation

- [ ] All tests pass
- [ ] Integration tests pass
- [ ] Performance benchmarks maintained
- [ ] Documentation updated
- [ ] Original files removed

## Approval Required

Please review this comprehensive plan and provide approval for:

1. **Module boundaries and naming conventions**
2. **Phased implementation timeline**
3. **Risk tolerance for each phase**
4. **Rollback strategy for each phase**
