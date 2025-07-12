# ERROR HANDLING MIGRATION PLAN

## Problem Statement

**Current State:** HuleEdu services use inconsistent error handling patterns ranging from modern exception-based handling (LLM Provider Service) to legacy tuple returns and custom exception classes with string-based error messages.

**Architectural Goals:**

- Standardize on HuleEduError exception-based pattern across all services
- Eliminate error_message fields in favor of structured error_detail
- Integrate with observability stack and structured logging
- Achieve consistent error propagation and handling

## Current Error Handling Audit

### MODERN PATTERN SERVICES (Already Migrated)

#### 1. LLM Provider Service ✅ COMPLETED

- **Pattern**: HuleEduError with factory functions
- **Location**: `services/llm_provider_service/`
- **Implementation**:
  - Uses `raise_configuration_error`, `raise_external_service_error`, etc.
  - Imports from `huleedu_service_libs.error_handling`
  - Proper correlation ID tracking
  - OpenTelemetry integration

#### 2. Partial Modern Services

##### CJ Assessment Service ⚠️ MIXED PATTERN

- **Modern Elements**: Some use of HuleEduError in implementations
- **Legacy Elements**: Custom `CJAssessmentError` hierarchy in `exceptions.py`
- **Issues**: Still uses `error_code` and `message` fields instead of ErrorDetail
- **Files Requiring Migration**:
  - `services/cj_assessment_service/exceptions.py` (FULL REFACTOR)
  - `services/cj_assessment_service/implementations/retry_manager_impl.py`
  - `services/cj_assessment_service/implementations/llm_provider_service_client.py`

### LEGACY PATTERN SERVICES (Require Migration)

#### 1. Class Management Service ❌ LEGACY CUSTOM EXCEPTIONS

- **Pattern**: Custom exception hierarchy with `.message` and `.error_code` attributes
- **Location**: `services/class_management_service/exceptions.py`
- **Issues**:
  - `ClassManagementServiceError` base class with `message` attribute
  - API routes access `e.message` and `e.error_code` directly
  - No correlation ID tracking
  - No observability integration

**Files Requiring Migration:**

- `services/class_management_service/exceptions.py` (COMPLETE REPLACEMENT)
- `services/class_management_service/api/class_routes.py` (ERROR HANDLING)
- `services/class_management_service/api/student_routes.py` (ERROR HANDLING)
- `services/class_management_service/implementations/class_management_service_impl.py`
- `services/class_management_service/implementations/class_repository_postgres_impl.py`

#### 2. File Service ❌ VALIDATION MODEL PATTERN

- **Pattern**: ValidationResult with `error_message` field
- **Location**: `services/file_service/validation_models.py`
- **Issues**:
  - `ValidationResult.error_message: str | None` field
  - Core logic creates validation error messages as strings
  - No structured error details or correlation ID tracking

**Files Requiring Migration:**

- `services/file_service/validation_models.py` (MODEL REFACTOR)
- `services/file_service/core_logic.py` (ERROR CREATION)
- `services/file_service/content_validator.py` (VALIDATION LOGIC)
- `services/file_service/implementations/batch_state_validator.py` (TUPLE RETURNS)

#### 3. Batch Conductor Service ❌ TUPLE RETURN PATTERN

- **Pattern**: Functions returning `(bool, str | None)` tuples
- **Location**: `services/batch_conductor_service/implementations/`
- **Issues**:
  - `validate_pipeline_compatibility()` returns `(bool, str | None)`
  - Pipeline validation errors as string messages
  - No correlation ID or structured error tracking

**Files Requiring Migration:**

- `services/batch_conductor_service/implementations/pipeline_rules_impl.py` (TUPLE RETURNS)
- `services/batch_conductor_service/implementations/pipeline_resolution_service_impl.py` (TUPLE RETURNS)
- `services/batch_conductor_service/protocols.py` (PROTOCOL SIGNATURES)

#### 4. Spell Checker Service ❌ MINIMAL ERROR HANDLING

- **Pattern**: Basic exception handling without structured errors
- **Location**: `services/spellchecker_service/`
- **Issues**:
  - Repository uses string error messages
  - No standardized error propagation
  - Basic database error handling

**Files Requiring Migration:**

- `services/spellchecker_service/repository_protocol.py`
- `services/spellchecker_service/implementations/spell_repository_postgres_impl.py`
- `services/spellchecker_service/protocol_implementations/`

#### 5. Essay Lifecycle Service ❌ MIXED PATTERNS

- **Pattern**: Mix of exception handling approaches
- **Location**: `services/essay_lifecycle_service/`
- **Issues**:
  - Various error handling patterns across implementations
  - No consistent error propagation strategy

#### 6. Batch Orchestrator Service ❌ MIXED PATTERNS

- **Pattern**: Mix of error handling approaches
- **Location**: `services/batch_orchestrator_service/`
- **Issues**:
  - Database models use `error_message` fields
  - Various error handling patterns in implementations

#### 7. Result Aggregator Service ❌ MIXED PATTERNS

- **Pattern**: Mix of error handling approaches with some modern elements
- **Location**: `services/result_aggregator_service/`
- **Issues**:
  - Some use of error_message fields
  - Inconsistent error propagation

## Modern Pattern Analysis

### HuleEduError Exception Hierarchy

**Core Components:**

```python
# From common_core/models/error_models.py
class ErrorDetail(BaseModel):
    error_code: ErrorCode
    message: str
    correlation_id: UUID
    timestamp: datetime
    service: str
    operation: str
    details: dict[str, Any] = Field(default_factory=dict)
    stack_trace: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

# From huleedu_service_libs/error_handling/huleedu_error.py
class HuleEduError(Exception):
    def __init__(self, error_detail: ErrorDetail) -> None:
        # Automatic OpenTelemetry integration
        # Correlation ID tracking
        # Structured error details
```

**Factory Functions Pattern:**

```python
# From huleedu_service_libs/error_handling/factories.py
def raise_validation_error(
    service: str,
    operation: str,
    field: str,
    message: str,
    correlation_id: UUID,
    value: Optional[Any] = None,
    **additional_context: Any,
) -> NoReturn:
```

**Service-Specific Factories:**

- `class_management_factories.py` (EXISTS)
- `file_validation_factories.py` (EXISTS)
- `llm_provider_factories.py` (EXISTS)

### Observability Integration

**OpenTelemetry Features:**

- Automatic span recording on error creation
- Error attributes added to traces
- Correlation ID propagation
- Status code setting

**Logging Integration:**

- Structured error details in logs
- Correlation ID context
- Error categorization

## Gap Analysis

### Current vs Modern Pattern Comparison

| Service | Current Pattern | Error Fields | Correlation ID | OpenTelemetry | Migration Complexity |
|---------|----------------|--------------|----------------|---------------|---------------------|
| LLM Provider | ✅ HuleEduError | ✅ ErrorDetail | ✅ Yes | ✅ Yes | COMPLETED |
| CJ Assessment | ⚠️ Mixed | ❌ Custom | ⚠️ Partial | ⚠️ Partial | MEDIUM |
| Class Management | ❌ Custom Exceptions | ❌ .message | ❌ No | ❌ No | HIGH |
| File Service | ❌ ValidationResult | ❌ error_message | ❌ No | ❌ No | HIGH |
| Batch Conductor | ❌ Tuple Returns | ❌ String messages | ❌ No | ❌ No | MEDIUM |
| Spell Checker | ❌ Basic | ❌ Strings | ❌ No | ❌ No | LOW |
| Essay Lifecycle | ❌ Mixed | ❌ Various | ❌ No | ❌ No | MEDIUM |
| Batch Orchestrator | ❌ Mixed | ❌ error_message | ❌ No | ❌ No | MEDIUM |
| Result Aggregator | ❌ Mixed | ❌ error_message | ❌ No | ❌ No | MEDIUM |

### Anti-Patterns to Eliminate

1. **Tuple Returns**: `return False, "error message"`
2. **Custom Exception .message**: `e.message` attribute access
3. **String Error Fields**: `error_message: str` in models
4. **Inconsistent Error Codes**: String-based vs enum-based codes
5. **No Correlation Tracking**: Missing request tracing
6. **No Observability**: No OpenTelemetry integration

## Service-by-Service Migration Plan

### Phase 1: Foundation Services (LOW Complexity)

#### 1.1 Spell Checker Service

**Complexity**: LOW
**Estimated Effort**: 1 development cycle
**Files to Modify**:

- `services/spellchecker_service/repository_protocol.py`
  - Replace method signatures to raise HuleEduError instead of returning tuples
- `services/spellchecker_service/implementations/spell_repository_postgres_impl.py`
  - Replace try/catch blocks to use `raise_processing_error`
- `services/spellchecker_service/protocol_implementations/`
  - Update error handling in all implementations

**Migration Steps**:

1. Add imports for HuleEduError factories
2. Replace string error returns with structured exceptions
3. Add correlation ID parameters to methods
4. Update protocol signatures
5. Test error propagation

### Phase 2: Medium Complexity Services

#### 2.1 Batch Conductor Service

**Complexity**: MEDIUM
**Estimated Effort**: 2 development cycles
**Files to Modify**:

- `services/batch_conductor_service/protocols.py`
  - Update `validate_pipeline_compatibility` signature: `async def validate_pipeline_compatibility(pipeline_name: str, batch_metadata: dict | None = None) -> None`
- `services/batch_conductor_service/implementations/pipeline_rules_impl.py`
  - Replace `return False, "error"` with `raise_validation_error`
  - Replace `return True, None` with simple return
- `services/batch_conductor_service/implementations/pipeline_resolution_service_impl.py`
  - Convert tuple returns to exceptions

#### 2.2 Essay Lifecycle Service  

**Complexity**: MEDIUM
**Estimated Effort**: 2 development cycles
**Files to Modify**:

- Survey and catalog current error handling patterns
- Replace with standardized HuleEduError approach
- Add correlation ID tracking throughout

#### 2.3 Batch Orchestrator Service

**Complexity**: MEDIUM  
**Estimated Effort**: 2 development cycles
**Files to Modify**:

- `services/batch_orchestrator_service/models_db.py`
  - Remove `error_message` fields from database models
  - Replace with `error_details` JSON field if needed
- Update all implementations to use HuleEduError

#### 2.4 Result Aggregator Service

**Complexity**: MEDIUM
**Estimated Effort**: 2 development cycles
**Files to Modify**:

- Replace error_message patterns with HuleEduError
- Add correlation ID tracking
- Update API error responses

### Phase 3: High Complexity Services

#### 3.1 File Service

**Complexity**: HIGH
**Estimated Effort**: 3 development cycles
**Files to Modify**:

- `services/file_service/validation_models.py`

  ```python
  # BEFORE
  class ValidationResult(BaseModel):
      is_valid: bool
      error_code: str | None = None
      error_message: str | None = None
      warnings: list[str] = []
  
  # AFTER - Remove ValidationResult, use direct exceptions
  # Validation functions will raise FileValidationError directly
  ```

- `services/file_service/core_logic.py`
  - Replace ValidationResult creation with exception raising
  - Use `raise_file_validation_error` factories
- `services/file_service/content_validator.py`
  - Convert validation logic to exception-based
- `services/file_service/implementations/batch_state_validator.py`
  - Replace `(bool, str)` returns with exceptions

**Migration Strategy**:

1. Create comprehensive file validation error factories
2. Replace ValidationResult with direct exception raising
3. Update API error handling to catch HuleEduError
4. Maintain user-friendly error messages through ErrorDetail

#### 3.2 Class Management Service

**Complexity**: HIGH
**Estimated Effort**: 3 development cycles
**Files to Modify**:

- `services/class_management_service/exceptions.py`

  ```python
  # COMPLETE REPLACEMENT - Remove entire custom hierarchy
  # Replace with imports from huleedu_service_libs.error_handling
  ```

- `services/class_management_service/api/class_routes.py`

  ```python
  # BEFORE
  except CourseNotFoundError as e:
      return jsonify({"error": e.message, "error_code": e.error_code}), 400
  
  # AFTER
  except HuleEduError as e:
      return jsonify({"error": e.error_detail.model_dump()}), 400
  ```

- `services/class_management_service/implementations/`
  - Replace custom exception raising with factory functions
  - Add correlation ID parameters

### Phase 4: Mixed Pattern Services

#### 4.1 CJ Assessment Service

**Complexity**: MEDIUM (Already partially modern)
**Estimated Effort**: 2 development cycles
**Files to Modify**:

- `services/cj_assessment_service/exceptions.py`
  - Remove custom `CJAssessmentError` hierarchy
  - Replace with imports and usage of standard HuleEduError
- Update all error handling to use modern factories

## Required Infrastructure Updates

### Service Library Enhancements

#### Error Handling Factories

**Create additional service-specific factories as needed:**

- Batch conductor error factories
- Essay lifecycle error factories
- Spell checker error factories

#### Quart Integration

**File**: `services/libs/huleedu_service_libs/error_handling/quart_handlers.py`

- Enhance error handler to work with HuleEduError
- Standardize HTTP status code mapping
- Ensure proper error response formatting

### Database Schema Updates

#### Services with error_message Fields

1. **Batch Orchestrator Service**: Remove error_message columns
2. **Result Aggregator Service**: Update error storage
3. **Any other services**: Survey and update database models

### API Response Standardization

#### Consistent Error Response Format

```json
{
  "error": {
    "error_code": "VALIDATION_ERROR",
    "message": "Required field 'course_codes' is missing",
    "correlation_id": "123e4567-e89b-12d3-a456-426614174000",
    "timestamp": "2025-07-12T10:30:00Z",
    "service": "class_management_service",
    "operation": "register_new_class",
    "details": {
      "field": "course_codes"
    }
  }
}
```

## Integration with Observability Stack

### OpenTelemetry Integration

- All HuleEduError instances automatically record to spans
- Error attributes added to traces
- Correlation ID propagation maintained

### Structured Logging

- Use `huleedu_service_libs.logging_utils`
- Include correlation ID in log context
- Structured error details in log entries

### Metrics Integration

- Error count metrics by service and error_code
- Error rate monitoring
- Observability dashboard updates

## Migration Strategy

### Sequential Migration Approach

1. **Infrastructure First**: Complete any missing error factories
2. **Low Complexity**: Spell Checker Service (foundation validation)
3. **Medium Complexity**: Batch services, Essay Lifecycle, Result Aggregator
4. **High Complexity**: File Service, Class Management Service  
5. **Cleanup**: CJ Assessment Service final standardization

### Risk Mitigation

- **Service-by-Service**: One service at a time with full testing
- **Backward Compatibility**: Maintain API response compatibility during transition
- **Rollback Plan**: Each service can be reverted independently
- **Testing**: Comprehensive test coverage for error scenarios

### Validation Criteria

Per service completion requirements:

- ✅ All tuple returns eliminated
- ✅ All custom .message/.error_code eliminated  
- ✅ All HuleEduError factory usage implemented
- ✅ Correlation ID tracking added
- ✅ Service tests pass with new error handling
- ✅ API error responses validated
- ✅ No degradation in error user experience

## Implementation Timeline

### Phase 1: Spell Checker Service (Week 1)

- Complete migration and validation
- Establish migration patterns

### Phase 2: Medium Complexity Services (Weeks 2-4)

- Batch Conductor Service
- Essay Lifecycle Service
- Batch Orchestrator Service
- Result Aggregator Service

### Phase 3: High Complexity Services (Weeks 5-7)

- File Service
- Class Management Service

### Phase 4: Final Standardization (Week 8)

- CJ Assessment Service cleanup
- Platform-wide validation
- Documentation updates

## Success Metrics

### Code Quality Metrics

- **Zero tuple returns** for error handling
- **Zero .message/.error_code** attribute access
- **100% HuleEduError usage** for all error scenarios
- **Complete correlation ID coverage**

### Observability Metrics

- **Error trace visibility** across all services
- **Structured error logging** implementation
- **Error rate monitoring** capability

### Developer Experience

- **Consistent error patterns** across all services
- **Improved debugging** with correlation IDs
- **Better error categorization** with ErrorCode enums

---

**Task Status**: Analysis Complete - Implementation Plan Ready  
**Priority**: High (Platform Standardization)  
**Complexity**: Platform-wide (9 services requiring changes)  
**Estimated Total Effort**: 8 development cycles  

**Architectural Impact**: ⭐⭐⭐⭐⭐ **PLATFORM TRANSFORMATION**

- Establishes consistent error handling excellence
- Enables comprehensive observability and debugging
- Creates foundation for reliable error reporting and monitoring

## ULTRATHINK: ERROR_DETAIL vs ERROR_MESSAGE MIGRATION

### Problem Definition

**Current State**: Services use inconsistent error field naming (`error_message`, `message`, custom attributes) preventing standardized error handling and observability integration.

**Target State**: All services use standardized `ErrorDetail` model with structured `error_detail` field, eliminating all `error_message` variations.

**Non-Negotiable Requirements**:

- NO dual population transition period
- CLEAN refactor approach without backwards compatibility
- ALL files, models, protocols, and methods must be updated atomically per service

### COMPREHENSIVE FILE INVENTORY

#### 1. DATABASE MODELS (`models_db.py`) - ERROR_MESSAGE FIELD ELIMINATION

**Batch Orchestrator Service**:

- File: `services/batch_orchestrator_service/models_db.py`
- Issues: Database columns with `error_message` fields
- Migration: Replace with `error_details` JSON column or eliminate entirely
- Impact: Database schema migration required

**Spell Checker Service**:

- File: `services/spellchecker_service/models_db.py`
- Issues: Potential error_message fields in job/token models
- Migration: Replace with structured error storage or remove
- Impact: Database schema changes

**Essay Lifecycle Service**:

- File: `services/essay_lifecycle_service/models_db.py`
- Issues: Error message fields in state models
- Migration: Convert to structured error details
- Impact: State machine error handling changes

**Result Aggregator Service**:

- File: `services/result_aggregator_service/models_db.py`
- Issues: Error message fields in aggregation models
- Migration: Replace with structured error tracking
- Impact: Aggregation error reporting changes

#### 2. API MODELS (`api_models.py`, `validation_models.py`) - ERROR_MESSAGE ELIMINATION

**File Service**:

- File: `services/file_service/validation_models.py`

  ```python
  # BEFORE
  class ValidationResult(BaseModel):
      error_message: str | None = None
  
  # AFTER - COMPLETE ELIMINATION
  # Replace entire ValidationResult pattern with direct HuleEduError raising
  ```

- File: `services/file_service/api_models.py`
- Migration: Remove ValidationResult usage entirely
- Impact: API response structure changes

**Class Management Service**:

- File: `services/class_management_service/api_models.py`
- Issues: Potential error response models with error_message
- Migration: Standardize on ErrorDetail response format
- Impact: API contract changes

#### 3. PROTOCOL DEFINITIONS - SIGNATURE UPDATES

**All Services Requiring Protocol Updates**:

**File Service**:

- File: `services/file_service/protocols.py`

  ```python
  # BEFORE
  async def validate_content(self, ...) -> ValidationResult
  
  # AFTER  
  async def validate_content(self, ...) -> None  # Raises HuleEduError
  ```

**Batch Conductor Service**:

- File: `services/batch_conductor_service/protocols.py`

  ```python
  # BEFORE
  async def validate_pipeline_compatibility(...) -> tuple[bool, str | None]
  
  # AFTER
  async def validate_pipeline_compatibility(...) -> None  # Raises HuleEduError
  ```

**Class Management Service**:

- File: `services/class_management_service/protocols.py`
- Updates: All protocol methods must use HuleEduError pattern
- Impact: Protocol contract breaking changes

#### 4. IMPLEMENTATION FILES - ERROR HANDLING LOGIC

**File Service Core Logic**:

- File: `services/file_service/core_logic.py`
- Lines: 105, 160, 198, 202 (error_message usage)
- Migration: Replace with `raise_file_validation_error` calls
- Impact: Core validation logic restructure

**File Service Content Validator**:

- File: `services/file_service/content_validator.py`
- Issues: Creates ValidationResult with error_message
- Migration: Direct exception raising instead
- Impact: Validation flow changes

**File Service Batch State Validator**:

- File: `services/file_service/implementations/batch_state_validator.py`
- Lines: 56, 59, 64, 76, 83, 105 (tuple returns with error messages)
- Migration: Replace with HuleEduError raising
- Impact: Batch validation logic changes

**Class Management Service Exceptions**:

- File: `services/class_management_service/exceptions.py`
- Lines: 12, 14 (`.message` attribute)
- Migration: COMPLETE FILE REPLACEMENT with HuleEduError imports
- Impact: Exception hierarchy elimination

**Class Management Service API Routes**:

- File: `services/class_management_service/api/class_routes.py`
- Lines: 62, 71, 80, 211, 220, 229 (`e.message` access)
- Migration: Replace with `e.error_detail.message`
- Impact: API error response changes

#### 5. TEST FILES - ERROR_MESSAGE ASSERTIONS

**File Service Tests**:

- File: `services/file_service/tests/unit/test_content_validator.py`
- Lines: 41, 49-51, 68-69, 79-82, 92-95, 163-164, 174-175, 210-211
- Issues: Assertions on `result.error_message`
- Migration: Replace with exception testing patterns
- Impact: Test methodology changes

**File Service Test Protocols**:

- File: `services/file_service/tests/unit/test_validation_protocols.py`
- Line: 52 (`error_message="Content is empty"`)
- Migration: Remove ValidationResult mock patterns
- Impact: Mock strategy changes

#### 6. SERVICE IMPLEMENTATION FILES

**CJ Assessment Service**:

- File: `services/cj_assessment_service/implementations/retry_manager_impl.py`
- Lines: 211, 291 (`.message` access on exceptions)
- Migration: Replace with `.error_detail.message`
- Impact: Retry logic error handling

**LLM Provider Service**:

- File: `services/llm_provider_service/implementations/event_publisher_impl.py`
- Line: 127 (`error_message=metadata.get("error_message")`)
- Migration: Replace with structured error details
- Impact: Event publishing error metadata

### SERVICE-SPECIFIC MIGRATION SPECIFICATIONS

#### File Service - COMPLETE VALIDATION FRAMEWORK REFACTOR

**Phase 1: Model Elimination**

```python
# DELETE ENTIRELY
# services/file_service/validation_models.py
class ValidationResult(BaseModel):
    is_valid: bool
    error_code: str | None = None
    error_message: str | None = None  # ← TARGET FOR ELIMINATION
    warnings: list[str] = []
```

**Phase 2: Core Logic Transformation**

```python
# services/file_service/core_logic.py
# BEFORE
validation_result = ValidationResult(
    is_valid=False,
    error_message=f"Failed to store raw file: {storage_error}"
)

# AFTER
raise_file_validation_error(
    service="file_service",
    operation="store_raw_file",
    validation_type="RAW_STORAGE_FAILED",
    message=f"Failed to store raw file: {storage_error}",
    correlation_id=correlation_id,
    file_name=file_name
)
```

**Phase 3: Protocol Signature Updates**

```python
# services/file_service/protocols.py
# BEFORE
async def validate_content(self, content: str, filename: str) -> ValidationResult

# AFTER  
async def validate_content(self, content: str, filename: str, correlation_id: UUID) -> None
```

#### Class Management Service - EXCEPTION HIERARCHY REPLACEMENT

**Phase 1: Complete Exception File Replacement**

```python
# services/class_management_service/exceptions.py
# BEFORE - DELETE ENTIRELY
class ClassManagementServiceError(Exception):
    def __init__(self, message: str, error_code: str | None = None) -> None:
        self.message = message  # ← TARGET FOR ELIMINATION
        self.error_code = error_code

# AFTER - COMPLETE REPLACEMENT
from huleedu_service_libs.error_handling import (
    raise_validation_error,
    raise_resource_not_found,
    HuleEduError
)
from common_core.error_enums import ClassManagementErrorCode
```

**Phase 2: API Route Error Handling**

```python
# services/class_management_service/api/class_routes.py
# BEFORE
except CourseNotFoundError as e:
    return jsonify({"error": e.message, "error_code": e.error_code}), 400

# AFTER
except HuleEduError as e:
    return jsonify({"error": e.error_detail.model_dump()}), 400
```

### IMPLEMENTATION SEQUENCE

#### Service-by-Service Atomic Migration

**1. File Service (3 development cycles)**

- Week 1: ValidationResult elimination + core logic refactor
- Week 2: Protocol updates + implementation changes  
- Week 3: Test migration + API response validation

**2. Class Management Service (3 development cycles)**

- Week 1: Exception hierarchy replacement
- Week 2: API route error handling updates
- Week 3: Implementation + repository error handling

**3. Batch Conductor Service (2 development cycles)**

- Week 1: Tuple return elimination + protocol updates
- Week 2: Implementation migration + testing

**4. Database Model Services (2-3 cycles each)**

- Batch Orchestrator, Spell Checker, Essay Lifecycle, Result Aggregator
- Schema migrations + model updates + implementation changes

### VALIDATION CRITERIA

#### Per-Service Completion Checklist

**File-Level Validation**:

- ✅ NO `error_message` fields in any models
- ✅ NO `.message` attribute access in code
- ✅ NO ValidationResult or similar patterns
- ✅ NO tuple returns for error handling
- ✅ ALL error handling uses HuleEduError pattern
- ✅ ALL methods include correlation_id parameters

**Functional Validation**:

- ✅ Service tests pass with new error handling
- ✅ API error responses maintain user experience
- ✅ Error details properly propagated to observability
- ✅ Correlation IDs tracked through error flows

**Integration Validation**:

- ✅ Cross-service error handling compatibility
- ✅ Observability stack receives structured errors
- ✅ Monitoring dashboards display error categories
- ✅ No regression in error visibility or debugging

### RISK MITIGATION

#### Breaking Change Management

- **API Compatibility**: Maintain user-facing error message quality
- **Database Migration**: Careful schema migration for error storage
- **Service Dependencies**: Coordinate changes affecting service interactions

#### Rollback Strategy

- **Service-Level**: Each service can be reverted independently
- **Database**: Schema rollback procedures for error field changes
- **API**: Error response format rollback capability

---

**ULTRATHINK SUMMARY**: Complete elimination of `error_message` patterns across 9 services requiring atomicmigration of 40+ files, with database schema changes, protocol updates, and comprehensive test migration. Zero dual-population, clean architectural refactor targeting structured `ErrorDetail` excellence.
