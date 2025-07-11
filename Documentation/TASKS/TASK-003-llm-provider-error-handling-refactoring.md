# TASK-003: LLM Provider Service Error Handling Refactoring

## 📋 Task Overview

**Objective**: Refactor the LLM Provider Service to use standardized HuleEdu error handling patterns matching the CJ Assessment Service reference implementation.

**Priority**: HIGH  
**Complexity**: HIGH  
**Estimated Sessions**: 4-5 sessions  
**Dependencies**: CJ Assessment Service (completed reference implementation)

## 🎯 Success Criteria

### Functional Requirements

- ✅ Complete migration from tuple returns to exception-based error handling
- ✅ All error handling uses `HuleEduError` with structured `ErrorDetail`
- ✅ Integration with service libraries error factories and observability stack
- ✅ Zero functional regression in LLM Provider Service capabilities
- ✅ Seamless integration with CJ Assessment Service and other consumers

### Architectural Requirements

- ✅ 100% compliance with `.cursor/rules/048-structured-error-handling-standards.mdc`
- ✅ Consistent error handling patterns across all provider implementations
- ✅ Proper integration with OpenTelemetry observability stack
- ✅ Clean protocol signatures without tuple returns

## 📊 Current State Analysis

### Issues Identified

1. **Mixed Error Patterns**: Uses both custom exceptions and tuple returns
2. **Field Inconsistencies**: Uses `error_message` instead of standardized `message`
3. **Missing Integration**: No HuleEduError or service libraries integration  
4. **Protocol Violations**: Tuple returns violate exception-based architecture
5. **Observability Gaps**: Missing automatic span recording and structured logging

### Files Requiring Refactoring (16+ files identified)

- **Core Models**: `internal_models.py`, `queue_models.py`, `exceptions.py`
- **Protocols**: `protocols.py` (all method signatures)
- **Implementations**: 7 provider implementation files
- **API Layer**: `api/llm_routes.py`, `api_models.py`
- **Supporting**: `response_validator.py`

## 🏗️ Implementation Strategy

### Phase-Based Approach

1. **Core Infrastructure**: Update error models and factory integration
2. **Protocol Migration**: Refactor protocol signatures to exception-based
3. **Provider Implementations**: Migrate each provider individually
4. **API Integration**: Update HTTP handlers and response models
5. **Cross-Service Validation**: Ensure integration with other services

### Session Management

- Each session handles 3-5 related files maximum
- Includes validation and testing within session scope
- Uses subagents for repetitive refactoring patterns
- Implements clean refactor with immediate pattern adoption

---

# 📋 SESSION-BASED TASK BREAKDOWN

## 🚀 Session 1: Core Infrastructure Refactoring

**Scope**: Foundation models and error infrastructure  
**Duration**: 1 session  
**Files**: 3-4 core files

### Subtasks

#### 1.1 Migrate Core Error Models

**Files**: `internal_models.py`, `queue_models.py`

- [ ] Update `LLMProviderError` model to use `message` instead of `error_message`
- [ ] Integrate with `ErrorDetail` from common_core
- [ ] Update `QueuedRequest` and `QueueStatusResponse` error fields
- [ ] Validate Pydantic model field updates

#### 1.2 Integrate Service Libraries Error Factories

**Files**: `exceptions.py`, new `error_factories.py`

- [ ] Replace custom exceptions with HuleEduError integration
- [ ] Create LLM-specific error factory functions using service libraries
- [ ] Map LLM error types to ErrorCode enum values
- [ ] Integrate correlation ID propagation patterns

#### 1.3 Update Error Types and Enums

**Files**: `error_types.py`, integration with common_core

- [ ] Align LLM error types with ErrorCode enum in common_core
- [ ] Create LLM-specific error codes if needed
- [ ] Ensure proper HTTP status code mapping

#### 1.4 Session Validation

- [ ] Run targeted tests for modified models
- [ ] Verify error factory functions work correctly
- [ ] Validate clean integration with service libraries

---

## 🔄 Session 2: Protocol Signature Refactoring

**Scope**: Protocol definitions and method signatures  
**Duration**: 1 session  
**Files**: `protocols.py` and related interface definitions

### Subtasks

#### 2.1 Refactor Core Protocol Signatures

**File**: `protocols.py`

- [ ] Convert `LLMProviderProtocol.generate_comparison()` from tuple return to exception-based
- [ ] Convert `LLMOrchestratorProtocol.perform_comparison()` to exception-based
- [ ] Update all protocol method signatures to remove tuple returns
- [ ] Add proper type hints for exception propagation

#### 2.2 Update Protocol Documentation

- [ ] Update protocol docstrings to document raised exceptions
- [ ] Specify HuleEduError exceptions in method documentation
- [ ] Update correlation ID handling in protocol contracts
- [ ] Document error propagation patterns

#### 2.3 Protocol Validation Utilities

- [ ] Create validation functions for protocol compliance
- [ ] Implement protocol signature verification

#### 2.4 Session Validation

- [ ] Validate protocol type checking with mypy
- [ ] Check protocol interface consistency
- [ ] Verify protocol documentation accuracy

---

## 🏭 Session 3: Provider Implementation Migration (Part 1)

**Scope**: Core provider implementations  
**Duration**: 1 session  
**Files**: Core provider implementation files (3-4 providers)

### Subtasks

#### 3.1 Refactor Primary Provider Implementations

**Files**: `anthropic_provider_impl.py`, `openai_provider_impl.py`, `google_provider_impl.py`

- [ ] Convert tuple returns to HuleEduError exceptions
- [ ] Integrate error factories for provider-specific errors
- [ ] Update correlation ID propagation throughout implementation
- [ ] Integrate OpenTelemetry span recording for errors

#### 3.2 Update Provider Error Handling Logic

- [ ] Map HTTP errors to appropriate ErrorCode values
- [ ] Implement structured error details for provider failures
- [ ] Update retry logic to work with exception-based patterns
- [ ] Integrate circuit breaker patterns with structured errors

#### 3.3 Refactor Provider Response Validation

**File**: `response_validator.py`

- [ ] Update validation error handling to use HuleEduError
- [ ] Integrate structured error details for validation failures
- [ ] Update correlation ID handling in validation layer

#### 3.4 Session Validation

- [ ] Test provider implementation error scenarios
- [ ] Validate error propagation through provider implementations
- [ ] Check integration with updated protocols
- [ ] Verify observability integration works correctly

---

## 🏭 Session 4: Provider Implementation Migration (Part 2) & Queue System

**Scope**: Remaining providers and queue processing  
**Duration**: 1 session  
**Files**: Remaining implementations and queue management

### Subtasks

#### 4.1 Complete Provider Implementation Migration

**Files**: `openrouter_provider_impl.py`, `mock_provider_impl.py`

- [ ] Apply same error handling patterns as Session 3
- [ ] Ensure consistency across all provider implementations
- [ ] Complete correlation ID propagation patterns
- [ ] Finalize observability integration

#### 4.2 Refactor Queue Management

**Files**: `queue_processor_impl.py`, `resilient_queue_manager_impl.py`

- [ ] Update queue error handling to use HuleEduError patterns
- [ ] Integrate structured error propagation in queue processing
- [ ] Update error recovery and retry logic
- [ ] Ensure queue failure scenarios use proper error factories

#### 4.3 Update LLM Orchestrator

**File**: `llm_orchestrator_impl.py`

- [ ] Refactor orchestrator error handling to match new patterns
- [ ] Update provider coordination error handling
- [ ] Integrate proper error aggregation and propagation
- [ ] Update business logic error scenarios

#### 4.4 Session Validation

- [ ] Test complete provider ecosystem error handling
- [ ] Validate queue processing error scenarios
- [ ] Check orchestrator error coordination
- [ ] Verify end-to-end error propagation

---

## 🌐 Session 5: API Layer Integration & Cross-Service Validation

**Scope**: HTTP API layer and service integration  
**Duration**: 1 session  
**Files**: API routes, models, and integration validation

### Subtasks

#### 5.1 Refactor API Layer Error Handling

**Files**: `api/llm_routes.py`, `api_models.py`

- [ ] Update HTTP route error handling to use HuleEduError
- [ ] Integrate with service libraries error response factories
- [ ] Update API response models to use standardized error format
- [ ] Implement proper correlation ID extraction and propagation

#### 5.2 Update HTTP Error Response Patterns

- [ ] Replace manual error response construction with standard factories
- [ ] Integrate automatic HTTP status code mapping from ErrorCode
- [ ] Update error response serialization to match platform standards
- [ ] Ensure consistent error response format across all endpoints

#### 5.3 Cross-Service Integration Validation

- [ ] Test integration with CJ Assessment Service error handling
- [ ] Validate error propagation across service boundaries
- [ ] Check Kafka event error handling integration
- [ ] Verify correlation ID propagation across services

#### 5.4 Comprehensive Service Validation

- [ ] Run integration tests across all refactored components
- [ ] Validate error handling in realistic failure scenarios
- [ ] Test observability integration (logging, metrics, tracing)
- [ ] Verify integration with CJ Assessment Service

---

# 🔧 Implementation Guidelines

## Error Handling Patterns

### Factory Function Usage

```python
# CORRECT: Use service libraries factories
raise_external_service_error(
    service="llm_provider_service",
    operation="anthropic_api_call",
    external_service="anthropic_api",
    message="Failed to generate comparison",
    correlation_id=correlation_id,
    details={"model": model, "provider": "anthropic"}
)
```

### Protocol Implementation

```python
# CORRECT: Exception-based protocol implementation
async def generate_comparison(
    self, 
    request: LLMProviderRequest,
    correlation_id: UUID
) -> LLMProviderResponse:
    """
    Raises:
        HuleEduError: On any failure to generate comparison
    """
```

### Error Context Preservation

```python
# CORRECT: Maintain error context through layers
try:
    response = await provider.generate_comparison(request, correlation_id)
except HuleEduError:
    # Error already logged and recorded to span
    raise  # Re-raise for upper layer handling
```

## Development Workflow

### Session Execution Pattern

1. **Pre-work**: Use subagent to analyze files requiring changes
2. **Implementation**: Apply refactoring patterns consistently
3. **Validation**: Test changes within session scope
4. **Documentation**: Update any affected documentation
5. **Integration Check**: Verify compatibility with other components

### Quality Assurance

- Run `pdm run lint-fix` after each session
- Execute targeted tests for modified components
- Validate mypy type checking passes
- Check integration with CJ Assessment Service patterns

### Rollback Strategy

- Document any breaking changes and mitigation strategies

---

# 📁 File Dependencies and Order

## Critical Path

1. **Core Models** → **Protocols** → **Implementations** → **API Layer**
2. Must complete error infrastructure before protocol changes
3. Must complete protocols before implementation refactoring
4. Must complete implementations before API integration

## Cross-Session Dependencies

- Session 1 outputs required for all subsequent sessions
- Session 2 protocol changes required for Sessions 3-4
- Sessions 3-4 implementation changes required for Session 5
- Session 5 validates entire refactoring effort

---

# 🎯 Expected Outcome

A completely refactored LLM Provider Service that:

- ✅ Achieves 100% consistency with CJ Assessment Service error handling
- ✅ Uses service libraries exception architecture throughout
- ✅ Maintains all existing functionality with zero regression  
- ✅ Integrates seamlessly with HuleEdu observability stack
- ✅ Serves as a second reference implementation for error handling

## Success Metrics

- All protocol signatures use exception-based error handling
- All error responses use standardized ErrorDetail format
- Complete integration with OpenTelemetry observability
- Zero test regressions after refactoring
- Successful integration with CJ Assessment Service workflows

---

# 📝 Notes

## Out of Scope for Current Task

- ☐ **Validate and Test Refactored Implementation** (separate task)
- ☐ **Create Universal Error Handling Refactoring Guide** (separate task)

## Future Considerations

- Consider automated migration scripts for other services
- Document lessons learned for future service refactoring
- Create validation checklist for error handling compliance
- Plan integration with additional HuleEdu services

---

**Task Created**: 2024-07-11  
**Last Updated**: 2024-07-11  
**Assignee**: Claude Code Assistant  
**Status**: Ready for Implementation
