Start-of-Conversation Prompt for RAS Event Publishing Infrastructure

⏺ ULTRATHINK: Result Aggregator Service (RAS) Event Publishing Infrastructure - Session 2.3

PROJECT CONTEXT

HuleEdu is a TEACHER-CENTRIC educational platform where teachers upload essay batches for
assessment processing. The platform uses event-driven microservices with PostgreSQL persistence,
Kafka for async communication, and a clean separation between domain events and teacher
notifications. The Result Aggregator Service (RAS) collects and aggregates results from various
processing phases (spellcheck, CJ assessment, etc.) but currently acts as a "dead end" - it
receives and stores results but never publishes events to notify downstream services or teachers.

IMPLEMENTATION STATUS

✅ COMPLETED - Session 1.1: Transactional Outbox Pattern
- EventOutbox model added to models_db.py (11 columns, 3 indexes)
- Database migration applied successfully
- OutboxManager implementation (direct copy from file_service pattern)
- PostgreSQLOutboxRepository and OutboxManager providers in DI
- 7/7 unit tests passing for OutboxManager
- Database verified: table event_outbox exists in result_aggregator DB (port 5436)

✅ COMPLETED - Session 2.1 & 2.2: Event Publisher and Contracts
- ResultEventPublisher implemented with TRUE OUTBOX PATTERN
- Event contracts added to common_core/events/result_events.py
- BatchResultsReadyV1 and BatchAssessmentCompletedV1 events defined
- ProcessingEvent enum updated with new event types
- Topic mappings added to _TOPIC_MAPPING dictionary
- DI container updated with KafkaBus, CircuitBreaker, and ResilientKafkaPublisher
- EventPublisherProtocol added to protocols.py
- 12/12 unit tests passing for event publisher
- Stub NotificationProjector created for future Session 3.1

🔴 CURRENT BLOCKER: RAS Cannot Notify About Results

CRITICAL ISSUE: While RAS now has the infrastructure to publish events (outbox + publisher),
it's NOT ACTUALLY USING IT! The EventPublisher is created but never called. This means:
- Teachers NEVER get "Results ready" notifications when processing completes
- Teachers NEVER get "Assessment completed" notifications when CJ finishes
- WebSocket service waits forever for events that never come
- Phase 3B of WEBSOCKET_TEACHER_NOTIFICATION_LAYER.md remains blocked

ULTRATHINK: SESSION 2.3 OBJECTIVE - Wire EventPublisher Into Event Handlers

We need to integrate the EventPublisher at two critical points in EventProcessorImpl where
RAS receives completion events but currently does nothing with them. This session focuses
on adding the actual publishing calls that will trigger downstream notifications.

DISCOVERED INTEGRATION POINTS FROM INVESTIGATION

Through analysis of the existing code, we've identified EXACTLY where to integrate:

1. INTEGRATION POINT 1: process_batch_phase_outcome() - Line 130-184
   - Currently: Updates DB with phase completion, invalidates cache, then STOPS
   - Needed: Check if ALL phases complete, then publish BatchResultsReadyV1
   - Impact: Finally notifies teachers their batch processing is complete

2. INTEGRATION POINT 2: process_cj_assessment_completed() - Line 288-347
   - Currently: Stores rankings in DB, invalidates cache, then STOPS
   - Needed: Publish BatchAssessmentCompletedV1 after storing rankings
   - Impact: Notifies teachers that CJ assessment rankings are available

EXISTING INFRASTRUCTURE TO USE

From Session 2.1-2.2 Implementation:
- ResultEventPublisher - Ready with publish_batch_results_ready() and publish_batch_assessment_completed()
- EventPublisherProtocol - Interface defined in protocols.py
- Event Contracts - BatchResultsReadyV1 and BatchAssessmentCompletedV1 in common_core
- DI Providers - All wiring ready, just need to inject into EventProcessorImpl

MANDATORY READING REQUIREMENTS

YOU MUST READ THESE FILES IN THIS EXACT ORDER BEFORE IMPLEMENTING:

Rules (Read FIRST for Context and Patterns):

1. /Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/000-rule-index.mdc - Understand rule structure
2. /Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/042.1-transactional-outbox-pattern.mdc - TRUE OUTBOX PATTERN requirements
3. /Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/030-event-driven-architecture-eda-standards.mdc - Event publishing standards
4. /Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/050-python-coding-standards.mdc - Code style requirements
5. /Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/042-async-patterns-and-di.mdc - DI injection patterns
6. /Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/048-structured-error-handling-standards.mdc - Error handling patterns
7. /Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/075-test-creation-methodology.mdc - Test creation methodology
8. /Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/081-pdm-dependency-management.mdc - PDM dependency management


Task Documentation (Understand the full roadmap):

1. /Users/olofs_mba/Documents/Repos/huledu-reboot/TASKS/RAS_EVENT_PUBLISHING_INFRASTRUCTURE.md - Read Session 2.3 requirements (Lines 92-302)
2. /Users/olofs_mba/Documents/Repos/huledu-reboot/TASKS/WEBSOCKET_TEACHER_NOTIFICATION_LAYER.md - Understand what this unblocks

Current Implementation to Understand (WHAT WE BUILT):

1. /Users/olofs_mba/Documents/Repos/huledu-reboot/services/result_aggregator_service/implementations/event_publisher_impl.py - The EventPublisher we need to use
2. /Users/olofs_mba/Documents/Repos/huledu-reboot/services/result_aggregator_service/protocols.py - EventPublisherProtocol interface (Lines 250-279)
3. /Users/olofs_mba/Documents/Repos/huledu-reboot/services/result_aggregator_service/di.py - Current DI setup (Lines 291-305)
4. /Users/olofs_mba/Documents/Repos/huledu-reboot/libs/common_core/src/common_core/events/result_events.py - Event contracts we'll create

Integration Target (WHERE TO ADD CODE):

1. /Users/olofs_mba/Documents/Repos/huledu-reboot/services/result_aggregator_service/implementations/event_processor_impl.py - Read entire file, focus on:
   - Lines 130-184: process_batch_phase_outcome() method
   - Lines 288-347: process_cj_assessment_completed() method
   - Lines 37-46: Current __init__ method that needs EventPublisher injection

Database Models (Understand data structures):

1. /Users/olofs_mba/Documents/Repos/huledu-reboot/services/result_aggregator_service/models_db.py - BatchResult and EssayResult models

ULTRATHINK: IMPLEMENTATION CHECKLIST

Session 2.3 deliverables (DO THESE IN ORDER):

1. UPDATE EventProcessorImpl Constructor
   - Modify __init__ to accept EventPublisherProtocol parameter
   - Store as self.event_publisher instance variable
   - Update imports to include EventPublisherProtocol

2. UPDATE DI Container
   - Modify provide_event_processor() in di.py
   - Inject EventPublisherProtocol dependency
   - Ensure proper provider ordering

3. INTEGRATE at process_batch_phase_outcome()
   - After line 177 (cache invalidation), add batch completion check
   - Create helper method _check_batch_completion()
   - Create helper method _calculate_phase_results()
   - Create helper method _determine_overall_status()
   - Create helper method _calculate_duration()
   - If all phases complete, create BatchResultsReadyV1 event
   - Call self.event_publisher.publish_batch_results_ready()

4. INTEGRATE at process_cj_assessment_completed()
   - After line 331 (cache invalidation), fetch batch for user_id
   - Create BatchAssessmentCompletedV1 event with thin rankings
   - Call self.event_publisher.publish_batch_assessment_completed()

5. CREATE Integration Tests
   - Test batch completion detection logic
   - Test event creation with proper data mapping
   - Test correlation_id propagation
   - Mock EventPublisher to verify method calls

6. VALIDATE End-to-End
   - Run existing unit tests to ensure no regression
   - Verify DI container can resolve all dependencies
   - Check that events are stored in outbox table

ULTRATHINK: SUCCESS CRITERIA

The session is complete when:

1. EventProcessorImpl RECEIVES EventPublisher via DI
2. Batch completion TRIGGERS BatchResultsReadyV1 publication
3. CJ assessment completion TRIGGERS BatchAssessmentCompletedV1 publication
4. Events are STORED in outbox table (can verify with SQL)
5. Integration tests PASS for both scenarios
6. Code passes: pdm run lint-fix && pdm run typecheck-all

ULTRATHINK: CRITICAL CONSTRAINTS

NO DIRECT KAFKA: Events must go through EventPublisher which uses OutboxManager
PRESERVE CORRELATION: Always pass envelope.correlation_id to publisher
CHECK COMPLETION: Only publish BatchResultsReadyV1 when ALL phases complete
THIN EVENTS: Rankings in BatchAssessmentCompletedV1 are summary only
USE EXISTING PATTERNS: Follow the exact patterns from Session 2.1-2.2

WORKING DIRECTORY

/Users/olofs_mba/Documents/Repos/huledu-reboot

IMMEDIATE NEXT STEPS

1. READ ALL RULES AND REFERENCE FILES (no agents, direct reading only)
2. EXAMINE current EventProcessorImpl implementation
3. UPDATE constructor and DI container
4. ADD integration at process_batch_phase_outcome()
5. ADD integration at process_cj_assessment_completed()
6. CREATE helper methods for data transformation
7. WRITE integration tests
8. VALIDATE with lint and typecheck

KEY QUESTIONS TO ANSWER

1. How do we determine if all phases are complete for a batch?
2. What data from BatchResult needs to map to BatchResultsReadyV1?
3. How do we calculate processing duration from timestamps?
4. Should we publish events even for partial failures?
5. What happens if EventPublisher.publish_* methods fail?

REMEMBER

- Integration First: We're wiring existing components, not creating new ones
- Data Mapping: BatchResult → Event requires careful field mapping
- Correlation Context: Always propagate correlation_id from incoming envelope
- Test Everything: Integration points are critical - test thoroughly
- No Agents: Read files directly, understand patterns completely

CRITICAL CONTEXT FROM PREVIOUS SESSIONS

The EventPublisher follows TRUE OUTBOX PATTERN - it stores events in the database first,
then a relay worker publishes to Kafka asynchronously. The NotificationProjector is stubbed
for now (Session 3.1) but the EventPublisher is ready to invoke it when available.

The WebSocket service is actively waiting for these events to push real-time notifications
to teachers. Without this integration, the entire notification pipeline is broken.

Current Working Directory: /Users/olofs_mba/Documents/Repos/huledu-reboot

Begin by reading ALL referenced rules and files to understand the complete context, then
examine the EventProcessorImpl to understand current flow before adding the integration
points. This session connects the final pieces that enable RAS to announce results to
the world instead of silently storing them.

BEGIN READING RULES AND FILE REFERENCES