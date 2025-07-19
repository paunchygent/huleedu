# WebSocket Service Post-Refactor Improvements - Session Prompt

## Context for New Claude Session

You are continuing work on the HuleEdu monorepo, specifically implementing post-refactor improvements for the WebSocket and API Gateway services. The WebSocket refactor has been completed - the service has been extracted from API Gateway into a dedicated microservice. Now you need to implement critical improvements discovered during code review.

## Primary Request and Intent

**ULTRATHINK**: The user wants you to implement the improvements documented in `/TASKS/WEBSOCKET_POST_REFACTOR_IMPROVEMENTS.md`, which addresses:
1. Standardizing error handling using the existing HuleEduError pattern
2. Increasing test coverage for WebSocket service from 75% to >90%
3. Adding OpenTelemetry spans for observability
4. Implementing service enhancements (timeouts, graceful shutdown, etc.)

**Key Discovery**: The HuleEdu codebase already has mature error handling and observability infrastructure in `huleedu_service_libs`. You must use these existing patterns, not create new ones.

## Critical Rules and Guidelines

### Must Read First
1. **Start with the rule index**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/000-rule-index.mdc`
2. **Understand error handling patterns**: 
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/048-structured-error-handling-standards.mdc`
   - Existing implementation: `/Users/olofs_mba/Documents/Repos/huledu-reboot/libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/`
3. **Follow observability standards**: 
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/071.2-jaeger-tracing-patterns.mdc`
4. **Testing requirements**: 
   - `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/070-testing-and-quality-assurance.mdc`

### Development Principles
- **NO cast() usage** except where absolutely necessary
- **NO relative imports** - always use absolute imports
- **Mock protocols, not implementations** in tests
- **Follow existing patterns** - don't introduce new conventions
- **Use agents for complex tasks** as specified in `.cursor/rules/110.2-coding-mode.mdc`

## Key Technical Discoveries

### Error Handling Infrastructure
```
ULTRATHINK: Analyze the existing error handling system:
1. HuleEduError class exists in huleedu_service_libs/error_handling/huleedu_error.py
2. Factory functions for all error codes in factories.py
3. ERROR_CODE_TO_HTTP_STATUS mapping in quart_handlers.py
4. No new error codes needed - existing ErrorCode enum is comprehensive
```

**Key Files**:
- `/libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/huleedu_error.py` - Base exception class
- `/libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/factories.py` - Error factory functions
- `/libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/error_detail_factory.py` - ErrorDetail creation
- `/libs/common_core/src/common_core/error_enums.py` - All error codes
- `/libs/common_core/src/common_core/models/error_models.py` - ErrorDetail model

### Services Requiring Updates

#### WebSocket Service
- **Location**: `/services/websocket_service/`
- **Current Issues**:
  - Returns `None` instead of raising HuleEduError
  - WebSocket close doesn't include ErrorDetail in reason
  - Test coverage only 75%
  - Missing OpenTelemetry spans

**Files to modify**:
- `implementations/jwt_validator.py` - Replace None returns with raise_authentication_error
- `routers/websocket_routes.py` - Add HuleEduError handling and spans
- `implementations/message_listener.py` - Add error handling for Redis failures
- `startup_setup.py` - Add tracing initialization

#### API Gateway Service
- **Location**: `/services/api_gateway_service/`
- **Current Issues**:
  - Uses HTTPException instead of HuleEduError
  - Missing structured error responses
  - No custom spans for business operations

**Files to modify**:
- `auth.py` - Replace HTTPException with raise_authentication_error
- `routers/status_routes.py` - Use proper error factories
- `routers/batch_routes.py` - Add trace_operation for Kafka publish
- `app/main.py` - Register FastAPI error handlers

## Pending Tasks

### Priority 1: Error Handling Implementation
```
ULTRATHINK: Create a subagent to implement HuleEduError pattern:
1. Read existing error handling patterns in huleedu_service_libs
2. Update WebSocket service to use error factories
3. Update API Gateway to use error factories
4. Create FastAPI error handler (only missing component)
5. Ensure WebSocket errors include ErrorDetail in close reason
```

**Specific Implementation**:
- JWT errors → `raise_authentication_error()`
- Connection limits → `raise_quota_exceeded()`
- Redis failures → `raise_connection_error()` or `raise_external_service_error()`
- Validation errors → `raise_validation_error()`

### Priority 2: Test Coverage Improvement
```
ULTRATHINK: Analyze test gaps and create comprehensive tests:
1. Current coverage: 75% (target: >90%)
2. Uncovered files: di.py (0%), main.py (0%), protocols.py (63%)
3. Create integration tests for app startup
4. Test error paths in all implementations
5. Ensure protocol mocking pattern is followed
```

### Priority 3: Observability Implementation
```
ULTRATHINK: Add OpenTelemetry spans using existing patterns:
1. HuleEduError already auto-records to spans
2. Use trace_operation from huleedu_service_libs.observability
3. Add spans for: token validation, connection, message forwarding
4. Propagate trace context in events using inject_trace_context
```

### Priority 4: Service Enhancements
- Configurable channel prefix (currently hardcoded "ws:")
- Connection timeout handling
- Prometheus metrics registration
- Graceful shutdown on SIGTERM

## Implementation Approach

1. **Start by reading** `/TASKS/WEBSOCKET_POST_REFACTOR_IMPROVEMENTS.md` - it contains all implementation details
2. **Use existing infrastructure** - Don't create new error patterns or observability helpers
3. **Follow the examples** in the improvements document - they show exact code changes needed
4. **Test incrementally** - Run tests after each change to ensure no regressions

## Important Context

### What Was Already Completed
- WebSocket service extraction from API Gateway ✅
- All legacy WebSocket code removed from API Gateway ✅
- Frontend migration guide created ✅
- Type issues fixed ✅
- Documentation updated ✅

### What You're NOT Doing
- Creating new error codes (use existing ErrorCode enum)
- Creating new error handling patterns (use existing factories)
- Implementing backwards compatibility (this is an atomic refactor)
- Creating new observability patterns (use existing helpers)

## Testing Your Changes

```bash
# Run WebSocket service tests
pdm run pytest services/websocket_service/tests/ -v

# Check coverage
pdm run pytest services/websocket_service/tests/ --cov=services/websocket_service --cov-report=term-missing

# Run API Gateway tests
pdm run pytest services/api_gateway_service/tests/ -v

# Type checking
pdm run mypy services/websocket_service/
pdm run mypy services/api_gateway_service/
```

## Success Criteria

1. **Error Handling**: All services use HuleEduError with proper error codes
2. **Test Coverage**: WebSocket service achieves >90% coverage
3. **Observability**: Key operations have spans with business context
4. **No Regressions**: All existing tests still pass
5. **Type Safety**: mypy passes with no errors

## Reference Architecture Examples

Look at these services for patterns:
- **Error Handling**: `services/spellchecker_service/event_processor.py` - Shows HuleEduError usage
- **Test Coverage**: `services/class_management_service/tests/` - Shows comprehensive testing
- **Observability**: `services/cj_assessment_service/` - Shows span creation patterns

## Final Notes

- The infrastructure is mature - use it, don't reinvent it
- When in doubt, check how other services implement similar functionality
- Always use agents for complex file operations to ensure pattern compliance
- Document any discoveries or pattern updates in the appropriate `.cursor/rules/` file

Remember: You're implementing improvements to align the WebSocket and API Gateway services with established HuleEdu patterns, not creating new patterns.