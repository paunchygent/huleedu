---
description: "Rules for the Common Core package. Ensures consistency in shared models, enums, and services across microservices."
globs: 
  - "**/common_core/**/*.py"
alwaysApply: true
---
# 024: Common Core Architecture

## 1. Purpose
Defines HuleEdu's Common Core package with shared models, enums, and event schemas.

## 2. Package Overview

### 2.1. Package Identity
- **Name**: `huleedu-common-core`
- **Type**: Shared library (Pydantic, Python typing)
- **Context**: Single source of truth for data contracts

### 2.2. Module Structure
```
common_core/
├── enums.py           # Business enums
├── metadata_models.py # Metadata/reference models
├── pipeline_models.py # Pipeline state
└── events/            # Event schemas
    ├── envelope.py
    └── spellcheck_models.py
```

## 3. Core Enums

### 3.1. ProcessingStage
`PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED`

### 3.2. ProcessingEvent
- Lifecycle: upload, validation, completion
- Phases: spellcheck, NLP, AI feedback
- System: cancellation, errors

### 3.3. EssayStatus
- Upload: `uploaded`, `text_extracted`
- Spellcheck: `awaiting_spellcheck`, `spellchecked_*`
- Processing: `awaiting_nlp`, `nlp_*`
- Final: `all_processing_completed`, `critical_failure`

### 3.4. BatchStatus
`created`, `uploading`, `processing`, `completed`, `failed`, `cancelled`

### 3.5. ContentType
`ORIGINAL_ESSAY`, `CORRECTED_TEXT`, `NLP_ANALYSIS`, `AI_FEEDBACK`

## 4. Models

### 4.1. EntityReference
```python
entity_id: str
type: str
parent_id: Optional[str]
```

### 4.2. SystemProcessingMetadata
```python
entity: EntityReference
timeline: {started_at, completed_at, timestamp}
stage: Optional[ProcessingStage]
event: Optional[str]
```

### 4.3. StorageReference
```python
references: Dict[ContentType, Dict[str, str]]
```

## 5. Event System

### 5.1. EventEnvelope
```python
type: str           # Versioned ID
source: str         # Service name
correlation_id: str
timestamp: datetime
data: T             # Typed payload
```

### 5.2. Base Event
```python
event: str
entity: EntityReference
status: str
metadata: SystemProcessingMetadata
```

### 5.3. Spellcheck Events
```python
class SpellcheckRequested:
    text_storage_id: str

class SpellcheckResult:
    storage: StorageReference
    corrections: int
```

## 6. Implementation

### 6.1. Pydantic
- All models inherit `BaseModel`
- Type hints required
- Custom validators as needed

### 6.2. Type Checking
- MyPy with strict mode
- No untyped definitions
- No `Any` returns

### 6.3. Dependencies
- Core: `pydantic[email]>=2.0`
- Dev: MyPy, Pytest, Ruff

## 7. Versioning
- Semantic versioning (0.1.0)
- Breaking changes = major version
- Event models use V1, V2 suffixes
- Backward compatibility within major versions
