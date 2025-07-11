# CJ Assessment Service Exception Migration - Handoff Prompt

Start of Conversation Prompt for New Claude Instance

You are inheriting a codebase where exception-based error handling has been successfully implemented. The HuleEdu platform is NOT DEPLOYED - there are NO backward compatibility constraints. This is a CLEAN REFACTOR environment.

## CRITICAL CONTEXT

The platform has transitioned from tuple-based error returns to a pure exception-based error handling system with:

1. **ErrorDetail** (pure data model in common_core) - contains ONLY fields, NO methods
2. **HuleEduError** (exception wrapper in service libs) - wraps ErrorDetail for transport
3. **Factory functions** - standardized error creation that raises exceptions
4. **Utility modules** - separate modules for creation logic and formatting

## MIGRATION STATUS: 75% COMPLETE

**✅ ARCHITECTURAL FOUNDATIONS COMPLETED:**

- Enhanced ErrorDetail with full observability fields
- HuleEduError exception class with OpenTelemetry integration
- Complete factory function library organized by domain
- Quart integration handlers and testing utilities
- Error handling rule documented (048-structured-error-handling-standards.mdc)

**✅ CJ ASSESSMENT SERVICE - PHASES 1-3 COMPLETED:**

- Phase 1: Protocol signatures updated (3 methods) ✅
- Phase 2: Retry manager fully migrated to exception-based pattern ✅
- Phase 3: Content client implementation migrated ✅

**🔄 CURRENT TASK: LLM Provider Service Client Migration**

- 9 methods need migration from tuple returns to exceptions
- This is the last complex implementation requiring architectural decisions

**📋 REMAINING: Agent-Driven Mechanical Tasks**

- Phase 4: 12 direct ErrorDetail instantiations need factory replacement (exact inventory below)
- Phase 5: Test updates to use exception-based patterns

## YOUR IMMEDIATE TASK

### Step 1: Understand the Current Architecture

**Read these critical files in order**:

- `/documentation/TASKS/TASK-003-exception-based-error-handling.md` - the main task document
- `/documentation/TASKS/ERROR_HANDLING_MIGRATION_REPORT.md` - analysis of what needs migration
- `/documentation/TASKS/CJ_ASSESSMENT_SERVICE_MIGRATION_CHECKLIST.md` - specific service migration plan
- `/.cursor/rules/048-structured-error-handling-standards.mdc` - the error handling rule
- `/common_core/src/common_core/models/error_models.py` - pure ErrorDetail model
- `/services/libs/huleedu_service_libs/error_handling/` - all files in this directory

### Step 2: Research Current State with Agents

**Launch these research agents in parallel**:

1. **Agent 1**: Analyze LLM Provider Service Client tuple returns
   - Task: "Find all tuple return signatures in llm_provider_service_client.py that need migration"
   - Focus: Method signatures, line numbers, return patterns
   - Expected: 9 methods with specific locations

2. **Agent 2**: Map ErrorDetail instantiations to factory functions
   - Task: "Map all direct ErrorDetail instantiations in CJ Assessment Service to appropriate factory functions"
   - Focus: ErrorCode usage patterns, required factory function mapping
   - Expected: 12 instances with clear factory mapping

3. **Agent 3**: Analyze LLM interaction dependencies
   - Task: "Understand how llm_interaction_impl.py calls the LLM provider client and what needs updating"
   - Focus: Call sites, error handling patterns, integration points
   - Expected: Clear dependency chain and update requirements

### Step 3: Complete LLM Provider Client Migration

**Current Type Error to Resolve:**

```text
services/cj_assessment_service/implementations/llm_provider_service_client.py:95: error: Return type incompatible with supertype "LLMProviderProtocol"
```

**9 Methods Requiring Migration:**

Based on previous analysis:

- Line 104: `generate_comparison()` (main protocol method)
- Line 163: `make_request()` (inner function)
- Line 258: `_handle_immediate_response()`
- Line 310: `_handle_queued_response()`
- Line 393: `_handle_error_response()`
- Line 446: `_poll_for_results()`
- Line 603: `make_status_request()` (inner function)
- Line 712: `_retrieve_queue_result()`
- Line 723: `make_result_request()` (inner function)

**Migration Pattern:**

```python
# BEFORE (tuple return)
async def method() -> tuple[dict[str, Any] | None, ErrorDetail | None]:
    if error_condition:
        error_detail = ErrorDetail(...)  # Direct instantiation
        return None, error_detail
    return result, None

# AFTER (exception-based)
async def method() -> dict[str, Any]:
    if error_condition:
        raise_external_service_error(  # Use factory
            service="cj_assessment_service",
            operation="method_name",
            external_service="llm_provider_service",
            message="...",
            correlation_id=correlation_id,
            **additional_context
        )
    return result
```

### Step 4: Verify Migration Success

**Always use:** `pdm run typecheck-all` (from root)

**Success Criteria:**

- No type errors in CJ Assessment Service
- All protocol methods return single values
- All error conditions raise HuleEduError via factories
- LLM interaction implementation works with new signatures

## PHASE 4: ErrorDetail Instantiation Inventory

### Complete List of 12 ErrorDetail Instantiations

| File | Line | Context | Error Type |
|------|------|---------|------------|
| api/health_routes.py | 30 | create_error_response function | Dynamic |
| event_processor.py | 402 | _create_parsing_error_detail function | PARSING_ERROR |
| event_processor.py | 418 | _categorize_processing_error (CJAssessmentError) | Dynamic |
| event_processor.py | 438 | _categorize_processing_error (general) | Dynamic |
| event_processor.py | 454 | _create_publishing_error_detail function | KAFKA_PUBLISH_ERROR |
| implementations/db_access_impl.py | 323 | _reconstruct_error_detail function | Dynamic |
| implementations/llm_interaction_impl.py | 184 | Exception handling in task processing | PROCESSING_ERROR |
| implementations/llm_interaction_impl.py | 214 | Exception handling from gather | PROCESSING_ERROR |
| implementations/llm_interaction_impl.py | 251 | Critical processing error | PROCESSING_ERROR |
| tests/test_llm_interaction_overrides.py | 178 | Test setup | EXTERNAL_SERVICE_ERROR |
| tests/unit/test_llm_provider_service_client.py | 61 | HTTPStatusError handling | Dynamic |
| tests/unit/test_llm_provider_service_client.py | 77 | General exception handling | Dynamic |

### Migration Strategy

**Phase 4a: Core Implementation Files** (8 instances)

- implementations/llm_interaction_impl.py: 3 instances (simplest cases)
- event_processor.py: 4 instances (complex with dynamic error codes)
- api/health_routes.py: 1 instance (requires refactoring)

**Phase 4b: Special Cases** (1 instance)

- implementations/db_access_impl.py: 1 instance (requires custom reconstruction logic)

**Phase 4c: Test Updates** (3 instances)

- Update all test files to use pytest.raises pattern
- Remove ErrorDetail creation in tests

## ARCHITECTURAL DECISIONS MADE

1. **Domain-specific error factories remain in `services/libs`** for consistency and cross-service usage
2. **Retry manager uses error code classification** for intelligent retry decisions
3. **Correlation IDs flow through all error contexts** for full traceability
4. **OpenTelemetry integration is automatic** via HuleEduError constructor

## KEY PATTERNS ESTABLISHED

### Factory Function Usage

```python
from huleedu_service_libs.error_handling import (
    raise_external_service_error,
    raise_timeout_error,
    raise_validation_error,
    # ... others as needed
)

# Map ErrorCode to factory:
# ErrorCode.EXTERNAL_SERVICE_ERROR → raise_external_service_error()
# ErrorCode.TIMEOUT → raise_timeout_error()
# ErrorCode.VALIDATION_ERROR → raise_validation_error()
```

### Error Context Preservation

```python
# Always include service context
raise_external_service_error(
    service="cj_assessment_service",
    operation="generate_comparison",
    external_service="llm_provider_service",
    message="LLM request failed",
    correlation_id=correlation_id,
    status_code=500,  # Additional context
    provider_name="anthropic"  # Domain-specific details
)
```

### Retry Integration

The retry manager automatically:

- Classifies errors by ErrorCode for retry decisions
- Preserves correlation IDs across attempts
- Adds retry context to final errors
- Uses `HuleEduError.add_detail()` for enhancement

## NEXT PHASE PREPARATION

After completing LLM Provider Client migration, prepare for agent-driven tasks:

1. **Create agent instruction template** for ErrorDetail → factory replacement
2. **Verify all integration points** work with exception flow
3. **Update any remaining callers** that expect tuple returns

## VERIFICATION COMMANDS

```bash
# Type checking (ALWAYS from root)
pdm run typecheck-all

# Linting specific files
pdm run -p services/cj_assessment_service ruff check <file>

# Syntax verification
pdm run -p services/cj_assessment_service python -m py_compile <file>
```

## ARCHITECTURAL REFERENCE

- **Rule 048**: `.cursor/rules/048-structured-error-handling-standards.mdc`
- **ErrorDetail Model**: `common_core/src/common_core/models/error_models.py`
- **Factory Functions**: `services/libs/huleedu_service_libs/error_handling/factories.py`
- **Domain Factories**: `services/libs/huleedu_service_libs/error_handling/*_factories.py`
- **HuleEduError**: `services/libs/huleedu_service_libs/error_handling/huleedu_error.py`
- **Phase 4 Detailed Instructions**: `MIGRATION_PHASE_4_ERRORDETAIL.md`

Begin by reading the architecture files, then launch the research agents to understand current state before proceeding with the LLM Provider Client migration.