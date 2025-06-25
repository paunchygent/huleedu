# String to Enum Refactoring Task

## Overview

This document outlines all identified instances where string literals should be replaced with proper enums across the codebase. The goal is to improve type safety, reduce errors from typos, and make the code more maintainable.

## 1. Missing Enum Imports

### 1.1 Batch Conductor Service

**File**: `services/batch_conductor_service/protocols.py`

```python
# Missing imports:
# from common_core.enums import ProcessingStage, BatchStatus, ErrorCode, ValidationStatus
# from common_core.pipeline_models import PhaseName
```

### 1.2 Essay Lifecycle Service

**File**: `services/essay_lifecycle_service/protocols.py`

```python
# Missing imports:
# from common_core.enums import BatchStatus, ErrorCode, ValidationStatus, OperationStatus
# from common_core.pipeline_models import PhaseName
```

### 1.3 CJ Assessment Service

**File**: `services/cj_assessment_service/protocols.py`

```python
# Missing imports:
# from common_core.enums import ErrorCode, ProcessingStage, OperationStatus
```

### 1.4 Content Service

**File**: `services/content_service/implementations/prometheus_content_metrics.py`

```python
# Missing imports:
# from common_core.enums import OperationStatus, OperationType
```

### 1.5 File Service

**File**: `services/file_service/core_logic.py`

```python
# Missing imports:
# from common_core.enums import ValidationStatus
```

## 2. String Literals Instead of Enums

### 2.1 Processing Operations

**File**: `services/batch_conductor_service/protocols.py`

```python
# Before
async def record_essay_step_completion(
    self, batch_id: str, essay_id: str, step_name: str, metadata: dict | None = None
) -> bool:

# Should be:
async def record_essay_step_completion(
    self, 
    batch_id: str, 
    essay_id: str, 
    step_name: PhaseName,  # Use PhaseName enum
    metadata: dict | None = None
) -> bool:
```

### 2.2 Event Types

**File**: `services/essay_lifecycle_service/protocols.py`

```python
# Before
async def register_event_callback(
    self, event_type: str, callback: Callable[[Any], Awaitable[None]]
) -> None:

# Should be:
async def register_event_callback(
    self, 
    event_type: ProcessingEvent,  # Use ProcessingEvent enum
    callback: Callable[[Any], Awaitable[None]]
) -> None:
```

### 2.3 Processing Status Values

**File**: `services/batch_orchestrator_service/implementations/batch_repository_impl.py`

```python
# Before
return {"id": batch_id, "status": "pending", "processing_metadata": {}}

# Should be:
from common_core.enums import ProcessingStatus
return {"id": batch_id, "status": ProcessingStatus.PENDING, "processing_metadata": {}}
```

### 2.4 Pipeline Phase Names

**File**: `services/batch_orchestrator_service/implementations/batch_processing_service_impl.py`

```python
# Before
requested_pipelines = ["spellcheck"]
if include_cj_assessment:
    requested_pipelines.append("cj_assessment")

# Should be:
from common_core.pipeline_models import PhaseName
requested_pipelines = [PhaseName.SPELLCHECK]
if include_cj_assessment:
    requested_pipelines.append(PhaseName.CJ_ASSESSMENT)
```

## 3. Inconsistent Error Handling

### 3.1 String Error Messages

**File**: `services/batch_conductor_service/protocols.py`

```python
# Before
raise ValueError("Invalid pipeline configuration")

# Should be:
from common_core.enums import ErrorCode
raise ValueError(ErrorCode.INVALID_CONFIGURATION)
```

### 3.2 Error Code Returns

**File**: `services/cj_assessment_service/protocols.py`

```python
# Before
def get_cache_stats(self) -> dict[str, Any]:
    # Returns string status values
    return {"status": "ok", "hits": 10, "misses": 5}

# Should be:
def get_cache_stats(self) -> dict[str, Any]:
    from common_core.enums import CacheStatus
    return {"status": CacheStatus.OK, "hits": 10, "misses": 5}
```

### 3.3 API Error Responses

**File**: `services/file_service/api/file_routes.py`

```python
# Before
return jsonify({"error": "batch_id is required in form data."}), 400

# Should be:
from common_core.enums import ErrorCode
return jsonify({"error": ErrorCode.MISSING_REQUIRED_FIELD, "field": "batch_id"}), 400
```

## 4. Status Fields

### 4.1 Batch Status

**File**: `services/batch_orchestrator_service/protocols.py`

```python
# Before
async def update_batch_status(
    self, batch_id: str, status: str, details: dict | None = None
) -> bool:

# Should be:
async def update_batch_status(
    self, batch_id: str, status: BatchStatus, details: dict | None = None
) -> bool:
```

### 4.2 Processing Stage in Tests

**File**: `services/spell_checker_service/tests/unit/test_spell_idempotency_basic.py`

```python
# Before
event_data = {
    "processing_stage": "pending",
    # ... other fields
}

# Should be:
from common_core.enums import ProcessingStage
event_data = {
    "processing_stage": ProcessingStage.PENDING,
    # ... other fields
}
```

## 5. Content Type Handling

### 5.1 Content Type Parameters

**File**: `services/content_service/protocols.py`

```python
# Before
async def store_content(
    self, content: bytes, content_type: str, metadata: dict | None = None
) -> str:

# Should be:
async def store_content(
    self, content: bytes, content_type: ContentType, metadata: dict | None = None
) -> str:
```

### 5.2 Validation Status

**File**: `services/file_service/core_logic.py`

```python
# Before
validation_status = "success"

# Should be:
from common_core.enums import ValidationStatus
validation_status = ValidationStatus.SUCCESS
```

## 6. Validation Error Codes

### 6.1 File Validation

**File**: `services/file_service/protocols.py`

```python
# Before
async def validate_file(
    self, file_data: bytes, file_type: str
) -> tuple[bool, str | None]:

# Should be:
async def validate_file(
    self, file_data: bytes, file_type: str
) -> tuple[bool, FileValidationErrorCode | None]:
```

## 7. Event Publishing

### 7.1 Event Type Parameters

**File**: `services/libs/huleedu_service_libs/protocols.py`

```python
# Before
async def publish_event(
    self, event_type: str, payload: dict, correlation_id: str | None = None
) -> bool:

# Should be:
async def publish_event(
    self, 
    event_type: ProcessingEvent, 
    payload: dict, 
    correlation_id: str | None = None
) -> bool:
```

## 8. Metrics Collection

### 8.1 Metric Names

**File**: `services/batch_orchestrator_service/protocols.py`

```python
# Before
def record_metric(
    self, 
    metric_name: str, 
    value: float, 
    tags: dict[str, str] | None = None
) -> None:

# Should be:
from common_core.enums import MetricName

def record_metric(
    self, 
    metric_name: MetricName,  # Use MetricName enum
    value: float, 
    tags: dict[str, str] | None = None
) -> None:
```

### 8.2 Operation Status in Metrics

**File**: `services/content_service/implementations/prometheus_content_metrics.py`

```python
# Before
def record_operation(self, operation: str, status: str) -> None:
    # ...

# Should be:
from common_core.enums import OperationStatus, OperationType

def record_operation(self, operation: OperationType, status: OperationStatus) -> None:
    # ...
```

## 9. Database Operations

### 9.1 Query Filters

**File**: `services/essay_lifecycle_service/implementations/essay_repository_impl.py`

```python
# Before
async def find_by_status(self, status: str) -> list[EssayState]:

# Should be:
async def find_by_status(self, status: EssayStatus) -> list[EssayState]:
```

## 10. Configuration Values

### 10.1 Environment-Specific Settings

**File**: `services/batch_orchestrator_service/config.py`

```python
# Before
class EnvironmentSettings:
    ENVIRONMENT: str = "development"  # "development", "staging", "production"

# Should be:
class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

class EnvironmentSettings:
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
```

## 11. Additional Enum Usage Cases

### 11.1 Content Service Metrics

**File**: `services/content_service/protocols.py`

```python
# Before
def record_operation(self, operation: str, status: str) -> None:

# Should be:
from common_core.enums import OperationType, OperationStatus

def record_operation(
    self, 
    operation: OperationType, 
    status: OperationStatus
) -> None:
```

### 11.2 Batch Status Updates

**File**: `services/batch_orchestrator_service/implementations/batch_repository_impl.py`

```python
# Before
async def update_batch_status(self, batch_id: str, new_status: str) -> bool:

# Should be:
from common_core.enums import BatchStatus

async def update_batch_status(
    self, 
    batch_id: str, 
    new_status: BatchStatus
) -> bool:
```

### 11.3 State Transitions

**File**: `services/essay_lifecycle_service/implementations/metrics_collector.py`

```python
# Before
def record_state_transition(self, from_status: str, to_status: str) -> None:

# Should be:
from common_core.enums import EssayStatus

def record_state_transition(
    self, 
    from_status: EssayStatus, 
    to_status: EssayStatus
) -> None:
```

### 11.4 Cache Operations

**File**: `services/cj_assessment_service/implementations/cache_manager_impl.py`

```python
# Before
def add_to_cache(self, cache_key: str, data: dict[str, Any]) -> None:

# Should be:
from common_core.enums import CacheOperation, CacheStatus

def add_to_cache(
    self, 
    cache_key: str,  
    data: dict[str, Any],
    operation: CacheOperation = CacheOperation.SET
) -> CacheStatus:
```

## Implementation Guidelines

1. **For each change**:
   - Add the appropriate enum import at the top of the file
   - Update the type hints to use the enum instead of `str`
   - Update any string literals to use the enum values
   - Update any tests to use the enum values

2. **Testing**:
   - Ensure all tests pass after making changes
   - Add new tests to verify enum validation works as expected
   - Test edge cases (e.g., invalid enum values)

3. **Documentation**:
   - Update any relevant documentation to reflect the use of enums
   - Add docstrings explaining valid enum values where helpful

## Related Files

- `common_core/enums.py` - Contains core enums
- `common_core/pipeline_models.py` - Contains pipeline-related enums
- Service-specific protocol files for type definitions
