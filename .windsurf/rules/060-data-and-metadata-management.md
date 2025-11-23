---
id: "060-data-and-metadata-management"
type: "architecture"
created: 2025-05-25
last_updated: 2025-11-17
scope: "all"
---

# 060: Data and Metadata Management

## 1. Common Data Models (Pydantic)

### 1.1. Central Data Model Repository
- All shared data models **MUST** be defined as Pydantic models in `common/models/`
- Includes event payloads, API DTOs, shared entities
- **MUST** reference and use these common models for inter-service data

### 1.2. Common Metadata Models
- Standard metadata **MUST** use Pydantic models from `common/models/metadata_models.py`
- `StorageReferenceMetadata` **SHALL** be used for data references in events/APIs

### 1.3. Model Definition Standards
- **MUST** be fully type-hinted with clear field descriptions
- **SHOULD** be versioned implicitly via location or explicitly in naming

## 2. Data Storage and Access

### 2.1. Service Owns its Data Store
- Each service **SHALL** interact with its own dedicated data store
- Direct access to another service's data store **STRICTLY FORBIDDEN**
- Data access **MUST** be mediated via owning service's API or events

### 2.2. ORM/Client Usage
- Use async-compatible ORMs or database clients
- Keep data access logic within service's bounded context

## 3. Metadata Management

### 3.1. EventEnvelope and API Responses
- Essential metadata (`event_id`, `event_timestamp`, `source_service`, `correlation_id`) **MUST** be in `EventEnvelope`
- API responses **SHOULD** include relevant metadata (timestamp, request ID)

### 3.2. Logging Includes Metadata
- Logging **MUST** include relevant metadata, especially `correlation_id`

### 3.3. Typed Metadata Overlay Pattern

```python
from pydantic import BaseModel, ConfigDict

# Define typed model for known fields
class CJProcessingMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_prompt_storage_id: str | None = None
    student_prompt_text: str | None = None

# Merge into existing dict (preserves unknown keys)
existing_metadata = entity.processing_metadata or {}
typed_metadata = CJProcessingMetadata(
    student_prompt_storage_id="abc123"
).model_dump(exclude_none=True)

entity.processing_metadata = {**existing_metadata, **typed_metadata}
```

**Use for**: Gradual migration from dict to typed models, workflow systems with domain + dynamic fields

## 4. Data Schema Evolution

### 4.1. Backward Compatibility
- Prioritize backward compatibility when evolving schemas in `common/models/`
- Adding optional fields is safe
- Removing/changing existing fields **REQUIRES** careful versioning strategy
