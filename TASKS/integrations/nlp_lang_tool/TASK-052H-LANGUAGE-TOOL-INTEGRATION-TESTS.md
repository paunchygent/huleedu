---
id: 'TASK-052H-LANGUAGE-TOOL-INTEGRATION-TESTS'
title: 'TASK-052H — Language Tool Service Integration Tests'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'integrations'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-09-12'
last_updated: '2025-11-17'
related: []
labels: []
---
# TASK-052H — Language Tool Service Integration Tests

## Objective

Implement behavioral integration tests for Language Tool Service to validate real-world interactions with LanguageTool Java processes, Dishka DI container, and observability infrastructure. Tests must follow Rule 070 principles: no mocking of implementation details, focus on behavioral outcomes, and validate actual system integration points.

## Current State

- ✅ 299 unit tests with full Rule 070 compliance (no @patch usage)
- ❌ Empty integration test directory (`tests/integration/` contains only `__init__.py`)
- ❌ No validation of Java process lifecycle management
- ❌ No end-to-end verification of LanguageTool integration
- ❌ No real metrics emission validation

## Integration Test Requirements

### 1. LanguageTool Process Lifecycle (`test_languagetool_process_lifecycle.py`)

**Behavioral Outcomes to Validate**:

- Java process starts successfully with real JAR file
- Health checks return accurate JVM status (running, heap usage)
- Process restart behavior when LanguageTool becomes unresponsive
- Graceful shutdown cleans up Java processes
- Fallback to stub mode when JAR is missing

**Test Infrastructure**:

- Real LanguageTool JAR in test resources
- Process isolation using TestContainers or subprocess management
- Timeout handling for slow startup/shutdown

### 2. Grammar Analysis Pipeline (`test_grammar_analysis_pipeline.py`)

**Behavioral Outcomes to Validate**:

- End-to-end grammar analysis with real LanguageTool responses
- Category filtering excludes TYPOS/MISSPELLING/SPELLING as configured
- Multiple language support (en-US, sv-SE) produces different results
- Concurrent request handling maintains response quality
- Error propagation from Java exceptions to structured HTTP errors

**Test Data**:

- Text samples with known grammar errors for each supported language
- Malformed text that triggers LanguageTool exceptions
- Large text samples to test timeout behavior

### 3. Metrics Emission Validation (`test_metrics_emission.py`)

**Behavioral Outcomes to Validate**:

- `wrapper_duration_seconds{language}` metrics appear in `/metrics` endpoint
- `api_errors_total{endpoint,error_type}` increments on real error conditions
- Metrics persist across multiple requests
- Prometheus format compliance in actual HTTP responses
- Metric labels contain expected values from real operations

**Verification Method**:

- Parse actual Prometheus metrics from `/metrics` endpoint
- Validate metric values increase with real requests
- No mocking of metrics collection infrastructure

### 4. Configuration Integration (`test_configuration_integration.py`)

**Behavioral Outcomes to Validate**:

- Environment variables correctly configure LanguageTool JAR path
- Port binding works for both HTTP (8085) and LanguageTool (8081)
- Invalid configuration triggers appropriate fallback behavior
- Settings validation prevents startup with incompatible values

**Test Scenarios**:

- Missing JAR file triggers stub mode
- Port conflicts are detected and reported
- Invalid heap size settings are rejected
- Environment variable precedence works correctly

### 5. Dishka DI Container Integration (`test_di_container_integration.py`)

**Behavioral Outcomes to Validate**:

- Full container lifecycle with real providers (not test mocks)
- Protocol compliance: `LanguageToolWrapperProtocol` implementations work
- Dependency resolution provides correct implementations based on environment
- Scope management: APP scope persists, REQUEST scope creates new instances
- Container cleanup releases resources properly

**Validation Approach**:

- Use real DI container with actual providers
- Verify protocol implementations through behavioral contracts
- No mocking of Dishka infrastructure

## Implementation Guidelines

### Test Structure

```
tests/integration/
├── conftest.py                           # TestContainers setup, real JAR management
├── test_languagetool_process_lifecycle.py
├── test_grammar_analysis_pipeline.py
├── test_metrics_emission.py
├── test_configuration_integration.py
└── test_di_container_integration.py
```

### Rule 070 Compliance

- **NO @patch usage**: Test real implementations, not mocks
- **Behavioral focus**: Validate what the system does, not how it does it
- **Real infrastructure**: Use actual LanguageTool JAR, real HTTP clients, real metrics
- **Isolation**: Each test must be independent and clean up resources
- **Timeouts**: ≤ 60 seconds per test, default to 30 seconds for event-driven flows

### Test Infrastructure Requirements

- **TestContainers**: For isolated Java process testing
- **Real LanguageTool JAR**: Bundle in `tests/integration/resources/`
- **HTTP Test Client**: Real Quart test client, not mocked responses
- **Process Management**: Clean startup/shutdown in test isolation
- **Metrics Parsing**: Real Prometheus client to validate `/metrics` output

## Acceptance Criteria

1. **Process Reliability**: Java process lifecycle works in isolated test environment
2. **End-to-End Validation**: Real grammar analysis produces expected categorized results
3. **Observability Verification**: Metrics actually appear in Prometheus format
4. **Configuration Robustness**: Environment-based configuration works in practice
5. **DI Container Integrity**: Real dependency injection with protocol compliance
6. **Performance Baseline**: Integration tests complete within timeout limits
7. **Resource Cleanup**: No leaked processes or resources after test completion

## Dependencies

- LanguageTool JAR file (download and bundle in test resources)
- TestContainers or equivalent process isolation
- Prometheus client library for metrics validation
- Real environment variable management in tests

## Success Metrics

- All integration tests pass consistently
- No process leaks or resource cleanup issues
- Test execution time within acceptable limits (< 5 minutes total)
- Coverage of critical integration points identified in gap analysis
- Behavioral validation of real-world usage scenarios

## References

- Rule 070: Testing and Quality Assurance (behavioral testing principles)
- TASK-052G: Observability & Health (metrics requirements)
- Service README: Current unit test coverage (299 tests)
- Memory: Protocol-based testing patterns for Dishka DI services
