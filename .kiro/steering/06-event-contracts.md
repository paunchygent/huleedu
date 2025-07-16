---
inclusion: fileMatch
fileMatchPattern: "**/common_core/**"
---

# Event Contracts and Data Models

## Event Contract Standards

### Event Envelope Pattern
All events MUST use the standardized `EventEnvelope` wrapper:

```python
from common_core.events import EventEnvelope
from common_core.events.essay_events import EssayContentProvisionedV1

# Creating an event
event_data = EssayContentProvisionedV1(
    essay_id="essay-123",
    text_storage_id="content-456",
    language="en"
)

envelope = EventEnvelope(
    event_type="EssayContentProvisionedV1",
    data=event_data,
    correlation_id="batch-789"
)
```

### Event Naming Conventions
- Event names end with version suffix (V1, V2, etc.)
- Use past tense for completed actions: `EssayContentProvisionedV1`
- Use imperative for commands: `BatchSpellcheckInitiateCommandV1`
- Group related events in modules: `essay_events.py`, `batch_events.py`

### Event Versioning Strategy
- Breaking changes require new version (V1 → V2)
- Maintain backward compatibility when possible
- Deprecate old versions gradually
- Document migration paths between versions

## Common Event Patterns

### Essay Processing Events
```python
# Essay content provisioning
EssayContentProvisionedV1(
    essay_id: str,
    text_storage_id: str,
    language: str,
    metadata: Optional[Dict[str, Any]] = None
)

# Processing phase completion
ELSBatchPhaseOutcomeV1(
    batch_id: str,
    phase: ProcessingPhase,
    outcome: PhaseOutcome,
    essay_outcomes: List[EssayPhaseOutcome]
)
```

### Command Events
```python
# Service initiation commands
BatchSpellcheckInitiateCommandV1(
    batch_id: str,
    essays: List[EssayProcessingInfo],
    language: str
)

BatchCJAssessmentInitiateCommandV1(
    batch_id: str,
    essays: List[EssayProcessingInfo],
    assessment_config: CJAssessmentConfig
)
```

### Error and Status Events
```python
# Error reporting
ServiceErrorEventV1(
    service_name: str,
    error_code: str,
    error_message: str,
    context: Dict[str, Any]
)

# Health status
ServiceHealthEventV1(
    service_name: str,
    status: HealthStatus,
    dependencies: List[DependencyHealth]
)
```

## Data Model Standards

### Base Model Patterns
```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class BaseEntity(BaseModel):
    id: str = Field(..., description="Unique identifier")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
```

### Validation Patterns
```python
from pydantic import validator, root_validator

class Essay(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)
    language: str = Field(..., regex=r'^[a-z]{2}$')
    
    @validator('content')
    def validate_content(cls, v):
        if not v.strip():
            raise ValueError('Content cannot be empty or whitespace only')
        return v.strip()
```

### Enum Definitions
```python
from enum import Enum

class ProcessingPhase(str, Enum):
    SPELLCHECK = "spellcheck"
    CJ_ASSESSMENT = "cj_assessment"
    AI_FEEDBACK = "ai_feedback"
    NLP_METRICS = "nlp_metrics"

class PhaseOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
```