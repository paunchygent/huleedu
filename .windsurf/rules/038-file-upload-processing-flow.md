---
id: "038-file-upload-processing-flow"
type: "workflow"
scope: "cross-service"
title: "File Upload Processing Flow"
category: "workflow"
priority: "high"
applies_to: "all"
created: "2025-11-27"
last_updated: "2025-11-27"
---

# File Upload Processing Flow (FLOW-05)

**Purpose:** Client file upload to essay slot assignment and content provisioning
**Scope:** Cross-service processing from File Service through Content Service to ELS

## Core Principles

- **Pre-emptive Raw Storage**: All uploaded files stored as immutable raw blobs before processing
- **Validation-First**: Content validation occurs before slot assignment
- **Idempotent Operations**: File processing handles duplicate uploads gracefully
- **Traceability**: `file_upload_id` tracks individual files through entire pipeline

## Event Flow Architecture

```
Client → API Gateway → File Service → Content Service
                            ↓              ↓
                      [Raw Storage]  [Text Storage]
                            ↓
                       [Validation]
                            ↓
                    ┌───────┴────────┐
                    ↓                ↓
            [Success Path]    [Failure Path]
                    ↓                ↓
    EssayContentProvisionedV1  EssayValidationFailedV1
                    ↓                ↓
                   ELS              ELS
                    ↓                ↓
           [Slot Assignment]   [Adjust Expectations]
                    ↓
         EssaySlotAssignedV1
                    ↓
         [All Slots Filled?]
                    ↓
    BatchContentProvisioningCompletedV1
                    ↓
                   BOS
                    ↓
         ┌──────────┴──────────┐
         ↓                     ↓
    [GUEST Path]         [REGULAR Path]
         ↓                     ↓
  Direct Readiness      Student Matching
```

## Service Responsibilities

### File Service
- Receives multipart file uploads
- Stores raw file immediately (pre-emptive pattern)
- Extracts text via Strategy Pattern (Txt, Docx, Pdf)
- Validates extracted text (length constraints)
- Stores validated text in Content Service
- Publishes success/failure events via transactional outbox

### Content Service
- Blob storage/retrieval for raw files and extracted text
- UUID-based flat file storage
- No business logic, opaque blob handling

### Essay Lifecycle Service (ELS)
- Receives `EssayContentProvisionedV1` events
- Assigns content to pre-allocated essay slots
- Publishes `EssaySlotAssignedV1` (maps `file_upload_id` → `essay_id`)
- Tracks completion: `provisioned_count` vs `expected_essay_count`
- Publishes `BatchContentProvisioningCompletedV1` when complete

### Batch Orchestrator Service (BOS)
- Receives `BatchContentProvisioningCompletedV1`
- Routes based on `class_id`:
  - **GUEST** (`class_id = null`): Direct to `READY_FOR_PIPELINE_EXECUTION`
  - **REGULAR** (`class_id != null`): Initiate Phase 1 student matching

## Key Events

| Event | Publisher | Consumer | Topic |
|-------|-----------|----------|-------|
| `EssayContentProvisionedV1` | File Service | ELS | `huleedu.file.essay.content.provisioned.v1` |
| `EssayValidationFailedV1` | File Service | ELS | `huleedu.file.essay.validation.failed.v1` |
| `EssaySlotAssignedV1` | ELS | Clients | `huleedu.els.essay.slot.assigned.v1` |
| `BatchContentProvisioningCompletedV1` | ELS | BOS | `huleedu.els.batch.content.provisioning.completed.v1` |

## Validation Error Codes

- `EMPTY_CONTENT`: Whitespace-only or empty text
- `CONTENT_TOO_SHORT`: Below MIN_CONTENT_LENGTH (50 chars)
- `CONTENT_TOO_LONG`: Above MAX_CONTENT_LENGTH (50,000 chars)
- `ENCRYPTED_FILE_UNSUPPORTED`: Encrypted PDF files
- `CORRUPTED_FILE`: Malformed files
- `UNSUPPORTED_FILE_TYPE`: Unknown extension
- `TEXT_EXTRACTION_FAILED`: Technical extraction failure

## GUEST vs REGULAR Batch Handling

| Batch Type | `class_id` | After Content Complete | Next Phase |
|------------|------------|------------------------|------------|
| GUEST | `null` | Direct to pipeline | Phase 2 |
| REGULAR | set | Student matching | Phase 1 |

## Failure Handling

- **Partial failures**: Success/failure events per file, ELS adjusts expectations
- **Excess uploads**: First N assigned, excess triggers `ExcessContentProvisionedV1`
- **Service unavailability**: Transactional outbox ensures event delivery
- **Idempotency**: ELS handles duplicate events gracefully

## Performance Targets

- File upload throughput: 10 concurrent per batch
- Text extraction: <500ms per file
- Slot assignment: <50ms per essay
- Maximum file size: 10MB
- Maximum batch size: 100 essays

## Key Files

**Event Contracts:**
- `libs/common_core/src/common_core/events/file_events.py`
- `libs/common_core/src/common_core/events/els_events.py`

**Service Implementation:**
- `services/file_service/README.md`
- `services/essay_lifecycle_service/README.md`
- `services/content_service/README.md`

**Related Rules:**
- `036-phase1-processing-flow.md` - Student matching (REGULAR batches)
- `037-phase2-processing-flow.md` - Pipeline execution
- `042.1-transactional-outbox-pattern.md` - Outbox pattern
