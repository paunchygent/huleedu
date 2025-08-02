# Conversation Prompt: NLP Phase 1 Class Management Service Kafka Infrastructure

## Session Context

You are continuing the implementation of NLP Service Phase 1 Student Matching Integration for the HuleEdu platform. In the previous session, we successfully implemented the NLP Service handler that was blocking the Phase 1 flow. Now we need to implement the Class Management Service Kafka infrastructure to receive and process the student matching suggestions from the NLP Service.

## 📚 Essential Rules to Read FIRST

**IMPORTANT: Read these rules BEFORE starting any implementation:**

1. `.cursor/rules/000-rule-index.mdc` - Understand the rule system and find relevant rules
2. `.cursor/rules/010-foundational-principles.mdc` - Core architectural principles (DDD, SOLID, YAGNI)
3. `.cursor/rules/020-architectural-mandates.mdc` - Service boundaries and communication patterns
4. `.cursor/rules/030-event-driven-architecture-eda-standards.mdc` - Event patterns and Kafka usage
5. `.cursor/rules/042-async-patterns-and-di.mdc` - Dependency injection patterns
6. `.cursor/rules/048-structured-error-handling-standards.mdc` - Error handling patterns
7. `.cursor/rules/051-event-envelope-versioning-strategy.mdc` - Event envelope usage
8. `.cursor/rules/052-event-design-patterns.mdc` - Event design patterns
9. `.cursor/rules/080-repository-workflow-and-tooling.mdc` - Development workflow
10. `.cursor/rules/085-database-migration-standards.md` - Database migration patterns

## Previous Session Summary

### What We Accomplished

1. **Fixed NLP Service Handler**: Updated `EssayStudentMatchingHandler` to:
   - Listen for correct event type: `huleedu.batch.student.matching.requested.v1`
   - Process entire batches using `BatchStudentMatchingRequestedV1`
   - Publish `BatchAuthorMatchesSuggestedV1` to Class Management Service
   - Added comprehensive error handling and test coverage

2. **Protocol Updates**: Added `publish_batch_author_match_results` method to `NlpEventPublisherProtocol`

3. **Test Suite**: Created unit tests and fixed integration tests for the updated handler

### Current Architecture Status

The Phase 1 student matching flow now works as follows:

1. ✅ **GUEST Batches** (no class_id): 
   - ELS publishes `BatchContentProvisioningCompletedV1`
   - BOS transitions directly to `READY_FOR_PIPELINE_EXECUTION`

2. ✅ **REGULAR Batches** (with class_id) - Working up to Class Management:
   - ELS publishes `BatchContentProvisioningCompletedV1`
   - BOS publishes `BatchServiceStudentMatchingInitiateCommandDataV1`
   - ELS receives command and publishes `BatchStudentMatchingRequestedV1`
   - NLP Service processes batch and publishes `BatchAuthorMatchesSuggestedV1`
   - ❌ **BREAKS HERE**: Class Management has NO Kafka infrastructure to receive events

## 🚨 CRITICAL BLOCKER: Class Management Service Kafka Infrastructure

### Investigation Results

The Class Management Service currently:
- ✅ Has database models for student associations
- ✅ Has API endpoints for validation
- ❌ Has NO Kafka consumer infrastructure
- ❌ Cannot receive `BatchAuthorMatchesSuggestedV1` events from NLP
- ❌ Cannot publish `StudentAssociationsConfirmedV1` events to ELS

### Required Implementation

## 🧠 ULTRATHINK: Class Management Kafka Infrastructure Implementation

### Step 1: Study Existing Patterns

**CRITICAL**: Study how other services implement Kafka infrastructure:
- Review `services/batch_orchestrator_service/kafka_consumer.py` for consumer patterns
- Check `services/essay_lifecycle_service/kafka_consumer.py` for event routing
- Examine `services/batch_orchestrator_service/event_processing.py` for handler dispatch
- Study `services/essay_lifecycle_service/di.py` for Kafka DI setup

### Step 2: Create Kafka Consumer Infrastructure

**File to Create**: `services/class_management_service/kafka_consumer.py`

```python
"""Kafka consumer for Class Management Service events."""

# Follow patterns from other services
# Key components:
# - KafkaConsumerWorker class
# - Message processing with error handling
# - Event routing to appropriate handlers
# - Graceful shutdown
```

### Step 3: Create Event Processing Router

**File to Create**: `services/class_management_service/event_processing.py`

```python
"""Event processing router for Class Management Service."""

async def process_single_message(
    msg: ConsumerRecord,
    container: AsyncContainer,
    http_session: ClientSession,
    correlation_id: UUID,
    span: Span | None = None,
) -> None:
    """Route events to appropriate handlers."""
    # Parse envelope
    # Route based on event_type
    # Handle BatchAuthorMatchesSuggestedV1
```

### Step 4: Create Batch Author Matches Handler

**File to Create**: `services/class_management_service/handlers/batch_author_matches_handler.py`

```python
"""Handler for batch author match suggestions from NLP Service."""

class BatchAuthorMatchesHandler:
    """
    Processes BatchAuthorMatchesSuggestedV1 events from NLP Service.
    
    Flow:
    1. Receive match suggestions for entire batch
    2. Store suggestions in database
    3. Update batch status to awaiting_validation
    4. Optionally auto-accept high confidence matches
    5. Wait for teacher validation via API
    """
```

### Step 5: Update Dependency Injection

**File to Update**: `services/class_management_service/di.py`

- Add Kafka consumer dependencies
- Wire up event handlers
- Configure HTTP session for outbound calls
- Set up outbox pattern for publishing events

### Step 6: Create Student Association Confirmation Publisher

**File to Create**: `services/class_management_service/implementations/event_publisher.py`

```python
"""Event publisher for Class Management Service."""

class ClassManagementEventPublisher:
    """Publishes events via outbox pattern."""
    
    async def publish_student_associations_confirmed(
        self,
        batch_id: str,
        associations: list[dict],
        correlation_id: UUID,
    ) -> None:
        """Publish StudentAssociationsConfirmedV1 to ELS."""
```

### Step 7: Database Migrations

**Check if needed**: `services/class_management_service/alembic/versions/`

- Verify student_associations table exists
- Add any missing fields for Phase 1
- Ensure proper indexes for batch_id queries

### Step 8: Docker Configuration

**File to Update**: `docker-compose.yml`

- Ensure Class Management Service has Kafka environment variables
- Verify service dependencies include Kafka
- Check health checks and startup order

## 📋 Implementation Checklist

### Infrastructure Setup
- [ ] Create `kafka_consumer.py` with consumer worker
- [ ] Create `event_processing.py` for event routing
- [ ] Update `di.py` with Kafka dependencies
- [ ] Configure Kafka topics in environment

### Event Handlers
- [ ] Create `BatchAuthorMatchesHandler` for NLP events
- [ ] Implement storage of match suggestions
- [ ] Add batch status updates
- [ ] Handle validation timeout scenarios

### Event Publishing
- [ ] Create event publisher with outbox pattern
- [ ] Implement `publish_student_associations_confirmed`
- [ ] Add correlation ID propagation
- [ ] Ensure atomic database + outbox operations

### Integration Points
- [ ] Verify existing API endpoints work with Kafka flow
- [ ] Test teacher validation UI integration
- [ ] Ensure proper error handling throughout
- [ ] Add comprehensive logging

### Testing
- [ ] Unit tests for all handlers
- [ ] Integration tests with testcontainers
- [ ] E2E test of full Phase 1 flow
- [ ] Performance testing for batch operations

## 🔍 Key Files to Reference

### Event Models
- `libs/common_core/src/common_core/events/nlp_events.py` - BatchAuthorMatchesSuggestedV1
- `libs/common_core/src/common_core/events/class_management_events.py` - StudentAssociationsConfirmedV1
- `libs/common_core/src/common_core/event_enums.py` - Event type constants

### Kafka Infrastructure Examples
- `services/batch_orchestrator_service/kafka_consumer.py` - Consumer implementation
- `services/essay_lifecycle_service/event_processing.py` - Event routing patterns
- `services/nlp_service/di.py` - Kafka DI configuration

### Handler Examples
- `services/batch_orchestrator_service/implementations/student_associations_confirmed_handler.py` - Similar handler pattern
- `services/essay_lifecycle_service/implementations/student_associations_handler.py` - Association handling

### Database Models
- `services/class_management_service/models_domain.py` - Check existing models
- `services/class_management_service/repositories/` - Repository patterns

## ⚡ Quick Start Commands

```bash
# Navigate to Class Management Service
cd services/class_management_service

# Check existing structure
ls -la
find . -name "*.py" | grep -E "(kafka|event|handler)"

# Run existing tests
pdm run pytest tests/ -v

# Check for database migrations
pdm run alembic history

# Lint new code
pdm run ruff check .

# Type checking
pdm run mypy .
```

## 🎯 Success Criteria

1. **Kafka Consumer Running**: Service successfully connects to Kafka and consumes events
2. **Event Processing**: BatchAuthorMatchesSuggestedV1 events are received and processed
3. **Database Updates**: Match suggestions stored and batch status updated
4. **Event Publishing**: StudentAssociationsConfirmedV1 published via outbox
5. **Integration Tests**: Full Phase 1 flow works E2E
6. **No Regressions**: Existing Class Management features continue working

## ⚠️ Common Pitfalls to Avoid

1. **Don't forget the outbox pattern** - All event publishing must use outbox
2. **Check topic names** - Use the topic_name() utility for consistency
3. **Validate event data** - Use Pydantic models for all event parsing
4. **Handle missing batches** - Gracefully handle events for non-existent batches
5. **Respect DDD boundaries** - Don't add fields that belong to other contexts

## 📊 Architecture Context

The Class Management Service is responsible for:
- Managing class rosters and student information
- Receiving AI-suggested student-essay matches
- Providing teacher validation UI
- Publishing confirmed associations back to the system

This implementation completes the Phase 1 student matching flow, enabling teachers to validate AI-suggested matches before essay processing begins.

## Next Steps After This Session

Once Class Management Kafka infrastructure is complete:
1. Integration testing of full Phase 1 flow
2. Performance testing with large batches
3. Teacher UI updates for validation workflow
4. Monitoring and observability setup
5. Feature flag configuration for gradual rollout

Start by examining the existing Class Management Service structure and understanding how it currently handles student associations via API, then implement the Kafka infrastructure following the patterns established in other services.