LLM PROVIDER SERVICE EVENT-DRIVEN CALLBACK TRANSFORMATION - PHASE 2 CONTINUATION

  You are Claude Code, continuing Phase 2 of LLM Provider Service event-driven callback transformation in the HuleEdu platform. This session builds upon successful Phase 1
   infrastructure completion.

  ULTRATHINK MISSION OVERVIEW

  PRIMARY OBJECTIVE: Complete Phase 2 of TASK-LLM-01 by implementing event-driven callback publishing, removing polling infrastructure, and updating API contracts to
  require callback topics.

  CONTEXT: Phase 1 has been successfully completed with comprehensive event infrastructure:

- ✅ Event models (LLMComparisonResultV1, TokenUsage) with mutual exclusion validation
- ✅ Error infrastructure (LLMErrorCode enum with 14 provider-specific codes)
- ✅ Event system integration (ProcessingEvent.LLM_COMPARISON_RESULT, topic mapping)
- ✅ Comprehensive testing (19 event model tests, 5 enum tests, all passing)
- ✅ Confidence score alignment fix (1-5 scale matching CJ Assessment expectations)

  CURRENT STATE: Event contract infrastructure complete, ready for API transformation and callback implementation.

  MANDATORY WORKFLOW

  STEP 1: Build Architectural Knowledge

  Read these foundational documents in order:

  1. /Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/000-rule-index.mdc - Navigate to all relevant rules
  2. /Users/olofs_mba/Documents/Repos/huledu-reboot/CLAUDE.md - Project architectural mandates
  3. /Users/olofs_mba/Documents/Repos/huledu-reboot/documentation/TASKS/TASK-LLM-01.md - Complete task context with Phase 1 completion
  4. /Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/020.13-llm-provider-service-architecture.mdc - Service-specific architecture rules

  STEP 2: ULTRATHINK Agent Deployment

  Deploy agents to implement Phase 2 systematically using TodoWrite for progress tracking:

  Agent Alpha: API contract updates (make callback_topic required)
  Agent Beta: Event publisher infrastructure (add publish_to_topic method)Agent Gamma: Polling endpoint removal (delete status/results routes)
  Agent Delta: Queue processor callback implementation
  Agent Echo: Validation testing and quality assurance

  PHASE 1 ACHIEVEMENTS ✅

  Event Infrastructure Complete

- Event Models: LLMComparisonResultV1 with @model_validator ensuring mutual exclusion between success (winner, justification, confidence) and error (error_detail) fields
- Token Tracking: TokenUsage model with non-negative validation for prompt/completion/total tokens
- Error Codes: LLMErrorCode enum with 14 codes covering provider/request/processing/response/system errors
- Topic Integration: ProcessingEvent.LLM_COMPARISON_RESULT = "llm_provider.comparison_result" mapping to huleedu.llm_provider.comparison_result.v1

  Critical Discovery - Confidence Score Alignment ✅

  Issue Found: Original task spec used 0-1 confidence range, but investigation revealed:

- LLM Provider Service API outputs 1-5 scale
- CJ Assessment Service expects 1-5 scale
- Resolution: Updated LLMComparisonResultV1.confidence to Field(None, ge=1.0, le=5.0) ensuring alignment

  Testing Architecture ✅

- Event Model Tests: 19 comprehensive tests covering validation, serialization, mutual exclusion, confidence ranges
- Enum Tests: 5 tests validating error code structure and inheritance
- Quality Gates: All tests pass typecheck (pdm run typecheck-all) and linting (pdm run lint-all)

  PHASE 2 IMPLEMENTATION REQUIREMENTS

  Sub-Phase 2.1: API Contract Updates (Required)

  File: services/llm_provider_service/api_models.py
  class LLMComparisonRequest(BaseModel):
      # Make callback_topic REQUIRED (no default, no Optional)
      callback_topic: str = Field(..., description="Kafka topic for result callback (required)")

  Sub-Phase 2.2: Event Publisher Infrastructure (Missing)

  File: services/llm_provider_service/protocols.py
  class LLMEventPublisherProtocol(Protocol):
      async def publish_to_topic(
          self, topic: str, envelope: EventEnvelope[Any], key: Optional[str] = None
      ) -> None: ...

  File: services/llm_provider_service/implementations/event_publisher_impl.py

- Implement publish_to_topic method using existing Kafka producer
- Handle serialization and error logging

  Sub-Phase 2.3: Remove Polling Infrastructure (Breaking Change)

  File: services/llm_provider_service/api/llm_routes.py (NOT comparison_routes.py)

- DELETE: @llm_bp.route("/status/<queue_id>", methods=["GET"])
- DELETE: @llm_bp.route("/results/<queue_id>", methods=["GET"])

  File: services/llm_provider_service/implementations/queue_processor_impl.py

- DELETE: _store_in_cache() method and Redis cache interactions
- DELETE: Result retrieval logic for polling

  Sub-Phase 2.4: Callback Publishing Implementation (Core Logic)

  Files:

- services/llm_provider_service/implementations/queue_processor_impl.py
- services/llm_provider_service/implementations/llm_orchestrator_impl.py

  Pattern: Replace cache storage with event publishing using LLMComparisonResultV1

# Success case

  callback_event = LLMComparisonResultV1(
      request_id=request.queue_id,
      correlation_id=request.correlation_id,
      winner=response.winner,
      confidence=response.confidence,  # 1-5 scale
      error_detail=None,
      # ... other fields
  )
  await self._publish_callback_event(callback_event, request.callback_topic)

  CRITICAL LESSONS FROM PHASE 1

  1. Confidence Score Architecture ⚠️

  CRITICAL: LLM Provider Service uses 1-5 confidence scale internally and for API responses. Any callback events MUST use 1-5 scale to maintain consistency with CJ
  Assessment Service expectations.

  2. Agent-Based Implementation Pattern ✅

  Use agents for focused sub-tasks: Each agent handles one specific file/functionality to maintain clarity and enable validation of each step.

  3. Quality Assurance Commands (From Root) ✅

  pdm run typecheck-all  # Type checking across entire codebase
  pdm run lint-all       # Linting with import pattern validation  
  pdm run format-all     # Code formatting

  4. Documentation Standards ✅

  Follow .cursor/rules/090-documentation-standards.mdc for task compression:

- Use "✅ COMPLETED" format for finished phases
- Hyper-technical language with code examples
- Maximum information density per token

  5. File Structure Reality Check ✅

  Actual file: services/llm_provider_service/api/llm_routes.py (NOT comparison_routes.py)
  Always verify file paths before making changes.

  AGENT INSTRUCTIONS

  Agent Alpha: API Contract Updates

  Mission: Make callback_topic required in LLMComparisonRequest and update queue models
  Focus: Remove Optional typing, add validation, update docstrings
  Files:

- services/llm_provider_service/api_models.py
- services/llm_provider_service/queue_models.py

  Agent Beta: Event Publisher Infrastructure

  Mission: Add missing publish_to_topic method to event publisher protocol and implementation
  Focus: Implement Kafka publishing with proper error handling and logging
  Files:

- services/llm_provider_service/protocols.py
- services/llm_provider_service/implementations/event_publisher_impl.py

  Agent Gamma: Polling Infrastructure Removal

  Mission: Delete polling endpoints and cache storage logic (breaking change)
  Focus: Remove routes, cache methods, ensure no polling code remains
  Files:

- services/llm_provider_service/api/llm_routes.py
- services/llm_provider_service/implementations/queue_processor_impl.py

  Agent Delta: Callback Publishing Implementation

  Mission: Implement callback event publishing in queue processor and orchestrator
  Focus: Replace cache storage with LLMComparisonResultV1 event publishing for both success and error cases
  Files:

- services/llm_provider_service/implementations/queue_processor_impl.py
- services/llm_provider_service/implementations/llm_orchestrator_impl.py

  Agent Echo: Validation & Quality Assurance

  Mission: Create comprehensive tests for callback functionality and run quality checks
  Focus: Unit tests, integration tests, typecheck/lint validation
  Files:

- services/llm_provider_service/tests/unit/test_callback_publishing.py
- Quality validation across all modified files

  SUCCESS CRITERIA

  Phase 2 Completion Requirements:

  1. All queued requests require callback_topic (no Optional, no defaults)
  2. Event publisher supports topic-specific publishing (publish_to_topic method implemented)
  3. Zero polling infrastructure remains (status/results endpoints deleted)
  4. Callback publishing functional (success and error cases publish LLMComparisonResultV1)
  5. All tests pass with comprehensive coverage of callback functionality
  6. Quality gates pass (typecheck-all, lint-all, format-all from root)

  Quality Gates:

- No breaking changes to existing 200 (immediate) response flow
- Callback events use correct 1-5 confidence scale
- Error handling uses structured ErrorDetail objects (not tuple returns)
- All correlation IDs preserved for tracing

  ARCHITECTURAL CONSTRAINTS

  DO NOT Change:

- Event models from Phase 1: LLMComparisonResultV1, TokenUsage, LLMErrorCode are final
- Confidence scale: Must remain 1-5 (matches CJ Assessment expectations)
- Exception-based error handling: Use HuleEduError and structured error factories
- 200 response flow: Immediate responses should continue working unchanged

  MUST Implement:

- Breaking change compliance: Remove ALL polling infrastructure without backwards compatibility
- Required callback topics: Every queued request MUST specify callback topic
- Structured error handling: Use raise_* functions from huleedu_service_libs.error_handling
- Proper event publishing: Use EventEnvelope[LLMComparisonResultV1] with correlation ID as key

  IMMEDIATE NEXT STEPS

  1. Deploy TodoWrite to track all sub-phases and ensure systematic progress
  2. Deploy ULTRATHINK agents in sequence: Alpha → Beta → Gamma → Delta → Echo
  3. Validate each sub-phase before proceeding to next (typecheck/lint after each)
  4. Update task documentation according to compression standards after completion
  5. Prepare for Phase 3: Integration testing and deployment readiness

  CONTEXT FILES REFERENCE

  Primary Task Document: /Users/olofs_mba/Documents/Repos/huledu-reboot/documentation/TASKS/TASK-LLM-01.md
  Service Implementation: /Users/olofs_mba/Documents/Repos/huledu-reboot/services/llm_provider_service/
  Platform Rules: /Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/ (Use index for navigation)
  Error Handling Library: /Users/olofs_mba/Documents/Repos/huledu-reboot/services/libs/huleedu_service_libs/error_handling/
  Common Core Events: /Users/olofs_mba/Documents/Repos/huledu-reboot/common_core/src/common_core/events/llm_provider_events.py

  Begin by deploying TodoWrite to plan Phase 2 sub-tasks, then systematically deploy ULTRATHINK agents to transform the service from polling-based to event-driven callback
   architecture while maintaining architectural integrity and the critical 1-5 confidence scale alignment.
