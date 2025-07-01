## 🚀 Circuit Breaker Phase 3: External API Protection - Implementation Guide

You are implementing **Phase 3** of the circuit breaker system for HuleEdu microservices. **Phase 2 (Kafka Circuit Breakers) is 100% COMPLETE** - now we protect external API calls from failures and rate limiting.

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
- `services/cj_assessment_service/config.py` - Circuit breaker configuration pattern
- `services/cj_assessment_service/di.py` - DI integration with registry pattern
- `services/libs/huleedu_service_libs/resilience/circuit_breaker.py` - Core circuit breaker class
- `services/libs/huleedu_service_libs/resilience/registry.py` - Registry management
- `services/libs/huleedu_service_libs/resilience/resilient_client.py` - Generic wrapper pattern

## **Phase 3 Objective**

**Protect external API calls (LLM providers) from failures, rate limiting, and outages with intelligent fallback strategies.**

### **Primary Targets: CJ Assessment Service LLM Providers**

**High-Value Protection** - These API calls are expensive and frequently fail:

1. **Anthropic Provider**: `services/cj_assessment_service/implementations/anthropic_provider_impl.py`
   - Cost: ~$0.03 per assessment call
   - Common failures: Rate limits, API outages, timeout errors
   
2. **OpenAI Provider**: `services/cj_assessment_service/implementations/openai_provider_impl.py`  
   - Cost: ~$0.02 per assessment call
   - Common failures: Rate limits, model overload, network issues

3. **Google Provider**: `services/cj_assessment_service/implementations/google_provider_impl.py`
   - Cost: ~$0.01 per assessment call
   - Common failures: Quota exceeded, service unavailable

4. **OpenRouter Provider**: `services/cj_assessment_service/implementations/openrouter_provider_impl.py`
   - Cost: Variable based on model
   - Common failures: Provider-specific rate limits, model switching

## **🎯 Implementation Strategy**

### **Pattern 1: Provider-Level Circuit Breakers**

**Wrap each LLM provider with dedicated circuit breaker protection:**

```python
# Individual provider protection
@provide(scope=Scope.APP)
def provide_anthropic_llm_provider(
    self,
    session: aiohttp.ClientSession,
    settings: Settings,
    retry_manager: RetryManagerProtocol,
    circuit_breaker_registry: CircuitBreakerRegistry,  # Add this
) -> LLMProviderProtocol:
    """Provide Anthropic LLM provider with circuit breaker protection."""
    base_provider = AnthropicProviderImpl(session, settings, retry_manager)
    
    if settings.CIRCUIT_BREAKER_ENABLED:
        anthropic_breaker = CircuitBreaker(
            name=f"{settings.SERVICE_NAME}.anthropic_provider",
            failure_threshold=3,  # Lower threshold for expensive APIs
            recovery_timeout=timedelta(seconds=120),  # Longer recovery for rate limits
            success_threshold=2,
            expected_exception=(aiohttp.ClientError, AnthropicAPIError),
        )
        circuit_breaker_registry.register("anthropic_provider", anthropic_breaker)
        return make_resilient(base_provider, anthropic_breaker)
    
    return base_provider
```

### **Pattern 2: Multi-Provider Fallback Strategy**

**Implement intelligent provider switching when primary fails:**

```python
class ResilientLLMOrchestrator(LLMInteractionProtocol):
    """Orchestrates LLM calls with circuit breaker protection and provider fallback."""
    
    def __init__(
        self,
        primary_providers: dict[str, LLMProviderProtocol],  # Circuit-breaker protected
        settings: Settings,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ):
        self.providers = primary_providers
        self.settings = settings
        self.registry = circuit_breaker_registry
        
        # Define fallback chains
        self.fallback_chains = {
            "anthropic": ["openai", "google"],
            "openai": ["anthropic", "google"], 
            "google": ["openai", "anthropic"],
            "openrouter": ["anthropic", "openai"],
        }
```

## **📋 Phase 3 Implementation Tasks**

### **Task 3.1: Configuration Updates** ⭐⭐⭐ (CRITICAL)

**File**: `services/cj_assessment_service/config.py`

**Add provider-specific circuit breaker configuration:**

```python
# LLM Provider Circuit Breaker Configuration
LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(
    default=3,
    description="Number of failures before opening circuit for LLM providers"
)
LLM_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = Field(
    default=120,
    description="Seconds to wait before attempting recovery for LLM providers (longer for rate limits)"
)
LLM_CIRCUIT_BREAKER_SUCCESS_THRESHOLD: int = Field(
    default=2,
    description="Successful calls needed to close circuit for LLM providers"
)

# Provider-specific overrides
ANTHROPIC_CIRCUIT_BREAKER_TIMEOUT: int = Field(default=120, description="Anthropic-specific timeout")
OPENAI_CIRCUIT_BREAKER_TIMEOUT: int = Field(default=90, description="OpenAI-specific timeout")
GOOGLE_CIRCUIT_BREAKER_TIMEOUT: int = Field(default=60, description="Google-specific timeout")

# Fallback Configuration
ENABLE_LLM_PROVIDER_FALLBACK: bool = Field(
    default=True,
    description="Enable automatic fallback to secondary providers when primary fails"
)
```

### **Task 3.2: DI Provider Updates** ⭐⭐⭐ (CRITICAL)

**File**: `services/cj_assessment_service/di.py`

**Update each LLM provider to include circuit breaker protection:**

```python
# Add to imports
from huleedu_service_libs.resilience import make_resilient
from aiohttp import ClientError

# Update provider methods (example for Anthropic)
@provide(scope=Scope.APP)
def provide_anthropic_llm_provider(
    self,
    session: aiohttp.ClientSession,
    settings: Settings,
    retry_manager: RetryManagerProtocol,
    circuit_breaker_registry: CircuitBreakerRegistry,  # Add dependency
) -> LLMProviderProtocol:
    """Provide Anthropic LLM provider with circuit breaker protection."""
    base_provider = AnthropicProviderImpl(session, settings, retry_manager)
    
    if settings.CIRCUIT_BREAKER_ENABLED:
        anthropic_breaker = CircuitBreaker(
            name=f"{settings.SERVICE_NAME}.anthropic_provider",
            failure_threshold=settings.LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=timedelta(seconds=settings.ANTHROPIC_CIRCUIT_BREAKER_TIMEOUT),
            success_threshold=settings.LLM_CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
            expected_exception=(ClientError, Exception),  # Broad exception catching for API errors
        )
        circuit_breaker_registry.register("anthropic_provider", anthropic_breaker)
        return make_resilient(base_provider, anthropic_breaker)
    
    return base_provider

# Repeat pattern for OpenAI, Google, OpenRouter providers
```

### **Task 3.3: LLM Interaction Orchestrator** ⭐⭐ (HIGH)

**File**: `services/cj_assessment_service/implementations/resilient_llm_orchestrator.py` (NEW)

**Create intelligent orchestrator with fallback logic:**

```python
"""Resilient LLM orchestrator with circuit breaker protection and provider fallback."""

from typing import Dict, List, Optional
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreakerError
from ..protocols import LLMInteractionProtocol, LLMProviderProtocol

class ResilientLLMOrchestrator(LLMInteractionProtocol):
    """Orchestrates LLM calls with circuit breaker protection and intelligent fallback."""
    
    def __init__(
        self,
        providers: Dict[str, LLMProviderProtocol],  # Circuit breaker protected providers
        settings: Settings,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ):
        self.providers = providers
        self.settings = settings
        self.registry = circuit_breaker_registry
        
        # Define intelligent fallback chains based on cost and reliability
        self.fallback_chains = {
            "anthropic": ["openai", "google"],  # Fallback to cheaper options
            "openai": ["anthropic", "google"],
            "google": ["openai", "anthropic"],  # Google cheapest, try others first
            "openrouter": ["anthropic", "openai", "google"],
        }
    
    async def make_assessment_call(
        self,
        provider_name: str,
        prompt: str,
        essay_a: str,
        essay_b: str,
    ) -> AssessmentResult:
        """Make LLM assessment call with automatic fallback on provider failure."""
        
        # Try primary provider
        try:
            primary_provider = self.providers[provider_name]
            return await primary_provider.make_assessment_call(prompt, essay_a, essay_b)
            
        except CircuitBreakerError:
            logger.warning(f"Primary provider {provider_name} circuit breaker is open, trying fallbacks")
            
            # Try fallback providers if enabled
            if self.settings.ENABLE_LLM_PROVIDER_FALLBACK:
                for fallback_name in self.fallback_chains.get(provider_name, []):
                    try:
                        fallback_provider = self.providers[fallback_name]
                        logger.info(f"Attempting fallback to provider: {fallback_name}")
                        return await fallback_provider.make_assessment_call(prompt, essay_a, essay_b)
                        
                    except (CircuitBreakerError, Exception) as e:
                        logger.warning(f"Fallback provider {fallback_name} also failed: {e}")
                        continue
            
            # All providers failed
            raise AssessmentProviderUnavailableError(
                f"All LLM providers unavailable. Primary: {provider_name}, "
                f"Fallbacks attempted: {self.fallback_chains.get(provider_name, [])}"
            )
```

### **Task 3.4: Exception Handling** ⭐⭐ (HIGH)

**File**: `services/cj_assessment_service/exceptions.py` (UPDATE)

**Add provider-specific exceptions:**

```python
class AssessmentProviderUnavailableError(Exception):
    """Raised when all LLM providers are unavailable due to circuit breakers."""
    pass

class LLMProviderCircuitBreakerError(Exception):
    """Raised when LLM provider circuit breaker is open."""
    pass
```

### **Task 3.5: Provider-Specific Error Detection** ⭐⭐ (HIGH)

**Files**: Update each provider implementation

**Example for Anthropic provider** (`anthropic_provider_impl.py`):

```python
# Add specific error detection for circuit breaker triggering
async def make_assessment_call(self, prompt: str, essay_a: str, essay_b: str) -> AssessmentResult:
    """Make assessment call with enhanced error handling for circuit breakers."""
    try:
        # Existing implementation...
        response = await self._make_api_call(...)
        return self._parse_response(response)
        
    except aiohttp.ClientResponseError as e:
        if e.status == 429:  # Rate limit
            raise AnthropicRateLimitError(f"Rate limited: {e}")
        elif e.status >= 500:  # Server errors
            raise AnthropicServerError(f"Server error: {e}")
        else:
            raise AnthropicAPIError(f"API error: {e}")
            
    except aiohttp.ClientTimeout:
        raise AnthropicTimeoutError("Request timeout")
        
    except aiohttp.ClientError as e:
        raise AnthropicConnectionError(f"Connection error: {e}")
```

### **Task 3.6: Unit Tests** ⭐⭐⭐ (CRITICAL)

**File**: `services/cj_assessment_service/tests/unit/test_llm_circuit_breaker_protection.py` (NEW)

**Comprehensive test coverage:**

```python
"""Unit tests for LLM provider circuit breaker protection."""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import timedelta
from aiohttp import ClientError, ClientResponseError

from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerError
from services.cj_assessment_service.implementations.resilient_llm_orchestrator import ResilientLLMOrchestrator

@pytest.mark.asyncio
async def test_anthropic_provider_circuit_breaker_protection():
    """Test that Anthropic provider is protected by circuit breaker."""
    # Test circuit breaker opens after repeated failures
    # Test fallback to OpenAI when Anthropic fails
    # Test recovery when Anthropic becomes available again

@pytest.mark.asyncio 
async def test_provider_fallback_chain():
    """Test intelligent fallback between providers."""
    # Test fallback order follows cost optimization
    # Test all providers failing gracefully
    # Test provider preference restoration after recovery

@pytest.mark.asyncio
async def test_rate_limit_circuit_breaker_behavior():
    """Test circuit breaker behavior for rate limit scenarios."""
    # Test 429 errors trigger circuit breaker appropriately
    # Test longer recovery timeouts for rate limits
    # Test exponential backoff integration
```

## **📊 Success Criteria for Phase 3**

### **Functional Requirements:**
1. **✅ Zero LLM Call Loss**: Failed calls automatically retry with fallback providers
2. **✅ Cost Optimization**: Intelligent fallback chains prefer cheaper providers
3. **✅ Fast Failure Detection**: Circuit breakers open within 3 failed calls
4. **✅ Smart Recovery**: Longer timeouts for rate limit scenarios (120s vs 30s)
5. **✅ Graceful Degradation**: Service continues operating even if primary provider fails

### **Technical Requirements:**
1. **✅ Configuration Driven**: All thresholds configurable via environment variables
2. **✅ Provider Isolation**: Each provider has independent circuit breaker state
3. **✅ Comprehensive Testing**: Unit tests cover all failure scenarios and fallback paths
4. **✅ Observable**: Circuit breaker states visible in metrics and logs
5. **✅ DI Integration**: Seamless integration with existing dependency injection patterns

## **🔧 Implementation Order (Priority)**

### **Week 1: Core Protection (Critical)**
1. **Day 1-2**: Configuration updates (`config.py`) - **Task 3.1**
2. **Day 3-4**: DI provider updates (`di.py`) - **Task 3.2** 
3. **Day 5**: Basic unit tests and validation

### **Week 2: Advanced Features (High Value)**
1. **Day 1-3**: Resilient orchestrator implementation - **Task 3.3**
2. **Day 4**: Provider-specific error handling - **Task 3.5**
3. **Day 5**: Comprehensive testing - **Task 3.6**

### **Week 3: Monitoring & Optimization (Medium)**
1. **Day 1-2**: Exception handling improvements - **Task 3.4**
2. **Day 3-4**: Performance testing and optimization
3. **Day 5**: Documentation and handoff preparation

## **🚨 Critical Implementation Notes**

### **Cost Optimization Priority:**
- **Google** cheapest (~$0.01/call) → prefer in fallback chains
- **OpenAI** moderate cost (~$0.02/call) → good fallback option  
- **Anthropic** highest cost (~$0.03/call) → avoid unnecessary fallbacks
- **OpenRouter** variable cost → use sparingly

### **Rate Limit Handling:**
- **Anthropic**: 429 errors common → longer recovery timeout (120s)
- **OpenAI**: Model-specific limits → provider-aware timeout
- **Google**: Quota-based → daily/hourly limit detection

### **Error Categorization:**
- **Retriable**: Network timeouts, 503 server errors, rate limits
- **Non-Retriable**: 401 auth errors, 400 bad requests, quota exceeded
- **Circuit Breaker Triggers**: Connection errors, timeouts, 500+ errors, rate limits

## **📁 Key Files Reference**

### **Files to Read (Study Patterns):**
- `services/cj_assessment_service/config.py` - Current configuration
- `services/cj_assessment_service/di.py` - Current DI setup
- `services/libs/huleedu_service_libs/resilience/resilient_client.py` - Generic wrapper pattern

### **Files to Modify:**
- `services/cj_assessment_service/config.py` - Add LLM circuit breaker config
- `services/cj_assessment_service/di.py` - Wrap providers with circuit breakers
- `services/cj_assessment_service/implementations/*.py` - Add error detection

### **Files to Create:**
- `services/cj_assessment_service/implementations/resilient_llm_orchestrator.py` - Fallback orchestrator
- `services/cj_assessment_service/tests/unit/test_llm_circuit_breaker_protection.py` - Test suite

## **Commands to Run After Implementation**

```bash
# Test circuit breaker integration
pdm run pytest services/cj_assessment_service/tests/unit/test_llm_circuit_breaker_protection.py -v

# Test existing functionality still works
pdm run pytest services/cj_assessment_service/tests/ -k "not integration" -v

# Code quality check
pdm run ruff check services/cj_assessment_service/
pdm run mypy services/cj_assessment_service/

# Verify DI configuration
pdm run python -c "from services.cj_assessment_service.di import CJAssessmentServiceProvider; print('DI configuration valid')"
```

## **Questions for User Before Starting**

1. "Should I start with provider-level circuit breakers (Task 3.2) or configuration updates (Task 3.1) first?"
2. "Do you want me to implement all providers in parallel or focus on Anthropic/OpenAI first?"  
3. "Should I prioritize fallback orchestration or basic circuit breaker protection first?"

---

**Phase 3 focuses on protecting expensive LLM API calls with intelligent fallback strategies. The goal is zero-loss resilience with cost optimization through smart provider switching.**