---
type: epic
id: EPIC-002
title: Teacher Dashboard
status: draft
phase: 2
sprint_target: TBD
created: 2025-11-27
last_updated: 2025-11-27
---

# EPIC-002: Teacher Dashboard

## Summary

Deliver a web interface for teachers to submit essays for CJ Assessment, monitor processing status, and view comparative judgment results. Built on existing backend services with real-time updates via WebSocket Service.

**Business Value**: Transforms CJ Assessment backend into accessible teacher-facing product.

**Scope Boundaries**:
- **In Scope**: Batch submission, file upload, processing status, CJ results display
- **Out of Scope**: LMS integration, full analytics dashboards, mobile UI, AI Feedback UI

## User Stories

### US-002.1: Batch Submission
**As a** teacher
**I want to** create a new batch for essay assessment
**So that** I can submit student work for comparative judgment.

**Acceptance Criteria**:
- [ ] Create batch via form (title, class selection)
- [ ] Batch created in BOS via API Gateway
- [ ] Batch ID returned for file uploads

### US-002.2: Essay File Upload
**As a** teacher
**I want to** upload essay files (PDF/DOCX/TXT) for a batch
**So that** student work enters the assessment pipeline.

**Acceptance Criteria**:
- [ ] Drag-and-drop or file picker upload
- [ ] Progress indicator per file
- [ ] Files processed via File Service → Content Service → ELS
- [ ] Essay list updates as files are processed

### US-002.3: Processing Status
**As a** teacher
**I want to** see real-time progress of my batch
**So that** I know when assessment is complete.

**Acceptance Criteria**:
- [ ] Batch list shows status (pending, processing, completed)
- [ ] Detail view shows phase progress (upload → spellcheck → CJ rounds)
- [ ] WebSocket updates status within 2 seconds of backend events

### US-002.4: CJ Results Viewing
**As a** teacher
**I want to** view comparative judgment rankings
**So that** I can see how student essays compare.

**Acceptance Criteria**:
- [ ] Results page shows essay rankings with scores
- [ ] Click essay to view details (content, spellcheck results)
- [ ] Data sourced from Result Aggregator Service

## Technical Architecture

### Existing Services (Backend)
- **API Gateway**: `services/api_gateway_service/` - REST endpoints
- **WebSocket Service**: `services/websocket_service/` - Real-time events
- **Result Aggregator Service**: `services/result_aggregator_service/` - Query materialized views
- **File Service**: `services/file_service/` - Upload handling
- **BOS**: `services/batch_orchestrator_service/` - Batch/pipeline management

### Frontend (To Be Created)
- **Stack**: Vue 3 + Vite + TypeScript + Tailwind CSS
- **Location**: `frontend/teacher-dashboard/`
- **API Client**: Generated from OpenAPI spec
- **Real-time**: WebSocket connection to WebSocket Service

### Data Flows
```
Teacher UI → API Gateway → BOS (batch creation)
Teacher UI → API Gateway → File Service (upload)
File Service → ELS → Processing Pipeline → RAS (results)
RAS → WebSocket Service → Teacher UI (status updates)
Teacher UI → API Gateway → RAS (query results)
```

## Dependencies

- EPIC-001: Identity & Access (authentication)
- API Gateway REST endpoints operational
- WebSocket Service broadcasting essay/batch events
- RAS materialized views populated

## Notes

- Initial focus on CJ Assessment results only
- NLP metrics and AI Feedback UI deferred to separate epics
- Desktop-first; mobile responsiveness deferred
- Class management UI uses existing Class Management Service endpoints
