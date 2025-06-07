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
│   ├── test_metrics_endpoints.py   # Prometheus metrics validation
│   ├── test_end_to_end_workflows.py    # TODO: End-to-end workflow testing
│   └── test_container_integration.py   # TODO: Docker integration testing
└── fixtures/                      # Test fixtures and utilities
    ├── __init__.py
    └── docker_services.py         # Docker Compose management fixtures
```

## Test Categories

### 🔍 **Service Health Testing** (`test_service_health.py`)

- **Health Endpoints**: Validates `/healthz` endpoints across all HTTP services
- **Metrics Endpoints**: Validates `/metrics` endpoints return Prometheus format
- **Response Times**: Ensures services respond within acceptable time limits
- **Kafka Service Health**: Special handling for Kafka-based services

### 📊 **Metrics Validation** (`test_metrics_endpoints.py`)

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

## Usage

### Prerequisites

1. **Docker Services Running**: Ensure all services are up and healthy

   ```bash
   docker-compose up -d
   ```

2. **Dependencies Installed**: Install testing dependencies

   ```bash
   pdm install -G monorepo-tools
   ```

### Running Tests

#### **All Functional Tests**

```bash
pdm run test-all tests/functional/ -v
```

#### **Service Health Only**

```bash
pdm run test-all tests/functional/test_service_health.py -v
```

#### **Specific Test**

```bash
pdm run test-all tests/functional/test_service_health.py::TestServiceHealth::test_all_services_health_endpoints -s
```

#### **With Live Output**

```bash
pdm run test-all tests/functional/ -s -v
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

- [ ] Complete `test_metrics_endpoints.py` implementation
- [ ] Add container integration tests with DockerComposeManager
- [ ] Add test data fixtures for common scenarios

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
