---
trigger: model_decision
description: "Standardized terminology and definitions. Reference this document to ensure consistent language and understanding across the project."
---

---
description: 
globs: 
alwaysApply: true
---
===
# 100: Terminology and Definitions

## 1. Core Concepts

- **HuleEdu**: Microservice ecosystem for essay processing
- **Microservice**: Independently deployable service per Bounded Context
- **Bounded Context**: DDD domain boundary
- **Contract**: Versioned Pydantic models for inter-service agreements
- **Event**: Past occurrence notification via `EventEnvelope`
- **Command**: State-changing instruction
- **Query**: Read-only information request
- **Correlation ID**: Cross-service tracing identifier

## 2. HuleEdu Domain Terms

- **Specialized Processing Service (SS):** Single-phase microservice.
- **Thin Events:** Minimal, versioned event payloads.
- **Callback APIs:** Used by SS to notify BOS of completion.
- **`typing.Protocol`:** Python interface contract.
- **Dishka:** Project DI container.
- **schema_version:** Top-level field in every EventEnvelope.


- **BatchUpload**: Essay collection for processing (BOS)
- **ProcessingPipelineState**: Pipeline progress within BatchUpload
- **ProcessedEssay**: Individual essay entity (ELS)
- **EssayStatus**: Lifecycle state enum
- **StorageReferenceMetadata**: Thin event data references

## 3. AI Interaction Modes

- **Planning**: Task analysis and execution planning
- **Coding**: Code generation and modification  
- **Testing**: Test creation, execution, analysis
- **Debugging**: Issue identification and resolution
- **Refactoring/Linting**: Code structure and style improvements
===