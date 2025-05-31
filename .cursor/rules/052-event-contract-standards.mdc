---
description: Always read before creating new event contracts or using them in code implementations
globs: 
alwaysApply: false
---

# 035: Common Core Usage Patterns

## 1. Purpose

These patterns ensure consistent event handling across services using `common-core` components, emphasizing type safety and architectural principles.

## 2. EventEnvelope Structure

### 2.1. Rule: Top-Level `schema_version`

The `EventEnvelope` must include `schema_version` as a top-level field.

```python
from uuid import uuid4
from common_core.events import EventEnvelope
from common_core.events.example_models import ExampleEventDataV1

event_data = ExampleEventDataV1(key="value")
envelope = EventEnvelope[ExampleEventDataV1](
    event_type="example.event.v1",
    source_service="service-name",
    schema_version="1.0.0",
    data=event_data
)
```

## 3. Thin Events and Callback APIs

### 3.1. Rule: Use `StorageReferenceMetadata`

For large payloads, use `StorageReferenceMetadata` instead of embedding data directly.

```python
from uuid import UUID, uuid4
from pydantic import BaseModel
from common_core.models.metadata_models import StorageReferenceMetadata

class DocumentDataV1(BaseModel):
    doc_id: UUID
    content_ref: StorageReferenceMetadata

storage_ref = StorageReferenceMetadata(
    storage_id=str(uuid4()),
    provider="s3",
    bucket_name="bucket",
    object_key=f"docs/{uuid4()}/file.txt"
)
event_data = DocumentDataV1(
    doc_id=uuid4(),
    content_ref=storage_ref
)
```

### 3.2. Rule: Consume via Callback APIs

Fetch large data using the storage reference.

```python
async def fetch_content(
    event_data: DocumentDataV1,
    http_client
) -> bytes:
    ref = event_data.content_ref
    url = f"http://storage-svc/api/objects/{ref.storage_id}"
    async with http_client.get(url) as response:
        response.raise_for_status()
        return await response.read()
```

---
