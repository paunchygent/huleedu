CJ ASSESSMENT SERVICE BATCH LLM INTEGRATION - PROPER IMPLEMENTATION

  You are Claude Code, tasked with implementing TASK-CJ-03 to properly integrate batch LLM processing into the CJ Assessment Service's existing core logic in the HuleEdu
  platform.

  ULTRATHINK MISSION OVERVIEW

  PRIMARY OBJECTIVE: Implement the batch LLM processing plan from TASK-CJ-03 by transforming the existing CJ Assessment workflow to support batch submission and async
  callbacks, while maintaining all proven core logic.

  CONTEXT: Previous work has created foundation but with architectural misalignment:

  Previous Session Achievements ✅

- ✅ Completed Phase 1 & 2 of TASK-LLM-02 (state management, callback processing)
- ✅ Added CJBatchState model with comprehensive tracking
- ✅ Implemented dual-topic Kafka consumer for callbacks
- ✅ Created BatchMonitor for stuck batch detection
- ✅ Added comprehensive Prometheus metrics

  Critical Issue Identified ⚠️

- Created workflow_logic.py as a parallel, disconnected workflow
- Does NOT integrate with existing workflow_orchestrator.py
- Creates architectural confusion with two competing workflows
- Missing actual implementations (TODOs for scoring, publishing)

  New Understanding 💡

- Need to TRANSFORM existing workflow, not replace it
- Batch processing should enhance current logic, not create parallel system
- Must maintain proven Bradley-Terry scoring and pair generation
- Support admin-configurable batch sizes and future stability thresholds

  MANDATORY WORKFLOW

  STEP 1: Build Architectural Knowledge

  Read these documents in order:

  1. /Users/olofs_mba/Documents/Repos/huledu-reboot/documentation/TASKS/TASK-CJ-03-batch-llm-integration.md - NEW implementation plan
  2. /Users/olofs_mba/Documents/Repos/huledu-reboot/CLAUDE.md - Platform architectural mandates
  3. /Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/020.7-cj-assessment-service.md - Service architecture (updated)
  4. Analyze existing core logic:
     - services/cj_assessment_service/cj_core_logic/workflow_orchestrator.py
     - services/cj_assessment_service/cj_core_logic/comparison_processing.py
     - services/cj_assessment_service/cj_core_logic/scoring_ranking.py

  STEP 2: ULTRATHINK Agent Deployment

  Deploy agents to implement TASK-CJ-03 systematically using TodoWrite for progress tracking:

  Agent Alpha: Refactor workflow_logic.py

- Transform into focused batch_callback_handler.py
- Remove workflow duplication
- Focus only on callback processing that triggers existing logic

  Agent Beta: Create BatchProcessor module

- Implement batch submission logic
- Handle batch size configuration
- Track submission state in CJBatchState

  Agent Charlie: Integrate with existing workflow

- Modify comparison_processing.py minimally
- Replace synchronous LLM calls with batch submission
- Maintain all existing logic flow

  Agent Delta: Implement failed comparison pool

- Add pool management to processing_metadata
- Implement retry batch formation
- Ensure equal comparison counts for fairness

  Agent Echo: Configuration system

- Add BatchConfigOverrides to API models
- Implement settings hierarchy
- Enable admin overrides

  Agent Foxtrot: Testing and validation

- Update tests for batch processing
- Add integration tests
- Ensure backward compatibility

  CURRENT STATE ANALYSIS

  What Works ✅

- Database schema ready (CJBatchState, ComparisonPair with correlation IDs)
- Callback processing infrastructure in place
- Monitoring and metrics implemented
- LLM Provider Service supports batch submission

  What Needs Fixing 🔧

  1. workflow_logic.py creates parallel workflow - needs refactoring
  2. No batch submission mechanism in current workflow
  3. No failed comparison pool implementation
  4. Configuration not exposed to admin API

  What Must Be Preserved 🛡️

- Bradley-Terry scoring algorithm (scoring_ranking.py)
- Existing database relationships
- Current API contracts

  IMPLEMENTATION REQUIREMENTS

  Key Design Principles

  1. Minimal changes to proven logic
  2. Batch submission replaces individual LLM calls
  3. Callbacks trigger continuation of existing workflow
  4. Failed comparisons pooled and retried as batches
  5. Configuration hierarchy: defaults → environment → request

  Batch Processing Flow

  1. Generate comparison pairs (existing logic)
  2. Submit in batches up to 200 comparisons
  3. Update state to WAITING_CALLBACKS
  4. Process callbacks as they arrive
  5. Check if batch complete or threshold reached
  6. Continue with scoring (existing logic)

  Failed Comparison Pool

- Preserve original pairing for fairness
- Collect failures until threshold (20)
- Submit retry batch with same constraints
- Track retry attempts per comparison
- Ensure all essays get equal comparisons

  CRITICAL CONSTRAINTS

  MUST Follow

- Use existing event models and database schema
- Maintain backward compatibility
- Follow async SQLAlchemy patterns from rule 053
- Use structured error handling with HuleEduError
- Implement idempotent operations

  Integration Points

- Modify comparison_processing.perform_comparison_iteration()
- Update LLMInteractionImpl to support batch submission
- Enhance workflow_orchestrator to handle WAITING_CALLBACKS state
- Add batch config to CJAssessmentRequest model

  AGENT INSTRUCTIONS

  Agent Alpha: Fix workflow_logic.py
  Focus: Remove parallel workflow, create focused callback handler
  Output: batch_callback_handler.py that integrates with existing workflow
  Reference: TASK-CJ-03 section on callback integration

  Agent Beta: BatchProcessor Implementation
  Focus: Clean batch submission with configuration support
  Output: cj_core_logic/batch_processor.py
  Reference: TASK-CJ-03 Phase 1 implementation details

  Agent Charlie: Workflow Integration
  Focus: Minimal changes to existing proven logic
  Output: Updated comparison_processing.py
  Reference: TASK-CJ-03 integration points section

  Agent Delta: Failed Pool Management
  Focus: Fair retry mechanism preserving pairs
  Output: Pool management in BatchProcessor
  Reference: TASK-CJ-03 section 2.4

  Agent Echo: Configuration
  Focus: Admin overrides and settings hierarchy
  Output: Updated models_api.py and config.py
  Reference: TASK-CJ-03 configuration system

  Agent Foxtrot: Testing
  Focus: Comprehensive test coverage
  Output: New and updated test files
  Reference: Rule 070 testing patterns

  SUCCESS CRITERIA

  Functional Requirements

- ✅ Batch submission up to 200 comparisons
- ✅ Async callback processing
- ✅ Failed comparison retry pools
- ✅ Partial completion support (85% threshold)
- ✅ Admin configuration overrides

  Technical Requirements

- ✅ Integrate with existing workflow
- ✅ No parallel competing systems
- ✅ Maintain all current functionality
- ✅ Support future stability thresholds

  Performance Requirements

- ✅ 50%+ reduction in processing time
- ✅ Support 3+ concurrent batches
- ✅ Handle partial failures gracefully
- ✅ Scale to 1000+ concurrent assessments

  IMMEDIATE NEXT STEPS

  1. Deploy TodoWrite to track implementation tasks
  2. Start with Agent Alpha to fix architectural confusion
  3. Implement BatchProcessor (Agent Beta) as foundation
  4. Integrate with existing workflow (Agent Charlie)
  5. Add failure handling and configuration
  6. Comprehensive testing throughout

  CONTEXT FILES REFERENCE

  Implementation Plan: /Users/olofs_mba/Documents/Repos/huledu-reboot/documentation/TASKS/TASK-CJ-03-batch-llm-integration.md
  Previous Tasks: TASK-LLM-01.md (LLM Provider), TASK-LLM-02.md (CJ Event-Driven)
  Service Implementation: /Users/olofs_mba/Documents/Repos/huledu-reboot/services/cj_assessment_service/
  Platform Rules: /Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/
  Current Issues: workflow_logic.py creating parallel workflow instead of integration

  Begin by reading TASK-CJ-03 to understand the proper integration approach, then systematically deploy agents to transform the CJ Assessment Service for efficient batch
  processing while preserving all proven core logic.

  Remember: Transform and enhance, don't replace! The existing workflow has proven logic that must be preserved.
