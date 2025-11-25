# CJ Assessment ENG5 / Real DB / Prompt Workflow Review (2025-11-25)

## Scope

- `services/cj_assessment_service/tests/integration/test_eng5_scale_flows.py`
- `services/cj_assessment_service/tests/integration/test_real_database_integration.py`
- `services/cj_assessment_service/tests/integration/test_student_prompt_workflow.py`
- `services/cj_assessment_service/cj_core_logic/grade_projector.py`
- `services/cj_assessment_service/cj_core_logic/workflow_continuation.py`
- `services/cj_assessment_service/cj_core_logic/batch_callback_handler.py`
- `services/cj_assessment_service/message_handlers/llm_callback_handler.py`
- `services/cj_assessment_service/event_processor.py`
- `services/cj_assessment_service/kafka_consumer.py`
- `services/cj_assessment_service/api/admin/student_prompts.py`
- `services/cj_assessment_service/tests/integration/callback_simulator.py`
- `services/cj_assessment_service/worker_main.py`

## Alignment With PR Root-Cause Analysis

- ENG5 scale tests now create instructions/anchors in a committed session and build batches via `SessionProviderProtocol`, matching the FK-visibility diagnosis and avoiding cross-session inconsistencies (`test_eng5_scale_flows.py`:54–69, 71–109, 110–185).
- A dedicated helper constructs `GradeProjector` with a real `ProjectionContextService` wired to `session_provider` + per-aggregate repositories in ENG5 and real-db tests, matching the DI contract and ensuring the correct grade scale is resolved from instructions (`test_eng5_scale_flows.py`:54–69; `test_real_database_integration.py`:164–203).
- `GradeProjector.__init__` now hard-requires `session_provider` and `ProjectionContextService`, and `calculate_projections` uses the injected session provider to store projections, matching the “no implicit defaults / explicit DI” intent (`grade_projector.py`:38–69, 162–172).
- Workflow continuation paths take an optional `grade_projector` parameter and raise explicitly if finalization is attempted without one; callback handlers and Kafka consumer thread the injected projector all the way through, consistent with the PR description that continuation/finalization must use DI-aligned projectors (`workflow_continuation.py`:111–125, 266–282; `batch_callback_handler.py`:135–163; `llm_callback_handler.py`:180–198; `event_processor.py`:90–103, 162–176, 198–210; `kafka_consumer.py`:32–36, 114–133, 120–137).
- The real DB lifecycle test now constructs a single projector instance for the request path, callback simulation, and final continuation, aligning with the stated goal of using one DI-consistent projector from request through finalization (`test_real_database_integration.py`:164–203, 226–241, 264–279).
- CallbackSimulator’s surface accepts a `GradeProjector` and passes it into `continue_cj_assessment_workflow`, so the test harness mirrors production DI instead of reconstructing projectors ad hoc (`callback_simulator.py`:53–67, 193–207).
- Student prompt workflow fixes match the root cause: the test seeds `AssessmentInstruction` and explicitly commits, and the admin upload endpoint calls `session.commit()` after `upsert_assessment_instruction`, ensuring prompt changes are visible across sessions and through the HTTP surface (`test_student_prompt_workflow.py`:95–107, 114–161; `student_prompts.py`:70–76, 113–125).
- `ContextBuilder` now resolves the grade scale from instructions when present and only falls back to `swedish_8_anchor` when no instruction exists, which, combined with test seeding of explicit ENG5 scales, is consistent with the PR’s goal of avoiding silent defaulting to the wrong scale (`context_builder.py`:98–116, 126–133, 145–159).

## Remaining Gaps / Risks

- `worker_main.py` still constructs `GradeProjector()` with no arguments, which no longer matches the constructor signature and will raise at runtime if this worker entrypoint is used; this contradicts the “all GradeProjector usage is DI-aligned” assumption from the PR (`worker_main.py`:243–247).
- There is an implicit assumption that all production traffic goes through the Kafka consumer wired via Dishka/`CJAssessmentKafkaConsumer`; if `worker_main.py` is used in any environment, it will bypass the DI-provided projector and fail early.
- Some legacy helpers and tests still import projectors directly, but the ones inspected now pass explicit mocks or DI-built instances; a broader grep confirms consistency but future edits should continue to avoid bare `GradeProjector()` construction outside DI (`tests/unit/test_event_processor_prompt_context.py`:92–135, 176–208; `tests/unit/test_cj_idempotency_failures.py`:104–147).

## Questions / Clarifications for Dev Team

- Can we formally deprecate or update `worker_main.py` to either construct `GradeProjector` via the Dishka container or delegate entirely to `CJAssessmentKafkaConsumer`, so there is a single, DI-consistent worker path?
- Are there any remaining deployment targets or scripts that invoke `worker_main.py` directly, or is the Kafka consumer entrypoint the only supported path in practice?
