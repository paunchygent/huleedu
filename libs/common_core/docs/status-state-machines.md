# Status State Machines

ProcessingStage, EssayStatus, BatchStatus enums with state transitions.

## Processing Stage (Generic)

```python
from common_core.status_enums import ProcessingStage

class ProcessingStage(str, Enum):
    PENDING = "pending"
    INITIALIZED = "initialized"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def terminal(cls) -> set[ProcessingStage]:
        return {cls.COMPLETED, cls.FAILED, cls.CANCELLED}

    @classmethod
    def active(cls) -> set[ProcessingStage]:
        return {cls.COMPLETED, cls.INITIALIZED, cls.PROCESSING}
```

Used in ProcessingUpdate events (thin events).

## Essay Status

```python
from common_core.status_enums import EssayStatus

# File Service
UPLOADED = "uploaded"
TEXT_EXTRACTED = "text_extracted"

# Content Ingestion
CONTENT_INGESTING = "content_ingester"
CONTENT_INGESTION_FAILED = "content_ingestion_failed"

# ELS Pipeline
READY_FOR_PROCESSING = "ready_for_processing"

# Spellcheck
AWAITING_SPELLCHECK = "awaiting_spellcheck"
SPELLCHECKING_IN_PROGRESS = "spellchecking_in_progress"
SPELLCHECKED_SUCCESS = "spellchecked_success"
SPELLCHECK_FAILED = "spellcheck_failed"

# NLP
AWAITING_NLP = "awaiting_nlp"
NLP_IN_PROGRESS = "nlp_processing_in_progress"
NLP_SUCCESS = "nlp_success"
NLP_FAILED = "nlp_failed"

# CJ Assessment
AWAITING_CJ_ASSESSMENT = "awaiting_cj_assessment"
CJ_ASSESSMENT_IN_PROGRESS = "cj_assessment_processing_in_progress"
CJ_ASSESSMENT_SUCCESS = "cj_assessment_success"
CJ_ASSESSMENT_FAILED = "cj_assessment_failed"

# Terminal
ALL_PROCESSING_COMPLETED = "all_processing_completed"
ESSAY_CRITICAL_FAILURE = "essay_critical_failure"
```

## Batch Status

```python
from common_core.status_enums import BatchStatus

# Phase 1: Content
AWAITING_CONTENT_VALIDATION = "awaiting_content_validation"
CONTENT_INGESTION_FAILED = "content_ingestion_failed"

# Configuration
AWAITING_PIPELINE_CONFIGURATION = "awaiting_pipeline_configuration"
READY_FOR_PIPELINE_EXECUTION = "ready_for_pipeline_execution"

# Processing
PROCESSING_PIPELINES = "processing_pipelines"

# Student Validation (REGULAR batches only)
AWAITING_STUDENT_VALIDATION = "awaiting_student_validation"
STUDENT_VALIDATION_COMPLETED = "student_validation_completed"
VALIDATION_TIMEOUT_PROCESSED = "validation_timeout_processed"

# Terminal
COMPLETED_SUCCESSFULLY = "completed_successfully"
COMPLETED_WITH_FAILURES = "completed_with_failures"
FAILED_CRITICALLY = "failed_critically"
CANCELLED = "cancelled"
```

## Client-Facing Status

Simplified for API responses:

```python
from common_core.status_enums import BatchClientStatus

# Initial
PENDING_CONTENT = "pending_content"  # Awaiting content validation

# Ready
READY = "ready"  # Ready for pipeline execution

# Active
PROCESSING = "processing"  # Any pipeline phase

# Terminal
COMPLETED_SUCCESSFULLY = "completed_successfully"
COMPLETED_WITH_FAILURES = "completed_with_failures"
FAILED = "failed"
CANCELLED = "cancelled"
```

## State Transition Examples

### Essay Phase Transitions

```
UPLOADED
  ↓ (File Service extracts text)
TEXT_EXTRACTED
  ↓ (Content Service provisions)
READY_FOR_PROCESSING
  ↓ (Spellcheck initiated)
AWAITING_SPELLCHECK
  ↓ (Spellcheck processing)
SPELLCHECKING_IN_PROGRESS
  ↓ (Success)
SPELLCHECKED_SUCCESS
  ↓ (NLP initiated)
AWAITING_NLP
  ...
```

### Batch Flow (GUEST)

```
AWAITING_CONTENT_VALIDATION
  ↓ (All essays provisioned)
AWAITING_PIPELINE_CONFIGURATION
  ↓ (Client initiates pipeline)
READY_FOR_PIPELINE_EXECUTION
  ↓ (Spellcheck command sent)
PROCESSING_PIPELINES
  ↓ (All phases complete)
COMPLETED_SUCCESSFULLY
```

### Batch Flow (REGULAR with Student Matching)

```
AWAITING_CONTENT_VALIDATION
  ↓ (All essays provisioned)
AWAITING_STUDENT_VALIDATION
  ↓ (Teacher confirms associations)
STUDENT_VALIDATION_COMPLETED
  ↓ (Client initiates pipeline)
READY_FOR_PIPELINE_EXECUTION
  ↓ (Pipeline processing)
PROCESSING_PIPELINES
  ↓ (Complete)
COMPLETED_SUCCESSFULLY
```

## Terminal State Checks

```python
from common_core.status_enums import ProcessingStage

if stage in ProcessingStage.terminal():
    # No further processing
    pass

# Individual checks
if batch.status == BatchStatus.COMPLETED_SUCCESSFULLY:
    # Success handling
elif batch.status in [
    BatchStatus.COMPLETED_WITH_FAILURES,
    BatchStatus.FAILED_CRITICALLY,
    BatchStatus.CANCELLED
]:
    # Failure/termination handling
```

## Related

- `common_core/status_enums.py` - All status enums
- Essay Lifecycle Service - State machine implementation
