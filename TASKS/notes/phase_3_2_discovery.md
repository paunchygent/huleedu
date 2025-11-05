# Phase 3.2 – Prompt Architecture Discovery Notes

## Registration Payloads
- `services/api_gateway_service/routers/batch_routes.py:62-112` defines `ClientBatchRegistrationRequest` with required `essay_instructions: str` and no `assignment_id`; the gateway forwards this field unchanged to BOS via `BatchRegistrationRequestV1`.  
- `libs/common_core/src/common_core/api_models/batch_registration.py:15-96` keeps `essay_instructions` mandatory in the shared contract, enforcing non-empty text.  
- `services/batch_orchestrator_service/implementations/batch_processing_service_impl.py:129-168` persists the registration context and emits `BatchEssaysRegistered` events that embed `essay_instructions` directly.  
- BOS stores the full `BatchRegistrationRequestV1` in-memory (and in future persistence) via `store_batch_context`, so downstream initiators read the raw prompt string (e.g., `services/batch_orchestrator_service/implementations/nlp_initiator_impl.py:86-110`).

## Event Contracts Propagating Prompts
- `libs/common_core/src/common_core/events/batch_coordination_events.py:33-119` carries `essay_instructions` in both `BatchEssaysRegistered` and `BatchEssaysReady`, so ELS mirrors the inline prompt through coordination events.  
- `libs/common_core/src/common_core/events/nlp_events.py:100-134` (BatchNlpProcessingRequestedV2) and `libs/common_core/src/common_core/events/ai_feedback_events.py:34-72` require `essay_instructions` strings in their payloads.  
- `libs/common_core/src/common_core/events/cj_assessment_events.py:102-124` mandates `essay_instructions` on `ELS_CJAssessmentRequestV1` alongside optional `assignment_id`, coupling CJ dispatch to inline text.

## Essay Lifecycle Usage
- `services/essay_lifecycle_service/implementations/batch_expectation.py:17-36` stores the prompt as part of the immutable `BatchExpectation`, so readiness tracking assumes BOS-supplied text.  
- Dispatchers in ELS pass the same string into downstream command handlers (e.g., `services/essay_lifecycle_service/implementations/service_request_dispatcher.py:169-334`), reinforcing the expectation of inline instructions.

## Downstream Consumers
- NLP service attaches instructions to its outbox metadata when provided (`services/nlp_service/implementations/event_publisher_impl.py:202-244`).  
- AI Feedback contracts require the raw string inside `AIFeedbackInputDataV1` (`libs/common_core/src/common_core/events/ai_feedback_events.py:34-72`).  
- CJ batch preparation presently reads `essay_instructions` off the BOS request payload when seeding jobs (`services/cj_assessment_service/cj_core_logic/batch_preparation.py:51-73`).

## BCS Dependency Resolution Baseline
- `services/batch_conductor_service/implementations/pipeline_rules_impl.py:34-220` only enforces topological dependencies and relies on `BatchStateRepositoryProtocol.is_batch_step_complete` to gate execution; there is no prompt-aware metadata today.  
- Batch state persistence tracks phase completion in Redis/PostgreSQL (`services/batch_conductor_service/implementations/redis_batch_state_repository.py:240-360`, `services/batch_conductor_service/implementations/postgres_batch_state_repository.py:86-180`), but they store per-step completion booleans—not arbitrary batch metadata—so a new `prompt_attached` flag would need an explicit storage path (e.g., dedicated Redis hash/JSON or BOS-provided metadata projection).  
- BCS ingests thin completion events via `services/batch_conductor_service/kafka_consumer.py:20-200` and never calls BOS for registration context, so any prompt-attachment signal must be carried with the pipeline request (or an equivalent pre-populated cache).

## Content Service Reference Patterns
- Shared client `libs/huleedu_service_libs/src/huleedu_service_libs/http_client/content_service_client.py:22-182` performs unauthenticated POST/GET calls (headers default to `None`) and returns `storage_id` strings for stored blobs.  
- The Content Service REST API (`services/content_service/api/content_routes.py:17-148`) exposes `POST /v1/content` and `GET /v1/content/{storage_id}` without additional auth layers; validation is limited to payload presence and hex-format storage IDs.  
- `StorageReferenceMetadata` in `libs/common_core/src/common_core/metadata_models.py:31-78` is the canonical structure for passing Content Service references downstream, reinforcing that prompt payloads should move to reference dictionaries keyed by `ContentType`.

## Prompt Architecture Plan (Prototype)
- **BOS → BCS gating**  
  - Extend `BCSPipelineDefinitionRequestV1` with a `batch_metadata` object (e.g., `{ "prompt_attached": true, "prompt_source": "cms" | "canonical" }`).  
  - `ClientPipelineRequestHandler` computes that metadata from the stored `BatchRegistrationRequestV1` before calling `BatchConductorClient.resolve_pipeline`.  
  - `DefaultPipelineResolutionService` forwards the metadata into `pipeline_rules.validate_pipeline_compatibility`, which blocks prompt-dependent phases when `prompt_attached` is missing or false via the existing `raise_pipeline_compatibility_failed` path.  
  - Keeps BCS stateless for prompt artefacts while still enforcing invariants even if BOS caller logic misses checks.

- **Prompt payload switch (hard cutover)**  
  - Replace every `essay_instructions: str` field with a reference-based structure (e.g., `student_prompt_ref: StorageReferenceMetadata | None`) across Gateway DTOs, BOS storage, ELS coordination events, and downstream service contracts (NLP, AI Feedback, CJ).  
  - Consumers fetch prompt text from Content Service on demand; remove legacy branches that expect inline strings to maintain coherence in the prototype.  
  - Document the reference-only contract in service READMEs/ADR so future contributors do not reintroduce inline prompts.

- **Discarded alternative**  
  - Persisting prompt flags or prompt blobs inside BCS repositories would require new endpoints and introduce unnecessary coordination complexity for a prototype; the metadata-in-request approach is leaner and keeps responsibilities clear.
## Contract Update Checklist
- Gateway DTO → drop essay_instructions, keep prompt union {assignment_id|cms_prompt_ref}
- BatchRegistrationRequestV1 → remove essay_instructions, optionally add student_prompt_ref reference slot
- BatchProcessingServiceImpl → populate BatchEssaysRegistered.student_prompt_ref and include in processing_metadata
- BatchEssaysRegistered/BatchEssaysReady events → replace essay_instructions with student_prompt_ref: StorageReferenceMetadata
- BOS pipeline request model → include PipelinePromptPayload union enforcing assignment vs cms reference
- BCSPipelineDefinitionRequestV1 → add batch_metadata (prompt_attached, prompt_source)
- BatchConductorClientImpl → POST batch_metadata alongside batch_id/requested_pipeline
- DefaultPipelineRules.validate_pipeline_compatibility → deny prompt-dependent phases when prompt_attached is false
- BatchExpectation & ELS dispatchers → store/forward student_prompt_ref instead of strings
- NLP, AI Feedback, CJ services → fetch prompt text via ContentServiceClient using reference, drop inline handling
- CMS prompt APIs → accept/return StorageReferenceMetadata, persist hash + storage_id
- Documentation → update sample payloads + ADR for reference-only prompts
