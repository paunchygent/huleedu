# Circuit Breaker Implementation - Phase 2 Handoff Document

## Context for Next Session

You are continuing the circuit breaker implementation for HuleEdu microservices. Phase 1 (HTTP client circuit breakers) is COMPLETE and tested. This document provides everything needed to continue with Phase 2.

## Current State Summary

### ✅ What's Already Implemented (Phase 1)

1. **Core Circuit Breaker Infrastructure** (fully tested and working):
   - `services/libs/huleedu_service_libs/resilience/circuit_breaker.py` - Main circuit breaker class
   - `services/libs/huleedu_service_libs/resilience/registry.py` - Registry for managing multiple breakers
   - `services/libs/huleedu_service_libs/resilience/resilient_client.py` - Generic wrapper using `make_resilient()`
   - `services/libs/huleedu_service_libs/error_handling/context_manager.py` - Enhanced error context

2. **Example Implementation** (use as reference):
   - `services/batch_orchestrator_service/config.py` - Configuration with circuit breaker settings
   - `services/batch_orchestrator_service/di.py` - DI integration pattern (see `provide_batch_conductor_client`)
   - `services/batch_orchestrator_service/tests/integration/test_circuit_breaker_integration.py` - Test patterns

3. **Documentation Updates**:
   - `.cursor/rules/040-service-implementation-guidelines.mdc` - Section 4.11 added for resilience patterns
   - `.cursor/rules/020.11-service-libraries-architecture.mdc` - Section 6.6 added for circuit breaker utilities

## 🚀 Next Task: Phase 2 - Kafka Producer Circuit Breakers

### Primary Reference Documents

1. **Main Implementation Plan**: `/Documentation/TASKS/CIRCUIT_BREAKER_REMAINING_PHASES.md`
   - Start at "Phase 2: Kafka Producer Circuit Breakers"
   - Contains detailed implementation steps and code examples

2. **Architectural Rules to Read First**:
   - `.cursor/rules/010-foundational-principles.mdc` - Core principles
   - `.cursor/rules/040-service-implementation-guidelines.mdc` - Section 4.11 for resilience patterns
   - `.cursor/rules/051-event-system-standards.mdc` - Kafka patterns
   - `.cursor/rules/042-async-patterns-and-di.mdc` - DI patterns

### Phase 2 Implementation Steps

1. **Create Resilient Kafka Bus** (`services/libs/huleedu_service_libs/kafka/resilient_kafka_bus.py`):
   ```python
   class ResilientKafkaBus(KafkaBus):
       def __init__(self, *args, circuit_breaker: Optional[CircuitBreaker] = None, **kwargs):
           super().__init__(*args, **kwargs)
           self.circuit_breaker = circuit_breaker
           self._fallback_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
   ```

2. **Implement Fallback Queue Handler** (`services/libs/huleedu_service_libs/kafka/fallback_handler.py`):
   - Queue messages when Kafka is unavailable
   - Retry when circuit closes
   - Monitor queue size

3. **Update Each Service's DI Provider**:
   - Add circuit breaker to Kafka bus in each service's `di.py`
   - Follow pattern from Batch Orchestrator's `provide_batch_conductor_client`
   - Services to update: Batch Orchestrator, Essay Lifecycle, Spell Checker, CJ Assessment, File Service, Class Management

### Key Patterns to Follow

1. **DI Integration Pattern** (from Phase 1):
   ```python
   @provide(scope=Scope.APP)
   def provide_kafka_bus(settings: Settings, circuit_breaker_registry: CircuitBreakerRegistry) -> KafkaBus:
       if settings.CIRCUIT_BREAKER_ENABLED:
           breaker = CircuitBreaker(...)
           circuit_breaker_registry.register("kafka_producer", breaker)
           return ResilientKafkaBus(..., circuit_breaker=breaker)
       return KafkaBus(...)
   ```

2. **Configuration Pattern**:
   - Add to each service's `config.py`:
   ```python
   KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 10
   KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 30
   ```

3. **Testing Pattern**:
   - Create `tests/integration/test_kafka_circuit_breaker.py`
   - Follow patterns from `test_circuit_breaker_integration.py`

### Important Implementation Notes

1. **Import Paths**: Use full module paths (`huleedu_service_libs.resilience`) not relative imports
2. **Logging**: Use `create_service_logger()` from `huleedu_service_libs.logging_utils`
3. **Type Safety**: Maintain protocol compatibility - `ResilientKafkaBus` must implement same interface as `KafkaBus`
4. **Backwards Compatibility**: Circuit breakers must be optional (controlled by `CIRCUIT_BREAKER_ENABLED`)

### Success Criteria for Phase 2

1. Kafka publishing protected by circuit breakers in all services
2. Failed messages queued locally during outages
3. Automatic retry when Kafka recovers
4. No message loss during circuit breaker transitions
5. All existing tests still pass

### Commands to Run

```bash
# After implementation, run tests:
pdm run pytest services/libs/huleedu_service_libs/tests/test_resilient_kafka_bus.py -v
pdm run pytest tests/integration/test_kafka_circuit_breaker.py -v

# Check code quality:
pdm run ruff check services/libs/huleedu_service_libs/kafka/
pdm run mypy services/libs/huleedu_service_libs/kafka/
```

## Questions to Ask User

Before starting implementation:
1. "Should I proceed with Phase 2 (Kafka circuit breakers) or is there a different priority?"
2. "Are there any specific Kafka failure scenarios you want to handle beyond basic connection failures?"
3. "What's the preferred behavior for the fallback queue - in-memory only or should critical messages persist to disk?"

## Final Notes

- All Phase 1 code is production-ready and tested
- The circuit breaker pattern is proven to work with the DI system
- Follow the established patterns from Phase 1 for consistency
- Refer to `/Documentation/TASKS/CIRCUIT_BREAKER_REMAINING_PHASES.md` for complete details on all remaining phases