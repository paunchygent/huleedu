---
id: "039-results-retrieval-flow"
type: "workflow"
scope: "cross-service"
title: "Results Retrieval and Aggregation Flow"
category: "workflow"
priority: "high"
applies_to: "all"
created: "2025-11-27"
last_updated: "2025-11-27"
---

# Results Retrieval and Aggregation Flow (FLOW-06)

**Purpose:** Assessment result collection, aggregation, and client retrieval
**Scope:** Cross-service result aggregation from CJ Assessment to client dashboards via RAS

## Core Principles

- **Thin vs Rich Event Separation**: State tracking (ELS) vs business data (RAS)
- **Direct Publishing**: Assessment services publish results directly to RAS
- **Materialized Views**: RAS maintains queryable aggregation of all processing phases
- **Event-Driven + WebSocket**: Real-time updates via event projection, NOT polling

## Event Flow Architecture

```
CJ Assessment Service
        ↓
    [Assessment Complete]
        ↓
    ┌───────┴────────┐
    ↓                ↓
[Thin Event]    [Rich Event]
    ↓                ↓
   ELS              RAS
    ↓                ↓
[State Update]  [Store Results]
                     ↓
            [All Phases Complete?]
                     ↓
              [Aggregate Results]
                     ↓
         BatchResultsReadyV1
                ↓
        ┌───────┴───────┐
        ↓               ↓
  Notification      WebSocket
   Projector         Service
        ↓               ↓
  Email Queue    Dashboard Update
```

## Thin vs Rich Event Pattern

Assessment services publish TWO events simultaneously:

| Event Type | Consumer | Purpose | Content |
|------------|----------|---------|---------|
| **Thin Event** | ELS | Workflow orchestration | Essay IDs, counts, status |
| **Rich Event** | RAS | Business data storage | Scores, grades, metrics, confidence |

Both events share same `correlation_id` for traceability.

## Service Responsibilities

### CJ Assessment Service
- Performs comparative judgment assessment
- Dual publishes: `CJAssessmentCompletedV1` (thin) + `AssessmentResultV1` (rich)
- Includes `assignment_id` for grade projection context

### Result Aggregator Service (RAS)
- Consumes rich events from all assessment services
- Stores results in `batch_results` and `essay_results` tables
- Publishes `BatchResultsReadyV1` when all phases complete
- Exposes REST query API (`/internal/v1/batches/...`)
- Invokes NotificationProjector directly (no Kafka round-trip)

### Essay Lifecycle Service (ELS)
- Consumes thin events only
- Updates essay state: `CONTENT_ASSIGNED` → `ASSESSED`
- Does NOT store or parse business data

### WebSocket Service
- Subscribes to `BatchResultsReadyV1`
- Pushes real-time updates to connected clients

## Key Events

| Event | Publisher | Consumer | Topic |
|-------|-----------|----------|-------|
| `CJAssessmentCompletedV1` | CJ Assessment | ELS | `huleedu.cj_assessment.completed.v1` |
| `AssessmentResultV1` | CJ Assessment | RAS | `huleedu.cj_assessment.result.published.v1` |
| `BatchResultsReadyV1` | RAS | WebSocket, Notifications | `huleedu.batch.results.ready.v1` |

## Query API (RAS)

**Base**: `/internal/v1` (requires `X-Internal-API-Key`, `X-Service-ID`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/batches/{batch_id}/status` | GET | Full batch status with essays |
| `/batches/user/{user_id}` | GET | Paginated user batches |

## Critical Constraints

1. **ELS never stores rich data** - only state transitions
2. **RAS is source of truth** for assessment results
3. **Notification uses direct invocation** - no Kafka round-trip for email projection
4. **WebSocket for real-time** - clients don't poll RAS
5. **Redis idempotency** - 24-hour TTL on `ras:idempotency:{event_id}`
6. **Cache invalidation** - atomic invalidation on result updates

## Failure Handling

- **Partial failures**: Successful essays stored, failed tracked in `processing_summary`
- **Kafka unavailable**: Transactional outbox with event relay
- **Cache miss**: Fail-open pattern, serve from database

## Performance Targets

- Event processing: <100ms
- Query response (cached): <200ms
- Query response (uncached): <500ms
- Cache hit rate: >80%

## Key Files

**Event Contracts:**
- `libs/common_core/src/common_core/events/cj_assessment_events.py`
- `libs/common_core/src/common_core/events/batch_events.py`

**Service Implementation:**
- `services/result_aggregator_service/README.md`
- `services/cj_assessment_service/README.md`

**Related Rules:**
- `037-phase2-processing-flow.md` - Phase 2 CJ assessment flow
- `042.1-transactional-outbox-pattern.md` - Outbox pattern
- `048-structured-error-handling-standards.md` - Error handling

**Operational:**
- `docs/operations/cj-assessment-foundation.md` - Debugging and troubleshooting
