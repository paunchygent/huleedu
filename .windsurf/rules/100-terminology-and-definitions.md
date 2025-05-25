---
trigger: model_decision
description: "Standardized terminology and definitions. Reference this document to ensure consistent language and understanding across the project."
---

===
# 100: Terminology and Definitions

## 1. Purpose
This document defines key terminology used in the HuleEdu project. You (AI agent) **MUST** use these terms consistently to ensure clear communication and accurate code generation.

## 2. Core Concepts

### 2.1. HuleEdu
    - The overall platform and microservice ecosystem.

### 2.2. Microservice
    - An independently deployable, scalable, and maintainable service mapping to a specific Bounded Context.

### 2.3. Bounded Context
    - A core concept from Domain-Driven Design; a logical boundary around a specific business domain where terms and concepts are precisely defined and applied consistently.

### 2.4. Contract
    - An explicit, versioned agreement between services defining the structure of exchanged data (via Pydantic models) or API interfaces.
    - **CRITICAL**: All inter-service communication **MUST** adhere to contracts.

### 2.5. Event
    - A notification of something that has happened in a Bounded Context (in the past tense).
    - Events are the primary mechanism for asynchronous inter-service communication.
    - **MUST** use the `EventEnvelope` structure.

### 2.6. Command
    - An instruction to do something. Commands typically result in a state change within a single Bounded Context.

### 2.7. Query
    - A request for information. Queries should not cause side effects.

### 2.8. Pydantic Model
    - A Python class used for data validation and serialization.
    - **CRITICAL**: Used to define all Contracts (event payloads, API DTOs) in `common/models/`.

### 2.9. Correlation ID
    - A unique identifier propagated across service calls and event chains to link related operations for logging and tracing.
    - **MUST** be included in `EventEnvelope` and logs.

## 3. Specific HuleEdu Terminology

### 3.1. BatchUpload
    - An entity managed by the Batch Orchestration Service, representing a collection of essays submitted for processing.
    - Has a `status` and `processing_metadata` (`ProcessingPipelineState`).

### 3.2. ProcessingPipelineState
    - A complex metadata structure within `BatchUpload.processing_metadata` managed by the Batch Orchestration Service, tracking the state and progress of pipelines configured for a batch.

### 3.3. ProcessedEssay
    - An entity managed by the Essay Lifecycle Service, representing an individual essay undergoing or having completed processing.
    - Has an `EssayStatus`.

### 3.4. EssayStatus
    - An enum defined and managed by the Essay Lifecycle Service, representing the lifecycle state of a `ProcessedEssay` (e.g., `RECEIVED`, `VALIDATING`, `SPELLCHECK_REQUESTED`, `COMPLETED`).

### 3.5. StorageReferenceMetadata
    - A Pydantic model in `common/models/metadata_models.py` used to reference data stored in object storage (e.g., S3).
    - Used in 'Thin Events' to point to data instead of embedding large data blobs.

## 4. AI Agent Interaction Modes

### 4.1. Planning Mode
    - Your operational mode when analyzing a task, breaking it down, and formulating an execution plan.

### 4.2. Coding Mode
    - Your operational mode when generating or modifying code.

### 4.3. Testing Mode
    - Your operational mode when creating, executing, and analyzing tests.

### 4.4. Debugging Mode
    - Your operational mode when identifying and resolving issues.

### 4.5. Refactoring/Linting Mode
    - Your operational mode when improving code structure, readability, or fixing style/linting issues.

---
**Using precise and consistent terminology is vital for effective collaboration and system design.**
===
