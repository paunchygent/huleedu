# Distributed Testing Infrastructure for Essay Lifecycle Service

This directory contains comprehensive distributed testing infrastructure for validating the horizontal scaling capabilities, race condition prevention, and performance characteristics of the Essay Lifecycle Service under realistic multi-instance deployment scenarios.

## Overview

The distributed testing infrastructure implements **Phase 3: Integration Testing** of the ELS-002 distributed state management implementation. It validates Option B database-only assignment prevents race conditions across instances.

## Key Testing Capabilities

### 🔄 Race Condition Prevention
- Validates atomic slot assignment under concurrent load
- Tests identical content provisioning events across multiple instances
- Ensures only single slot assignment occurs despite concurrent requests
- Verifies database constraint enforcement prevents duplicate assignments

### 📊 Redis State Consistency 
- Tests Redis atomic operations under high load (SPOP, HSET, WATCH/MULTI/EXEC)
- Validates state consistency during connection failures and recovery
- Tests distributed lock behavior under contention
- Benchmarks Redis operation performance (target: < 0.1s)

### ⚡ Performance and Scaling
- Validates horizontal scaling benefits (2x+ improvement with 5 instances)
- Tests memory usage independence from batch size
- Validates performance targets (< 0.2s database, < 1s coordination)
- Measures sustained load performance over time

### 🐳 Docker Compose Infrastructure
- Multi-instance ELS deployment with shared Redis and PostgreSQL
- Load balancer for distributing events across instances
- Monitoring stack (Prometheus, Grafana) for observability
- Event generator for realistic concurrent workload simulation

## Architecture

### Test Infrastructure Components

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   ELS Worker 1  │  │   ELS Worker 2  │  │   ELS Worker 3  │
└─────────┬───────┘  └─────────┬───────┘  └─────────┬───────┘
          └────────────────────┼────────────────────┘
                               │
                    ┌─────────┴────────┐
                    │  Load Balancer   │
                    └─────────┬────────┘
                              │
                    ┌─────────▼────────┐
                    │   PostgreSQL     │
                    │  (Option B MVCC) │
                    └──────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
    ┌─────▼─────┐       ┌─────▼─────┐       ┌─────▼─────┐
    │   Redis   │       │   Kafka   │       │ Prometheus │
    │(Idempotency)│     │ (Events)  │       │ (Metrics)  │
    └───────────┘       └───────────┘       └───────────┘
```

### Option B Coordination Flow

1. **Batch Setup**: BOS sends `BatchEssaysRegistered` to ELS
2. **Slot Creation**: ELS creates essay_states rows with status='UPLOADED'  
3. **Content Events**: File Service sends `EssayContentProvisionedV1` to Kafka
4. **Load Distribution**: Kafka distributes to N ELS instances
5. **Assignment**: PostgreSQL FOR UPDATE SKIP LOCKED ensures single winner
6. **Idempotency**: Partial unique index on (batch_id, text_storage_id)
7. **Completion**: ELS publishes `BatchContentProvisioningCompletedV1` to BOS

## Test Files

### Core Test Suites

- **`test_concurrent_slot_assignment.py`**: Race condition prevention and cross-instance coordination
- **`test_redis_state_consistency.py`**: Redis atomic operations and state integrity
- **`test_distributed_performance.py`**: Performance, scaling, and load testing

### Infrastructure

- **`conftest.py`**: Distributed test fixtures and utilities
- **`docker-compose.distributed-test.yml`**: Multi-instance deployment definition
- **`event_generator.py`**: Concurrent event generation for load testing
- **`run_distributed_tests.py`**: Comprehensive test orchestration script

### Configuration

- **`nginx.conf`**: Load balancer configuration for event distribution
- **`prometheus.yml`**: Metrics collection from all ELS instances
- **`grafana/`**: Dashboard and visualization configuration

## Usage

### Quick Start

```bash
# Run complete distributed test suite
cd services/essay_lifecycle_service/tests/distributed
python run_distributed_tests.py --scenario all

# Run specific test scenarios
python run_distributed_tests.py --scenario race_conditions
python run_distributed_tests.py --scenario redis_consistency  
python run_distributed_tests.py --scenario performance

# Run with custom configuration
python run_distributed_tests.py --instances 5 --duration 120
```

### Individual Test Execution

```bash
# Race condition tests
pdm run pytest test_concurrent_slot_assignment.py -v

# Redis consistency tests  
pdm run pytest test_redis_state_consistency.py -v

# Performance tests
pdm run pytest test_distributed_performance.py -m performance -v
```

### Docker Compose Testing

```bash
# Start distributed infrastructure
docker compose -f docker-compose.distributed-test.yml up -d --build

# Check service health
docker compose -f docker-compose.distributed-test.yml ps

# View logs
docker compose -f docker-compose.distributed-test.yml logs -f

# Run event generator
docker compose -f docker-compose.distributed-test.yml run --rm event_generator

# Stop infrastructure
docker compose -f docker-compose.distributed-test.yml down --remove-orphans
```

## Performance Targets

The tests validate these performance requirements:

| Operation Type | Target | Validation |
|---|---|---|
| Redis atomic operations | < 0.1s | P95 duration under concurrent load |
| Database operations | < 0.2s | Average duration for state updates |
| Batch coordination | < 1s | End-to-end slot assignment |
| Horizontal scaling | 2x improvement | 5 instances vs 1 instance throughput |
| Memory efficiency | Size-independent | Memory usage independent of batch size |
| Success rate | > 95% | Under concurrent contention |

## Test Scenarios

### Scenario 1: Concurrent Race Condition Prevention

Tests that multiple identical content provisioning events result in exactly one slot assignment:

```python
# 20 concurrent identical events → 1 successful assignment
# Validates: Redis SPOP atomicity, database constraints
# Expected: No duplicate assignments, data integrity maintained
```

### Scenario 2: Cross-Instance Coordination

Tests slot assignment coordination across multiple ELS instances:

```python
# 6 essays across 3 instances → 6 unique assignments
# Validates: Distributed coordination, no conflicts
# Expected: All slots filled, unique content per slot
```

### Scenario 3: Batch Completion Detection

Tests distributed batch completion detection:

```python
# Fill all slots from different instances → BatchEssaysReady event
# Validates: Completion coordination, event publishing
# Expected: Single completion event, proper timing
```

### Scenario 4: High Concurrency Performance

Tests performance under high concurrent load:

```python
# 30 tasks competing for 15 slots → 15 successful assignments
# Validates: Performance under contention, atomicity
# Expected: Target performance maintained, no data corruption
```

### Scenario 5: Redis State Consistency

Tests Redis state integrity under various conditions:

```python
# Connection failures, high load, lock contention
# Validates: Atomic operations, recovery, consistency
# Expected: State integrity maintained, performance targets met
```

### Scenario 6: Horizontal Scaling Benefits

Tests performance improvement with multiple instances:

```python
# Compare 1 vs 3 vs 5 instances → Linear scaling improvement
# Validates: Scaling benefits, resource utilization
# Expected: >1.5x improvement with 3 instances, >2x with 5 instances
```

## Monitoring and Observability

### Prometheus Metrics

The test infrastructure collects metrics from all ELS instances:

- **Operation timing**: Request duration distributions
- **Success rates**: Success/failure ratios per instance
- **Redis operations**: SPOP, HSET, HGETALL timing
- **Database operations**: Query timing and connection pool usage
- **Coordination events**: Batch registration, slot assignment, completion

### Grafana Dashboards

Visualization of distributed performance:

- Real-time operation timing across instances
- Redis and PostgreSQL performance comparison
- Memory usage patterns and scaling efficiency
- Error rates and success rate trends

### Log Aggregation

Centralized logging from all instances for debugging:

- Coordination event tracing with correlation IDs
- Redis operation debugging with key analysis
- Database constraint violation detection
- Load balancer request distribution analysis

## Validation Criteria

### ✅ Distributed Safety Validation

- [x] Multiple service instances coordinate without conflicts
- [x] Pod restarts do not corrupt batch coordination state  
- [x] Concurrent content provisioning handled atomically
- [x] Zero duplicate slot assignments under load

### ✅ Performance Validation

- [x] Redis operations < 0.1s per slot assignment
- [x] Database operations < 0.2s for state updates
- [x] Batch coordination < 1s for completion detection
- [x] Memory usage independent of batch size

### ✅ Integration Validation

- [x] Cross-instance event coordination works correctly
- [x] Database constraints prevent integrity violations
- [x] Redis state consistency maintained under load
- [x] Horizontal scaling provides performance benefits

## Troubleshooting

### Common Issues

**Docker Compose Services Not Starting**
```bash
# Check Docker daemon and available resources
docker system info
docker compose -f docker-compose.distributed-test.yml logs
```

**Redis Connection Failures**
```bash
# Verify Redis container health
docker compose -f docker-compose.distributed-test.yml exec redis redis-cli ping
```

**PostgreSQL Connection Issues**
```bash
# Check PostgreSQL readiness
docker compose -f docker-compose.distributed-test.yml exec postgres pg_isready
```

**Test Timeouts**
```bash
# Increase test timeouts for slower environments
python run_distributed_tests.py --duration 180
```

### Debug Mode

Enable detailed logging for troubleshooting:

```bash
export LOG_LEVEL=DEBUG
python run_distributed_tests.py --scenario race_conditions
```

### Performance Debugging

Monitor system resources during tests:

```bash
# Monitor Docker containers
docker stats

# Monitor system resources
htop

# Check Redis memory usage
docker compose -f docker-compose.distributed-test.yml exec redis redis-cli info memory
```

## Architecture Compliance

This testing infrastructure follows HuleEdu architectural standards:

- **Rule 070**: Protocol-based testing with real infrastructure
- **Rule 042**: Async patterns and dependency injection testing
- **Rule 084**: Docker containerization standards
- **Rule 071**: Comprehensive observability integration

The tests validate that the distributed implementation maintains the architectural principles while achieving horizontal scaling and eliminating race conditions in slot assignment.