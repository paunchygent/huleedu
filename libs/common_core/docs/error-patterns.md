# Error Patterns

Centralized error codes and SystemProcessingMetadata.error_info structure.

## ErrorCode Base Enum

```python
from common_core.error_enums import ErrorCode

class ErrorCode(str, Enum):
    # Generic errors
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"

    # Service errors
    KAFKA_PUBLISH_ERROR = "KAFKA_PUBLISH_ERROR"
    CONTENT_SERVICE_ERROR = "CONTENT_SERVICE_ERROR"
    SPELLCHECK_SERVICE_ERROR = "SPELLCHECK_SERVICE_ERROR"
    NLP_SERVICE_ERROR = "NLP_SERVICE_ERROR"
    CJ_ASSESSMENT_SERVICE_ERROR = "CJ_ASSESSMENT_SERVICE_ERROR"

    # External service errors
    TIMEOUT = "TIMEOUT"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    RATE_LIMIT = "RATE_LIMIT"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
    PROCESSING_ERROR = "PROCESSING_ERROR"
```

## Service-Specific Enums

Extend ErrorCode pattern for domain-specific errors:

```python
# CJ Assessment Service
class CJAssessmentErrorCode(str, Enum):
    CJ_INSUFFICIENT_COMPARISONS = "CJ_INSUFFICIENT_COMPARISONS"
    CJ_SCORE_CONVERGENCE_FAILED = "CJ_SCORE_CONVERGENCE_FAILED"
    CJ_CALLBACK_CORRELATION_FAILED = "CJ_CALLBACK_CORRELATION_FAILED"

# LLM Provider Service
class LLMErrorCode(str, Enum):
    PROVIDER_UNAVAILABLE = "LLM_PROVIDER_UNAVAILABLE"
    PROVIDER_RATE_LIMIT = "LLM_PROVIDER_RATE_LIMIT"
    INVALID_PROMPT = "LLM_INVALID_PROMPT"
    CONTENT_TOO_LONG = "LLM_CONTENT_TOO_LONG"

# Identity Service
class IdentityErrorCode(str, Enum):
    INVALID_CREDENTIALS = "IDENTITY_INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "IDENTITY_TOKEN_EXPIRED"
    EMAIL_NOT_VERIFIED = "IDENTITY_EMAIL_NOT_VERIFIED"
```

## SystemProcessingMetadata.error_info

Error details stored in system_metadata of thin events:

```python
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import ProcessingStage

system_metadata = SystemProcessingMetadata(
    entity_id=batch_id,
    entity_type="batch",
    processing_stage=ProcessingStage.FAILED,
    error_info={
        "error_code": CJAssessmentErrorCode.CJ_INSUFFICIENT_COMPARISONS,
        "error_message": "Minimum 5 comparisons required per essay, got 3",
        "error_type": "InsufficientDataError",
        "context": {
            "essay_count": 10,
            "comparison_count": 30,
            "required_minimum": 50
        }
    }
)
```

## Publishing Failure Events

```python
from common_core.events.cj_assessment_events import CJAssessmentFailedV1

failure_event = CJAssessmentFailedV1(
    entity_ref=batch_id,
    status=ProcessingStage.FAILED,
    system_metadata=system_metadata,  # Contains error_info
    cj_assessment_job_id=job_id
)

envelope = EventEnvelope[CJAssessmentFailedV1](
    event_type=topic_name(ProcessingEvent.CJ_ASSESSMENT_FAILED),
    source_service="cj_assessment_service",
    correlation_id=correlation_id,
    data=failure_event
)

await kafka_bus.publish(topic, envelope.model_dump_json().encode('utf-8'))
```

## Consuming Failure Events

```python
# Essay Lifecycle Service
async def handle_cj_failure(self, message: bytes):
    envelope = EventEnvelope[Any].model_validate_json(message)
    failure = CJAssessmentFailedV1.model_validate(envelope.data)

    error_info = failure.system_metadata.error_info
    error_code = error_info.get("error_code")
    error_message = error_info.get("error_message")

    logger.error(
        "CJ assessment failed",
        batch_id=failure.entity_ref,
        error_code=error_code,
        error_message=error_message,
        correlation_id=str(envelope.correlation_id)
    )

    # Update batch status
    await self.mark_batch_failed(failure.entity_ref, error_info)
```

## error_info Structure

Standard fields:

```python
{
    "error_code": str,          # From ErrorCode or service-specific enum
    "error_message": str,       # Human-readable description
    "error_type": str,          # Exception class name
    "context": dict,            # Optional additional context
    "stack_trace": str | None  # Optional for debugging (not production)
}
```

## Related

- `common_core/error_enums.py` - All error enums
- `common_core/metadata_models.py` - SystemProcessingMetadata
- `libs/huleedu_service_libs/docs/error-handling.md` - Error handling implementation
