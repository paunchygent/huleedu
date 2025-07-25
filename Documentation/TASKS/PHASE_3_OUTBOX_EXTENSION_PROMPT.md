# Phase 3: Transactional Outbox Pattern Extension - Start of Conversation Prompt

## ULTRATHINK Methodology Declaration
This conversation will follow ULTRATHINK methodology throughout, ensuring systematic analysis, thorough planning, and meticulous implementation of the Transactional Outbox Pattern across all critical services.

## Context: What Has Been Accomplished

### Phase 1 & 2 Complete ✅
The Transactional Outbox Pattern has been successfully implemented in the **Essay Lifecycle Service** as documented in `documentation/TASKS/EVENT_PUBLISHING_ARCHITECTURAL_DEBT.md` (marked COMPLETE on July 24, 2025).

**Key Accomplishments:**
1. **Database Infrastructure**
   - Created `event_outbox` table via Alembic migration
   - Implemented `EventOutbox` SQLAlchemy model
   - Created `OutboxRepositoryProtocol` with PostgreSQL implementation

2. **Event Publishing Migration**
   - All 7 event publishing methods in `DefaultEventPublisher` migrated
   - All 2 methods in `DefaultSpecializedServiceRequestDispatcher` migrated
   - Zero direct Kafka calls remain in business logic

3. **Event Relay Worker**
   - Implemented `EventRelayWorker` with retry logic (max 5 retries)
   - Integrated into `worker_main.py` for automatic startup
   - Configurable polling and batch processing

4. **Configuration & DI**
   - Added outbox settings to `config.py`
   - Updated DI container with proper protocol-based injection
   - Full type safety maintained throughout

## Current State Overview

### Working Implementation Files (Essay Lifecycle Service)
- `/services/essay_lifecycle_service/models_db.py` - EventOutbox model
- `/services/essay_lifecycle_service/protocols.py` - OutboxRepositoryProtocol definition
- `/services/essay_lifecycle_service/implementations/outbox_repository_impl.py` - PostgreSQL implementation
- `/services/essay_lifecycle_service/implementations/event_relay_worker.py` - Relay worker
- `/services/essay_lifecycle_service/implementations/event_publisher.py` - Migrated publishers
- `/services/essay_lifecycle_service/di.py` - DI configuration
- `/services/essay_lifecycle_service/config.py` - Outbox settings
- `/services/essay_lifecycle_service/alembic/versions/20250724_0001_add_event_outbox_table.py` - DB migration

### Immediate Tasks Required

#### Task 1: Fix Import Error (if present)
**ULTRATHINK Analysis Required:**
- Identify specific import error in the codebase
- Trace dependency chain causing the error
- Apply fix following Rule 055 (absolute imports)
- Validate fix with unit tests

#### Task 2: Quality Assurance Checks
**ULTRATHINK Verification Steps:**
1. Run all Essay Lifecycle Service tests to ensure stability
2. Verify event relay worker is processing events correctly
3. Check monitoring metrics are being collected
4. Validate database transaction boundaries
5. Confirm idempotency is preserved

## Phase 3: Service Extension Objectives

### Primary Goal
Extend the proven Transactional Outbox Pattern to all services with critical event publishing paths, starting with the highest-priority services.

### Target Services (Priority Order)
1. **File Service** (CRITICAL - handles essay content provisioning)
2. **Batch Orchestrator Service** (orchestrates batch processing)
3. **CJ Assessment Service** (assessment workflow events)
4. **Result Aggregator Service** (result compilation events)
5. **Spellchecker Service** (if event publishing exists)
6. **Class Management Service** (class-related events)

### Implementation Strategy per Service
For each service, following ULTRATHINK methodology:

1. **Analysis Phase**
   - Identify all event publishing methods
   - Map critical vs non-critical events
   - Document current failure modes
   - Assess database transaction boundaries

2. **Design Phase**
   - Plan outbox table schema (reuse Essay Lifecycle pattern)
   - Design repository implementation
   - Plan DI integration
   - Consider service-specific requirements

3. **Implementation Phase**
   - Create Alembic migration
   - Implement models and repository
   - Migrate event publishers
   - Integrate relay worker
   - Update DI configuration

4. **Testing Phase**
   - Unit tests for repository
   - Integration tests for end-to-end flow
   - Failure scenario testing
   - Performance validation

5. **Deployment Phase**
   - Apply migrations
   - Deploy with feature flag (if needed)
   - Monitor metrics
   - Validate in production

## Relevant Architecture Rules

### Core Rules to Follow
- **Rule 010**: Understand task and context before acting
- **Rule 020**: Event-driven architecture via Kafka
- **Rule 030**: Explicit contracts using Pydantic models
- **Rule 040**: Fixed tech stack (Python 3.11, PostgreSQL, Dishka)
- **Rule 042**: Dependency injection with protocols
- **Rule 050**: Full type hints and Google-style docstrings
- **Rule 051**: Pydantic V2 serialization with model_dump(mode="json")
- **Rule 053**: Repository pattern for database access
- **Rule 055**: Absolute imports for all modules
- **Rule 070**: Testing from repository root
- **Rule 081**: PDM for dependency management
- **Rule 084**: Docker with PYTHONPATH=/app

### Outbox-Specific Patterns
1. **Atomic Transactions**: Outbox writes MUST be in same transaction as business logic
2. **Idempotency**: All consumers already implement @idempotent_consumer
3. **Event Ordering**: Preserve order by aggregate_id
4. **Failure Handling**: Max 5 retries with exponential backoff
5. **Monitoring**: Prometheus metrics for queue depth and processing rate

## ULTRATHINK Methodology Reminders

### For Each Service Migration:
1. **Understand** - Deep dive into current implementation
2. **List** - Enumerate all components needing change
3. **Think** - Consider edge cases and failure modes
4. **Reason** - Justify design decisions with architectural principles
5. **Analyze** - Assess impact on existing functionality
6. **Test** - Comprehensive testing at each layer
7. **Handle** - Graceful error handling and recovery
8. **Integrate** - Seamless integration with existing patterns
9. **Notify** - Clear logging and monitoring
10. **Keep** - Maintain consistency with Essay Lifecycle implementation

### Quality Gates
- No direct Kafka calls in business logic
- All events stored in outbox before publishing
- Transaction boundaries properly defined
- Full test coverage for new code
- Monitoring metrics implemented
- Documentation updated

## First Actions Upon Start

1. **Identify and Fix Import Error**
   - Run Essay Lifecycle Service tests
   - Identify specific import failure
   - Apply fix following established patterns

2. **Create Phase 3 Implementation Plan**
   - Analyze File Service event publishing
   - Document all publish points
   - Create detailed migration plan

3. **Begin File Service Migration**
   - Most critical service after Essay Lifecycle
   - Follow proven pattern from Phase 1/2
   - Ensure zero downtime migration

## Success Criteria for Phase 3

1. All critical services use outbox pattern
2. Zero event loss during Kafka outages
3. Performance impact < 5ms per transaction
4. Monitoring shows queue depth trends
5. No regression in existing functionality
6. Clear documentation for future services

## References
- Original Task: `documentation/TASKS/OUTBOX_IMPLEMENTATION_TASK.md`
- Completed Analysis: `documentation/TASKS/EVENT_PUBLISHING_ARCHITECTURAL_DEBT.md`
- Essay Lifecycle Implementation: `/services/essay_lifecycle_service/implementations/`
- Architecture Rules: `/.cursor/rules/`

---

**Remember**: Follow ULTRATHINK methodology, respect all architecture rules, and maintain the high quality standards established in Phase 1 & 2. The Essay Lifecycle Service implementation serves as the reference pattern for all subsequent migrations.