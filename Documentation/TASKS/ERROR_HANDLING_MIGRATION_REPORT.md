# Error Handling Migration Report - Exception-Based Pattern

**Generated**: 2025-07-10  
**Scope**: Full codebase analysis for migration to exception-based error handling

## Executive Summary

This report identifies all error handling patterns across the HuleEdu codebase that need migration to the new exception-based system. The analysis shows that while CJ Assessment Service is the primary user of `ErrorDetail`, several other services use various error handling patterns that should be standardized.

## Migration Categories

### 1. Tuple Return Patterns with ErrorDetail

**CJ Assessment Service** - Primary user of ErrorDetail tuple returns:

#### Protocols (`services/cj_assessment_service/protocols.py`)

- Line 23: `async def fetch_content(...) -> tuple[str | None, ErrorDetail | None]`
- Line 44: `async def with_retry(...) -> tuple[Any, ErrorDetail | None]`
- Line 65: `async def complete_assessment(...) -> tuple[dict[str, Any] | None, ErrorDetail | None]`

#### Implementations

**`content_client_impl.py`**

- Lines 41, 60: Returns `tuple[str | None, ErrorDetail | None]`
- Lines 70-86, 98-114, 122-154, 157-182, 185-226: Direct ErrorDetail instantiation
- Pattern: Creates ErrorDetail objects directly instead of using factories

**`llm_provider_service_client.py`**

- Lines 104, 163, 258, 310, 393, 446, 601, 710, 721: Returns `tuple[dict[str, Any] | None, ErrorDetail | None]`
- Multiple direct ErrorDetail instantiations throughout

**`retry_manager_impl.py`**

- Lines 153, 171, 192, 195: Returns tuples with ErrorDetail
- Line 139: Direct ErrorDetail instantiation

### 2. String-Based Error Fields

**File Service** (`services/file_service/`)

- `validation_models.py` Line 46: `error_message: str | None = None`
- `core_logic.py` Lines 105, 160, 215: `validation_error_message` field usage
- `content_validator.py` Lines 50, 59, 70: Returns ValidationResult with `error_message`

**Common Core Events**

- `common_core/src/common_core/events/file_events.py` Line 60: `validation_error_message: str`
- `common_core/src/common_core/events/llm_provider_events.py` Line 30: `error_message: str | None`

### 3. Database Models with Error Fields

**Spell Checker Service**

- `models_db.py` Line 64: `error_message: Mapped[str | None]`
- `alembic/versions/20250630_0001_initial_schema.py` Line 32: `sa.Column("error_message", sa.Text())`

**Batch Orchestrator Service**

- `models_db.py` Lines 80, 143-144: `error_details` and `error_message` fields
- `alembic/versions/20250706_0001_initial_schema.py` Line 82: `sa.Column("error_message", sa.Text())`

**CJ Assessment Service**

- `models_db.py` Lines 160-164: Structured error fields (error_code, error_details, etc.)
- Already partially migrated to structured approach

### 4. LLM Provider Service Error Handling

The LLM Provider Service uses a mixed approach with `error_message` fields:

**Provider Implementations** (anthropic, openai, google, openrouter)

- All use dictionaries with `error_message` keys
- Example patterns in lines 70, 112, 204, 249, 298, etc.

**Event Publishing**

- `event_publisher_impl.py` Line 127: `error_message=metadata.get("error_message")`

**Queue Models**

- `queue_models.py` Lines 84, 195: `error_message: Optional[str]`
- `internal_models.py` Line 68: `error_message: str`

### 5. Result Aggregator Service

**Event Processor**

- `event_processor_impl.py` Line 111: Creates metadata with `error_message`

**Tests**

- Multiple test files use `error_message` in test data and assertions

### 6. Error Context Usage

No usage of `ErrorContext` found in the codebase (already cleaned up).

## Service-by-Service Migration Requirements

### CJ Assessment Service (PRIMARY - Most Complex)

1. **Protocols**: Update all protocol signatures to remove tuple returns
2. **Implementations**:
   - Replace direct ErrorDetail instantiation with factory methods
   - Convert tuple returns to exception raising
   - Update retry manager to handle exceptions
3. **Database**: Already has structured error fields

### File Service

1. **Models**: Replace `error_message` in ValidationResult with structured error
2. **Core Logic**: Update validation error handling to use exceptions
3. **Events**: Update FileValidationFailed event structure

### LLM Provider Service

1. **Models**: Replace `error_message` fields with ErrorDetail
2. **Providers**: Standardize error handling across all providers
3. **Queue Processing**: Update error handling in queue models

### Spell Checker Service

1. **Database**: Migrate from `error_message` column to structured error storage
2. **Repository**: Update error handling methods

### Batch Orchestrator Service

1. **Database**: Already has `error_details` JSON field, remove `error_message`
2. **Event Handlers**: Update error handling patterns

### Result Aggregator Service

1. **Event Processing**: Replace string error messages with structured errors

## Migration Priority

1. **Phase 1**: CJ Assessment Service (most complex, primary ErrorDetail user)
2. **Phase 2**: Common Core events and models
3. **Phase 3**: File Service (validation patterns)
4. **Phase 4**: LLM Provider Service (multiple providers)
5. **Phase 5**: Other services (Spell Checker, Batch Orchestrator, Result Aggregator)

## Key Patterns to Replace

1. **Tuple Returns**: `tuple[T | None, ErrorDetail | None]` → Exception raising
2. **Direct Instantiation**: `ErrorDetail(...)` → `ErrorDetail.create_with_context(...)`
3. **String Errors**: `error_message: str` → Structured ErrorDetail
4. **Mixed Fields**: `error_code` + `error_message` → Single ErrorDetail object

## Database Migration Notes

Several services store error information in databases:

- Some use `error_message` text columns
- Some use `error_details` JSON columns
- CJ Assessment already uses structured fields

Recommendation: Standardize on JSON storage of full ErrorDetail objects.
