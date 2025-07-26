# Essay Lifecycle Service: Shared Outbox Library Migration

**Task ID:** `ARCH-013`  
**Type:** Refactoring  
**Priority:** High  
**Created:** July 25, 2025  
**Estimated Effort:** 1-2 days  

## 1. Executive Summary

Migrate Essay Lifecycle Service from its prototype outbox implementation to the shared library in `huleedu_service_libs.outbox`. This is a straightforward refactoring where the main change is properly passing the `topic` parameter that's already available in the code.

## 2. Current State Analysis

### What ELS Currently Has
1. **Event Publisher**: `publish_to_outbox` method that accepts `topic` parameter but doesn't pass it to repository
2. **Service Request Dispatcher**: Stores topic in event_data JSON as workaround: `event_data["topic"] = topic`
3. **Custom Implementations**: Local OutboxRepositoryProtocol, PostgreSQLOutboxRepository, EventRelayWorker

### Key Finding
The topic information is already available everywhere it's needed. We just need to pass it properly to the shared library's `add_event` method.

## 3. Migration Plan

### Step 1: Add OutboxProvider to DI Container

**File:** `/services/essay_lifecycle_service/worker_main.py`
```python
# Add import
from huleedu_service_libs.outbox import OutboxProvider

# Update container initialization
container = make_async_container(
    CoreInfrastructureProvider(),
    ServiceClientsProvider(),
    CommandHandlerProvider(),
    CoordinationHandlerProvider(),
    OutboxProvider(),  # ADD THIS LINE
)
```

### Step 2: Update DI Configuration

**File:** `/services/essay_lifecycle_service/di.py`

Add these methods to CoreInfrastructureProvider:
```python
@provide(scope=Scope.APP)
def provide_service_name(self, settings: Settings) -> str:
    """Provide service name for outbox configuration."""
    return settings.SERVICE_NAME

@provide(scope=Scope.APP)
def provide_outbox_settings(self, settings: Settings) -> OutboxSettings:
    """Provide custom outbox settings."""
    from huleedu_service_libs.outbox.relay import OutboxSettings
    
    return OutboxSettings(
        poll_interval_seconds=settings.OUTBOX_POLL_INTERVAL_SECONDS,
        batch_size=settings.OUTBOX_BATCH_SIZE,
        max_retries=settings.OUTBOX_MAX_RETRIES,
        error_retry_interval_seconds=settings.OUTBOX_ERROR_RETRY_INTERVAL_SECONDS,
        enable_metrics=True,
    )
```

Update imports at the top:
```python
# Add to existing imports
from huleedu_service_libs.outbox import OutboxRepositoryProtocol, EventRelayWorker
```

Remove the local provider methods:
- Remove `provide_outbox_repository`
- Remove `provide_event_relay_worker`

### Step 3: Update Event Publisher

**File:** `/services/essay_lifecycle_service/implementations/event_publisher.py`

1. Update import:
```python
# Change from:
from services.essay_lifecycle_service.protocols import OutboxRepositoryProtocol
# To:
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
```

2. Fix the `publish_to_outbox` method to pass topic to `add_event`:
```python
# Current code around line 634:
outbox_id = await self.outbox_repository.add_event(
    aggregate_id=aggregate_id,
    aggregate_type=aggregate_type,
    event_type=event_type,
    event_data=serialized_data,
    event_key=event_key,
)

# Change to:
outbox_id = await self.outbox_repository.add_event(
    aggregate_id=aggregate_id,
    aggregate_type=aggregate_type,
    event_type=event_type,
    event_data=serialized_data,
    topic=topic,  # ADD THIS LINE - topic is already a parameter of publish_to_outbox
    event_key=event_key,
)
```

### Step 4: Update Service Request Dispatcher

**File:** `/services/essay_lifecycle_service/implementations/service_request_dispatcher.py`

1. Update import:
```python
# Change from:
from services.essay_lifecycle_service.protocols import OutboxRepositoryProtocol
# To:
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
```

2. Fix spellcheck request (around line 89):
```python
# Current code:
event_data = envelope.model_dump(mode="json")
event_data["topic"] = topic  # Add topic to event data for relay worker
await self.outbox_repository.add_event(
    aggregate_id=essay_ref.essay_id,
    aggregate_type="essay",
    event_type=envelope.event_type,
    event_data=event_data,
    event_key=essay_ref.essay_id,
)

# Change to:
event_data = envelope.model_dump(mode="json")
# Remove the line: event_data["topic"] = topic
await self.outbox_repository.add_event(
    aggregate_id=essay_ref.essay_id,
    aggregate_type="essay",
    event_type=envelope.event_type,
    event_data=event_data,
    topic=topic,  # ADD THIS PARAMETER
    event_key=essay_ref.essay_id,
)
```

3. Fix CJ assessment request (around line 175) - same pattern:
```python
# Remove: event_data["topic"] = topic
# Add topic parameter to add_event call
```

### Step 5: Update Worker Main

**File:** `/services/essay_lifecycle_service/worker_main.py`

Update import:
```python
# Change from:
from services.essay_lifecycle_service.implementations.event_relay_worker import EventRelayWorker
# To:
from huleedu_service_libs.outbox import EventRelayWorker
```

### Step 6: Update Tests

For each test file that mocks OutboxRepositoryProtocol:

1. Update import:
```python
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
```

2. Update mock assertions to include topic:
```python
# Example assertion update:
mock_outbox.add_event.assert_called_with(
    aggregate_id=expected_id,
    aggregate_type="essay",
    event_type=expected_type,
    event_data=ANY,
    topic=expected_topic,  # ADD THIS
    event_key=expected_key,
)
```

### Step 7: Remove Obsolete Files

After all tests pass, delete:
1. `/services/essay_lifecycle_service/implementations/outbox_repository_impl.py`
2. `/services/essay_lifecycle_service/implementations/event_relay_worker.py`
3. Remove OutboxRepositoryProtocol and OutboxEvent from `/services/essay_lifecycle_service/protocols.py`
4. Remove EventOutbox model from `/services/essay_lifecycle_service/models_db.py`

## 4. Testing Strategy

1. **After each step**, run the specific tests for that component
2. **Before deleting files**, run the full test suite: `pdm run -p services/essay_lifecycle_service test`
3. **Key test files to verify**:
   - `test_event_publisher.py`
   - `test_service_request_dispatcher.py`
   - Any integration tests using outbox

## 5. Validation Checklist

- [ ] All imports updated to shared library
- [ ] Topic parameter added to all `add_event` calls
- [ ] Removed topic workaround from service_request_dispatcher
- [ ] All 234 tests pass
- [ ] Prometheus metrics endpoint shows outbox metrics
- [ ] Event relay worker starts and processes events
- [ ] Old implementation files deleted

## 6. Common Issues and Solutions

1. **Missing topic parameter**: Type checker will catch this - look for `TypeError: add_event() missing 1 required positional argument: 'topic'`
2. **Import errors**: Make sure to update ALL imports, including in test files
3. **Test failures**: Usually due to missing `topic` in mock assertions

## 7. Benefits After Migration

- Single source of truth for outbox implementation
- Built-in Prometheus metrics
- Session injection support for better transactional consistency
- Reduced code maintenance (~500 lines removed)
- Aligned with File Service pattern