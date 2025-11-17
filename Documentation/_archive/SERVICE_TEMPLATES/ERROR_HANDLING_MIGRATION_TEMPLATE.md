# ERROR HANDLING MIGRATION TEMPLATE

**Template Version:** 1.0  
**Based on:** Spellchecker Service Modernization (150 passing tests)  
**Target Services:** Content, Batch Orchestrator, Essay Lifecycle, File, CJ Assessment, Class Management, Result Aggregator, LLM Provider  

## TEMPLATE OVERVIEW

This template provides a systematic approach to migrate any HuleEdu microservice from legacy error handling patterns to platform-compliant structured error handling using the proven patterns from the spellchecker service modernization.

### Success Criteria
- ✅ 100% generic error function adoption
- ✅ Complete correlation ID coverage  
- ✅ Full observability integration
- ✅ Zero functional regression
- ✅ All tests passing
- ✅ Zero MyPy/Ruff violations

## PHASE 1: COMPLIANCE RESTORATION

### Step 1.1: Audit Current Error Functions

Create an inventory of all service-specific error functions that need replacement:

```bash
# Search for service-specific error functions
grep -r "raise_${SERVICE_NAME}" services/${SERVICE_NAME}_service/
grep -r "def raise_" services/${SERVICE_NAME}_service/
```

**Expected Pattern Violations:**
- `raise_${service}_*` functions → Generic platform functions
- Custom ErrorDetail creation → Factory functions  
- Direct logging without correlation_id → Structured error handling

### Step 1.2: Map Legacy Functions to Generic Equivalents

**Core Mapping Pattern (proven in spellchecker):**

| Legacy Pattern | Generic Function | Import Source |
|---------------|------------------|---------------|
| `raise_{service}_content_service_error` | `raise_content_service_error` | `huleedu_service_libs.error_handling` |
| `raise_{service}_algorithm_error` | `raise_processing_error` | `huleedu_service_libs.error_handling` |
| `raise_{service}_database_connection_error` | `raise_connection_error` | `huleedu_service_libs.error_handling` |
| `raise_{service}_result_storage_error` | `raise_processing_error` | `huleedu_service_libs.error_handling` |
| `raise_{service}_data_retrieval_error` | `raise_processing_error` | `huleedu_service_libs.error_handling` |
| `raise_{service}_event_publishing_error` | `raise_kafka_publish_error` | `huleedu_service_libs.error_handling` |
| `raise_{service}_validation_error` | `raise_validation_error` | `huleedu_service_libs.error_handling` |
| `raise_{service}_parsing_error` | `raise_parsing_error` | `huleedu_service_libs.error_handling` |

### Step 1.3: Update Import Statements

**Replace service-specific imports:**

```python
# BEFORE (Legacy)
from services.{service}_service.error_handling import (
    raise_{service}_content_service_error,
    raise_{service}_algorithm_error,
    # ... other service-specific functions
)

# AFTER (Platform Compliant) 
from huleedu_service_libs.error_handling import (
    raise_content_service_error,
    raise_processing_error,
    raise_connection_error,
    raise_kafka_publish_error,
    raise_validation_error,
    raise_parsing_error,
)
```

### Step 1.4: Replace Function Calls

**Pattern-by-pattern replacement:**

```python
# BEFORE (Legacy)
raise_{service}_content_service_error(
    message="Failed to fetch content",
    storage_id=storage_id
)

# AFTER (Platform Compliant)
raise_content_service_error(
    service="{service}_service",
    operation="fetch_content", 
    message="Failed to fetch content",
    correlation_id=correlation_id,  # CRITICAL: Always required
    storage_id=storage_id
)
```

### Step 1.5: Update All Implementation Files

**Target files (adapt service name):**
- `implementations/*_impl.py`
- `core_logic.py` 
- Main service entry points
- Any custom error handling modules

## PHASE 2: EVENT PROCESSING INTEGRATION

### Step 2.1: Modernize Event Processor

**Key areas to update in `event_processor.py`:**

1. **Correlation ID Extraction Pattern:**
```python
# Extract correlation_id early - critical for error tracking
correlation_id = request_envelope.correlation_id
```

2. **Structured Error Handling in Message Processing:**
```python
try:
    raw_message = msg.value.decode("utf-8")
    request_envelope = EventEnvelope[YourRequestModel].model_validate_json(raw_message)
except Exception as e:
    # Use structured error handling for parsing failures
    correlation_id = uuid4()  # Generate for parsing errors
    raise_parsing_error(
        service="{service}_service",
        operation="parse_kafka_message",
        parse_target="EventEnvelope[YourRequestModel]", 
        message=f"Failed to parse Kafka message: {str(e)}",
        correlation_id=correlation_id,
        topic=msg.topic,
        offset=msg.offset,
        raw_message_length=len(raw_message),
    )
```

3. **Error Categorization Function:**
```python
def _categorize_processing_error(exception: Exception, correlation_id: UUID) -> ErrorDetail:
    """Categorize processing exceptions into appropriate ErrorCode types."""
    if isinstance(exception, HuleEduError):
        return exception.error_detail

    error_message = str(exception)
    exception_type = type(exception).__name__

    if "timeout" in error_message.lower() or "timeout" in exception_type.lower():
        error_code = ErrorCode.TIMEOUT
    elif "connection" in error_message.lower() or "connection" in exception_type.lower():
        error_code = ErrorCode.CONNECTION_ERROR
    elif "validation" in error_message.lower() or "ValidationError" in exception_type:
        error_code = ErrorCode.VALIDATION_ERROR
    elif "parse" in error_message.lower() or "json" in error_message.lower():
        error_code = ErrorCode.PARSING_ERROR
    else:
        error_code = ErrorCode.PROCESSING_ERROR

    return create_error_detail_with_context(
        error_code=error_code,
        message=f"Categorized error: {error_message}",
        service="{service}_service",
        operation="categorize_processing_error", 
        correlation_id=correlation_id,
        details={
            "original_exception_type": exception_type,
            "original_message": error_message,
        },
        capture_stack=False,
    )
```

### Step 2.2: Implement Graceful Degradation

**Critical Pattern (prevents poison message loops):**

```python
async def _process_single_message_impl(...) -> bool:
    try:
        # Core business logic here
        return True
    except HuleEduError as he:
        # Already structured error - log and publish
        logger.error(
            f"Structured error processing message: {he.error_detail.message}",
            exc_info=True,
            extra={"correlation_id": str(he.error_detail.correlation_id)}
        )
        # Publish structured error event
        await _publish_structured_error_event(...)
        return True  # CRITICAL: Return True to commit offset
    except Exception as e:
        # Convert unstructured error 
        error_detail = _categorize_processing_error(e, correlation_id)
        # Publish structured error event
        await _publish_structured_error_event(...)
        return True  # CRITICAL: Return True to commit offset
```

### Step 2.3: OpenTelemetry Integration

**Span Error Recording Pattern:**

```python
try:
    # Business logic
    pass
except HuleEduError as he:
    if span:
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(he)))
        span.set_attributes({
            "error.type": he.error_detail.error_code.value,
            "error.message": he.error_detail.message,
            "error.correlation_id": str(he.error_detail.correlation_id),
        })
    raise
```

### Step 2.4: Update Kafka Consumer

**Connection failure handling in `kafka_consumer.py`:**

```python
except Exception as e:
    raise_connection_error(
        service="{service}_service",
        operation="kafka_consumer_connect",
        target="kafka_broker",
        message=f"Failed to connect to Kafka: {str(e)}",
        correlation_id=correlation_id,
        kafka_bootstrap_servers=bootstrap_servers,
    )
```

### Step 2.5: Update Worker Main

**Service startup error handling in `worker_main.py`:**

```python
except Exception as e:
    raise_initialization_failed(
        service="{service}_service",
        operation="service_startup",
        component="main_worker",
        message=f"Failed to start service: {str(e)}",
        correlation_id=startup_correlation_id,
    )
```

## PHASE 3: COMPREHENSIVE TESTING

### Step 3.1: Create Test Infrastructure

**Required test files (adapt service name):**

1. **Error Categorization Tests:**
```python
# tests/test_error_categorization.py
class TestErrorCategorizationBusinessLogic:
    def test_categorize_preserves_correlation_id(self) -> None:
        correlation_id = uuid4()
        exc = Exception("Test error")
        error_detail = _categorize_processing_error(exc, correlation_id)
        assert error_detail.correlation_id == correlation_id
```

2. **Business Logic Robustness Tests:**
```python  
# tests/test_business_logic_robustness.py
class TestBusinessLogicRobustness:
    async def test_graceful_degradation_with_infrastructure_failures(self, ...):
        # Test that infrastructure failures don't block processing
        result = await process_single_message(...)
        assert result is True  # Processing completed despite failures
```

3. **Boundary Failure Tests:**
```python
# tests/test_boundary_failure_scenarios.py  
class TestBoundaryFailureScenarios:
    async def test_external_service_timeout_handling(self, ...):
        # Mock external boundaries only
        # Test real business logic handles timeouts properly
```

4. **Observability Tests:**
```python
# tests/test_observability_features.py
class TestObservabilityFeatures:
    async def test_opentelemetry_span_recording_successful_flow(self, ...):
        # Test spans are recorded with correlation_id
        spans = opentelemetry_test_isolation.get_finished_spans()
        kafka_span = next((s for s in spans if "kafka.consume" in s.name), None)
        assert str(correlation_id) in str(kafka_span.attributes.get("correlation_id", ""))
```

### Step 3.2: Testing Philosophy

**Boundary Mocking Philosophy:**
- Mock external boundaries only (HTTP clients, Kafka, database)
- Use real business logic for robustness validation
- Test through actual service entry points when possible

**Fixture Pattern:**
```python
@pytest.fixture
def boundary_mocks(self) -> dict[str, AsyncMock]:
    """Create mocks for external boundaries only."""
    return {
        "content_client": AsyncMock(spec=ContentClientProtocol),
        "result_store": AsyncMock(spec=ResultStoreProtocol), 
        "event_publisher": AsyncMock(spec=YourEventPublisherProtocol),
        "kafka_bus": AsyncMock(),
        "http_session": AsyncMock(),
    }
```

### Step 3.3: OpenTelemetry Test Isolation

**Required fixture for OpenTelemetry tests:**
```python
@pytest.fixture
def opentelemetry_test_isolation() -> InMemorySpanExporter:
    """Isolate OpenTelemetry spans for testing."""
    exporter = InMemorySpanExporter()
    # Setup test tracer with in-memory exporter
    return exporter
```

### Step 3.4: Prometheus Registry Cleanup

**Required fixture for metrics tests:**
```python
@pytest.fixture(autouse=True)
def _clear_prometheus_registry() -> Generator[None, None, None]:
    """Clear Prometheus registry between tests to avoid metric conflicts."""
    from prometheus_client import REGISTRY
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except KeyError:
            pass
    yield
```

## PHASE 4: SERVICE-SPECIFIC ADAPTATIONS

### Content Service Adaptations

**Specific error patterns:**
- File storage errors → `raise_processing_error` 
- Content validation errors → `raise_validation_error`
- Metadata extraction errors → `raise_processing_error`

### Batch Orchestrator Service Adaptations

**Specific error patterns:**
- Batch validation errors → `raise_validation_error`
- Job scheduling errors → `raise_processing_error` 
- State transition errors → `raise_validation_error`

### Essay Lifecycle Service Adaptations

**Specific error patterns:**
- State machine errors → `raise_validation_error`
- Transition validation errors → `raise_validation_error`
- Essay status errors → `raise_processing_error`

### File Service Adaptations  

**Specific error patterns:**
- File upload errors → `raise_processing_error`
- File validation errors → Use file validation factories from `huleedu_service_libs.error_handling.file_validation_factories`
- Storage errors → `raise_processing_error`

### CJ Assessment Service Adaptations

**Specific error patterns:**
- Assessment scoring errors → `raise_cj_assessment_service_error`
- Pair generation errors → `raise_processing_error`
- Ranking calculation errors → `raise_processing_error`

### Class Management Service Adaptations

**Specific error patterns:**
- Class operations → Use class management factories from `huleedu_service_libs.error_handling.class_management_factories`
- Student enrollment errors → `raise_student_not_found`, `raise_class_not_found`
- Course validation errors → `raise_course_validation_error`

### Result Aggregator Service Adaptations

**Specific error patterns:**
- Result aggregation errors → `raise_processing_error`
- Data consistency errors → `raise_validation_error`
- Report generation errors → `raise_processing_error`

### LLM Provider Service Adaptations

**Specific error patterns:**
- API key validation → `raise_invalid_api_key`
- Rate limiting → `raise_rate_limit_error`
- Provider communication → `raise_external_service_error`
- Token limit errors → `raise_quota_exceeded`

## PHASE 5: VALIDATION & COMPLETION

### Step 5.1: Run Service-Specific Tests

**Execute targeted test scope:**
```bash
# Run only the specific service tests (NOT test-all)
pdm run pytest services/{service}_service/tests/ -v
```

### Step 5.2: Quality Assurance Checks

**Required quality gates:**
```bash
# Type checking
pdm run mypy services/{service}_service/

# Linting 
pdm run ruff check services/{service}_service/

# Formatting
pdm run ruff format services/{service}_service/
```

### Step 5.3: Import Resolution Verification

**Check for import conflicts:**
```bash
python scripts/check_import_patterns.py
```

### Step 5.4: Integration Test Execution

**Run integration tests with infrastructure:**
```bash
pdm run pytest services/{service}_service/tests/integration/ -m expensive -v
```

## TROUBLESHOOTING GUIDE

### Common Issue 1: Legacy Test Failures

**Symptom:** Tests expecting old error return patterns fail  
**Solution:** Update test expectations to handle HuleEduError exceptions instead of error tuples

```python
# BEFORE
result, error = await service.operation()
assert error is None

# AFTER  
result = await service.operation()  # Will raise HuleEduError on failure
assert result is not None
```

### Common Issue 2: Missing Correlation ID

**Symptom:** `TypeError: missing required argument: 'correlation_id'`  
**Solution:** Ensure all error factory calls include correlation_id parameter

```python
# Add correlation_id to all error function calls
raise_processing_error(
    service="my_service",
    operation="my_operation",
    message="Error message",
    correlation_id=correlation_id,  # This is required
)
```

### Common Issue 3: OpenTelemetry Test Failures

**Symptom:** Tests fail with span recording issues  
**Solution:** Ensure proper test isolation with in-memory span exporter

```python
# Use the opentelemetry_test_isolation fixture
async def test_with_tracing(opentelemetry_test_isolation: InMemorySpanExporter):
    # Test logic here
    spans = opentelemetry_test_isolation.get_finished_spans()
```

### Common Issue 4: Import Resolution Conflicts

**Symptom:** `ModuleNotFoundError` or circular import errors  
**Solution:** Follow proper import hierarchy from service-specific to generic

```python
# Correct import order
from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail
from huleedu_service_libs.error_handling import raise_processing_error
```

## VALIDATION CRITERIA

### Technical Excellence Checklist

- [ ] All service-specific error functions replaced with generic equivalents
- [ ] Correlation ID tracking implemented throughout service
- [ ] OpenTelemetry error recording operational
- [ ] Graceful degradation patterns implemented
- [ ] All tests passing with proper isolation
- [ ] Zero MyPy type checking errors
- [ ] Zero Ruff linting violations
- [ ] Import resolution functional

### Platform Compliance Checklist

- [ ] Generic ErrorCode enum usage only
- [ ] HuleEduError exception pattern adopted
- [ ] Structured error detail creation via factories
- [ ] Observability integration complete
- [ ] Testing philosophy aligned (boundary mocking only)
- [ ] No functional regression in business logic

### Success Metrics

**Quantitative Measures:**
- 100% generic error function adoption
- 100% test pass rate
- Zero type checking violations  
- Zero linting violations
- 100% correlation ID coverage

**Qualitative Measures:**  
- Platform-consistent error categorization
- Full observability integration
- Maintainable test architecture
- Clear error propagation patterns

## REFERENCES

### Architectural Standards
- `.cursor/rules/048-structured-error-handling-standards.mdc`
- `.cursor/rules/070-testing-and-quality-assurance.mdc`
- `.cursor/rules/071-observability-core-patterns.mdc`

### Implementation Examples
- `services/spellchecker_service/` (Complete reference implementation)
- `services/libs/huleedu_service_libs/error_handling/` (Error factory functions)
- `common_core/src/common_core/error_enums.py` (Error codes)
- `common_core/src/common_core/models/error_models.py` (ErrorDetail model)

### Testing Patterns
- `services/spellchecker_service/tests/test_error_categorization.py`
- `services/spellchecker_service/tests/test_business_logic_robustness.py`
- `services/spellchecker_service/tests/test_boundary_failure_scenarios.py`
- `services/spellchecker_service/tests/test_observability_features.py`

**Migration Template Version 1.0 - Based on proven spellchecker service patterns with 150 passing tests**