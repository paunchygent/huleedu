# API Gateway Service: Complete Test Coverage Implementation

## BLOCKING DEPENDENCY
🚨 **PAUSED**: This task is blocked by critical architectural refactoring requirement.

**Blocker**: [TASKS/clean-refactor-remove-bos-fallback-from-api-gateway.md](./clean-refactor-remove-bos-fallback-from-api-gateway.md)

**Reason**: `routers/status_routes.py` contains BOS fallback anti-pattern that violates architectural boundaries. Must be refactored before implementing tests to avoid testing flawed logic.

---

### Health Routes ✅ COMPLETED
**Implementation**: `services/api_gateway_service/tests/test_health_routes.py` - 7 comprehensive tests using UnifiedMockApiGatewayProvider, protocol-based mocking, explicit DI metrics initialization, function patching for error scenarios. All tests pass, no linting/type errors.

**Remaining Coverage Gaps**:
- Total tests passing: 70/70 (7 new health tests added)
- `app/main.py` (11% coverage) - Missing lines: 23-44, 52-67, 73-77, 82-87, 92-107, 112-116, 123-132
- `app/startup_setup.py` (44% coverage) - Missing lines: 51-67, 72-75, 80-84, 105-114, 142-147
- `auth.py` (80% coverage) - Missing lines: 36-38, 54-55
- `config.py` (82% coverage) - Missing lines: 79-81
- `app/rate_limiter.py` (22% coverage) - Missing lines: 23-31, 38-44, 48-53
- `routers/status_routes.py` (0% coverage) - BLOCKED by architectural refactoring

## Implementation Strategy

**Priority Order** (post-refactoring):
1. **Rate Limiter** (22% -> 95% coverage) - Security critical
2. **Startup Setup** (44% -> 95% coverage) - Initialization critical  
3. **Main Application** (11% -> 95% coverage) - Application bootstrap
4. **Authentication** (80% -> 95% coverage) - Edge cases
5. **Config** (82% -> 95% coverage) - Environment validation
6. **Status Routes** (0% -> 95% coverage) - After BOS refactoring

## Implementation Guidelines

### ULTRATHINK: Strict Adherence to Patterns

1. **Protocol-Based Mocking** (Rule 070.1)
   - Mock ONLY protocol interfaces, never implementations
   - Use the established `UnifiedMockApiGatewayProvider` pattern
   - Create manual call tracking for non-Mock objects (as done for Redis)

2. **Test Structure**
   - Follow existing test file naming: `test_<module_name>.py`
   - Group tests in classes: `class Test<ComponentName>`
   - Use descriptive test names: `test_<scenario>_<expected_behavior>`

3. **Async Testing**
   - Use `pytest.mark.asyncio` for async tests
   - Handle async context managers properly
   - Ensure proper cleanup in fixtures

4. **Coverage Requirements**
   - Each test must verify business logic, not just code execution
   - Include both success and failure scenarios
   - Test edge cases and error handling
   - Verify logging and monitoring integration

## Technical Constraints

1. **DI Container Testing**
   - Use the established pattern from `conftest.py`
   - Match production provider signatures exactly
   - Handle `AsyncIterator` patterns correctly

2. **FastAPI Testing**
   - Use `TestClient` for synchronous tests
   - Handle WebSocket tests with proper context management
   - Mock external dependencies at the protocol level

3. **Monorepo Compliance**
   - Run all commands from repository root
   - Use `pdm run pytest` for test execution
   - Follow import patterns (no standard library logging)

## Success Criteria

### ULTRATHINK: Definition of Done

1. **Coverage Metrics**
   - Overall coverage ≥ 95%
   - No file below 80% coverage
   - All critical paths tested

2. **Test Quality**
   - All tests follow protocol-based mocking
   - Tests verify business logic, not implementation
   - Proper error scenarios covered
   - No test shortcuts or mocking internals

3. **Code Quality**
   - Pass `pdm run typecheck-all`
   - Pass `pdm run lint-all`
   - Pass `pdm run format-all`
   - No debug artifacts in code

## Execution Workflow

1. **Setup Phase** (Use Subagent)
   - Analyze current coverage gaps in detail
   - Create comprehensive test plan
   - Set up test fixtures as needed

2. **Implementation Phase**
   - Implement tests file by file
   - Run tests after each file completion
   - Verify coverage improvements

3. **Validation Phase** (Use Subagent)
   - Run full test suite
   - Generate coverage report
   - Run quality checks (type, lint, format)
   - Fix any issues found

## Important Notes

- **NO DEBUG PRINTS**: Remove all debug statements before finalizing
- **NO SHORTCUTS**: Follow established patterns exactly
- **NO ASSUMPTIONS**: Read actual implementation before writing tests
- **USE SUBAGENTS**: For complex analysis and validation tasks

Remember: The codebase has well-established patterns. Use them. Don't introduce new patterns without compelling reasons.