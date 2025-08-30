# TASK-045: LLM Provider Service Test Fixes - Async Architecture Alignment

## Status: ✅ COMPLETED

**Created**: 2025-01-30
**Priority**: CRITICAL
**Estimated Effort**: 8-12 hours
**Assignee**: Development Team

## Problem Statement

The LLM Provider Service has 12 failing tests due to an architectural shift to async-only, queue-based processing. Tests assume synchronous behavior while the service mandates:
- ALL requests are queued (returns `LLMQueuedResult`)
- `callback_topic` is REQUIRED for all requests
- Results delivered via Kafka callbacks only

### Failing Tests
1. `test_mock_provider_with_queue_processor.py::test_queue_processor_handles_mock_provider_errors`
2. `test_end_to_end_performance.py::TestEndToEndPerformance::test_end_to_end_load_scenario`
3. `test_end_to_end_performance.py::TestEndToEndPerformance::test_mixed_workload_performance`
4. `test_infrastructure_performance.py::TestInfrastructurePerformance::test_realistic_concurrent_requests_performance`
5. `test_infrastructure_performance.py::TestInfrastructurePerformance::test_end_to_end_infrastructure_load`
6. `test_single_request_performance.py::TestSingleRequestPerformance::test_multiple_sequential_requests`
7. `test_single_request_performance.py::TestSingleRequestPerformance::test_infrastructure_overhead_analysis`
8. `test_callback_publishing.py::TestPublishFailureHandling::test_request_processing_continues_after_publish_failure`
9. `test_orchestrator.py::test_orchestrator_successful_comparison`
10. `test_orchestrator.py::test_orchestrator_queues_when_provider_unavailable`
11. `test_orchestrator.py::test_orchestrator_provider_error`
12. `test_orchestrator.py::test_orchestrator_with_overrides`

### Root Causes
1. **Architectural Mismatch**: Tests expect synchronous responses, service is async-only
2. **Missing Parameters**: Tests don't provide required `callback_topic`
3. **Test Design**: Unit and integration concerns are conflated
4. **Error Propagation**: Circuit breaker wrappers affect error code mapping

## Architectural Solution

### Core Principle: Separation of Concerns
Following DDD and Clean Architecture principles:
- **Domain Layer**: Business logic (comparison processing)
- **Application Layer**: Orchestration and queuing
- **Infrastructure Layer**: Kafka, Redis, HTTP

### Key Design Decisions
1. **NO TEST MODE FLAGS**: Maintain single code path, use DI for test variants
2. **PROCESSOR EXTRACTION**: Separate domain logic from infrastructure
3. **TYPED FIXTURES**: Use Pydantic settings, not MagicMocks
4. **CLEAR TEST SCOPES**: Unit tests for domain, integration for full flow

## Implementation Plan

### Phase 1: Domain Extraction (Day 1 Morning)

#### 1.1 Define Processor Protocol
```python
# services/llm_provider_service/protocols.py
class ComparisonProcessorProtocol(Protocol):
    """Domain logic for essay comparison processing."""
    
    async def process_comparison(
        self,
        provider: LLMProviderType,
        user_prompt: str,
        essay_a: str,
        essay_b: str,
        correlation_id: UUID,
        **overrides: Any,
    ) -> LLMOrchestratorResponse:
        """Process comparison without infrastructure concerns.
        
        This is pure domain logic - no queuing, no callbacks.
        Used by QueueProcessor for actual LLM invocation.
        """
        ...
```

#### 1.2 Extract Implementation
```python
# services/llm_provider_service/implementations/comparison_processor_impl.py
class ComparisonProcessorImpl:
    """Processes LLM comparisons - domain logic only."""
    
    def __init__(
        self,
        providers: Dict[LLMProviderType, LLMProviderProtocol],
        event_publisher: LLMEventPublisherProtocol,
        settings: Settings,
    ):
        # Domain dependencies only
        self.providers = providers
        self.event_publisher = event_publisher
        self.settings = settings
    
    async def process_comparison(self, ...) -> LLMOrchestratorResponse:
        # Extract from current orchestrator._make_direct_llm_request()
        # This contains the actual provider calling logic
        ...
```

#### 1.3 Wire into Worker
```python
# services/llm_provider_service/implementations/queue_processor_impl.py
class QueueProcessorImpl:
    def __init__(
        self,
        comparison_processor: ComparisonProcessorProtocol,  # NEW
        queue_manager: QueueManagerProtocol,
        # ... other deps
    ):
        self.comparison_processor = comparison_processor
        # ...
    
    async def _process_request(self, queued_request: QueuedRequest):
        # Use processor instead of orchestrator.process_queued_request
        result = await self.comparison_processor.process_comparison(...)
```

#### 1.4 Update DI Container
```python
# services/llm_provider_service/di.py
class LLMProviderServiceProvider(Provider):
    comparison_processor = provide(
        ComparisonProcessorImpl,
        scope=Scope.APP,
        provides=ComparisonProcessorProtocol,
    )
```

### Phase 2: Test Infrastructure (Day 1 Afternoon)

#### 2.1 Create Fake Queue Bus
```python
# services/llm_provider_service/tests/fixtures/fake_queue_bus.py
class FakeQueueBus:
    """In-memory queue for unit testing."""
    
    def __init__(self):
        self.enqueued_requests: List[QueuedRequest] = []
        self.processed_requests: List[UUID] = []
        
    async def enqueue(self, request: QueuedRequest) -> bool:
        self.enqueued_requests.append(request)
        return True
        
    async def dequeue(self) -> Optional[QueuedRequest]:
        if self.enqueued_requests:
            return self.enqueued_requests.pop(0)
        return None
```

#### 2.2 Create Fake Event Publisher
```python
# services/llm_provider_service/tests/fixtures/fake_event_publisher.py
class FakeEventPublisher:
    """Records events for assertion without Kafka."""
    
    def __init__(self):
        self.published_events: List[Dict[str, Any]] = []
        
    async def publish_llm_request_completed(self, **kwargs):
        self.published_events.append({
            "type": "llm_request_completed",
            **kwargs
        })
```

#### 2.3 Typed Settings Fixtures
```python
# services/llm_provider_service/tests/fixtures/test_settings.py
class TestSettings(Settings):
    """Typed settings for tests."""
    
    # Override defaults for testing
    QUEUE_MAX_SIZE: int = 100
    QUEUE_REQUEST_TTL_HOURS: int = 1
    LLM_CIRCUIT_BREAKER_ENABLED: bool = False  # Unit tests
    
@pytest.fixture
def unit_test_settings() -> TestSettings:
    """Settings for unit tests - no infrastructure."""
    return TestSettings(
        REDIS_ENABLED=False,
        KAFKA_ENABLED=False,
    )

@pytest.fixture
def integration_test_settings() -> TestSettings:
    """Settings for integration tests - full stack."""
    return TestSettings(
        REDIS_ENABLED=True,
        KAFKA_ENABLED=True,
    )
```

#### 2.4 Callback Topic Factory
```python
# services/llm_provider_service/tests/fixtures/callback_fixtures.py
from huleedu_service_libs.kafka_utils import topic_name

@pytest.fixture
def callback_topic_factory():
    """Generate unique callback topics for tests."""
    def _factory(test_name: str) -> str:
        return topic_name(
            service="test",
            entity=test_name.replace("test_", ""),
            event="callback",
            version="v1"
        )
    return _factory
```

### Phase 3: Test Migration (Day 2 Morning)

#### 3.1 Unit Tests - Target Processor
```python
# services/llm_provider_service/tests/unit/test_comparison_processor.py
class TestComparisonProcessor:
    """Unit tests for domain logic only."""
    
    @pytest.fixture
    def processor(self, unit_test_settings):
        mock_provider = AsyncMock(spec=LLMProviderProtocol)
        fake_publisher = FakeEventPublisher()
        
        return ComparisonProcessorImpl(
            providers={LLMProviderType.MOCK: mock_provider},
            event_publisher=fake_publisher,
            settings=unit_test_settings,
        )
    
    async def test_successful_comparison(self, processor):
        # Test domain logic directly - no queue
        result = await processor.process_comparison(
            provider=LLMProviderType.MOCK,
            user_prompt="Compare",
            essay_a="A",
            essay_b="B",
            correlation_id=uuid4(),
        )
        
        assert isinstance(result, LLMOrchestratorResponse)
        assert result.winner in ["Essay A", "Essay B"]
```

#### 3.2 Integration Tests - Full Flow
```python
# services/llm_provider_service/tests/integration/test_orchestrator_integration.py
class TestOrchestratorIntegration:
    """Integration tests with queue and callbacks."""
    
    async def test_queued_request_with_callback(
        self,
        orchestrator,
        kafka_test_manager,
        callback_topic_factory,
    ):
        callback_topic = callback_topic_factory("orchestrator_callback")
        
        # Orchestrator should queue the request
        result = await orchestrator.perform_comparison(
            provider=LLMProviderType.MOCK,
            user_prompt="Compare",
            essay_a="A",
            essay_b="B",
            correlation_id=uuid4(),
            callback_topic=callback_topic,  # REQUIRED
        )
        
        # Verify queued result
        assert isinstance(result, LLMQueuedResult)
        assert result.status == "queued"
        
        # Wait for callback on topic
        callback_event = await kafka_test_manager.consume_event(
            topic=callback_topic,
            timeout=10.0
        )
        
        assert callback_event is not None
        assert callback_event["status"] == "completed"
```

#### 3.3 Performance Tests - Split Concerns
```python
# services/llm_provider_service/tests/performance/test_ingress_performance.py
@pytest.mark.kafka
class TestIngressPerformance:
    """Test queue acceptance rate."""
    
    async def test_ingress_throughput(
        self,
        orchestrator,
        callback_topic_factory,
    ):
        requests_sent = 0
        requests_accepted = 0
        
        for i in range(100):
            callback_topic = callback_topic_factory(f"ingress_{i}")
            
            result = await orchestrator.perform_comparison(
                provider=LLMProviderType.MOCK,
                user_prompt=f"Request {i}",
                essay_a="A",
                essay_b="B",
                correlation_id=uuid4(),
                callback_topic=callback_topic,
            )
            
            requests_sent += 1
            if isinstance(result, LLMQueuedResult):
                requests_accepted += 1
        
        acceptance_rate = requests_accepted / requests_sent
        assert acceptance_rate >= 0.95  # 95% acceptance SLA

# services/llm_provider_service/tests/performance/test_e2e_latency.py
@pytest.mark.slow
@pytest.mark.kafka
class TestEndToEndLatency:
    """Test processing latency."""
    
    async def test_callback_latency_p99(
        self,
        orchestrator,
        kafka_test_manager,
        callback_topic_factory,
    ):
        latencies = []
        
        for i in range(20):
            callback_topic = callback_topic_factory(f"e2e_{i}")
            start_time = time.time()
            
            # Send request
            await orchestrator.perform_comparison(
                provider=LLMProviderType.MOCK,
                user_prompt=f"Request {i}",
                essay_a="A",
                essay_b="B",
                correlation_id=uuid4(),
                callback_topic=callback_topic,
            )
            
            # Wait for callback
            callback = await kafka_test_manager.consume_event(
                topic=callback_topic,
                timeout=30.0
            )
            
            if callback:
                latency = time.time() - start_time
                latencies.append(latency)
        
        p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]
        assert p99_latency < 5.0  # P99 under 5 seconds
```

### Phase 4: Contract Testing (Day 2 Afternoon)

#### 4.1 Event Schema Validation
```python
# services/llm_provider_service/tests/contracts/test_event_contracts.py
class TestEventContracts:
    """Validate event schemas."""
    
    async def test_callback_event_schema(self, fake_event_publisher):
        # Trigger event publication
        await fake_event_publisher.publish_llm_request_completed(
            provider="mock",
            correlation_id=uuid4(),
            success=True,
            result={"winner": "Essay A", "justification": "Better"},
        )
        
        # Validate against EventEnvelope
        event = fake_event_publisher.published_events[0]
        
        # Should be wrappable in EventEnvelope
        envelope = EventEnvelope(
            event_id=uuid4(),
            event_type="llm_request_completed",
            source_service="llm_provider_service",
            correlation_id=event["correlation_id"],
            payload=event,
        )
        
        # Validates against Pydantic model
        assert envelope.event_type == "llm_request_completed"
```

### Phase 5: Validation and Cleanup

#### 5.1 Type Checking
```bash
# From repository root
pdm run typecheck-all

# Expected: 0 errors across all files
```

#### 5.2 Test Execution
```bash
# Run service tests
pdm run pytest services/llm_provider_service/tests -m ""

# Run specific test categories
pdm run pytest -m "not kafka"  # Unit tests only
pdm run pytest -m kafka        # Integration tests
pdm run pytest -m slow         # Performance tests
```

#### 5.3 Coverage Verification
```bash
pdm run test-cov

# Target: >90% coverage for domain logic
# Target: >80% coverage for integration paths
```

## Success Criteria

### Functional
- ✅ All 12 failing tests pass
- ✅ Unit tests run without Kafka/Redis
- ✅ Integration tests validate full async flow
- ✅ Performance tests measure correct metrics

### Architectural
- ✅ Domain logic separated from infrastructure
- ✅ No test mode flags in production code
- ✅ DI patterns preserved (Rule 042)
- ✅ Type safety maintained (MyPy strict)

### Quality
- ✅ Tests follow Rule 075 methodology
- ✅ Clear test scope separation
- ✅ Reusable test infrastructure created
- ✅ Contract tests for event schemas

## Risk Mitigation

### Risks
1. **Processor extraction breaks existing functionality**
   - Mitigation: Incremental refactor with continuous test validation
   
2. **Test infrastructure adds complexity**
   - Mitigation: Start simple, enhance based on needs
   
3. **Performance test flakiness**
   - Mitigation: Add retries, timeouts, and environment markers

4. **DI container configuration errors**
   - Mitigation: Validate with integration tests after each change

## Architecture Decisions

### ADR-001: Processor Pattern for Domain Logic
**Status**: Accepted
**Context**: Need to test domain logic without infrastructure
**Decision**: Extract `ComparisonProcessorProtocol` from orchestrator
**Consequences**: 
- (+) Clean unit testing
- (+) Reusable domain logic
- (-) Additional abstraction layer

### ADR-002: No Test Mode Flags
**Status**: Accepted
**Context**: Avoid test/production code divergence
**Decision**: Use DI to inject test implementations
**Consequences**:
- (+) Single code path
- (+) Production fidelity
- (-) More test infrastructure needed

### ADR-003: Typed Test Settings
**Status**: Accepted
**Context**: MagicMocks reduce type safety
**Decision**: Use Pydantic-based TestSettings
**Consequences**:
- (+) MyPy validation in tests
- (+) IDE support
- (-) More verbose fixtures

## Implementation Checklist

### Day 1
- [ ] Define `ComparisonProcessorProtocol`
- [ ] Implement `ComparisonProcessorImpl`
- [ ] Wire processor into queue worker
- [ ] Update DI container configuration
- [ ] Create `FakeQueueBus` fixture
- [ ] Create `FakeEventPublisher` fixture
- [ ] Create typed `TestSettings` fixtures
- [ ] Create `callback_topic_factory` fixture

### Day 2
- [ ] Migrate unit tests to processor
- [ ] Add callback_topic to integration tests
- [ ] Split performance tests (ingress vs e2e)
- [ ] Add contract tests for events
- [ ] Run typecheck-all validation
- [ ] Execute full test suite
- [ ] Update documentation
- [ ] Create PR with changes

## Dependencies

### Technical
- Existing LLM Provider Service codebase
- Dishka DI framework
- Pytest and test fixtures
- KafkaTestManager for integration tests

### Documentation Updates
- Update service README with test patterns
- Add testing guide to `/docs/testing/`
- Document processor pattern in architecture docs

## Notes

### Implementation Order Rationale
1. Domain extraction first - establishes clean boundaries
2. Test infrastructure second - enables proper testing
3. Test migration third - validates the approach
4. Contract testing fourth - ensures compliance
5. Validation last - confirms everything works

### Lessons Learned
- Test mode flags create technical debt
- DI-based testing is more maintainable
- Clear test scopes reduce complexity
- Typed fixtures catch errors early

## References
- Rule 020: Architectural Mandates
- Rule 042: Async Patterns and DI
- Rule 070: Testing Patterns and Standards
- Rule 075: Test Creation Methodology
- TASK-043: MyPy Strict Typing Compliance

---
**Task Created**: 2025-01-30
**Last Updated**: 2025-01-30
**Status**: Ready for implementation