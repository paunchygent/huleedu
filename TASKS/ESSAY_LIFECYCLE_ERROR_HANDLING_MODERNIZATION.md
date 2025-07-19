---
id: ELS-001
title: "Essay Lifecycle Service Error Handling Modernization"
author: "Claude Code Assistant"
status: "In Progress"
created_date: "2025-01-19"
updated_date: "2025-01-19"
---

## 1. Objective

Modernize the Essay Lifecycle Service error handling from legacy patterns (ValueError, generic Exception) to the mature HuleEdu error infrastructure using factory functions, structured error codes, and automatic observability integration.

## 2. Architectural Drivers

- **Distributed Systems Reliability**: Current manual `uuid4()` correlation ID generation breaks distributed tracing chains, making debugging race conditions nearly impossible
- **Observability Foundation**: HuleEduError provides automatic OpenTelemetry integration essential for distributed systems
- **Infrastructure Maturity**: The HuleEdu error infrastructure has 42 error codes and 25 factory functions covering 95% of ELS needs
- **Foundation for Complexity**: Required before adding distributed coordination complexity

## 3. Current Problem Analysis

### 3.1 Legacy Error Patterns in ELS

**Repository Layer Issues**:

- `ValueError("Essay not found")` - No correlation ID, no structured context
- Generic `Exception` catch-all patterns throughout
- Manual `ErrorResponse` creation with isolated `uuid4()` generation

**Service Layer Issues**:

- Broken correlation chains across service boundaries
- No observability integration with spans/traces
- Inconsistent error propagation patterns

**API Layer Issues**:

- Manual error response construction
- No integration with Quart error handlers
- Missing structured error details

### 3.2 Error Scenario Mapping

All current ELS error scenarios map to existing infrastructure:

| Current Pattern | HuleEdu Factory Function | Error Code |
|----------------|-------------------------|------------|
| `ValueError("Essay not found")` | `raise_resource_not_found()` | `RESOURCE_NOT_FOUND` |
| Database connection errors | `raise_connection_error()` | `CONNECTION_ERROR` |
| Kafka publishing failures | `raise_kafka_publish_error()` | `KAFKA_PUBLISH_ERROR` |
| External service calls | `raise_spellcheck_service_error()` | `SPELLCHECK_SERVICE_ERROR` |
| State machine transitions | `raise_processing_error()` | `PROCESSING_ERROR` |
| Validation failures | `raise_validation_error()` | `VALIDATION_ERROR` |

## 4. Implementation Plan

### Phase 1: Repository Layer Modernization

**Files to Update**:

- `essay_repository_postgres_impl.py` ✅ **IN PROGRESS**
- `essay_crud_operations.py`
- `batch_tracker_persistence.py`

**Changes**:

- Add `correlation_id: UUID` parameters to repository methods
- Replace `ValueError` with `raise_resource_not_found()`
- Replace generic `Exception` with specific factory functions
- Add proper database error handling with `raise_connection_error()` and `raise_processing_error()`

### Phase 2: Service Layer Modernization

**Files to Update**:

- `batch_coordination_handler_impl.py`
- `service_request_dispatcher.py`
- `spellcheck_command_handler.py`
- `cj_assessment_command_handler.py`
- `service_result_handler_impl.py`

**Changes**:

- Replace generic `Exception` handling with specific error factories
- Use `raise_external_service_error()` for service integration failures
- Use `raise_processing_error()` for business logic failures
- Ensure correlation ID propagation through all operations

### Phase 3: Event Publishing Modernization

**Files to Update**:

- `event_publisher.py`
- `batch_essay_tracker_impl.py`

**Changes**:

- Use `raise_kafka_publish_error()` for Kafka failures
- Use `raise_external_service_error()` for Redis failures
- Maintain existing circuit breaker integration

### Phase 4: API Layer Modernization

**Files to Update**:

- `api/essay_routes.py`
- `api/batch_routes.py`
- `app.py` (error handlers)

**Changes**:

- Extract correlation IDs from request headers or generate at API boundary
- Remove manual `ErrorResponse` construction
- Update Quart error handlers for HuleEduError integration
- Leverage automatic HTTP status mapping

### Phase 5: Protocol Updates

**Files to Update**:

- `protocols.py`

**Changes**:

- Update protocol signatures to include `correlation_id` parameters where needed
- Document HuleEduError exceptions in protocol method signatures
- Maintain backward compatibility during transition

## 5. Correlation ID Integration Strategy

### 5.1 API Layer

- Extract correlation IDs from `X-Correlation-ID` headers
- Generate correlation IDs at API boundary if not provided
- Pass correlation IDs to all service operations

### 5.2 Service Layer

- Propagate correlation IDs through all business logic operations
- Include correlation IDs in all error factory calls
- Maintain correlation context across async operations

### 5.3 Repository Layer

- Accept correlation IDs as parameters for error handling
- Use correlation IDs in all database error scenarios

## 6. Testing Strategy

### 6.1 Error Scenario Testing

- Test all error paths with proper correlation tracking
- Validate HuleEduError integration with existing test patterns
- Ensure error responses maintain API contracts

### 6.2 Observability Testing

- Validate OpenTelemetry span integration
- Test correlation ID propagation across service boundaries
- Verify structured logging with error context

## 7. Success Criteria

### 7.1 Error Handling Compliance

- [ ] All `ValueError` exceptions replaced with `raise_resource_not_found()`
- [ ] All generic `Exception` patterns replaced with specific factory functions
- [ ] All error scenarios include correlation IDs
- [ ] OpenTelemetry integration working for all error paths

### 7.2 Observability Integration

- [ ] Error spans properly recorded in traces
- [ ] Correlation IDs propagated across service boundaries
- [ ] Structured logging includes error context

### 7.3 API Contract Compliance

- [ ] HTTP status codes properly mapped from error codes
- [ ] Error responses include structured details
- [ ] Quart error handlers integrated with HuleEduError

## 8. Dependencies and Blocking Tasks

### 8.1 Dependencies

- HuleEdu error infrastructure (existing, mature)
- OpenTelemetry integration (existing)
- Correlation ID extraction utilities (existing)

### 8.2 Blocks

- **ELS-002**: Distributed State Management Implementation
  - Requires reliable error handling for race condition debugging
  - Depends on correlation ID propagation for distributed coordination

## 9. Implementation Progress

### Completed ✅

- Analysis of existing error patterns
- Mapping to HuleEdu error infrastructure
- Repository layer modernization (in progress)

### In Progress 🔄

- `essay_repository_postgres_impl.py` error handling updates

### Pending ⏳

- Service layer modernization
- Event publishing error handling
- API layer integration
- Protocol signature updates
- Comprehensive testing

## 10. Risk Assessment

### 10.1 Low Risk

- Infrastructure is mature and well-tested
- Clear migration patterns established in other services
- Backward compatibility maintained during transition

### 10.2 Mitigation

- Incremental migration by layer
- Comprehensive testing at each phase
- Correlation ID fallback generation for transition period

---

**Note**: This task is a prerequisite for distributed state management improvements and provides the observability foundation required for distributed systems reliability.
