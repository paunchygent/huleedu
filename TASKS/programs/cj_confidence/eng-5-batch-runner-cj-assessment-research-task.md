---
id: eng-5-batch-runner-cj-assessment-research-task
title: ENG5 Runner & Essay Assessment Architecture
type: task
status: proposed
priority: medium
domain: programs
service: ''
owner_team: agents
owner: ''
program: cj_confidence
created: '2025-11-10'
last_updated: '2026-02-01'
related: []
labels: []
---
Context: What We've Completed

  We've fixed two critical issues with the ENG5 NP runner:

  1. CJ Service Connection: Fixed port configuration (9095→9090) in docker-compose.eng5-runner.yml
  2. CLI Requirements: Made assignment_id and course_id required parameters and documented the anchor registration workflow

  Documentation Created:

- scripts/cj_experiments_runners/eng5_np/ASSIGNMENT_SETUP.md - Assignment setup workflow
- scripts/cj_experiments_runners/eng5_np/ANCHOR_REGISTRATION_EXAMPLE.md - Practical anchor registration example

  TASK: Research & Document Complete Data Flow Architecture

  Critical Questions Requiring Investigation

  1. Assignment Creation & Ownership

  Question: Who owns assignment records and where are they created?

  Current Understanding:

- CJ Assessment Service has assessment_instructions table (stores assignment_id, grade_scale, instructions text)
- Admin API endpoint: POST /admin/v1/assessment-instructions
- CLI uses this to create assignment contexts

  INVESTIGATE:

- Does Class Management Service (CMS) also have assignment records?
- What's the relationship between CJ's assessment_instructions and CMS's assignment model?
- For teacher-created assignments via API Gateway, which service is the source of truth?
- Do we need cross-service synchronization or are these separate domains?
- Check: services/class_management_service/models_db.py for assignment models
- Check: Assignment creation flow through API Gateway → Batch Orchestrator → CMS
- Document ownership boundaries: Research data (CJ) vs Production assignments (CMS)

  Key Files to Investigate:
  services/class_management_service/models_db.py
  services/class_management_service/api/
  services/batch_orchestrator_service/
  services/api_gateway_service/
  libs/common_core/src/common_core/events/

  2. Anchor Essay Storage Architecture

  Question: Where and how are anchor essays stored (blob vs database)?

  Current Understanding:

- Content stored in Content Service (blob storage)
- References in CJ Assessment Service anchor_essay_references table
- Schema:
  anchor_essay_references (
    id, assignment_id, grade, grade_scale,
    text_storage_id,  -- Points to Content Service
    created_at
  )

  VALIDATE:

- Content Service stores actual essay text as blobs (confirm implementation)
- CJ Assessment stores only metadata + text_storage_id reference (confirm)
- Is this architecture consistent with other essay storage patterns?
- Check Content Service implementation: services/content_service/
- Verify storage ID format and retrieval mechanism
- Document: Anchor essay = Reference in CJ DB + Blob in Content Service

  Key Files to Investigate:
  services/content_service/models_db.py
  services/content_service/api/
  services/cj_assessment_service/models_db.py (AnchorEssayReference)
  services/cj_assessment_service/implementations/db_access_impl.py

  3. Student Essay Storage: Multiple Paths

  Question: How are student essays stored when uploaded via different paths?

  Path A: User Upload via API Gateway (Production)
  User → API Gateway → Batch Orchestrator → ??? → Storage

  Path B: CLI Upload (Research/Testing)
  ENG5 Runner CLI → Content Service → CJ Assessment Service

  INVESTIGATE:

- Path A (User Uploads):
  - Trace complete flow: API Gateway → Batch Orchestrator → File Service?
  - Does File Service store essays or delegate to Content Service?
  - Where does Essay Lifecycle Service fit?
  - What's CMS's role in user essay uploads?
  - Which service creates the essay records?
  - Database tables: Where are user essays tracked?
- Path B (CLI Uploads):
  - Currently: CLI → Content Service (confirmed)
  - Does CLI create records in any other service?
  - How do CLI-uploaded essays integrate with CMS/Batch Orchestrator?
- Cross-Path Questions:
  - Are these two separate flows or should they converge?
  - Should CLI uploads create CMS records?
  - How do we prevent duplicate storage?
  - What's the relationship between cj_processed_essays and other essay tables?

  Key Files to Investigate:
  services/api_gateway_service/
  services/batch_orchestrator_service/
  services/file_service/
  services/essay_lifecycle_service/
  services/class_management_service/ (student-essay associations)
  services/content_service/
  services/cj_assessment_service/models_db.py (ProcessedEssay)

  4. Assignment_ID Flow Across Services

  Question: How do assignment_id values propagate through the system?

  TRACE:

- Teacher creates assignment in CMS → assignment_id generated
- Teacher uploads essays for assignment → how is assignment_id linked?
- Batch Orchestrator triggers CJ assessment → how is assignment_id passed?
- CJ Assessment loads anchors → queries by assignment_id
- CLI creates assignment via admin API → same assignment_id space?
- Are research assignments (CLI) separate from production assignments (CMS)?

  Required Deliverable

  Create: .claude/research/eng5_runner_architecture_data_flow.md

  Structure:

# ENG5 Runner & Essay Assessment Architecture

## 1. Assignment Management

### Assignment Ownership Matrix

  | Service | Responsibility | Tables | API Endpoints |
  |---------|---------------|--------|---------------|
  | CJ Assessment Service | Research assignment contexts | assessment_instructions | POST /admin/v1/assessment-instructions |
  | Class Management Service | Production assignments | ??? | ??? |

### Assignment Creation Flows

- CLI Research Path: ...
- Teacher Production Path: ...
- Synchronization: ...

## 2. Anchor Essay Storage Architecture

### Storage Pattern

- **Blob Storage**: Content Service stores actual essay text
- **Metadata**: CJ Assessment Service stores references
- **Diagram**: [Draw architecture]

### Storage Flow

  1. CLI: `register-anchors` command
  2. Text extraction from .docx/.pdf
  3. POST to CJ `/api/v1/anchors/register`
  4. CJ stores in Content Service → gets storage_id
  5. CJ creates anchor_essay_references record

## 3. Student Essay Storage Patterns

### Path A: User Upload (Production)

  [Diagram/Flow]
  User → API Gateway → ??? → Storage

### Path B: CLI Upload (Research)

  [Diagram/Flow]
  CLI → Content Service → cj_processed_essays

### Storage Comparison

  | Aspect | User Uploads | CLI Uploads |
  |--------|-------------|-------------|
  | Entry Point | API Gateway | CLI |
  | Services Touched | ??? | Content Service |
  | Database Records | ??? | cj_processed_essays |
  | Ownership | CMS? | CJ Assessment |

## 4. Cross-Service Integration

### Assignment ID Flow

  [Diagram showing assignment_id propagation]

### Data Ownership Boundaries

- CJ Assessment: Research data, anchor essays, comparative judgments
- CMS: Teacher/student/class management, production assignments
- Content Service: Blob storage for all essay content
- File Service: ???
- Essay Lifecycle Service: ???

## 5. Architectural Recommendations

  Based on research findings:

- [ ] Should CLI uploads integrate with CMS?
- [ ] Consolidation opportunities?
- [ ] Clear service boundaries?

  Research Methodology

  1. Start with Service READMEs: Check each service's README for architecture overview
  2. Trace Data Models: Use models_db.py files to understand table relationships
  3. Follow Event Flows: Check libs/common_core/src/common_core/events/ for cross-service events
  4. API Exploration: Review API endpoints in each service's api/ directory
  5. Implementation Details: Check implementations/ for actual storage/retrieval logic

  Tools to Use

# Search for assignment_id usage across services

  grep -r "assignment_id" services/*/models_db.py

# Find essay-related tables

  grep -r "class.*Essay" services/*/models_db.py

# Trace Content Service usage

  grep -r "content_service" services/

# Find file upload endpoints

  grep -r "upload.*essay\|essay.*upload" services/*/api/

  Success Criteria

  The research document should answer:

- ✅ Clear ownership: Which service owns what data?
- ✅ Storage architecture: Where is essay content stored (blob vs DB)?
- ✅ Flow diagrams: Visual representation of both user and CLI upload paths
- ✅ Integration points: How services communicate for essay assessment
- ✅ Architectural alignment: Does current design follow DDD/microservice principles?
- ✅ Recommendations: Any consolidation or clarification needed?

  Files Modified So Far (For Context)

  docker-compose.eng5-runner.yml - Fixed CJ service URL port
  scripts/cj_experiments_runners/eng5_np/cli.py - Made assignment_id required
  scripts/cj_experiments_runners/eng5_np/ASSIGNMENT_SETUP.md - Created
  scripts/cj_experiments_runners/eng5_np/ANCHOR_REGISTRATION_EXAMPLE.md - Created

  ---
  NEXT AI SESSION: Use the Task tool with Explore or Plan agent to systematically investigate each question and build the comprehensive knowledge document
   in .claude/research/eng5_runner_architecture_data_flow.md

## Progress Update (2025-11-10)

- Consolidated ENG5 runner research into `.claude/research/eng5_runner_architecture_data_flow.md`, covering assignment ownership matrix, anchor/student flows, and assignment_id propagation.
- Mapped production upload path across API Gateway, File Service, Content Service, Essay Lifecycle, and CJ Assessment for inclusion in the research doc.
- Remaining: Track any follow-up alignment actions (assignment sync, observability) once recommendations are reviewed with stakeholders.
