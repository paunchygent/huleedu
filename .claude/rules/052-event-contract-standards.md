---
id: "052-event-contract-standards"
type: "standards"
created: 2025-05-31
last_updated: 2025-11-17
scope: "cross-service"
---

# 052: Event Contract Standards

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

## 3. Event Size Patterns

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

### 3.3. Dual Event Pattern

For services requiring both state management and business data, publish two specialized events:

```python
# Publisher: Spellchecker Service
from common_core.events.spellcheck_models import (
    SpellcheckPhaseCompletedV1,
    SpellcheckResultV1
)

# Thin event for state management (~300 bytes)
thin_event = SpellcheckPhaseCompletedV1(
    entity_id=essay_id,
    batch_id=batch_id,
    status=ProcessingStatus.SUCCESS,
    corrected_text_storage_id=storage_id,
    processing_duration_ms=duration_ms,
    timestamp=datetime.utcnow()
)

# Rich event for business data
rich_event = SpellcheckResultV1(
    entity_id=essay_id,
    corrections_made=metrics.total_corrections,
    correction_metrics=metrics,
    original_text_storage_id=original_storage_id,
    corrected_text_storage_id=storage_id,
    processing_duration_ms=duration_ms
)

# Publishers handle both events via outbox pattern
await event_publisher.publish_both_events(thin_event, rich_event)
```

**Consumer Patterns**:

```python
# ELS/BCS: Consume thin event for state transitions
@subscribe(topic_name("huleedu.batch.spellcheck.phase.completed.v1"))
async def handle_spellcheck_phase_completed(event: SpellcheckPhaseCompletedV1):
    # Update state only, no business metrics needed
    await self.repository.update_essay_status(
        event.entity_id, event.status, event.corrected_text_storage_id
    )

# RAS: Consume rich event for business data
@subscribe(topic_name("huleedu.essay.spellcheck.results.v1"))
async def process_spellcheck_result(event: SpellcheckResultV1):
    # Store complete business metrics for reporting
    await self.repository.update_essay_spellcheck_result_with_metrics(
        event.entity_id, event.correction_metrics, event.corrections_made
    )
```

**Benefits**:
- **Performance**: State consumers avoid processing unnecessary business data
- **Separation of Concerns**: Clear distinction between state and analytics
- **Network Efficiency**: Reduced data transfer for state-only operations

---
