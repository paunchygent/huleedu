# Event Registry

ProcessingEvent enum and topic_name() function form the central registry for all Kafka events.

## ProcessingEvent Enum

Location: `common_core/event_enums.py`

Single source of truth for all event types. 100+ event constants organized by functional area.

```python
from common_core.event_enums import ProcessingEvent

class ProcessingEvent(str, Enum):
    # Batch coordination
    BATCH_ESSAYS_REGISTERED = "batch.essays.registered"
    BATCH_ESSAYS_READY = "batch.essays.ready"

    # Essay lifecycle
    ESSAY_CONTENT_PROVISIONED = "essay.content.provisioned"

    # Processing services
    ESSAY_SPELLCHECK_COMPLETED = "essay.spellcheck.completed"
    CJ_ASSESSMENT_COMPLETED = "cj_assessment.completed"

    # Identity
    IDENTITY_USER_REGISTERED = "identity.user.registered"

    # ... 100+ total events
```

## topic_name() Function

Converts ProcessingEvent enum to Kafka topic string. Enforces explicit topic mapping.

```python
from common_core.event_enums import ProcessingEvent, topic_name

topic = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)
# Returns: "huleedu.cj_assessment.completed.v1"

# ValueError if event not in _TOPIC_MAPPING
topic = topic_name(ProcessingEvent.NEW_EVENT)  # ❌ Raises ValueError
```

### _TOPIC_MAPPING Dictionary

Private mapping from ProcessingEvent to Kafka topic strings:

```python
_TOPIC_MAPPING = {
    ProcessingEvent.CJ_ASSESSMENT_COMPLETED: "huleedu.cj_assessment.completed.v1",
    ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED: "huleedu.essay.spellcheck.completed.v1",
    ProcessingEvent.BATCH_ESSAYS_REGISTERED: "huleedu.batch.essays.registered.v1",
    # ... all mapped events
}
```

Events MUST be in this mapping before use. Unmapped events raise descriptive ValueError with all mapped events listed.

## Event Categories

### Batch Coordination Events

```python
ProcessingEvent.BATCH_ESSAYS_REGISTERED = "batch.essays.registered"
ProcessingEvent.BATCH_ESSAYS_READY = "batch.essays.ready"
ProcessingEvent.BATCH_PIPELINE_COMPLETED = "batch.pipeline.completed"
ProcessingEvent.BATCH_PHASE_SKIPPED = "batch.phase.skipped"
```

**Producers**: Batch Orchestrator Service, Essay Lifecycle Service
**Consumers**: Essay Lifecycle Service, Batch Conductor Service

### Essay Lifecycle Events

```python
ProcessingEvent.ESSAY_SLOT_ASSIGNED = "essay.slot.assigned"
ProcessingEvent.ESSAY_CONTENT_PROVISIONED = "essay.content.provisioned"
ProcessingEvent.EXCESS_CONTENT_PROVISIONED = "excess.content.provisioned"
ProcessingEvent.ESSAY_VALIDATION_FAILED = "essay.validation.failed"
```

**Producers**: File Service, Essay Lifecycle Service
**Consumers**: Batch Orchestrator Service, Essay Lifecycle Service

### Processing Service Commands

```python
ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND = "batch.spellcheck.initiate.command"
ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND = "batch.cj_assessment.initiate.command"
ProcessingEvent.BATCH_AI_FEEDBACK_INITIATE_COMMAND = "batch.ai_feedback.initiate.command"
ProcessingEvent.BATCH_NLP_INITIATE_COMMAND = "batch.nlp.initiate.command"
ProcessingEvent.BATCH_NLP_INITIATE_COMMAND_V2 = "batch.nlp.initiate.command.v2"
```

**Producer**: Batch Orchestrator Service
**Consumers**: Essay Lifecycle Service (forwards to processing services)

### Processing Service Results

```python
ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED = "essay.spellcheck.completed"
ProcessingEvent.SPELLCHECK_PHASE_COMPLETED = "spellcheck.phase.completed"  # Thin
ProcessingEvent.SPELLCHECK_RESULTS = "spellcheck.results"  # Rich

ProcessingEvent.CJ_ASSESSMENT_COMPLETED = "cj_assessment.completed"  # Thin
ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED = "assessment.result.published"  # Rich

ProcessingEvent.ESSAY_NLP_COMPLETED = "essay.nlp.completed"
ProcessingEvent.BATCH_NLP_ANALYSIS_COMPLETED = "batch.nlp.analysis.completed"
```

**Producers**: Spellcheck, CJ Assessment, NLP services
**Consumers**: Essay Lifecycle Service, Result Aggregator Service

### Student Matching Events

```python
ProcessingEvent.BATCH_STUDENT_MATCHING_INITIATE_COMMAND = "batch.student.matching.initiate.command"
ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED = "batch.student.matching.requested"
ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED = "batch.author.matches.suggested"
ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED = "student.associations.confirmed"
ProcessingEvent.VALIDATION_TIMEOUT_PROCESSED = "validation.timeout.processed"
```

**Producers**: Batch Orchestrator, Essay Lifecycle, NLP, Class Management services
**Consumers**: Essay Lifecycle, Class Management services

### Class Management Events

```python
ProcessingEvent.CLASS_CREATED = "class.created"
ProcessingEvent.CLASS_UPDATED = "class.updated"
ProcessingEvent.STUDENT_CREATED = "student.created"
ProcessingEvent.STUDENT_UPDATED = "student.updated"
ProcessingEvent.ESSAY_STUDENT_ASSOCIATION_UPDATED = "essay.student.association.updated"
```

**Producer**: Class Management Service
**Consumers**: Essay Lifecycle Service, API Gateway (for cache invalidation)

### File Management Events

```python
ProcessingEvent.BATCH_FILE_ADDED = "batch.file.added"
ProcessingEvent.BATCH_FILE_REMOVED = "batch.file.removed"
```

**Producer**: File Service
**Consumers**: Essay Lifecycle Service

### Result Aggregation Events

```python
ProcessingEvent.BATCH_RESULTS_READY = "batch.results.ready"
ProcessingEvent.BATCH_ASSESSMENT_COMPLETED = "batch.assessment.completed"
```

**Producer**: Result Aggregator Service
**Consumers**: API Gateway, WebSocket Service

### LLM Provider Events

```python
ProcessingEvent.LLM_REQUEST_STARTED = "llm_provider.request.started"
ProcessingEvent.LLM_REQUEST_COMPLETED = "llm_provider.request.completed"
ProcessingEvent.LLM_PROVIDER_FAILURE = "llm_provider.failure"
ProcessingEvent.LLM_USAGE_ANALYTICS = "llm_provider.usage.analytics"
ProcessingEvent.LLM_COST_ALERT = "llm_provider.cost_alert"
ProcessingEvent.LLM_COST_TRACKING = "llm_provider.cost_tracking"
```

**Producer**: LLM Provider Service
**Consumers**: CJ Assessment Service (callbacks), Monitoring/Analytics services

### Identity Service Events

```python
ProcessingEvent.IDENTITY_USER_REGISTERED = "identity.user.registered"
ProcessingEvent.IDENTITY_EMAIL_VERIFICATION_REQUESTED = "identity.email.verification.requested"
ProcessingEvent.IDENTITY_EMAIL_VERIFIED = "identity.email.verified"
ProcessingEvent.IDENTITY_PASSWORD_RESET_REQUESTED = "identity.password.reset.requested"
ProcessingEvent.IDENTITY_PASSWORD_RESET_COMPLETED = "identity.password.reset.completed"
ProcessingEvent.IDENTITY_LOGIN_SUCCEEDED = "identity.login.succeeded"
ProcessingEvent.IDENTITY_LOGIN_FAILED = "identity.login.failed"
```

**Producer**: Identity Service
**Consumers**: Email Service, Entitlements Service, Analytics

### Email Service Events

```python
ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED = "email.notification.requested"
ProcessingEvent.EMAIL_SENT = "email.sent"
ProcessingEvent.EMAIL_DELIVERY_FAILED = "email.delivery_failed"
```

**Producer**: Identity Service, Notification logic
**Consumers**: Email Service

### Entitlements Service Events

```python
ProcessingEvent.ENTITLEMENTS_SUBSCRIPTION_ACTIVATED = "entitlements.subscription.activated"
ProcessingEvent.ENTITLEMENTS_SUBSCRIPTION_CHANGED = "entitlements.subscription.changed"
ProcessingEvent.ENTITLEMENTS_SUBSCRIPTION_CANCELED = "entitlements.subscription.canceled"
ProcessingEvent.ENTITLEMENTS_USAGE_AUTHORIZED = "entitlements.usage.authorized"
ProcessingEvent.ENTITLEMENTS_USAGE_RECORDED = "entitlements.usage.recorded"
ProcessingEvent.ENTITLEMENTS_CREDIT_BALANCE_CHANGED = "entitlements.credit.balance.changed"
ProcessingEvent.ENTITLEMENTS_RATE_LIMIT_EXCEEDED = "entitlements.rate_limit.exceeded"
```

**Producer**: Entitlements Service
**Consumers**: API Gateway (for quota checks), Billing/Analytics

### Resource Tracking Events

```python
ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED = "resource.consumption.reported"
```

**Producer**: All processing services
**Consumers**: Entitlements Service, Analytics

## Adding New Events

Follow this exact sequence to add a new event:

### 1. Add Enum Value

```python
# In common_core/event_enums.py
class ProcessingEvent(str, Enum):
    # ... existing events

    # Your new event (use descriptive dotted name)
    MY_NEW_EVENT = "my.new.event"
```

### 2. Add Topic Mapping

```python
# In common_core/event_enums.py _TOPIC_MAPPING
_TOPIC_MAPPING = {
    # ... existing mappings

    ProcessingEvent.MY_NEW_EVENT: "huleedu.service.my.new.event.v1",
}
```

Topic naming convention: `huleedu.<service_area>.<event_name>.<version>`

### 3. Create Event Data Model

```python
# In common_core/events/my_service_events.py
from common_core.events.base_event_models import BaseEventData
from common_core.event_enums import ProcessingEvent
from pydantic import Field

class MyNewEventV1(BaseEventData):
    """Event published when [specific condition occurs].

    Producer: MyService
    Consumers: ServiceA, ServiceB
    """

    event_name: ProcessingEvent = Field(default=ProcessingEvent.MY_NEW_EVENT)

    # Event-specific fields
    entity_id: str = Field(description="ID of entity affected")
    status: str
    # ...
```

### 4. Add to __all__ Exports

```python
# In common_core/events/my_service_events.py
__all__ = [
    "MyNewEventV1",
    # ... other exports
]
```

### 5. Update Service Event Handlers

Producer service:

```python
# In my_service/event_publisher.py
from common_core.events.envelope import EventEnvelope
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.my_service_events import MyNewEventV1

envelope = EventEnvelope[MyNewEventV1](
    event_type=topic_name(ProcessingEvent.MY_NEW_EVENT),
    source_service="my_service",
    correlation_id=correlation_id,
    data=MyNewEventV1(entity_id="123", status="completed")
)

await kafka_bus.publish(
    topic=topic_name(ProcessingEvent.MY_NEW_EVENT),
    value=envelope.model_dump_json().encode('utf-8')
)
```

Consumer service:

```python
# In consumer_service/kafka_handlers.py
async def handle_my_new_event(self, message: bytes) -> None:
    envelope = EventEnvelope[Any].model_validate_json(message)
    event_data = MyNewEventV1.model_validate(envelope.data)

    # Process event
    await self.process(event_data, envelope.correlation_id)
```

### 6. Verify topic_name() Works

```python
# Test in Python REPL
from common_core.event_enums import ProcessingEvent, topic_name

topic = topic_name(ProcessingEvent.MY_NEW_EVENT)
print(topic)  # Should print: huleedu.service.my.new.event.v1
```

## Topic Naming Conventions

### Version Suffix Required

All topics MUST include `.v1` suffix for future versioning:

```python
# CORRECT
"huleedu.cj_assessment.completed.v1"
"huleedu.batch.essays.registered.v1"

# WRONG - Missing version
"huleedu.cj_assessment.completed"  # ❌
```

### Service Area Prefix

Topics grouped by service area for Kafka ACLs and monitoring:

```python
# CJ Assessment Service
"huleedu.cj_assessment.*"

# Batch coordination
"huleedu.batch.*"
"huleedu.els.*"  # Essay Lifecycle Service
"huleedu.ras.*"  # Result Aggregator Service

# Identity & Auth
"huleedu.identity.*"
"huleedu.entitlements.*"
```

### Semantic Naming

Use past tense for events (already happened):

```python
# CORRECT - Past tense
"huleedu.cj_assessment.completed.v1"
"huleedu.essay.spellcheck.completed.v1"
"huleedu.batch.essays.registered.v1"

# WRONG - Present tense or imperative
"huleedu.cj_assessment.complete.v1"  # ❌
"huleedu.essay.spellcheck.v1"  # ❌ Not descriptive enough
```

Exception: Command events use imperative:

```python
# Commands use imperative (telling service to do something)
"huleedu.batch.cj_assessment.initiate.command.v1"
"huleedu.batch.spellcheck.initiate.command.v1"
```

## Event Versioning

When event data structure changes in breaking way:

### 1. Create V2 Enum Value

```python
class ProcessingEvent(str, Enum):
    # Old version
    MY_EVENT = "my.event"

    # New version
    MY_EVENT_V2 = "my.event.v2"
```

### 2. Create V2 Topic Mapping

```python
_TOPIC_MAPPING = {
    ProcessingEvent.MY_EVENT: "huleedu.service.my.event.v1",
    ProcessingEvent.MY_EVENT_V2: "huleedu.service.my.event.v2",  # New topic
}
```

### 3. Create V2 Event Data Model

```python
class MyEventV2(BaseEventData):  # New class
    """V2 with breaking changes: removed old_field, added new_field."""

    event_name: ProcessingEvent = Field(default=ProcessingEvent.MY_EVENT_V2)

    # new_field: str  # Breaking change
    # old_field removed
```

### 4. Dual Production During Migration

Producer publishes to both topics temporarily:

```python
# Publish V1 for old consumers
v1_envelope = EventEnvelope[MyEventV1](
    event_type=topic_name(ProcessingEvent.MY_EVENT),
    # ...
)
await kafka_bus.publish(topic_v1, v1_envelope.model_dump_json().encode('utf-8'))

# Publish V2 for new consumers
v2_envelope = EventEnvelope[MyEventV2](
    event_type=topic_name(ProcessingEvent.MY_EVENT_V2),
    # ...
)
await kafka_bus.publish(topic_v2, v2_envelope.model_dump_json().encode('utf-8'))
```

### 5. Consumer Migration

Consumers subscribe to both topics, handle both:

```python
async def handle_message(self, message: bytes) -> None:
    envelope = EventEnvelope[Any].model_validate_json(message)

    if envelope.event_type == topic_name(ProcessingEvent.MY_EVENT):
        # Handle V1
        data = MyEventV1.model_validate(envelope.data)
        await self.process_v1(data)

    elif envelope.event_type == topic_name(ProcessingEvent.MY_EVENT_V2):
        # Handle V2
        data = MyEventV2.model_validate(envelope.data)
        await self.process_v2(data)
```

### 6. Deprecate V1

After all consumers migrated:
1. Producer stops publishing to V1 topic
2. Remove V1 handlers from consumers
3. Mark `MY_EVENT` enum as deprecated in docstring
4. Eventually remove V1 from codebase

## Related Documentation

- [Event Envelope](event-envelope.md) - EventEnvelope structure
- [Dual-Event Pattern](dual-event-pattern.md) - Thin vs rich events
- `.claude/rules/052-event-contract-standards.mdc` - Event structure standards
