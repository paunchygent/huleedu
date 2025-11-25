---
id: "075-test-creation-methodology"
type: "testing"
created: 2025-08-03
last_updated: 2025-11-17
scope: "all"
child_rules: ["075.1-parallel-test-creation-methodology"]
---

# 075: Test Creation Methodology

## 1. ULTRATHINK Test Creation Protocol

### 1.1. Mandatory Pre-Implementation Phase
**MUST** complete in sequence before writing any test code:
1. **Rule Compliance**: Read all 8 mandatory architectural rules ([000-rule-index.md](mdc:000-rule-index.md))
2. **Service Architecture**: Read relevant service-specific rule (020.x series for service type)
3. **Domain Analysis**: Understand service's bounded context and domain requirements
4. **Pattern Study**: Analyze battle-tested test patterns from similar service types
5. **typecheck-all**: Run `pdm run typecheck-all` from repository root
6. **Behavior Analysis**: Understand actual behavior of code under test

### 1.2. Battle-Tested Pattern Sources Selection
**MUST** study relevant patterns based on service type:
- **Utility/Algorithm Testing**: `/services/spellchecker_service/tests/spell_logic/`
- **Protocol-based DI Testing**: `/services/essay_lifecycle_service/tests/unit/`
- **HTTP Service Testing**: `/services/file_service/tests/api/`
- **Worker Service Testing**: `/services/spell_checker_service/tests/worker/`
- **Integration Testing**: `/services/class_management_service/tests/integration/`

## 2. Test File Architecture Standards

### 2.1. File Size and Scope
- **MUST** keep test files under 500 LoC (hard limit)
- **MUST** focus on single responsibility per test file
- **MUST** use naming pattern: `test_[component]_[specific_aspect].py`

### 2.2. Test Class Organization
```python
class TestFunctionName:
    """Tests for the function_name function."""

    @pytest.mark.parametrize("param1, param2, expected", [...])
    def test_function_name_expected_behavior(self, param1, param2, expected):
        """Test description focusing on business behavior."""
```

## 3. Testing Patterns and Standards

### 3.1. Parametrized Testing (Preferred)
- **MUST** use `@pytest.mark.parametrize` for comprehensive test coverage
- **MUST** include edge cases, boundary conditions, and realistic scenarios
- **MUST** test Swedish characters and locale-specific scenarios *where applicable*
- **SHOULD** complement parametrized examples with property-based testing (e.g. Hypothesis or equivalent) for pure functions and algorithmic domains (scoring, batching, retry pools) where invariants can be expressed succinctly.

### 3.2. Behavioral Testing Requirements
- **MUST** test actual behavior and side effects
- **MUST** use method call assertions: `mock.assert_called_once_with(expected_params)`
- **FORBIDDEN**: Fragile log message testing (`assert "text" in caplog.text`)

### 3.3. Domain-Specific Context Testing
- **MUST** include domain-appropriate edge cases for service context
- **MUST** test realistic data patterns specific to bounded context
- **MUST** handle locale/encoding edge cases when applicable
- **Examples by Domain**:
  - **NLP Services**: Swedish characters `åäöÅÄÖ`, Unicode normalization
  - **Financial Services**: Currency precision, decimal handling
  - **File Services**: Path separators, encoding detection
  - **User Services**: Email formats, validation patterns

### 3.4. Domain Test Data Builders
- **SHOULD** centralize domain-specific test data creation in small builder helpers per bounded context (for example, comparison pair / batch state builders in CJ Assessment tests).
- **SHOULD** reuse shared builders across test files instead of duplicating inline dicts or ad-hoc objects.
- **PATTERN**: Keep builders thin and explicit (no hidden behavior); prefer functions or lightweight factory classes in dedicated test helper modules.

## 4. Quality Assurance Protocol

### 4.1. Mandatory Validation Sequence
**MUST** execute after creating each test file:
1. **Type Check**: `pdm run typecheck-all` from repository root
2. **Test Execution**: `pdm run pytest-root [test_file] -v`
3. **100% Pass Rate**: Fix ALL failures before proceeding
4. **Root Cause Analysis**: Fix implementation issues, not just tests

### 4.2. Implementation Fix Priority
- **MUST** investigate test failures for root cause issues
- **MUST** fix actual implementation bugs (e.g., fuzzy threshold adjustments)
- **FORBIDDEN**: Changing tests to accommodate broken implementation

## 5. Progressive Test Enhancement Strategy

### 5.1. Momentum Building
- **MUST** start with simplest utility functions
- **MUST** build complexity gradually using proven patterns
- **MUST** complete one test file fully before starting next

## 6. Dependency Injection Testing Patterns

### 6.1. Protocol-Based Testing
```python
# ✅ CORRECT - Protocol-based mocking
async def test_service_method(self):
    mock_dependency = AsyncMock(spec=DependencyProtocol)
    service = ServiceImpl(dependency=mock_dependency)
    await service.method()
    mock_dependency.expected_method.assert_called_once()
```

### 6.2. Dishka DI Testing
- **MUST** override Dishka providers in tests to inject mocks
- **MUST** use `make_async_container` with test `Provider`
- **PATTERN**: Bind protocols to mocks with appropriate scopes

### 6.3. JWT Authentication Testing

**Shared JWT Helpers** (`huleedu_service_libs.testing.jwt_helpers`):
- **MUST** use shared helpers for JWT token creation in unit tests
- **FORBIDDEN**: Local JWT encoding or helper duplication

### 6.4. Test Fixture Design
- **SHOULD** keep fixtures small and focused on a single concern (e.g. one fixture for `MockSession`, another for repository wiring).
- **SHOULD** place reusable cross-file fixtures and helpers in dedicated test helper modules rather than redefining them per file.
- **MUST NOT** create deeply nested fixture chains that obscure test intent unless there is a strong reuse benefit.

## 7. Anti-Patterns to Avoid

### 7.1. Forbidden Practices
- **FORBIDDEN**: Creating large monolithic test files (>500 LoC)
- **FORBIDDEN**: Testing implementation details instead of behavior
- **FORBIDDEN**: Skipping typecheck-all validation
- **FORBIDDEN**: Accepting test failures without root cause analysis
- **FORBIDDEN**: Using `try/except pass` blocks hiding issues

### 7.2. Quality Compromises
- **FORBIDDEN**: Simplifying tests to make them pass
- **FORBIDDEN**: Mocking at wrong abstraction levels
- **FORBIDDEN**: Ignoring domain-specific edge cases relevant to service context

## 8. Test Documentation Standards

### 8.1. Test Descriptions
- **MUST** write clear, business-focused test descriptions
- **MUST** explain what behavior is being verified
- **SHOULD** include edge case explanations in docstrings

### 8.2. Parametrize Documentation
```python
@pytest.mark.parametrize(
    "input_value, expected_output",
    [
        # Edge case: empty string should return default
        ("", "default"),
        # Domain-specific: should handle special characters
        ("Special-Case", "special_case"),
        # Boundary condition: maximum length handling
        ("x" * 1000, "truncated_result"),
    ],
)
```

## 9. Service Type Adaptation

### 9.1. HTTP Service Testing (Quart/FastAPI)
- **MUST** test endpoint routing and request/response handling
- **MUST** test authentication and authorization where applicable
- **MUST** mock external service dependencies via DI protocols
- **SHOULD** test error handling and status codes

### 9.2. Worker Service Testing (Kafka Consumers)
- **MUST** test event processing logic independently
- **MUST** mock Kafka consumer/producer via protocols
- **MUST** test idempotency and error handling
- **SHOULD** test event schema validation

### 9.3. Utility Library Testing
- **MUST** focus on pure function behavior
- **MUST** test boundary conditions and edge cases
- **MUST** use parametrized testing for comprehensive coverage
- **SHOULD** test performance characteristics where relevant

### 9.4. Repository/Data Layer Testing
- **MUST** test business logic without database dependencies
- **MUST** mock database sessions via async context managers
- **MUST** test transaction handling and rollback scenarios
- **SHOULD** use testcontainers for integration tests

### 9.5. JWT Authentication Testing

```python
from huleedu_service_libs.tests.jwt_helpers import create_default_test_token

# Basic token
token = create_default_test_token("user-123")

# Token with roles/org
token = create_default_test_token(
    "admin-456",
    roles=["admin", "teacher"],
    org_id="org-789",
    expires_in=timedelta(hours=2)
)

# Negative testing: missing claims
from huleedu_service_libs.tests.jwt_helpers import create_hs_token

payload = {"sub": "user-123", "aud": "huleedu", "iss": "identity"}  # No exp
token = create_hs_token(secret=settings.JWT_SECRET_KEY, payload=payload)
```

**Ref**: `libs/huleedu_service_libs/tests/jwt_helpers.py`, `services/api_gateway_service/tests/test_auth.py`

### 9.6. Content Client Testing

```python
@pytest.fixture
def mock_content_client() -> AsyncMock:
    client = AsyncMock(spec=ContentClientProtocol)
    client.fetch_content.return_value = "mock content"
    return client

# Call pure implementation with mock
result = await _operation_impl(
    content_client=mock_content_client,
    ...
)
```

**DO NOT** use `@patch` for protocol dependencies

---
**This methodology ensures reproducible, high-quality test creation following established HuleEdu architectural patterns.**
