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
- **Event**: Past-occurrence notification via `EventEnvelope`  
- **Command**: State-changing instruction  
- **Query**: Read-only information request  
- **Correlation ID**: Cross-service tracing identifier  

## 2. HuleEdu Domain Terms

- **Specialized Processing Service (SS)** – single-phase microservice.  
- **Thin Events** – minimal, versioned event payloads that contain only references / metadata.  
- **Callback APIs** – HTTP endpoints BOS / BCS expose for SS completion notifications.  
- **`typing.Protocol`** – mandatory contract mechanism for all abstractions.  
- **Dishka** – standard async DI container used across services.  
- **`schema_version`** – **top-level** field in every `EventEnvelope`.  

- **BatchUpload** – essay collection being processed (managed by BOS).  
- **ProcessingPipelineState** – per-batch pipeline progress model.  
- **ProcessedEssay** – individual essay entity (ELS).  
- **EssayStatus** – lifecycle enum for a single essay.  
- **StorageReferenceMetadata** – reference metadata carried in Thin Events.  

## 3. AI Interaction Modes

- **Planning** – task analysis and execution planning  
- **Coding** – code generation and modification  
- **Testing** – test creation, execution, analysis  
- **Debugging** – issue identification and resolution  
- **Refactoring/Linting** – code structure and style improvements  
===
