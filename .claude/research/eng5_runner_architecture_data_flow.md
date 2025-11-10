# ENG5 Runner & Essay Assessment Architecture

## 1. Assignment Management

### 1.1 Assignment Ownership Matrix

| Service | Responsibility | Persistent Tables | APIs / Contracts |
| --- | --- | --- | --- |
| CJ Assessment Service | Research-grade assignment contexts, anchor metadata, grade projection source of truth | `assessment_instructions`, `anchor_essay_references`, `cj_processed_essays`, `grade_projections` | Admin API `POST /admin/v1/assessment-instructions`, Anchor registration `POST /api/v1/anchors/register`, Kafka: `ELS_CJAssessmentRequestV1` |
| Class Management Service (CMS) | Teacher-managed classes, students, roster associations. No first-class assignments yet (tracks essay ownership via batch + student records) | `user_classes`, `students`, `essay_student_association` | HTTP blueprints `/v1/classes`, `/v1/students`, `/v1/batches` |
| Batch Orchestrator Service (BOS) | Batch context + canonical essay slots (ties `assignment_id` metadata to pipeline execution) | Internal persistence via repository (e.g., `batch_context`, `processing_pipeline_state`) | REST `POST /v1/batches/register`, Kafka `BatchEssaysRegistered`, pipeline coordination APIs |
| API Gateway Service | Authenticated façade that injects teacher identity and forwards batch + file commands downstream | No persistence (stateless proxy) | REST `/v1/batches/register`, `/v1/files/batch`, Kafka `ClientBatchPipelineRequestV1` |
| ENG5 Runner CLI | Research tooling that seeds CJ assignments and anchors | Local manifest only (no DB) | CLI `register-anchors`, `execute` commands posting to CJ service |

### 1.2 Assignment Creation Flows

1. **Research / ENG5 CLI path**
   - Operator runs `register-anchors` with `assignment_id` + corpus directory; CLI reads inventory and batches HTTP calls to CJ service anchor endpoint.@scripts/cj_experiments_runners/eng5_np/cli.py#60-108
   - CJ service validates `assignment_id` against `assessment_instructions`; if missing, operator first provisions instructions via admin API (grade scale is authoritative here).@services/cj_assessment_service/models_db.py#397-444
   - Anchors are ingested (see §2) and linked to the same `assignment_id` for subsequent batch preparation.

2. **Teacher Production path**
   - Teacher creates or selects coursework via front-end, which calls API Gateway. CMS persists class/student context; assignments are implied through batch metadata rather than a dedicated CMS table.@services/class_management_service/models_db.py#68-149
   - When teacher registers a batch, API Gateway proxies to BOS, enriching the payload with `user_id`/`org_id`.@services/api_gateway_service/routers/batch_routes.py#84-142
   - BOS stores batch context, generates CJ essay slots, and retains any `assignment_id` in the registration payload for later pipeline execution (see §4).@services/batch_orchestrator_service/implementations/batch_processing_service_impl.py#38-168

3. **Synchronization & Gaps**
   - Production `assignment_id` values originate from CMS UI but are surfaced only through batch registration metadata today—no automatic backfill into CJ `assessment_instructions`. Alignment requires either (a) admin tooling to mirror CMS assignments into CJ tables or (b) BOS enrichment that queries CMS on-demand when `assignment_id` is present.

## 2. Anchor Essay Storage Architecture

### 2.1 Storage Pattern

- **Blob storage:** Anchor documents (TXT/DOCX) and their extracted text live in Content Service, keyed by randomized storage IDs.@services/content_service/api/content_routes.py#21-75
- **Metadata:** CJ Assessment keeps only the reference (`text_storage_id`), grade, scale, and `assignment_id` in `anchor_essay_references`.@services/cj_assessment_service/models_db.py#426-444
- **Grade scale integrity:** `assessment_instructions` rows ensure `assignment_id` → `grade_scale` mapping, which anchor registration enforces to avoid mismatched grading contexts.@services/cj_assessment_service/models_db.py#397-444

### 2.2 Anchor Registration Flow

```mermaid
digraph AnchorFlow {
  CLI [label="ENG5 CLI\n(register-anchors)"]
  CJAPI [label="CJ Service\n/api/v1/anchors/register"]
  Content [label="Content Service\nPOST /v1/content"]
  CJDB [label="CJ DB\nanchor_essay_references"]

  CLI -> CJAPI [label="assignment_id, grade, file bytes"]
  CJAPI -> Content [label="store raw + extracted text"]
  Content -> CJAPI [label="storage_id"]
  CJAPI -> CJDB [label="assignment_id + storage_id"]
  CJDB -> CJAPI [label="grade scale resolved via assessment_instructions"]
}
```

1. CLI enumerates anchor files and posts multipart payloads to CJ endpoint with `assignment_id` and declared grade buckets.@scripts/cj_experiments_runners/eng5_np/cli.py#60-108
2. CJ service streams content to Content Service, acquiring storage IDs for raw text.@services/cj_assessment_service/cj_core_logic/batch_preparation.py#121-176
3. CJ writes an `AnchorEssayReference` row linking grade/scale to storage IDs, tied to the originating `assignment_id`.
4. Subsequent CJ batch preparation resolves anchors by `assignment_id` + `grade_scale`, fetching blobs from Content Service on demand.@services/cj_assessment_service/implementations/db_access_impl.py#545-579

## 3. Student Essay Storage Patterns

### 3.1 Path A – Teacher Upload via Product UI

1. Teacher submits files through UI → API Gateway `/v1/files/batch`, authenticated via JWT. Gateway validates form and forwards multipart data to File Service with identity headers and correlation ID.@services/api_gateway_service/routers/file_routes.py#38-479
2. File Service confirms batch mutability with BOS (`can_modify_batch_files`) to prevent mid-processing edits.@services/file_service/implementations/batch_state_validator.py#25-188
3. Files are:
   - Persisted as raw blobs in Content Service (`ContentType.RAW_UPLOAD_BLOB`).@services/file_service/core_logic.py#89-109
   - Run through extraction + validation; failures emit `EssayValidationFailedV1` for BOS/ELS reconciliation.@services/file_service/core_logic.py#178-289
   - Successful text stored as separate Content Service object and accompanied by `EssayContentProvisionedV1`.@services/file_service/core_logic.py#291-345
4. File Service records upload metadata (user, batch, storage IDs) and broadcasts thin `BatchFileAddedV1` for teacher notifications.@services/file_service/implementations/file_repository_impl.py#187-229@services/file_service/implementations/event_publisher_impl.py#142-191
5. Essay Lifecycle Service consumes provisioning events, allocating storage IDs to BOS-managed essay slots, updating `essay_states`, and projecting `BatchContentProvisioningCompletedV1` when inventories are satisfied.@services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py#62-333@services/essay_lifecycle_service/implementations/assignment_sql.py#24-134

### 3.2 Path B – ENG5 CLI Upload

1. CLI uploads student artifacts directly to Content Service (when preparing research batches) and bundles storage references into CJ request payloads.
2. CLI composes `ELS_CJAssessmentRequestV1` envelopes containing essay references and optional `assignment_id`; these are published to Kafka (or submitted via BOS in execute mode).@scripts/cj_experiments_runners/eng5_np/cli.py#238-384@libs/common_core/src/common_core/events/cj_assessment_events.py#106-132
3. CJ Assessment ingests essays, storing processed copies in `cj_processed_essays` (flags anchors vs student submissions) and attaches to CJ batch runs.@services/cj_assessment_service/models_db.py#100-134

### 3.3 Storage Comparison

| Aspect | Teacher Uploads (Production) | ENG5 CLI (Research) |
| --- | --- | --- |
| Entry Point | API Gateway `/v1/files/batch` | CLI direct to Content Service + CJ HTTP |
| Storage | Raw + text blobs in Content Service, metadata in File Service + Essay Lifecycle | Raw/text blobs in Content Service, metadata in CJ service tables |
| Ownership | Teacher identity enforced via JWT, BOS validates batch ownership | Research operator identity supplied manually; no CMS linkage |
| Eventing | `BatchFileAddedV1`, `EssayContentProvisionedV1` drive BOS/ELS orchestration | `ELS_CJAssessmentRequestV1` with embedded storage refs |
| Assignment Coupling | Batch registration may include `assignment_id` for grade projection | CLI requires explicit `assignment_id` to align with anchors |

### 3.4 Student Prompt Flow (Assignment vs Ad-hoc)

- **Unified storage path:** Teachers upload prompt text directly to Content Service, receiving a `storage_id` that populates `student_prompt_ref` during batch registration—identical for assignment-backed and ad-hoc batches.
- **Reference-only propagation:** BOS, ELS, NLP, and CJ Assessment pass the same `student_prompt_ref` reference, hydrating text from Content Service on demand; Result Aggregator persists only the reference for API responses.
- **Separation of concerns:** CJ’s `assessment_instructions` table continues to store judge guidance (anchors, grade scale); student prompts never live in CJ storage and remain orthogonal to `assignment_id` linkage.

## 4. Cross-Service Integration

### 4.1 Assignment ID Flow

```mermaid
graph LR
  CMS[Class Management
  (teacher UI)] -->|Course + class context| AGW
  AGW[API Gateway] -->|Batch registration
  (user_id, assignment_id)| BOS
  BOS -->|BatchEssaysRegistered
  (metadata includes assignment_id)| ELS[Essay Lifecycle Service]
  ELS -->|EssayContentProvisionedV1
  events| CJPrep[CJ Batch Prep]
  CJPrep -->|Fetch anchors, grade scale
  via assignment_id| CJDB[assessment_instructions +
  anchor_essay_references]
  Runner[ENG5 CLI] -->|register-anchors, CJ execute| CJPrep
```

- BOS includes `assignment_id` (when provided) in batch metadata and forwards it down to CJ requests, allowing CJ to resolve anchors and grade scales consistently.@services/batch_orchestrator_service/implementations/client_pipeline_request_handler.py#195-219
- Essay Lifecycle transports `assignment_id` implicitly through batch/essay state; when CJ pipeline executes, it uses the same identifier to fetch instructions and anchors, ensuring grade projection alignment.@services/cj_assessment_service/cj_core_logic/batch_preparation.py#52-176
- Research path bypasses CMS but still shares the `assignment_id` namespace, so naming collisions must be avoided or namespaced via conventions.

### 4.2 Data Ownership Boundaries

| Domain | Source of Truth | Notes |
| --- | --- | --- |
| Assignment metadata (grade scale, instructions) | CJ Assessment `assessment_instructions` | Required for any CJ run; CMS must integrate if production assignments need projections.@services/cj_assessment_service/models_db.py#397-444 |
| Class & roster management | CMS | Provides student identities used when associating essays to batches.@services/class_management_service/models_db.py#68-149 |
| Batch lifecycle and pipeline status | BOS + Essay Lifecycle | BOS tracks high-level phase states; ELS manages essay slot fulfillment.@services/batch_orchestrator_service/implementations/batch_processing_service_impl.py#38-168@services/essay_lifecycle_service/implementations/batch_coordination_handler_impl.py#62-333 |
| Anchor and essay content blobs | Content Service | Shared across research and production flows.@services/content_service/api/content_routes.py#21-75 |
| CJ scoring, grade projections | CJ Assessment | Stores processed essay artifacts, anchor metadata, grade projections.@services/cj_assessment_service/models_db.py#100-134@services/cj_assessment_service/models_db.py#446-479 |

## 5. Architectural Recommendations

1. **Assignment synchronisation:** Introduce a CMS → CJ sync job (or BOS hook) that creates/updates `assessment_instructions` whenever a production assignment is created, ensuring anchors and grade projections can be managed without manual admin calls.
2. **Namespace governance:** Establish a shared `assignment_id` schema (e.g., prefixed UUIDs) to avoid collisions between research and production pipelines, especially if ENG5 experiments run against live environments.
3. **Automated anchor provisioning:** Extend teacher tooling (or BOS) to surface anchor presence/health per `assignment_id`, pulling from `anchor_essay_references` to reduce reliance on CLI scripts.
4. **Content lineage tracking:** Persist Content Service storage IDs (raw + extracted) in CMS or BOS metadata to enable end-to-end auditing and simplify reprocessing scenarios.
5. **Observability alignment:** Ensure all services emit consistent metrics/tracing keyed by `assignment_id` so cross-service dashboards (BOS ↔ CJ ↔ ELS) can correlate runs quickly, especially during ENG5 phases.
