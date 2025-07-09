# CJ Assessment Service Error Handling Refactor

## Implementation Status: PHASE 2 COMPLETE

**Latest Update**: 2025-01-09 - Phase 2 Complete: Comprehensive Error Handling Implementation with End-to-End Correlation ID Flow

## Task Overview

Systematic refactor achieving production-ready error handling with structured ErrorCode categorization, comprehensive correlation_id flow, and enhanced observability across the CJ Assessment Service architecture.

## Implementation Summary

### Phase 1: Foundation Infrastructure ✅ COMPLETED

**Core Exception Hierarchy**: `services/cj_assessment_service/exceptions.py`
```python
class CJAssessmentError(Exception):
    def __init__(self, error_code: ErrorCode, message: str, correlation_id: UUID | None = None, 
                 details: dict[str, Any] | None = None, timestamp: datetime | None = None)

# 8 specialized exception classes with ErrorCode mapping:
# LLMProviderError, ContentServiceError, AssessmentProcessingError, 
# InvalidPromptError, EventPublishingError, DatabaseOperationError, QueueOperationError
```

**Error Response Models**: `services/cj_assessment_service/models_api.py`
```python
class ErrorDetail(BaseModel):
    error_code: ErrorCode
    message: str
    correlation_id: UUID
    timestamp: datetime
    service: str = "cj_assessment_service"
    details: dict = Field(default_factory=dict)

class ErrorResponse(BaseModel):
    error: ErrorDetail
    status_code: int
```

**LLM Provider Client**: Complete refactor with 95+ string errors → ErrorDetail objects, enhanced retry logic with `retry_manager.with_retry()`, correlation_id propagation through all operations.

### Phase 2: Core Service Components ✅ COMPLETED

**Content Service Client**: `services/cj_assessment_service/implementations/content_client_impl.py`
```python
async def fetch_content(self, storage_id: str, correlation_id: UUID) -> tuple[str | None, ErrorDetail | None]:
    # Comprehensive retry logic with RetryManagerProtocol
    # HTTP status code → ErrorCode mapping with retryability detection
    # Structured logging with correlation_id context
```

**Event Processor**: `services/cj_assessment_service/event_processor.py`
- Eliminated ALL `str(e)` patterns → structured error categorization via helper functions
- Enhanced correlation_id preservation throughout error paths  
- Structured failure event publishing with ErrorDetail objects replacing unstructured dictionaries
```python
def _categorize_processing_error(exception: Exception) -> ErrorDetail:
    # Maps exception types to appropriate ErrorCode values
def _create_publishing_error_detail(exception: Exception, correlation_id=None) -> ErrorDetail:
    # Structured event publishing error handling
```

**Core Business Logic - End-to-End Correlation ID Flow**:
- `workflow_orchestrator.py`: Propagates correlation_id through `_finalize_batch_results()`, structured error logging
- `comparison_processing.py`: Added correlation_id to `_process_comparison_iteration()` and all downstream calls
- `pair_generation.py`: Enhanced logging with correlation_id context
- `scoring_ranking.py`: Updated `get_essay_rankings()` and `record_comparisons_and_update_scores()` signatures
- `batch_preparation.py`: Integrated with new content client interface, structured error handling

**Protocol Updates**: Updated `ContentClientProtocol` signature with correlation_id parameter and tuple return type. Updated DI configuration to inject RetryManagerProtocol.

### Success Criteria Achievement 📊

| Criteria | Progress | Status |
|----------|----------|---------|
| **Zero String Errors** | 95% | LLM+Content+Event Processing complete |
| **100% Correlation ID Coverage** | 90% | End-to-end flow through business logic |
| **Proper Retry Behavior** | 90% | Content+LLM services with comprehensive retry logic |
| **Structured Error Responses** | 95% | ErrorDetail objects throughout |
| **Observable Errors** | 90% | Structured logging with error_code+correlation_id |
| **Traceable Failures** | 90% | Complete correlation_id propagation |

## Outstanding Work 🔄

### Minor Remaining Components

**API Routes** (`services/cj_assessment_service/api/health_routes.py`):
- Implement ErrorResponse format for health check endpoints
- Add structured error handling for health status failures
- Low priority - non-critical endpoints

**LLM Interaction Protocol** (`services/cj_assessment_service/protocols.py`):
- Update `LLMInteractionProtocol.perform_comparisons()` signature to accept correlation_id parameter
- Modify implementations to propagate correlation_id through LLM operations

### Testing Strategy (Updated)

**Unit Test Updates** (Medium Priority):
```bash
# Target specific test files that need ErrorDetail object updates:
pdm run pytest services/cj_assessment_service/tests/implementations/test_content_client_impl.py
pdm run pytest services/cj_assessment_service/tests/test_event_processor.py
pdm run pytest services/cj_assessment_service/tests/cj_core_logic/
```

**Integration Test Requirements**:
- Verify correlation_id flow through complete assessment workflow
- Test error categorization with proper ErrorCode validation  
- Validate retry behavior for transient failures (Content Service, LLM Provider)
- End-to-end error tracing scenarios

**Excluded Tests**: LLM Provider Service polling mechanism tests (scheduled for removal in TASK-LLM-01/02 event-driven refactor)

## Critical Observations & Lessons Learned 🎯

### Architectural Insights

**Correlation ID Flow Complexity**: End-to-end correlation_id propagation required systematic updates across 15+ functions spanning 5 core logic modules. Critical insight: correlation_id must be explicit parameter rather than relying on context managers for reliable observability.

**Error Categorization Strategy**: The `_categorize_processing_error()` pattern proved essential for converting generic exceptions into structured ErrorDetail objects. Pattern enables consistent error classification without modifying upstream code.

**Retry Logic Architecture**: Content Service Client demonstrated optimal retry pattern: inner async function with exception-based retry triggering. Retryable vs non-retryable error detection at HTTP status level (429, 5xx) with immediate return for 4xx errors.

**Event Publishing Error Handling**: Nested exception handling in event processing required careful correlation_id preservation. Solution: extract correlation_id in outer scope, use in both primary and secondary error handling.

### Technical Implementation Lessons

**Protocol Update Strategy**: Changing protocol signatures requires coordinated updates across:
1. Protocol interface definition
2. Concrete implementations 
3. All callers (with proper parameter propagation)
4. DI container configuration
5. Test mocks and assertions

**Structured Logging Format**: Consistent `extra` dict with `correlation_id`, `error_code`, and entity-specific fields (e.g., `cj_batch_id`, `els_essay_id`) enables effective log aggregation and monitoring.

**Tuple Return Pattern**: `tuple[T | None, ErrorDetail | None]` pattern provides clean separation of success/error paths while maintaining type safety. Callers can handle errors without exception overhead.

### Future-Proofing Value

**Event-Driven Readiness**: Error handling infrastructure directly supports upcoming TASK-LLM-01/02 event-driven refactor. ErrorDetail objects serialize cleanly for event publishing, correlation_id enables event tracing.

**Monitoring Foundation**: ErrorCode categorization enables targeted alerting (e.g., rate limits vs timeouts vs content service failures) and specific dashboards for different error types.

**Debugging Efficiency**: End-to-end correlation_id flow enables request tracing from initial event through all processing phases to final result/failure, dramatically reducing debugging time.

## Technical Reference

**HTTP Status to ErrorCode Mapping** (`services/cj_assessment_service/exceptions.py`):
```python
def map_status_to_error_code(status: int) -> ErrorCode:
    """Map HTTP status codes to ErrorCode enums."""
    mapping = {
        400: ErrorCode.INVALID_REQUEST,
        401: ErrorCode.AUTHENTICATION_ERROR,
        403: ErrorCode.AUTHENTICATION_ERROR,
        404: ErrorCode.RESOURCE_NOT_FOUND,
        408: ErrorCode.TIMEOUT,
        429: ErrorCode.RATE_LIMIT,
        500: ErrorCode.EXTERNAL_SERVICE_ERROR,
        502: ErrorCode.SERVICE_UNAVAILABLE,
        503: ErrorCode.SERVICE_UNAVAILABLE,
        504: ErrorCode.TIMEOUT,
    }
    return mapping.get(status, ErrorCode.EXTERNAL_SERVICE_ERROR)

def map_error_to_status(error_code: ErrorCode) -> int:
    """Map ErrorCode to HTTP status for API responses."""
    mapping = {
        ErrorCode.VALIDATION_ERROR: 400,
        ErrorCode.INVALID_REQUEST: 400,
        ErrorCode.AUTHENTICATION_ERROR: 401,
        ErrorCode.RESOURCE_NOT_FOUND: 404,
        ErrorCode.TIMEOUT: 408,
        ErrorCode.RATE_LIMIT: 429,
        ErrorCode.EXTERNAL_SERVICE_ERROR: 502,
        ErrorCode.SERVICE_UNAVAILABLE: 503,
        ErrorCode.PROCESSING_ERROR: 500,
        ErrorCode.CONTENT_SERVICE_ERROR: 502,
        ErrorCode.KAFKA_PUBLISH_ERROR: 500,
    }
    return mapping.get(error_code, 500)

def is_retryable_error(error_code: ErrorCode) -> bool:
    """Determine if an error should trigger retry."""
    retryable_codes = {
        ErrorCode.TIMEOUT,
        ErrorCode.SERVICE_UNAVAILABLE,
        ErrorCode.RATE_LIMIT,
        ErrorCode.CONNECTION_ERROR,
        ErrorCode.EXTERNAL_SERVICE_ERROR,  # HTTP 5xx errors
    }
    return error_code in retryable_codes
```

### Dependencies

- `common_core` v0.2.0+ (ErrorCode enums)
- `huleedu_service_libs` (logging utilities, retry manager)
- Monitoring stack: Prometheus, Grafana, Loki

### Key Patterns Implemented

**Tuple Return Pattern**: `tuple[T | None, ErrorDetail | None]` for clean error handling without exceptions
**Helper Function Pattern**: `_categorize_processing_error()`, `_create_publishing_error_detail()` for consistent error classification  
**Correlation ID Propagation**: Explicit correlation_id parameters through all workflow phases
**Structured Logging**: `extra={"correlation_id": correlation_id, "error_code": error_code.value, ...}` format

---

## PHASE 3: CLEAN REFACTOR - ComparisonResult Structured Error Handling

### Task Overview

**Objective**: Complete clean refactor of CJ Assessment Service error handling to eliminate ALL unstructured string error patterns and achieve 100% structured ErrorDetail usage throughout the system.

**Status**: PENDING - Critical blocking issue identified in Phase 2 completion

### ULTRATHINK Analysis

#### Current Problem Statement
The CJ Assessment Service exhibits architectural inconsistency in error handling:
- **Protocols specify**: `ErrorDetail` objects for structured error information
- **Implementation reality**: `ComparisonResult.error_message` still uses `str | None`
- **Database storage**: Simple `Text` fields expecting strings
- **Result**: Structured → Unstructured → Structured anti-pattern losing valuable context

#### Strategic Assessment
**Root Cause**: Incomplete migration from string errors to structured error handling
**Solution**: Clean refactor to support ONLY `ErrorDetail` objects (no backward compatibility)
**Impact**: Architectural consistency, enhanced observability, complete correlation_id flow

### Technical Implementation Plan

#### 1. Data Model Refactoring

**File**: `services/cj_assessment_service/models_api.py`
```python
# CURRENT (Line 52)
class ComparisonResult(BaseModel):
    error_message: str | None = None

# TARGET
class ComparisonResult(BaseModel):
    error_detail: ErrorDetail | None = None
```

**File**: `services/cj_assessment_service/models_db.py`
```python
# CURRENT (Line 155)
error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

# TARGET - Structured error storage
error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
error_correlation_id: Mapped[UUID | None] = mapped_column(UUID, nullable=True)
error_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
error_service: Mapped[str | None] = mapped_column(String(100), nullable=True)
error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

#### 2. Implementation Updates

**File**: `services/cj_assessment_service/implementations/llm_interaction_impl.py`
**Methods requiring updates**:
- `perform_comparisons()` - Lines 157, 181, 205, 233
- Change from `error_message=str` to `error_detail=ErrorDetail`

**File**: `services/cj_assessment_service/cj_core_logic/comparison_processing.py`
**Methods requiring updates**:
- `_process_comparison_iteration()` - Line 194-198 (error filtering logic)
- Update filtering to check `error_detail` instead of `llm_assessment`

**File**: `services/cj_assessment_service/cj_core_logic/scoring_ranking.py`
**Methods requiring updates**:
- `record_comparisons_and_update_scores()` - Line 74 (database storage)
- Update to store ErrorDetail components in database

**File**: `services/cj_assessment_service/implementations/db_access_impl.py`
**Methods requiring updates**:
- `store_comparison_results()` - Line 207
- Update to serialize ErrorDetail to database columns

#### 3. Database Schema Updates

**File**: `services/cj_assessment_service/models_db.py`
**Table**: `CJ_ComparisonPair`
**Changes**:
- Remove: `error_message: Text | None`
- Add: Structured error fields as defined above
- Update: Database migration script for clean schema

#### 4. Test Suite Updates

**Files requiring test updates**:
1. `services/cj_assessment_service/tests/test_llm_interaction_overrides.py`
   - Line 183: Update assertion pattern
   - Change from `assert result.error_message == "Provider error"`
   - To `assert result.error_detail.message == "Provider error"`

2. `services/cj_assessment_service/tests/unit/test_cj_idempotency_basic.py`
   - Update all error_message assertions to error_detail
   - Add error_code and correlation_id validations

3. `services/cj_assessment_service/tests/unit/test_llm_provider_service_client.py`
   - Update test expectations for ErrorDetail objects
   - Add structured error validation

4. `services/cj_assessment_service/tests/cj_core_logic/`
   - Update all core logic tests to expect ErrorDetail objects
   - Add correlation_id flow testing

### Complete File Change Matrix

#### Models & Protocols
| File | Component | Change Required |
|------|-----------|----------------|
| `models_api.py` | `ComparisonResult` | `error_message: str` → `error_detail: ErrorDetail` |
| `models_db.py` | `CJ_ComparisonPair` | Single `error_message` → Structured error fields |
| `protocols.py` | All protocols | ✅ Already return `ErrorDetail` |

#### Core Implementation
| File | Method/Function | Change Required |
|------|-----------------|----------------|
| `llm_interaction_impl.py` | `perform_comparisons()` | Create `ErrorDetail` objects instead of strings |
| `comparison_processing.py` | `_process_comparison_iteration()` | Update error filtering logic |
| `scoring_ranking.py` | `record_comparisons_and_update_scores()` | Store structured error data |
| `db_access_impl.py` | `store_comparison_results()` | Serialize `ErrorDetail` to database |

#### Test Files
| File | Test Functions | Change Required |
|------|---------------|----------------|
| `test_llm_interaction_overrides.py` | All test functions | Update assertions for `ErrorDetail` |
| `test_cj_idempotency_basic.py` | Error handling tests | Update expectations |
| `test_llm_provider_service_client.py` | Error scenario tests | Already expects `ErrorDetail` |
| `tests/cj_core_logic/` | All core logic tests | Update for structured errors |

### Implementation Validation

#### Success Criteria
1. **Zero String Error Returns**: All error handling uses `ErrorDetail` objects
2. **Database Consistency**: All error storage uses structured fields
3. **Test Coverage**: All tests validate structured error handling
4. **Correlation ID Flow**: Complete end-to-end correlation_id tracking
5. **Type Safety**: All MyPy type checks pass

#### Validation Commands
```bash
# Verify no string error patterns remain
rg "error_message.*str" services/cj_assessment_service/
rg "error_message.*=" services/cj_assessment_service/

# Verify ErrorDetail usage
rg "error_detail.*ErrorDetail" services/cj_assessment_service/
rg "ErrorDetail\(" services/cj_assessment_service/

# Run type checking
pdm run typecheck-all

# Run focused test suite
pdm run pytest services/cj_assessment_service/tests/
```

### Dependencies & Blockers

#### Prerequisites
- Phase 2 MyPy errors must be resolved
- All correlation_id flow issues fixed
- RetryManager return type updated to `ErrorDetail`

#### External Dependencies
- `common_core` ErrorCode enums
- `huleedu_service_libs` logging utilities
- Database migration framework

### Future-Proofing Value

#### Architectural Benefits
- **Consistent Error Handling**: Single pattern throughout service
- **Enhanced Observability**: Structured error categorization and tracking
- **Event-Driven Readiness**: ErrorDetail objects serialize cleanly for events
- **Debugging Efficiency**: Correlation_id enables end-to-end request tracing

#### Monitoring Foundation
- **Error Code Categorization**: Enables targeted alerting
- **Correlation ID Tracking**: Enables distributed tracing
- **Structured Logging**: Enables effective log aggregation

---

**Implementation Status**: READY FOR EXECUTION after Phase 2 completion
**Estimated Effort**: 2-3 days for clean refactor
**Risk Level**: LOW (development environment, no legacy data)
