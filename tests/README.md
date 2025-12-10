# HuleEdu Functional Testing Framework

## Overview

This is the comprehensive functional testing framework for the HuleEdu microservices platform. It provides automated testing capabilities for service health, metrics, and end-to-end workflows.

## Architecture

``` text
tests/
├── __init__.py                     # Framework package
├── README.md                       # This file
├── conftest.py                     # Pytest configuration and global fixtures
├── functional/                     # Functional test modules
│   ├── __init__.py
│   ├── test_service_health.py      # Health and metrics endpoint testing
│   ├── test_e2e_cj_assessment_workflows.py  # CJ assessment E2E workflows
│   ├── test_e2e_spellcheck_workflows.py     # Spellcheck E2E workflows
│   └── ...                         # Other E2E and validation tests
└── utils/                          # Test utilities and managers
    ├── __init__.py
    ├── service_test_manager.py
    ├── kafka_test_manager.py
    └── redis_test_manager.py
```

## Test Categories

### 🔍 **Service Health Testing** (`test_service_health.py`)

- **Health Endpoints**: Validates `/healthz` endpoints across all HTTP services
- **Metrics Endpoints**: Validates `/metrics` endpoints return Prometheus format
- **Response Times**: Ensures services respond within acceptable time limits
- **Kafka Service Health**: Special handling for Kafka-based services

### 📊 **Metrics Validation** (Integrated)

- **Format Compliance**: Validates Prometheus metrics format requirements
- **Standard Metrics**: Ensures HTTP services expose standard request metrics  
- **Service-Specific Metrics**: Validates specialized metrics (e.g., Kafka queue latency)
- **Content-Type Validation**: Ensures correct HTTP headers
- **Live Data**: Validates metrics contain actual data values

### 🔗 **Container Integration** (Planned)

- **Docker Compose Management**: Automated service startup/shutdown
- **Service Dependencies**: Validates proper dependency ordering
- **Health Waiting**: Waits for all services to be healthy before testing
- **Isolated Environments**: Function-scoped test isolation

### 🔄 **End-to-End Workflows** (Planned)

- **Content Upload → Spell Check → Results**: Complete processing pipeline
- **Batch Coordination**: Multi-service batch processing workflows
- **Event-Driven Flows**: Kafka event propagation validation
- **Error Scenarios**: Failure handling and recovery testing

## Batch Registration Entry Point

All functional tests register batches through the API Gateway (AGW) at port 8080.
This ensures tests validate the complete client flow including:
- Edge identity injection from JWT tokens
- Proper header forwarding (X-User-ID, X-Org-ID, X-Correlation-ID)
- EventEnvelope metadata population with org_id

Integration tests that mock service internals may bypass AGW as appropriate
for their abstraction level (see Rule 070/075).

## Usage

### Prerequisites

1. **Bring up the dev stack (single path; no functional profile)**  
   Uses the standard dev compose + overrides already used for day-to-day work.
   ```bash
   pdm run dev-build-start          # build (cached) + start all dev services
   # or, if already built:
   pdm run dev-start
   ```
   - Source `.env` for CLI access: `source .env`
   - Uses dev images with hot-reload mounts; no additional compose profiles

2. **Dependencies Installed**  
   ```bash
   pdm install -G monorepo-tools
   ```
3. **CJ functional guardrails**
   - Ensure the LLM Provider runs in mock mode (`LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true` in `.env`). The functional fixture will skip CJ flows when mock mode is disabled to avoid slow/paid calls.
   - Set `FUNCTIONAL_ASSIGNMENT_ID` (default used if unset: `test_eng5_writing_2025`) so uploads carry an assignment_id for CJ traceability/grade projection.

### Running Tests

- **All functional tests (docker-marked, skip slow)**  
  ```bash
  pdm run pytest-root tests/functional -m "docker and not slow"
  ```
- **Service health only**  
  ```bash
  pdm run pytest-root tests/functional/test_service_health.py -m docker
  ```
- **Specific test**  
  ```bash
  pdm run pytest-root tests/functional/test_service_health.py::TestServiceHealth::test_all_services_healthy -m docker -s
  ```
- **Tear down stack**  
  ```bash
  pdm run dev-stop
  ```

### Test Output Example

``` text
✅ content_service: 200 - {'message': 'Content Service is healthy.', 'status': 'ok'}
✅ batch_orchestrator_service: 200 - {'message': 'Batch Orchestrator Service is healthy', 'status': 'ok'}  
✅ essay_lifecycle_service: 200 - {'service': 'essay-lifecycle-service', 'status': 'healthy'}
📊 content_service: 200 - 5813 chars of metrics data
📊 batch_orchestrator_service: 200 - 3906 chars of metrics data
📊 essay_lifecycle_service: 200 - 3907 chars of metrics data
⚡ content_service: 0.089s response time
⚡ batch_orchestrator_service: 0.034s response time
⚡ essay_lifecycle_service: 0.031s response time
```

## Services Under Test

| **Service** | **HTTP Port** | **Health** | **Metrics** | **Type** |
|-------------|---------------|------------|-------------|----------|
| **Content Service** | 8001 | `/healthz` | `/metrics` | HTTP API |
| **Batch Orchestrator Service** | 5001 | `/healthz` | `/metrics` | HTTP API |
| **Essay Lifecycle Service** | 6001 | `/healthz` | `/metrics` | HTTP API + Kafka Worker |
| **Spell Checker Service** | 8002 | N/A | `/metrics` | Kafka Worker Only |

## Configuration

### **Pytest Configuration** (`conftest.py`)

- **Async Support**: Full pytest-asyncio integration
- **Test Markers**: `functional`, `slow`, `docker` markers for test categorization
- **Event Loop**: Session-scoped event loop for async tests
- **Fixtures**: Global fixture imports and configuration

### **Service URLs** (Configurable via fixtures)

```python
service_urls = {
    "content_service": "http://localhost:8001",
    "batch_orchestrator_service": "http://localhost:5001", 
    "essay_lifecycle_service": "http://localhost:6001",
    "spell_checker_metrics": "http://localhost:8002",
}
```

### **Environment Variables (dev defaults)**

- `JWT_SECRET` (shared by AGW/Identity; from `.env`)
- `HULEEDU_DB_USER`, `HULEEDU_DB_PASSWORD`, `HULEEDU_DB_HOST` (Postgres in dev compose)
- `KAFKA_BOOTSTRAP_SERVERS` (dev compose exposes `localhost:9093`)
- `REDIS_URL` (dev compose exposes `redis://localhost:6379`)
- `INTERNAL_API_KEY` (service-to-service auth; from `.env`)
- `FUNCTIONAL_ASSIGNMENT_ID` (optional, defaults to `test_eng5_writing_2025`): attached to file uploads for CJ/grade-projection traceability.
- `LLM_PROVIDER_SERVICE_USE_MOCK_LLM` should remain `true` for functional runs to keep CJ fast and deterministic.
- Always `source .env` in your shell before running functional tests so CLI helpers match the running stack.

## Technology Stack

- **Test Runner**: pytest with pytest-asyncio
- **HTTP Client**: httpx for async HTTP requests
- **Container Management**: Docker Compose via subprocess
- **Service Management**: Custom DockerComposeManager class
- **Async Support**: Full asyncio support for concurrent testing

## Development Guidelines

### **Adding New Tests**

1. **Create test file** in appropriate category directory
2. **Use async test methods** with `@pytest.mark.asyncio`
3. **Include print statements** for visibility (use `-s` flag)
4. **Test both success and failure scenarios**
5. **Use descriptive test names** and docstrings

### **Test Patterns**

```python
@pytest.mark.asyncio
async def test_service_functionality(self):
    """Test description with expected behavior."""
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8001/endpoint")
        assert response.status_code == 200
        print(f"✅ Service responded: {response.json()}")
```

### **Error Handling**

- **Connection Errors**: Graceful handling for services that may not be running
- **Timeouts**: Reasonable timeout values (5s default)
- **Service-Specific Logic**: Different handling for HTTP vs Kafka services
- **Skip vs Fail**: Use `pytest.skip()` for optional services, `pytest.fail()` for required ones

## Future Enhancements

### **Phase 1** (Immediate)

- [x] Enforce: timeouts >60s must be explicitly marked `@pytest.mark.slow`
- [ ] Expand metrics validation coverage
- [ ] Add container integration tests with DockerComposeManager
- [ ] Add test data fixtures for common scenarios
- [ ] Consolidate overlapping functional flows (pipeline happy-path variants, identity threading/email flows, duplicate NLP/pipeline combinations)

### **Phase 2** (Short-term)

- [ ] End-to-end workflow testing (content upload → spell check → results)
- [ ] Kafka event validation and tracing
- [ ] Performance benchmarking tests
- [ ] Service dependency validation

### **Phase 3** (Medium-term)

- [ ] Load testing capabilities
- [ ] Chaos engineering tests (service failure scenarios)
- [ ] Multi-environment testing (dev, staging, prod)
- [ ] Test reporting and metrics dashboard

## Contributing

1. **Follow naming conventions**: `test_*.py` files, `test_*` methods
2. **Use async patterns**: All HTTP calls should be async
3. **Include visibility**: Add print statements for test output
4. **Document test purpose**: Clear docstrings and comments
5. **Test locally**: Ensure Docker services are running before testing

---

**Status**: ✅ **OPERATIONAL** - Framework tested and functional (Jan 2025)  
**Coverage**: Health checks, metrics validation, response time testing  
**Next**: Container integration and end-to-end workflow testing
