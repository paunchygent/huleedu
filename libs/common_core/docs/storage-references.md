# Storage References

StorageReferenceMetadata pattern for large payloads to avoid Kafka message size limits.

## Threshold Rule

Event payload >50KB → Use StorageReferenceMetadata instead of inline data.

## Structure

```python
from common_core.metadata_models import StorageReferenceMetadata
from common_core.domain_enums import ContentType

class StorageReferenceMetadata(BaseModel):
    references: dict[ContentType, dict[str, str]] = Field(default_factory=dict)

    def add_reference(
        self,
        ctype: ContentType,
        storage_id: str,
        path_hint: str | None = None,
    ) -> None:
        self.references[ctype] = {"storage_id": storage_id, "path": path_hint or ""}
```

## Content Types

```python
class ContentType(str, Enum):
    ORIGINAL_ESSAY = "original_essay"
    CORRECTED_TEXT = "corrected_text"
    NLP_METRICS_JSON = "nlp_metrics_json"
    CJ_RESULTS_JSON = "cj_results_json"
    STUDENT_PROMPT_TEXT = "student_prompt_text"
    AI_DETAILED_ANALYSIS_JSON = "ai_detailed_analysis_json"
    # ... see domain_enums.py for full list
```

## Usage Pattern

```python
# Store large data in Content Service, get storage_id
storage_id = await content_service.store_json(large_results_dict)

# Create reference
storage_ref = StorageReferenceMetadata()
storage_ref.add_reference(
    ctype=ContentType.CJ_RESULTS_JSON,
    storage_id=storage_id,
    path_hint="cj/batch_123/results.json"  # Optional hint for debugging
)

# Use in event
event_data = MyEventV1(
    essay_id="essay_123",
    results_ref=storage_ref  # Reference instead of 50KB+ JSON
)
```

## Retrieval Pattern

```python
# Consumer extracts storage_id
storage_ref = event_data.results_ref
cj_ref = storage_ref.references.get(ContentType.CJ_RESULTS_JSON)

if cj_ref:
    storage_id = cj_ref["storage_id"]
    # Fetch from Content Service
    results_json = await content_service.fetch(storage_id, correlation_id)
    results = parse_json(results_json)
```

## CJ Assessment Example

```python
# Producer (CJ Service)
results_json = json.dumps(detailed_results_dict)  # 200KB
storage_id = await self.content_client.store_json(results_json, correlation_id)

storage_ref = StorageReferenceMetadata()
storage_ref.add_reference(
    ContentType.CJ_RESULTS_JSON,
    storage_id,
    f"cj/{job_id}/detailed_results.json"
)

event = ELS_CJAssessmentRequestV1(
    student_prompt_ref=storage_ref,  # Reference, not 200KB inline
    # ...
)

# Consumer (ELS)
if event.student_prompt_ref:
    ref = event.student_prompt_ref.references[ContentType.STUDENT_PROMPT_TEXT]
    prompt_text = await self.content_client.fetch(ref["storage_id"], correlation_id)
```

## Multiple References

Single StorageReferenceMetadata can hold multiple content types:

```python
storage_ref = StorageReferenceMetadata()

storage_ref.add_reference(ContentType.CORRECTED_TEXT, text_storage_id)
storage_ref.add_reference(ContentType.NLP_METRICS_JSON, metrics_storage_id)
storage_ref.add_reference(ContentType.PROCESSING_LOG, log_storage_id)

# All three references in single field
event = MyEventV1(all_content_refs=storage_ref)
```

## When to Use

| Payload Size | Pattern |
|--------------|---------|
| <10KB | Inline in event data |
| 10KB-50KB | Inline acceptable, consider reference for future |
| >50KB | MUST use StorageReferenceMetadata |
| >1MB | MUST use reference, split if possible |

## Related

- `libs/common_core/src/common_core/metadata_models.py` - Implementation
- `libs/common_core/src/common_core/domain_enums.py` - ContentType enum
- CJ Assessment Service - Uses student_prompt_ref
