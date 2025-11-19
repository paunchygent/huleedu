Complete Pipeline Architecture Map: From Client Request to Completion

  Table of Contents

  1. #system-overview
  2. #current-flow-end-to-end
  3. #service-boundaries--integration-points
  4. #pipeline-state-management
  5. #critical-gaps--pain-points
  6. #recommended-solutions
  7. #pydantic-models-reference
  8. #validation-questions

  ---

  1. System Overview

  Core Services

- Client → API Gateway → Event-driven microservices
- BOS (Batch Orchestrator Service) - Pipeline coordinator
- BCS (Batch Conductor Service) - Dependency resolver
- ELS (Essay Lifecycle Service) - Essay state manager
- SMS (Student Matching Service) - Student validation
- Processing Services: Spellcheck, CJ Assessment, NLP

  Communication Patterns

  Synchronous:  Client ←→ API Gateway ←→ Internal Services
                BOS ←→ BCS (HTTP/REST)
  Asynchronous: Services ←→ Kafka ←→ Services
                Services → Outbox → Kafka

  ---

  2. Current Flow: End-to-End

  Phase 0: Batch Registration

  sequenceDiagram
      participant Client
      participant API Gateway
      participant BOS
      participant ELS

      Client->>API Gateway: POST /batches/register
      API Gateway->>BOS: BatchRegistrationRequestV1 (Kafka)
      Note over BOS: Create batch record<br/>Status: REGISTERED
      BOS->>ELS: InitiateBatchContentProvisioningCommandV1
      Note over ELS: Create essay records<br/>Preserve batch_id
      ELS-->>BOS: BatchContentProvisioningCompleted
      Note over BOS: Status: AWAITING_STUDENT_VALIDATION

  Files & Functions:

- services/batch_orchestrator_service/implementations/batch_registration_handler.py
- services/essay_lifecycle_service/implementations/batch_content_provisioning_handler.py:56-120

  Phase 1: Student Matching

  sequenceDiagram
      participant BOS
      participant SMS
      participant ELS

      BOS->>SMS: BatchStudentMatchingRequested
      Note over SMS: Validate & match students
      SMS-->>BOS: BatchStudentMatchingCompleted
      BOS->>ELS: BatchEssaysReady
      Note over BOS: Status: READY_FOR_PIPELINE_EXECUTION

  Files & Functions:

- services/batch_orchestrator_service/implementations/batch_student_matching_completed_handler.py
- services/student_matching_service/event_processor.py

  Phase 2: Pipeline Execution

  2.1 Pipeline Request & Resolution

  sequenceDiagram
      participant Client
      participant API Gateway
      participant BOS
      participant BCS

      Client->>API Gateway: POST /batches/{id}/pipelines/cj_assessment
      API Gateway->>BOS: ClientBatchPipelineRequestV1 (Kafka)

      Note over BOS: Check batch status == READY_FOR_PIPELINE_EXECUTION
      Note over BOS: Check !_has_active_pipeline(pipeline_state)

      BOS->>BCS: POST /internal/v1/pipelines/define
      Note over BCS: resolve_pipeline_dependencies()
      Note over BCS: prune_completed_steps() [CURRENTLY BROKEN]
      BCS-->>BOS: {final_pipeline: ["spellcheck", "cj_assessment"]}

      Note over BOS: Update pipeline_state in DB
      BOS->>ELS: BatchServiceSpellcheckInitiateCommandDataV1

  Files & Functions:

- services/batch_orchestrator_service/implementations/client_pipeline_request_handler.py:70-175
  - Line 135: Status check
  - Line 165: _has_active_pipeline() check
  - Line 194: BCS resolution call
- services/batch_conductor_service/implementations/pipeline_rules_impl.py:59-120
  - Line 111: prune_completed_steps() - NOT WORKING (no state)
- services/batch_orchestrator_service/implementations/client_pipeline_request_handler.py:349-369
  - _has_active_pipeline() implementation

  2.2 Phase Processing (Parallel)

  Spellcheck Branch:
  sequenceDiagram
      participant BOS
      participant ELS
      participant Spellcheck

      BOS->>ELS: BatchServiceSpellcheckInitiateCommandDataV1
      ELS->>Spellcheck: SpellcheckRequestedV1
      Spellcheck-->>ELS: SpellcheckCompletedV1
      ELS-->>BOS: ELSBatchPhaseOutcomeV1
      Note over ELS: phase: "spellcheck"<br/>outcome: "completed_successfully"<br/>correlation_id: ORIGINAL

  CJ Assessment Branch (Complex):
  sequenceDiagram
      participant BOS
      participant ELS
      participant CJ
      participant LLM Provider

      BOS->>ELS: BatchServiceCJAssessmentInitiateCommandDataV1
      Note over BOS: correlation_id: "352c49b0-4eb7-41f5-a561-c4686489a620"

      ELS->>CJ: ELS_CJAssessmentRequestV1
      Note over CJ: Store in batch.event_correlation_id

      CJ->>LLM Provider: Multiple LLMComparisonRequestV1
      Note over CJ: NEW correlation_id per request<br/>for callback tracking

      LLM Provider-->>CJ: LLMComparisonResultV1 callbacks
      Note over CJ: Match via request_correlation_id

      CJ-->>ELS: CJAssessmentCompletedV1
      Note over CJ: Use ORIGINAL correlation_id<br/>[FIXED: batch_callback_handler.py:469]

      ELS-->>BOS: ELSBatchPhaseOutcomeV1
      Note over ELS: phase: "cj_assessment"<br/>outcome: "completed_successfully"<br/>correlation_id: ORIGINAL

  Files & Functions:

- CJ Assessment correlation fix: services/cj_assessment_service/cj_core_logic/batch_callback_handler.py:466-479
- Batch preparation: services/cj_assessment_service/cj_core_logic/batch_preparation.py:26-77
- Individual tracking: services/cj_assessment_service/cj_core_logic/batch_submission_tracking.py:48

  2.3 Pipeline Completion

  sequenceDiagram
      participant BOS
      participant BCS
      participant Test/Client

      Note over BOS: Receive final ELSBatchPhaseOutcomeV1
      Note over BOS: Log: "Pipeline completed for batch"

      Note over BOS: MISSING: Publish BatchPipelineCompletedV1
      Note over BOS: MISSING: Report to BCS
      Note over BOS: MISSING: Clear active pipeline flags

      Test/Client-->>Test/Client: Timeout waiting for<br/>BatchPipelineCompletedV1

  Files & Functions:

- services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py:193-199
  - Line 195: "Pipeline completed" log
  - Line 198: TODO comment - MISSING IMPLEMENTATION

  ---

  3. Service Boundaries & Integration Points

  Event Boundaries (Kafka Topics)

  | Producer    | Event                             | Topic                                       | Consumer | Purpose            |
  |-------------|-----------------------------------|---------------------------------------------|----------|--------------------|
  | API Gateway | ClientBatchPipelineRequestV1      | huleedu.client.batch_pipeline_request.v1    | BOS      | Pipeline request   |
  | ELS         | BatchContentProvisioningCompleted | huleedu.els.batch.provisioning.completed.v1 | BOS      | Provisioning done  |
  | SMS         | BatchStudentMatchingCompleted     | huleedu.sms.batch.matching.completed.v1     | BOS      | Matching done      |
  | ELS         | BatchEssaysReady                  | huleedu.els.batch.essays_ready.v1           | BOS      | Ready for pipeline |
  | ELS         | ELSBatchPhaseOutcomeV1            | huleedu.els.batch_phase_outcome.v1          | BOS      | Phase completion   |
  | BOS         | BatchPipelineCompletedV1          | huleedu.bos.batch_pipeline_completed.v1     | NONE     | MISSING            |

  HTTP/REST Boundaries

  | Client | Endpoint                            | Server      | Purpose              | Status    |
  |--------|-------------------------------------|-------------|----------------------|-----------|
  | BOS    | POST /internal/v1/pipelines/define  | BCS         | Resolve dependencies | ✅ Working |
  | BOS    | POST /internal/v1/phases/complete   | BCS         | Report completion    | ❌ MISSING |
  | Client | POST /batches/{id}/pipelines/{name} | API Gateway | Request pipeline     | ✅ Working |

  Command Boundaries (Service-to-Service)

  | Sender | Command                                       | Receiver      | Via   | Purpose              |
  |--------|-----------------------------------------------|---------------|-------|----------------------|
  | BOS    | InitiateBatchContentProvisioningCommandV1     | ELS           | Kafka | Start provisioning   |
  | BOS    | BatchServiceSpellcheckInitiateCommandDataV1   | ELS           | Kafka | Start spellcheck     |
  | BOS    | BatchServiceCJAssessmentInitiateCommandDataV1 | ELS           | Kafka | Start CJ assessment  |
  | ELS    | ELS_CJAssessmentRequestV1                     | CJ Assessment | Kafka | Forward to processor |

  ---

  4. Pipeline State Management

  BOS Pipeline State (PostgreSQL)

  Location: services/batch_orchestrator_service/models_db.py

# Line 71: Stored as JSON in batches table

  pipeline_configuration: Mapped[dict | None] = mapped_column(JSON, nullable=True)

  Structure: ProcessingPipelineState (common_core/pipeline_models.py)
  {
      "batch_id": "866c63dd-0e4b-4d2a-ab36-cd62e5b07b02",
      "requested_pipelines": ["spellcheck", "cj_assessment"],
      "spellcheck": {
          "status": "COMPLETED",  # PipelineExecutionStatus enum
          "started_at": "2025-01-15T10:25:00Z",
          "completed_at": "2025-01-15T10:25:40Z"
      },
      "cj_assessment": {
          "status": "COMPLETED",
          "started_at": "2025-01-15T10:25:42Z",
          "completed_at": "2025-01-15T10:25:43Z"
      }
  }

  State Transitions:
  PENDING_DEPENDENCIES → DISPATCH_INITIATED → IN_PROGRESS → COMPLETED/FAILED

  Active Detection: client_pipeline_request_handler.py:349-369
  def_has_active_pipeline(self, pipeline_state: ProcessingPipelineState) -> bool:
      active_statuses = {
          PipelineExecutionStatus.IN_PROGRESS,
          PipelineExecutionStatus.DISPATCH_INITIATED,
      }
      # Returns True if ANY phase is active

  BCS State Repository (Redis + PostgreSQL)

  Location: services/batch_conductor_service/implementations/redis_batch_state_repository.py

  Redis Keys:
  bcs:essay_state:{batch_id}:{essay_id} → {completed_steps: [...]}
  bcs:batch_summary:{batch_id} → {step_name: {completed: N, total: M}}

  Current Status: ❌ NOT POPULATED - No service reports completions

  Intended Use:

# pipeline_rules_impl.py:111-120

  async def prune_completed_steps(self, pipeline_steps: list[str], batch_id: str):
      for step in pipeline_steps:
          is_complete = await self.batch_state_repository.is_batch_step_complete(batch_id, step)
          # Would skip completed steps if state existed

  ---

  5. Critical Gaps & Pain Points

  Gap 1: Missing Pipeline Completion Event

- Location: pipeline_phase_coordinator_impl.py:198
- Impact: Tests timeout, BCS can't track completion, Client has no confirmation
- Current: Logs "Pipeline completed" but does nothing
- Needed: Publish BatchPipelineCompletedV1 event

  Gap 2: BCS State Never Populated

- Location: No integration exists
- Impact: Can't skip completed phases, redundant processing
- Current: prune_completed_steps() always returns all phases
- Needed: BOS → BCS phase completion reporting

  Gap 3: Pipeline State Persistence

- Location: BOS pipeline_configuration
- Impact: Completed pipelines block new requests until cleared
- Current: State persists forever
- Needed: Clear active flags while preserving completion history

  Gap 4: Batch Status Management

- Question: Should batch status change during pipeline execution?
- Current: Remains READY_FOR_PIPELINE_EXECUTION
- Alternative: Transition to PROCESSING_PIPELINES?

  ---

  6. Recommended Solutions

  Solution 1: Implement Pipeline Completion Event

  File: services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py

# Replace lines 198-199

  async def _complete_pipeline(self, batch_id: str, correlation_id: UUID):
      """Complete pipeline and publish completion event."""

      # 1. Publish completion event
      completion_event = BatchPipelineCompletedV1(
          batch_id=batch_id,
          correlation_id=correlation_id,
          completed_phases=self.pipeline_state.requested_pipelines,
          pipeline_status="completed",
          timestamp=datetime.now(UTC)
      )
      await self.event_publisher.publish(
          topic="huleedu.bos.batch_pipeline_completed.v1",
          event=completion_event
      )

      # 2. Report to BCS (see Solution 2)
      await self._report_pipeline_completion_to_bcs(batch_id)

      # 3. Clear active pipeline flags (keep history)
      await self._archive_pipeline_session(batch_id, correlation_id)

  Solution 2: BOS → BCS Completion Reporting

  Add to BOS: services/batch_orchestrator_service/implementations/batch_conductor_client_impl.py
  async def report_phase_completion(
      self,
      batch_id: str,
      phase_name: PhaseName,
      status: str,
      essays_processed: int,
      metadata: dict | None = None
  ) -> bool:
      """Report phase completion to BCS for dependency tracking."""
      try:
          response = await self.http_session.post(
              f"{self.bcs_endpoint}/phases/complete",
              json={
                  "batch_id": batch_id,
                  "phase_name": phase_name.value,
                  "status": status,
                  "essays_processed": essays_processed,
                  "metadata": metadata
              }
          )
          return response.status == 200
      except Exception as e:
          logger.warning(f"Failed to report to BCS: {e}")
          return False

  Add to BCS: services/batch_conductor_service/api/pipeline_routes.py
  @pipeline_bp.route("/internal/v1/phases/complete", methods=["POST"])
  @inject
  async def record_phase_completion(
      batch_state_repo: FromDishka[BatchStateRepositoryProtocol]
  ):
      """Record phase completion for dependency resolution."""
      data = await request.get_json()

      # Update state repository
      for essay_id in get_batch_essays(data["batch_id"]):
          await batch_state_repo.record_essay_step_completion(
              batch_id=data["batch_id"],
              essay_id=essay_id,
              step_name=data["phase_name"],
              metadata=data.get("metadata")
          )

      return jsonify({"status": "recorded"}), 200

  Solution 3: Pipeline State Archival

  Add to BOS: services/batch_orchestrator_service/implementations/batch_repository_impl.py
  async def archive_pipeline_session(
      self,
      batch_id: str,
      session_id: UUID
  ) -> bool:
      """Archive completed pipeline session and clear active flags."""
      async with self.session() as session:
          batch = await session.get(Batch, batch_id)

          # Archive current state
          archived_session = {
              "session_id": str(session_id),
              "completed_at": datetime.now(UTC).isoformat(),
              "phases": batch.pipeline_configuration
          }

          # Add to history (new field needed)
          if not batch.pipeline_history:
              batch.pipeline_history = []
          batch.pipeline_history.append(archived_session)

          # Clear active flags but keep completed states
          for phase in batch.pipeline_configuration:
              if phase.status in ["COMPLETED", "FAILED"]:
                  # Keep for BCS dependency resolution
                  continue
              else:
                  # Clear active/pending states
                  phase.status = None

          await session.commit()
          return True

  ---

  7. Pydantic Models Reference

  Event Models

  | Model                        | Location                                   | Purpose          | Key Fields
                      |
  |------------------------------|--------------------------------------------|------------------|---------------------------------
  --------------------|
  | ClientBatchPipelineRequestV1 | common_core/events/client_commands.py      | Pipeline request | batch_id, requested_pipeline,
  client_correlation_id |
  | ELSBatchPhaseOutcomeV1       | common_core/events/phase_outcome_events.py | Phase completion | batch_id, phase, outcome,
  correlation_id            |
  | BatchPipelineCompletedV1     | common_core/events/pipeline_events.py      | Pipeline done    | batch_id, completed_phases,
  correlation_id          |
  | EventEnvelope[T]             | common_core/events/envelope.py             | Event wrapper    | event_id, correlation_id, data:
  T                   |

  State Models

  | Model                   | Location                       | Purpose        | Key Fields
           |
  |-------------------------|--------------------------------|----------------|----------------------------------------------------
  ---------|
  | ProcessingPipelineState | common_core/pipeline_models.py | Pipeline state | batch_id, requested_pipelines, {phase}:
  PipelineStateDetail |
  | PipelineStateDetail     | common_core/pipeline_models.py | Phase state    | status, started_at, completed_at
           |
  | PipelineExecutionStatus | common_core/pipeline_models.py | Status enum    | PENDING, IN_PROGRESS, COMPLETED, FAILED
           |
  | PhaseName               | common_core/pipeline_models.py | Phase enum     | SPELLCHECK, CJ_ASSESSMENT, NLP
           |

  API Models

  | Model                           | Location                              | Purpose      | Key Fields                       |
  |---------------------------------|---------------------------------------|--------------|----------------------------------|
  | BCSPipelineDefinitionRequestV1  | batch_conductor_service/api_models.py | BCS request  | batch_id, requested_pipeline     |
  | BCSPipelineDefinitionResponseV1 | batch_conductor_service/api_models.py | BCS response | final_pipeline, analysis_summary |

  ---

   8. Validation Questions (Revised)

  Critical Architecture Decisions

  1. Pipeline Completion Event Consumer
    - Who should consume BatchPipelineCompletedV1?
    - Should the client poll or subscribe to events?
    - Should API Gateway translate to REST webhook?
  2. Batch Status During Pipeline
    - Should batch status remain READY_FOR_PIPELINE_EXECUTION during processing?
    - How to handle concurrent pipeline requests for same batch?
    - Should we track "active pipeline session" separately from batch status?
  3. BCS State Authority
    - Is BCS the authoritative source for phase completion?
    - How to handle BCS downtime during phase completion?
    - Should BOS cache BCS state or always query fresh?
  4. Pipeline Composition Rules
    - Can pipelines run in parallel (e.g., NLP + AI Feedback simultaneously)?
    - Should certain pipelines block others?
    - How to handle pipeline dependencies (e.g., Spellcheck required before NLP)?
  5. Error Handling & Retries
    - What happens if BCS reporting fails?
    - Should pipeline continue without state tracking?
    - How to handle partial phase failures?
  6. Client Notification Pattern
    - How does client know pipeline is complete?
    - Polling? WebSocket? Webhook?
    - What's the expected latency for completion notification?

  Implementation Priority & Sequencing

  Given the CRITICAL need for multi-pipeline support with NLP integration happening NOW:

  Phase 1: Immediate (This Sprint)

  Goal: Enable NLP Pipeline without redundant Spellcheck execution

  1. Implement BOS → BCS phase completion reporting
    - Add report_phase_completion() to BOS
    - Add /internal/v1/phases/complete endpoint to BCS
    - Wire up in pipeline_phase_coordinator_impl.py
  2. Fix pipeline completion flow
    - Publish BatchPipelineCompletedV1 event
    - Clear active pipeline flags (preserve completed states)
    - Enable sequential pipeline requests
  3. Test NLP Pipeline integration
    - Verify Spellcheck deduplication works
    - Confirm pipeline state transitions
    - Validate correlation_id preservation

  Phase 2: Next Sprint

  Goal: Support AI Feedback Pipeline and complex compositions

  1. Implement Comprehensive Pipeline support
    - Define composite pipeline configurations
    - Support "NLP + AI Feedback" combination
    - Handle multi-phase dependencies
  2. Add pipeline session tracking
    - Track each pipeline request as a session
    - Maintain session history for debugging
    - Support pipeline composition queries
  3. Enhance BCS dependency resolution
    - Support complex dependency graphs
    - Handle conditional phases
    - Optimize redundant phase detection

  Phase 3: Future Enhancement

  Goal: Production-ready pipeline orchestration

  1. Advanced pipeline features
    - Parallel phase execution where possible
    - Pipeline templates and presets
    - Dynamic pipeline modification
  2. Observability & monitoring
    - Pipeline execution metrics
    - Phase performance tracking
    - Bottleneck identification

  Development & Testing Strategy

  1. Test Coverage Requirements
# Essential test scenarios for multi-pipeline support
- Run CJ Assessment → Run NLP (Spellcheck should be skipped)
- Run NLP → Run CJ Assessment (Both should execute)
- Run Comprehensive Pipeline (All phases in sequence)
- Pipeline failure recovery and retry
- Concurrent pipeline rejection
  2. Development Environment Validation
    - All containers must support hot-reload for rapid iteration
    - Integration tests must cover multi-pipeline scenarios
    - E2E tests must validate complete flow including BCS
  3. Code Quality Standards
    - No backwards compatibility code (YAGNI)
    - No migration logic (clean development)
    - Clear service boundaries (no cross-service DB access)
    - Explicit error handling (no silent failures)

  Technical Decisions Needed

  1. Pipeline Definition in pipelines.yaml
    - How to define the new NLP pipeline in services/batch_conductor_service/pipelines.yaml?
    - Should composite pipelines (e.g., "comprehensive") reference other pipelines or duplicate steps?
    - How to handle conditional dependencies (e.g., NLP requires spellcheck but not CJ assessment)?
  2. State Reporting Granularity
    - Should BOS report phase completion immediately or batch at pipeline end?
    - What metadata should accompany phase completion (essay count, processing time, errors)?
    - How to handle partial phase success (e.g., 25/27 essays succeeded)?
  3. Pipeline Session Identity
    - Should each pipeline request get a unique session_id separate from correlation_id?
    - How to query pipeline history (by batch_id, by session_id, or both)?
    - Where to store session metadata (start time, requester, configuration)?
  4. Active Pipeline Detection Enhancement
    - Should _has_active_pipeline() distinguish between different pipeline types?
    - Can we allow NLP pipeline while CJ Assessment is running (non-overlapping phases)?
    - How to handle pipeline preemption or cancellation?
  5. BCS State Repository Operations
    - The 7-day Redis TTL is set - is this appropriate for all environments?
    - Should completed states in PostgreSQL persist indefinitely or have retention policy?
    - How to handle cache invalidation when phases are re-run?
  6. Event Flow Optimization
    - Should BatchPipelineCompletedV1 include full pipeline results or just status?
    - Do we need separate events for pipeline started/progress/completed?
    - How to handle event ordering and potential out-of-sequence delivery?

  ---
  Summary

  Multi-pipeline support is NOT a nice-to-have but a CRITICAL requirement for current development. The system architecture already
  supports it, but key integrations are missing. The implementation must be completed immediately to support:

  1. NLP Pipeline (integrating NOW)
  2. AI Feedback Pipeline (coming soon)
  3. Comprehensive Pipeline (combining multiple processors)

  The priority is clear: implement Phase 1 immediately to unblock NLP integration, then rapidly iterate through Phase 2 to support
  the full vision of composable, intelligent pipeline orchestration.
