---
id: "100-terminology-and-definitions"
type: "standards"
created: 2025-05-25
last_updated: 2025-11-17
scope: "all"
---
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

- **BatchUpload**: Essay collection for processing (BOS)
- **ProcessingPipelineState**: Pipeline progress within BatchUpload
- **ProcessedEssay**: Individual essay entity (ELS)
- **EssayStatus**: Lifecycle state enum
- **StorageReferenceMetadata**: Thin event data references
- **Specialized Processing Service (SS)**: Single-phase microservice
- **Thin Events**: Minimal, versioned event payloads

## 3. Technical Implementation Terms

- **`typing.Protocol`**: Python interface contract
- **Dishka**: Project DI container
- **schema_version**: Top-level field in every EventEnvelope

## 4. AI Interaction Modes

- **Planning**: Task analysis and execution planning
- **Coding**: Code generation and modification  
- **Testing**: Test creation, execution, analysis
- **Debugging**: Issue identification and resolution
- **Refactoring/Linting**: Code structure and style improvements
===
