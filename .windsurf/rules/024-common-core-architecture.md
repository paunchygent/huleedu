---
description: "Rules for the Common Core package. Ensures consistency in shared models, enums, and services across microservices."
globs: 
  - "**/common_core/**/*.py"
alwaysApply: true
---
# 024: Common Core Architecture

## 1. Purpose

Defines HuleEdu's Common Core package with shared models, enums, and event schemas. This package **IS** the single source of truth for all data contracts.

## 2. Package Overview

### 2.1. Package Identity

- **Name**: `huleedu-common-core`
- **Type**: Shared library (Pydantic, Python typing)
- **Context**: Single source of truth for data contracts

### 2.2. Module Structure

```text
common_core/
├── enums.py                    # Business enums, ProcessingEvent, topic mapping
├── metadata_models.py          # Metadata/reference models  
├── pipeline_models.py          # Pipeline state models
├── essay_service_models.py     # ELS request models
├── batch_service_models.py     # BOS command models
└── events/                     # Event schemas
    ├── envelope.py             # EventEnvelope wrapper
    ├── base_event_models.py    # Base event classes
    ├── file_events.py          # File Service domain events
    ├── batch_coordination_events.py # Batch coordination events
    ├── els_bos_events.py       # ELS to BOS communication events
    ├── spellcheck_models.py    # Spellcheck event data
    └── ai_feedback_events.py   # AI feedback event data
```

## 3. Core Enums

### 3.1. ProcessingStage

`PENDING`, `INITIALIZED`, `PROCESSING`, `COMPLETED`, `FAILED`, `CANCELLED`

### 3.2. ProcessingEvent

- **Pattern**: MUST be used to identify event types semantically.
- **Example**: `ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED`

### 3.3. EssayStatus

- **Pattern**: MUST be used to represent the state of an individual essay within a processing pipeline.
- **Example**: `EssayStatus.AWAITING_SPELLCHECK`, `EssayStatus.SPELLCHECKED_SUCCESS`

### 3.4. BatchStatus

- **Pattern**: MUST be used to represent the high-level state of an entire batch upload.
- **Example**: `BatchStatus.PROCESSING_PIPELINES`, `BatchStatus.COMPLETED_SUCCESSFULLY`

### 3.5. ContentType

`ORIGINAL_ESSAY`, `CORRECTED_TEXT`, `RAW_UPLOAD_BLOB`, `EXTRACTED_PLAINTEXT`, etc.

### 3.6. ErrorCode

- **Pattern**: Provides generic, system-wide error categories.
- **Example**: `ErrorCode.VALIDATION_ERROR`, `ErrorCode.EXTERNAL_SERVICE_ERROR`

### 3.7. FileValidationErrorCode

- **Pattern**: Provides specific error codes for file validation failures.
- **Example**: `FileValidationErrorCode.EMPTY_CONTENT`, `FileValidationErrorCode.RAW_STORAGE_FAILED`

### 3.8. Topic Mapping Function

- **MUST** use `topic_name(event: ProcessingEvent)` to get Kafka topic names.
- **FORBIDDEN**: Hardcoding topic names in services.
- Events intended for Kafka **MUST** have an explicit mapping in the `_TOPIC_MAPPING` dictionary within `enums.py`.

## 4. Core Models

### 4.1. EntityReference

- **Purpose**: A standard, immutable way to refer to any entity within the system.
- **Fields**: `entity_id: str`, `entity_type: str`, `parent_id: Optional[str]`

### 4.2. SystemProcessingMetadata

- **Pattern**: MUST be embedded in event data to provide processing context (entity, stage, errors).
- **Example Instantiation**:

  ```python
  SystemProcessingMetadata(
      entity=EntityReference(entity_id="essay-123", entity_type="essay"),
      timestamp=datetime.now(timezone.utc),
      processing_stage=ProcessingStage.COMPLETED,
      event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
      error_info={}
  )
  ```

### 4.3. EssayProcessingInputRefV1

- **Purpose**: A minimal, general-purpose contract for referencing an essay and its input text for a processing phase.
- **Fields**: `essay_id: str`, `text_storage_id: str`

## 5. Event System

### 5.1. EventEnvelope

- **MUST** be used as the standard wrapper for all asynchronous messages published to Kafka.
- **Fields MUST include**: `event_id`, `event_type`, `source_service`, `correlation_id`, `schema_version`, and `data`.

### 5.2. Base Event Models

- `BaseEventData`: The foundation for all event payloads.
- `ProcessingUpdate`: Extends `BaseEventData` to include a `status` and `system_metadata`. Used for events that represent a change in an entity's state.

### 5.3. Key Event Domain Models

- **`file_events.py`**: Defines `EssayContentProvisionedV1` and `EssayValidationFailedV1`. These are critical for the File Service -> ELS coordination.
- **`batch_coordination_events.py`**: Defines `BatchEssaysRegistered` (BOS->ELS) and `BatchEssaysReady` (ELS->BOS).
- **`els_bos_events.py`**: Defines `ELSBatchPhaseOutcomeV1`. This event is **CRITICAL** for dynamic pipeline orchestration, as it's how ELS reports the completion of a phase back to BOS.

## 6. Implementation & Type Safety

- All models **MUST** inherit from Pydantic's `BaseModel`.
- The `__init__.py` file **MUST** explicitly call `model_rebuild(raise_errors=True)` on all models with forward references to ensure type safety and prevent runtime errors.
- The package **MUST** include a `py.typed` file to support type checking by consumer services.
