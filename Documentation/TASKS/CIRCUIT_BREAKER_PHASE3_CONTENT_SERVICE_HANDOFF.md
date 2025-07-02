# 🚀 Circuit Breaker Phase 3: Content Service Protection - Implementation Guide

You are implementing **Phase 3** of the circuit breaker system for HuleEdu microservices. **Phase 2 (Kafka Circuit Breakers) is in progress** - now we protect Content Service HTTP calls from failures.

## **Workflow: The Unchanging Ritual**

### **Step 1: Ingest Core Architectural Knowledge (Mandatory First Action)**

Begin by reading the following files to understand our established patterns:
- `.cursor/rules/040-service-implementation-guidelines.mdc` - Service implementation patterns
- `.cursor/rules/042-async-patterns-and-di.mdc` - Async patterns and DI
- `.cursor/rules/043-service-configuration-and-logging.mdc` - Configuration patterns  
- `.cursor/rules/050-python-coding-standards.mdc` - Code quality standards
- `.cursor/rules/055-import-resolution-patterns.mdc` - Import conventions

### **Step 2: Review Phase 2 Success Patterns**

Study these **proven implementations** to understand the established pattern:
- `services/batch_orchestrator_service/config.py` - Circuit breaker configuration pattern
- `services/batch_orchestrator_service/di.py` - DI integration with registry pattern
- `services/libs/huleedu_service_libs/resilience/circuit_breaker.py` - Core circuit breaker class
- `services/libs/huleedu_service_libs/resilience/registry.py` - Registry management
- `services/libs/huleedu_service_libs/resilience/resilient_client.py` - Generic wrapper pattern

## **Phase 3 Objective**

**Protect Content Service HTTP calls from failures, timeouts, and service unavailability.**

### **Primary Targets: Content Client Implementations**

**High-Priority Protection** - Content Service is a critical dependency for multiple services:

1. **Spell Checker Service**: `services/spell_checker_service/protocol_implementations/content_client_impl.py`
   - Impact: Essay processing pipeline depends on content fetching
   - Failure mode: Timeouts, 503 errors during high load
   
2. **CJ Assessment Service**: `services/cj_assessment_service/implementations/content_client_impl.py`  
   - Impact: Assessment requires essay content for evaluation
   - Failure mode: Network errors, service unavailable

## **🎯 Implementation Strategy**

### **Pattern: HTTP Client Circuit Breakers**

**Wrap content client implementations with circuit breaker protection:**

```python
# Content client with circuit breaker
@provide(scope=Scope.APP)
def provide_content_client(
    self,
    settings: Settings,
    http_session: aiohttp.ClientSession,
    circuit_breaker_registry: CircuitBreakerRegistry,
) -> ContentClientProtocol:
    """Provide content client with circuit breaker protection."""
    base_client = DefaultContentClient(
        base_url=settings.CONTENT_SERVICE_URL,
        session=http_session,
    )
    
    if settings.CIRCUIT_BREAKER_ENABLED:
        content_breaker = CircuitBreaker(
            name=f"{settings.SERVICE_NAME}.content_client",
            failure_threshold=3,  # Lower threshold for critical service
            recovery_timeout=timedelta(seconds=30),
            success_threshold=2,
            expected_exception=(aiohttp.ClientError, ContentFetchError),
        )
        circuit_breaker_registry.register("content_client", content_breaker)
        return make_resilient(base_client, content_breaker)
    
    return base_client
```

## **📋 Phase 3 Implementation Tasks**

### **Task 3.1: Spell Checker Service Updates** ⭐⭐⭐ (HIGH PRIORITY)

#### **3.1.1 Configuration Updates**
**File**: `services/spell_checker_service/config.py`

Add content service circuit breaker configuration:

```python
# Content Service Circuit Breaker Configuration
CONTENT_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(
    default=3,
    description="Number of failures before opening circuit for content service"
)
CONTENT_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(
    default=30,
    description="Seconds to wait before attempting recovery"
)
CONTENT_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = Field(
    default=2,
    description="Successful calls needed to close circuit"
)
```

#### **3.1.2 DI Provider Updates**
**File**: `services/spell_checker_service/di.py`

Update the content client provider to include circuit breaker:

```python
# Add to imports
from huleedu_service_libs.resilience import make_resilient

# Update provider method
@provide(scope=Scope.APP)
def provide_content_client(
    self,
    settings: Settings,
    session: aiohttp.ClientSession,
    circuit_breaker_registry: CircuitBreakerRegistry,
) -> ContentClientProtocol:
    """Provide content client with circuit breaker protection."""
    from services.spell_checker_service.protocol_implementations.content_client_impl import (
        ContentClientImpl
    )
    
    base_client = ContentClientImpl(
        content_service_url=settings.CONTENT_SERVICE_URL,
        session=session,
    )
    
    if settings.CIRCUIT_BREAKER_ENABLED:
        content_breaker = CircuitBreaker(
            name=f"{settings.SERVICE_NAME}.content_client",
            failure_threshold=settings.CONTENT_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=timedelta(seconds=settings.CONTENT_CIRCUIT_BREAKER_RECOVERY_TIMEOUT),
            success_threshold=settings.CONTENT_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
            expected_exception=(aiohttp.ClientError, Exception),
        )
        circuit_breaker_registry.register("content_client", content_breaker)
        return make_resilient(base_client, content_breaker)
    
    return base_client
```

#### **3.1.3 Error Handling Enhancement**
**File**: `services/spell_checker_service/protocol_implementations/content_client_impl.py`

Enhance error detection for circuit breaker:

```python
async def get_content(self, content_reference: ContentReference) -> str:
    """Get content with enhanced error handling."""
    try:
        url = f"{self.content_service_url}/api/v1/content/{content_reference.reference_id}"
        
        async with self.session.get(url) as response:
            if response.status == 404:
                raise ContentNotFoundError(f"Content {content_reference.reference_id} not found")
            elif response.status >= 500:
                raise ContentServiceError(f"Content service error: {response.status}")
            
            response.raise_for_status()
            data = await response.json()
            return data["content"]
            
    except aiohttp.ClientTimeout:
        raise ContentTimeoutError("Content fetch timeout")
        
    except aiohttp.ClientConnectionError as e:
        raise ContentConnectionError(f"Connection error: {e}")
        
    except aiohttp.ClientError as e:
        raise ContentFetchError(f"Failed to fetch content: {e}")
```

### **Task 3.2: CJ Assessment Service Updates** ⭐⭐⭐ (HIGH PRIORITY)

#### **3.2.1 Configuration Updates**
**File**: `services/cj_assessment_service/config.py`

Add identical content service circuit breaker configuration as Spell Checker Service.

#### **3.2.2 DI Provider Updates**
**File**: `services/cj_assessment_service/di.py`

Follow the same pattern as Spell Checker Service for content client provider.

#### **3.2.3 Error Handling Enhancement**
**File**: `services/cj_assessment_service/implementations/content_client_impl.py`

Implement similar error categorization as Spell Checker Service.

### **Task 3.3: Integration Tests** ⭐⭐⭐ (CRITICAL)

#### **3.3.1 Spell Checker Service Tests**
**File**: `services/spell_checker_service/tests/integration/test_content_circuit_breaker.py` (NEW)

```python
"""Integration tests for content service circuit breaker."""

import pytest
from unittest.mock import AsyncMock
from aiohttp import ClientError
from datetime import timedelta

from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerError
from services.spell_checker_service.di import SpellCheckerServiceProvider

@pytest.mark.asyncio
async def test_content_circuit_breaker_opens_on_failures():
    """Test that circuit breaker opens after repeated content service failures."""
    provider = SpellCheckerServiceProvider()
    settings = provider.provide_settings()
    settings.CIRCUIT_BREAKER_ENABLED = True
    settings.CONTENT_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 2
    
    # Test implementation...

@pytest.mark.asyncio
async def test_content_circuit_breaker_recovery():
    """Test that circuit breaker recovers after timeout."""
    # Test implementation...
```

#### **3.3.2 CJ Assessment Service Tests**
**File**: `services/cj_assessment_service/tests/integration/test_content_circuit_breaker.py` (NEW)

Similar test structure as Spell Checker Service.

## **📊 Success Criteria for Phase 3**

### **Functional Requirements:**
1. **✅ Zero Content Fetch Loss**: Failed requests are properly handled with circuit breaker
2. **✅ Fast Failure Detection**: Circuit breakers open within 3 failed calls
3. **✅ Quick Recovery**: Services recover within 30 seconds
4. **✅ Graceful Degradation**: Services handle content unavailability appropriately

### **Technical Requirements:**
1. **✅ Configuration Driven**: All thresholds configurable via environment variables
2. **✅ Service Isolation**: Each service has independent circuit breaker state
3. **✅ Comprehensive Testing**: Integration tests cover failure scenarios
4. **✅ Observable**: Circuit breaker states visible in registry
5. **✅ DI Integration**: Seamless integration with existing patterns

## **🔧 Implementation Order**

### **Day 1-2: Spell Checker Service**
1. Configuration updates
2. DI provider updates
3. Error handling enhancement
4. Integration tests

### **Day 3-4: CJ Assessment Service**
1. Configuration updates
2. DI provider updates
3. Error handling enhancement
4. Integration tests

### **Day 5: Validation and Documentation**
1. End-to-end testing
2. Documentation updates
3. Handoff preparation

## **📁 Key Files Reference**

### **Files to Study (Patterns):**
- `services/batch_orchestrator_service/di.py` - Circuit breaker DI pattern
- `services/essay_lifecycle_service/di.py` - Kafka circuit breaker example
- `services/libs/huleedu_service_libs/resilience/resilient_client.py` - Wrapper pattern

### **Files to Modify:**
- `services/spell_checker_service/config.py` - Add configuration
- `services/spell_checker_service/di.py` - Wrap content client
- `services/spell_checker_service/protocol_implementations/content_client_impl.py` - Error handling
- `services/cj_assessment_service/config.py` - Add configuration
- `services/cj_assessment_service/di.py` - Wrap content client
- `services/cj_assessment_service/implementations/content_client_impl.py` - Error handling

### **Files to Create:**
- `services/spell_checker_service/tests/integration/test_content_circuit_breaker.py`
- `services/cj_assessment_service/tests/integration/test_content_circuit_breaker.py`

## **Commands to Run After Implementation**

```bash
# Test Spell Checker Service
pdm run pytest services/spell_checker_service/tests/integration/test_content_circuit_breaker.py -v

# Test CJ Assessment Service  
pdm run pytest services/cj_assessment_service/tests/integration/test_content_circuit_breaker.py -v

# Verify DI configuration
pdm run python -c "from services.spell_checker_service.di import SpellCheckerServiceProvider; print('DI configuration valid')"
pdm run python -c "from services.cj_assessment_service.di import CJAssessmentServiceProvider; print('DI configuration valid')"

# Run service-level tests
pdm run pytest services/spell_checker_service/tests/ -k "not integration" -v
pdm run pytest services/cj_assessment_service/tests/ -k "not integration" -v
```

---

**Phase 3 focuses on protecting Content Service dependencies with circuit breakers. This is simpler than external APIs but provides immediate value for system stability.**