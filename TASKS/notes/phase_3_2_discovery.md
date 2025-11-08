# Phase 3.2 – Prompt Architecture Discovery Notes (Updated 2025-11-08)

## Registration & Intake
- `services/api_gateway_service/routers/batch_routes.py:77-121` now accepts lean `ClientBatchRegistrationRequest` payloads with no prompt fields; teachers attach prompts later via BOS prompt payload union.
- `libs/common_core/src/common_core/api_models/batch_registration.py:31-88` exposes optional `student_prompt_ref: StorageReferenceMetadata | None`, keeping registration contracts compatible with both canonical assignments and CMS references.
- `services/batch_orchestrator_service/implementations/batch_processing_service_impl.py:118-166` persists `student_prompt_ref` inside the BOS batch context so downstream initiators inherit the Content Service reference without touching inline strings.

## Prompt Propagation Across Events
- `libs/common_core/src/common_core/events/batch_coordination_events.py:34-125` (BatchEssaysRegistered/Ready) and `libs/common_core/src/common_core/events/nlp_events.py:101-165` carry `student_prompt_ref`, ensuring ELS coordination never rehydrates prompt text.
- `libs/common_core/src/common_core/events/cj_assessment_events.py:103-170` and `libs/common_core/src/common_core/events/ai_feedback_events.py:35-73` expose the same reference so downstream services fetch prompt bodies locally.
- `services/essay_lifecycle_service/implementations/service_request_dispatcher.py:164-336` forwards `student_prompt_ref` to NLP/CJ dispatchers without legacy fallbacks—bridging logic was removed once consumers became reference-native.

## BOS → BCS Prompt Gating
- `services/batch_orchestrator_service/implementations/client_pipeline_request_handler.py:195-235` derives `prompt_attached` + `prompt_source` metadata from stored registration context or new prompt payloads before calling BCS.
- `services/batch_orchestrator_service/implementations/batch_conductor_client_impl.py:32-77` threads `batch_metadata` through `BCSPipelineDefinitionRequestV1`.
- `services/batch_conductor_service/implementations/pipeline_rules_impl.py:180-235` blocks prompt-dependent phases unless `batch_metadata["prompt_attached"]` is truthy and records `prompt_prerequisite_blocked_total`.

## Content Service Integration
- `libs/huleedu_service_libs/src/huleedu_service_libs/http_client/content_service_client.py:22-182` remains the single entry point for fetching prompt blobs by `StorageReferenceMetadata`.
- NLP and CJ services hydrate prompts locally and expose `huleedu_{nlp|cj}_prompt_fetch_failures_total` metrics to trace failures (`services/nlp_service/command_handlers/batch_nlp_analysis_handler.py:60-210`, `services/cj_assessment_service/workflows/batch_preparation.py:48-160`).
- `services/essay_lifecycle_service/implementations/batch_expectation.py:17-46` now stores only `student_prompt_ref` in `BatchExpectation`; the legacy `essay_instructions` column has been dropped via Alembic migration `services/essay_lifecycle_service/alembic/versions/20251106_2105_remove_essay_instructions.py`.

## Validation Snapshot (2025-11-08)
- Unit/contract coverage now enforces reference-based payloads:
  - `pdm run pytest-root services/api_gateway_service/tests/test_batch_registration_proxy.py`
  - `pdm run pytest-root services/batch_orchestrator_service/tests -k "prompt or idempotency or batch_context"`
- Updated fixtures no longer pass `essay_instructions`, so regressions in prompt plumbing will surface immediately.

## Remaining Notes
- AI Feedback, NLP, and CJ services all consume `student_prompt_ref`; Result Aggregator fixtures are scheduled to flip once AI Feedback functional tests adopt the new metadata (tracked in child plan).
- Prompt metadata now lives exclusively in Content Service references or `batch_metadata`, eliminating inline prompt strings across BOS/ELS.
