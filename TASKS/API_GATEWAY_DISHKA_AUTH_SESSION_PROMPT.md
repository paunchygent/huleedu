# API Gateway Dishka Authentication Integration - Session Prompt

## Context for New Claude Session

You are continuing work on the HuleEdu monorepo, specifically fixing a critical architectural issue with the API Gateway service's authentication system. The previous session successfully implemented HuleEduError patterns but discovered a fundamental incompatibility between Dishka (our DI framework) and FastAPI's native Depends mechanism.

## Primary Request and Intent

**ULTRATHINK**: The user needs you to properly integrate authentication with Dishka in the API Gateway service, following established patterns and avoiding code smells like:
1. No `# noqa` comments to suppress linter warnings
2. No backwards compatibility hacks
3. No mixing of dependency injection systems
4. Proper, maintainable solutions only

## Current State Analysis

### What Was Completed
1. ✅ HuleEduError pattern implemented in WebSocket service
2. ✅ HuleEduError pattern implemented in API Gateway service
3. ✅ FastAPI error handler created in huleedu_service_libs
4. ✅ Services rebuilt and running

### What Failed
1. ❌ Dishka + FastAPI Depends integration causes "request" query parameter error
2. ❌ AuthProvider pattern partially implemented but not working
3. ❌ Linter warnings (B008) for Form(...) and File(...) not properly resolved

## The Core Problem

**ULTRATHINK: Create a subagent to analyze the Dishka-FastAPI integration issue**

When combining:
- Dishka dependency injection (`FromDishka[T]`)
- FastAPI's `Depends()` for authentication
- FastAPI's `Form(...)` and `File(...)` for multipart data

Results in validation errors where FastAPI interprets function parameters as query parameters. This suggests a fundamental incompatibility in how the two DI systems process function signatures.

## Critical Files to Understand

### Rule System (Start Here)
1. `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/000-rule-index.mdc` - Entry point
2. `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/042-async-patterns-and-di.mdc` - DI patterns
3. `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/048-structured-error-handling-standards.mdc` - Error handling

### Current Implementation Files
1. `/services/api_gateway_service/app/auth_provider.py` - Attempted Dishka-based auth
2. `/services/api_gateway_service/routers/status_routes.py` - Routes with auth issues
3. `/services/api_gateway_service/routers/batch_routes.py` - Routes with Form/File issues
4. `/services/api_gateway_service/routers/file_routes.py` - File upload with B008 warnings

### Error Handling Infrastructure
1. `/libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/fastapi_handlers.py` - New FastAPI handler
2. `/libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/factories.py` - Error factories

## Research Tasks

**ULTRATHINK: Deploy a research subagent to investigate solutions**

1. **Dishka Documentation Deep Dive**
   - How does Dishka handle FastAPI security dependencies?
   - Are there examples of OAuth2/JWT with Dishka?
   - What's the recommended pattern for request-scoped auth?

2. **Alternative Patterns Research**
   - Can we use FastAPI middleware for authentication instead?
   - Should we create a custom dependency that bridges both systems?
   - Is there a way to make Dishka respect FastAPI's special dependencies?

3. **Linter Configuration**
   - Is B008 a false positive for FastAPI's Form/File?
   - Should we configure flake8-bugbear differently?
   - What do other FastAPI projects do?

## Proposed Solutions to Investigate

### Solution 1: Pure Dishka Authentication
**ULTRATHINK: Implement authentication entirely within Dishka's provider system**
- Move all auth logic to REQUEST-scoped providers
- Use FastAPI Request from context
- Avoid mixing with FastAPI's Depends

### Solution 2: Custom Dependency Bridge
**ULTRATHINK: Create a bridge between Dishka and FastAPI dependencies**
```python
def dishka_auth_depends():
    """Bridge between FastAPI Depends and Dishka"""
    # Implementation to investigate
```

### Solution 3: Middleware-Based Authentication
**ULTRATHINK: Move authentication to middleware layer**
- Implement auth checks before route handlers
- Store user_id in request.state
- Access via Dishka providers

### Solution 4: Manual Dependency Resolution
**ULTRATHINK: Manually resolve dependencies for authenticated routes**
- Get container from app.state
- Manually resolve dependencies
- More verbose but explicit

## Implementation Requirements

1. **No Code Smells**
   - No `# noqa` comments
   - No temporary compatibility layers
   - No mixing DI systems

2. **Follow Patterns**
   - Consistent with other HuleEdu services
   - Use established error handling
   - Maintain type safety

3. **Maintainable Solution**
   - Clear separation of concerns
   - Easy to test
   - Well documented

## Testing Plan

**ULTRATHINK: Create a testing subagent to validate the solution**

1. **Authentication Tests**
   - Missing token → HuleEduError with proper format
   - Invalid token → HuleEduError with details
   - Expired token → Appropriate error response

2. **File Upload Tests**
   - Multipart form data works correctly
   - No linter warnings
   - Proper error handling

3. **Integration Tests**
   - All routes work with new auth pattern
   - No regression in functionality
   - Performance is acceptable

## Success Criteria

1. **Authentication Working**
   - All protected routes properly secured
   - HuleEduError format for all auth failures
   - No query parameter validation errors

2. **Clean Code**
   - No linter warnings or suppressions
   - Follows HuleEdu patterns
   - Type-safe throughout

3. **Documentation**
   - Update relevant rule files
   - Document the chosen pattern
   - Explain why this approach was selected

## Starting Instructions

1. **Read the rule system** to understand HuleEdu patterns
2. **Analyze the current code** to see what was attempted
3. **Research Dishka-FastAPI integration** patterns
4. **Implement a clean solution** following all requirements
5. **Test thoroughly** before declaring success

## Important Context from Previous Session

- FastAPI's `Form(...)` and `File(...)` are not mutable defaults, they're dependency markers
- The B008 warning from flake8-bugbear is arguably a false positive
- Mixing `Depends()` with `FromDishka[]` causes FastAPI to misinterpret parameters
- The auth system must use HuleEduError, not HTTPException
- All services are currently running and can be tested live

## Warning Signs to Avoid

1. If you find yourself adding `# noqa` comments - STOP and reconsider
2. If you're creating compatibility layers - find a cleaner approach
3. If the solution feels hacky - it probably is
4. If you're fighting the framework - you're doing it wrong

Remember: The goal is a clean, maintainable solution that follows HuleEdu patterns and integrates smoothly with both Dishka and FastAPI.