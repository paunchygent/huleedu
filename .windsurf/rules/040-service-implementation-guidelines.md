---
trigger: model_decision
description: "Implementation patterns for HuleEdu services. Follow when developing or modifying services to ensure consistency and maintainability."
---

===

# 040: Service Implementation Guidelines

## 1. Purpose

These guidelines standardize HuleEdu microservice implementation. You (AI agent) **MUST** adhere to these when generating/modifying service code.

## 2. Frameworks & Libraries

### 2.1. Rule: Quart for Service Implementation

    - **Framework**: Quart **SHALL** be your primary web framework for async microservices.
    - **Asynchronous**: You **MUST** use Quart's native async capabilities for all request handling and I/O.

### 2.2. Rule: PDM for Dependency Management

    - **Tool**: Manage Python dependencies exclusively with PDM (`pyproject.toml`, `pdm.lock`).
    - **Your Action**: Add/update dependencies using PDM commands, ensuring `pdm.lock` is current.

## 3. Asynchronous Programming

### 3.1. Rule: Embrace `async/await`

    - All I/O-bound operations (network, DB, file system) **MUST** use `async/await` and async-compatible libraries.
    - You **MUST** avoid blocking calls in async code paths.

### 3.2. Rule: Proper Async Context Management

    - Use `async with` for async context managers. Manage task lifecycles and cancellation correctly.

## 4. State Management (Per Architectural Blueprint)

### 4.1. Rule: Batch Orchestration Service State

    - **Responsibility**: This service exclusively manages `BatchUpload.status` and `BatchUpload.processing_metadata` (holding `ProcessingPipelineState`).
    - **Your Action**: When coding for this service, strictly follow the state transition logic and `ProcessingPipelineState` updates from the Architectural Design Blueprint.

### 4.2. Rule: Essay Lifecycle Service State

    - **Responsibility**: This service exclusively manages `ProcessedEssay.status`.
    - **Your Action**: When coding for this service, strictly follow the `EssayStatus` enum and transition logic from the Architectural Design Blueprint.

### 4.3. Rule: Clear State Ownership & Eventing

    - Each service owns its primary entities' state. Significant state changes **MUST** be communicated via events published by the owning service (see [030-*.md](mdc:030-event-driven-architecture-eda-standards.md)).

## 5. Internal API Design (If Applicable)

    - If a service exposes synchronous APIs (use sparingly):
        - **MUST** follow RESTful principles.
        - **MUST** use Pydantic models (from `common/` or service-specific) for request/response schemas.
        - **MUST** include API versioning (e.g., `/v1/...`).
        - **MUST** use `ErrorInfoModel` (from `common/`) for standardized error responses.

## 6. Configuration Management

### 6.1. Rule: Environment Variables & Pydantic Settings

    - Manage service configuration via environment variables, loaded and validated using Pydantic's `BaseSettings`.
    - Sensitive info (credentials, API keys) **MUST NEVER** be hardcoded; supply via environment variables or secure secret stores.

## 7. Logging

### 7.1. Rule: Structured Logging (JSON)

    - Use structured logging (e.g., `python-json-logger`) for machine-readable JSON logs.

### 7.2. Rule: Mandatory Correlation IDs

    - For any operation chain (request/event), a `correlation_id` **MUST** be established or propagated.
    - This `correlation_id` **MUST** be in all log messages across all involved services.
    - You **MUST** ensure your logging statements include the `correlation_id`.

### 7.3. Rule: Consistent Log Levels & Clear Messages

    - Use appropriate levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
    - Log messages **MUST** be clear, concise, and contextual.

---

**Adhering to these guidelines ensures operational consistency and aligns with HuleEdu's architectural goals.**
===
