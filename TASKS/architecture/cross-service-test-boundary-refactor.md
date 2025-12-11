---
id: cross-service-test-boundary-refactor
title: Cross Service Test Boundary Refactor
type: task
status: blocked
priority: medium
domain: architecture
owner_team: agents
created: '2025-11-21'
last_updated: '2025-11-21'
service: ''
owner: ''
program: ''
related: []
labels: []
---

# Task: Cross-Service Test Refactoring to HTTP/Kafka Boundaries

**Date**: 2025-11-17
**Status**: DRAFT - Awaiting Principal Dev & Architecture Review
**Related**: `.claude/HANDOFF.md` - Architectural Refactor: HTTP API Contracts to common_core (completed 2025-11-17)

## Context

This task addresses the final phase of our service boundary enforcement initiative: refactoring two integration tests that currently violate Domain-Driven Design (DDD) boundaries by importing internal implementations from LLM Provider Service into CJ Assessment Service test suites.

Following the successful completion of the HTTP API contract refactor (2025-11-17):
- ✅ Moved all shared HTTP contracts to `libs/common_core/src/common_core/api_models/llm_provider.py`
- ✅ Refactored 13 production files across both services
- ✅ Validated: 801 tests passing, containers building, zero import violations in production code

**Remaining Violations**:
- 2 integration test files in `services/cj_assessment_service/tests/integration/` import LPS internal implementations
- Tests work in local development but fail in containerized environments
- Violate DDD principle: services should only communicate via published contracts (HTTP/Kafka)

## Problem Statement

### Test File #1: Metadata Round-Trip Integration

**File**: `services/cj_assessment_service/tests/integration/test_llm_metadata_roundtrip_integration.py`

**Violations** (lines 30-35):
```python
from services.llm_provider_service.config import Settings as LPSSettings
from services.llm_provider_service.implementations.queue_processor_impl import QueueProcessorImpl
from services.llm_provider_service.implementations.trace_context_manager_impl import TraceContextManagerImpl
from services.llm_provider_service.internal_models import LLMOrchestratorResponse
from services.llm_provider_service.queue_models import QueuedRequest
```

**Critical Contract Being Tested**:
- CJ sends metadata with comparison request → LPS echoes metadata in callback
- Metadata fields: `essay_a_id`, `essay_b_id`, `bos_batch_id`, `cj_llm_batching_mode`
- LPS adds `prompt_sha256` without overwriting CJ metadata
- 1:1 mapping guarantee: one request → exactly one callback with preserved metadata

**Why Current Approach Is Problematic**:
1. **Bypasses HTTP serialization**: Doesn't test Pydantic validation, JSON encoding/decoding
2. **Bypasses Kafka serialization**: Doesn't test event envelope encoding, topic routing
3. **Calls private method** (`_publish_callback_event`): Implementation detail, may change
4. **Creates LPS objects directly**: Doesn't validate HTTP API accepts our request format
5. **Mocks internal components**: Doesn't test real queue manager, event publisher

**Real-World Failure Mode**: If LPS changes internal queue models or callback publishing logic, this test passes but production integration fails.

---

### Test File #2: Model Manifest Integration

**File**: `services/cj_assessment_service/tests/integration/test_llm_provider_manifest_integration.py`

**Violation** (line 33):
```python
from services.llm_provider_service.model_manifest import ProviderName, get_model_config
```

**Critical Contract Being Tested**:
- CJ discovers available models from LPS
- CJ uses manifest data to build valid `LLMConfigOverrides`
- LPS accepts model IDs from manifest
- Callback events include actual model/provider used

**Why Current Approach Is Problematic**:
1. **No HTTP API for manifest discovery**: LPS doesn't expose manifest to external clients
2. **Tight coupling**: CJ tests depend on LPS internal module structure
3. **Incomplete contract**: Doesn't validate HTTP-based model discovery flow
4. **Discovery gap**: Real clients can't query available models via API

**Real-World Failure Mode**: When LPS adds new models or changes manifest structure, CJ has no way to discover them programmatically via HTTP.

## Proposed Solution

### Core Principle

Integration tests MUST exercise real service boundaries (HTTP/Kafka) to validate actual infrastructure behavior, not assumptions about internal implementations.

### Implementation Phases

```
Phase 1: LPS Manifest HTTP Endpoint (NEW)
├─ Add /api/v1/models endpoint to LPS
├─ Expose manifest data as HTTP-accessible contract
└─ Enable runtime model discovery for all clients

Phase 2: Metadata Round-Trip Refactoring (COMPLEX)
├─ Move test to root tests/integration/
├─ Replace LPS internal calls with HTTP POST
├─ Add Kafka consumer to receive callback
└─ Validate metadata in real Kafka event

Phase 3: Manifest Integration Refactoring (SIMPLE)
├─ Move test to root tests/integration/
├─ Replace direct import with HTTP GET to /api/v1/models
└─ Use HTTP response to build LLMConfigOverrides

Phase 4: Validation & Cleanup
├─ Run full test suites
├─ Verify zero cross-service imports (grep validation)
└─ Update documentation
```

## Phase 1: LPS Model Manifest HTTP Endpoint

### Rationale

- Makes manifest queryable by any HTTP client (not just internal code)
- Enables future admin UI/model discovery tools
- Follows microservice best practice: expose capabilities via API
- Provides value beyond fixing test violations

### API Design

**Endpoint**: `GET /api/v1/models`

**Query Parameters**:
- `provider` (optional): Filter by provider name (anthropic, openai, google, openrouter)
- `include_deprecated` (optional): Include deprecated models (default: false)

**Response** (200):
```json
{
  "providers": {
    "anthropic": [
      {
        "model_id": "claude-haiku-4-5-20251001",
        "display_name": "Claude 3.5 Haiku (Latest)",
        "provider": "anthropic",
        "api_version": "2023-06-01",
        "max_tokens": 8192,
        "cost_per_1k_input_tokens": 0.0008,
        "cost_per_1k_output_tokens": 0.004,
        "release_date": "2024-11-01T00:00:00Z",
        "deprecation_date": null,
        "is_default": true,
        "capabilities": {
          "structured_output": true,
          "structured_output_method": "json_schema"
        }
      }
    ]
  },
  "total_models": 2,
  "last_updated": "2025-11-17T10:30:00Z"
}
```

### Implementation

#### 1.1 Create API Models

**Location**: `services/llm_provider_service/api_models.py`

```python
class ModelInfo(BaseModel):
    """Information about a supported LLM model."""
    model_id: str
    display_name: str
    provider: str
    api_version: str | None
    max_tokens: int
    cost_per_1k_input_tokens: float | None
    cost_per_1k_output_tokens: float | None
    release_date: str | None
    deprecation_date: str | None
    is_default: bool
    capabilities: dict[str, Any]

class ModelManifestResponse(BaseModel):
    """Response containing all available models grouped by provider."""
    providers: dict[str, list[ModelInfo]]
    total_models: int
    last_updated: str
```

#### 1.2 Add Route Handler

**Location**: `services/llm_provider_service/api/llm_routes.py`

```python
@llm_bp.route("/models", methods=["GET"])
async def list_available_models() -> Response:
    """List all available LLM models from manifest.

    Returns manifest data in HTTP-friendly format for model discovery.
    Clients can use this to build valid llm_config_overrides.

    Query Parameters:
        provider (optional): Filter by provider name
        include_deprecated (optional): Include deprecated models (default: false)

    Returns:
        200: ModelManifestResponse with all available models
        500: Error response if manifest query fails
    """
    try:
        from services.llm_provider_service.model_manifest import list_models

        provider_filter = request.args.get("provider")
        include_deprecated = request.args.get("include_deprecated", "false").lower() == "true"

        # list_models() returns a flat list[ModelConfig]
        all_models = list_models()

        # Build response grouped by provider
        providers: dict[str, list[ModelInfo]] = {}

        for config in all_models:
            # Skip deprecated unless explicitly requested
            if config.deprecation_date and not include_deprecated:
                continue

            # Filter by provider if requested
            if provider_filter and config.provider.value.lower() != provider_filter.lower():
                continue

            provider_key = config.provider.value

            providers.setdefault(provider_key, []).append(
                ModelInfo(
                    model_id=config.model_id,
                    display_name=config.display_name,
                    provider=provider_key,
                    api_version=config.api_version,
                    max_tokens=config.max_tokens,
                    cost_per_1k_input_tokens=config.cost_per_1k_input_tokens,
                    cost_per_1k_output_tokens=config.cost_per_1k_output_tokens,
                    release_date=config.release_date.isoformat() if config.release_date else None,
                    deprecation_date=config.deprecation_date.isoformat() if config.deprecation_date else None,
                    is_default=config.is_default,
                    capabilities={
                        "structured_output": config.structured_output_method is not None,
                        "structured_output_method": config.structured_output_method.value if config.structured_output_method else None,
                    },
                )
            )

        total_models = sum(len(models_list) for models_list in providers.values())

        response = ModelManifestResponse(
            providers=providers,
            total_models=total_models,
            last_updated=datetime.now(UTC).isoformat(),
        )

        logger.info(
            f"Served model manifest: {total_models} models across {len(providers)} providers"
        )
        return jsonify(response.model_dump(mode="json")), 200

    except Exception as e:
        logger.exception("Failed to retrieve model manifest")
        return create_error_response(
            error=HuleEduError(
                error_code="MANIFEST_QUERY_FAILED",
                message="Failed to retrieve model manifest",
                details={"error": str(e)}
            ),
            status_code=500
        )
```

#### 1.3 Testing

**Unit Tests**: `services/llm_provider_service/tests/unit/test_manifest_endpoint.py`
- test_manifest_endpoint_returns_all_providers
- test_manifest_endpoint_filters_by_provider
- test_manifest_endpoint_excludes_deprecated_by_default
- test_manifest_endpoint_includes_deprecated_when_requested
- test_manifest_endpoint_error_handling

**Metrics**:
```python
# Add to services/llm_provider_service/metrics.py
manifest_queries_total = Counter(
    "llm_provider_manifest_queries_total",
    "Total manifest queries",
    ["provider_filter", "include_deprecated"]
)
```

## Phase 2: Metadata Round-Trip Test Refactoring

### Test Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Test Process (Orchestrator)                                 │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Create comparison task with metadata                    │
│  2. Build LLMComparisonRequest with metadata                │
│  3. POST to LPS /api/v1/comparison                          │
│     └─> HTTP serialization validated                        │
│                                                              │
│  4. LPS queues request, processes comparison                │
│     └─> Real queue manager behavior                         │
│                                                              │
│  5. LPS publishes callback to Kafka                         │
│     └─> Real event publisher, topic routing                 │
│                                                              │
│  6. Test's Kafka consumer receives callback                 │
│     └─> Kafka serialization validated                       │
│                                                              │
│  7. Parse EventEnvelope[LLMComparisonResultV1]              │
│  8. Verify metadata fields preserved                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Implementation

**New Location**: `tests/integration/test_cj_lps_metadata_roundtrip.py`

**Why Root `tests/`**:
- Cross-service integration test (not service-specific)
- Requires both CJ and LPS services running
- Validates contract between two services
- Aligns with monorepo pattern: service-internal tests in `services/*/tests/`, cross-service in root `tests/`

**Key Changes**:
1. Replace `QueueProcessorImpl` instantiation with HTTP POST to `/api/v1/comparison`
2. Replace direct `_publish_callback_event()` call with Kafka consumer listening for real callback
3. Add `aiokafka.AIOKafkaConsumer` fixture for callback reception
4. Add timeout protection (30s) to prevent hanging tests
5. Use `LLMProviderType.MOCK` to avoid external API costs

**Test Flow**:
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_metadata_roundtrip_via_http_and_kafka(
    http_session: aiohttp.ClientSession,
    kafka_consumer: AIOKafkaConsumer,
) -> None:
    """Verify CJ metadata survives full HTTP → Queue → Kafka → CJ callback loop."""

    # 1. Check LPS availability
    if not await check_lps_availability(http_session):
        pytest.skip("LPS service not available at localhost:8090")

    # 2. Build CJ comparison request with metadata
    correlation_id = uuid4()
    metadata = {
        "essay_a_id": str(uuid4()),
        "essay_b_id": str(uuid4()),
        "bos_batch_id": "bos-roundtrip-001",
        "cj_llm_batching_mode": "per_request",
    }

    request_payload = LLMComparisonRequest(
        user_prompt="Compare essay A vs essay B.",
        callback_topic="test.llm.callback",
        correlation_id=correlation_id,
        metadata=metadata,
        llm_config_overrides=LLMConfigOverrides(
            provider_override=LLMProviderType.MOCK,
            model_override="mock-model",
        ),
    )

    # 3. POST to LPS HTTP API (async-only, 202 expected)
    async with http_session.post(
        "http://localhost:8090/api/v1/comparison",
        json=request_payload.model_dump(mode="json"),
    ) as resp:
        assert resp.status == 202, f"Expected 202, got {resp.status}: {await resp.text()}"
        response_data = await resp.json()
        queued_response = LLMQueuedResponse(**response_data)
        queue_id = queued_response.queue_id

    # 4. Wait for Kafka callback with timeout
    callback_received = False
    callback_metadata = None

    async with asyncio.timeout(30):
        async for message in kafka_consumer:
            envelope = EventEnvelope[LLMComparisonResultV1](**message.value)
            if envelope.data.correlation_id == correlation_id:
                callback_received = True
                callback_metadata = envelope.data.request_metadata
                break

    # 5. Verify metadata preservation
    assert callback_received
    assert callback_metadata["essay_a_id"] == metadata["essay_a_id"]
    assert callback_metadata["bos_batch_id"] == metadata["bos_batch_id"]
    assert "prompt_sha256" in callback_metadata  # Added by LPS
```

## Phase 3: Manifest Integration Test Refactoring

### Implementation

**New Location**: `tests/integration/test_cj_lps_manifest_contract.py`

**Key Changes**:
1. Replace `from services.llm_provider_service.model_manifest import get_model_config` with HTTP GET to `/api/v1/models`
2. Parse manifest response to find default Anthropic model
3. Build `LLMConfigOverrides` from HTTP response data
4. Verify LPS accepts model IDs from manifest

**Test Flow**:
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_discover_models_via_http_manifest(
    http_session: aiohttp.ClientSession,
) -> None:
    """Verify CJ can discover available models via LPS HTTP manifest endpoint."""

    # 1. Query manifest endpoint
    async with http_session.get("http://localhost:8090/api/v1/models") as resp:
        assert resp.status == 200
        manifest = await resp.json()

    # 2. Validate manifest structure
    assert "providers" in manifest
    assert manifest["total_models"] > 0

    # 3. Get default Anthropic model
    anthropic_models = manifest["providers"]["anthropic"]
    default_model = next(m for m in anthropic_models if m["is_default"])

    # 4. Build LLMConfigOverrides from manifest data
    overrides = LLMConfigOverrides(
        provider_override=LLMProviderType.ANTHROPIC,
        model_override=default_model["model_id"],
        temperature_override=0.3,
    )

    # 5. Verify LPS accepts this model
    test_request = {
        "user_prompt": "Test prompt",
        "callback_topic": "test.callback",
        "correlation_id": str(uuid4()),
        "llm_config_overrides": overrides.model_dump(mode="json"),
    }

    async with http_session.post(
        "http://localhost:8090/api/v1/comparison",
        json=test_request,
    ) as resp:
        assert resp.status == 202, f"Expected 202, got {resp.status}: {await resp.text()}"
        queued_response = LLMQueuedResponse(**await resp.json())
        queue_id = queued_response.queue_id
```

**Migration Note**:
- Old test file had 6 test methods
- 5 can be migrated with minimal changes (replace import with HTTP call)
- 1 pure schema validation test can remain as unit test

## Phase 4: Validation & Cleanup

### Validation Checklist

```bash
# 1. Grep validation - MUST return zero results
grep -r "from services\.llm_provider_service" services/cj_assessment_service/ \
  --include="*.py" | grep -v "__pycache__"
# Expected: (empty output)

# 2. Run new integration tests
pdm run pytest-root tests/integration/test_cj_lps_metadata_roundtrip.py -v
pdm run pytest-root tests/integration/test_cj_lps_manifest_contract.py -v
# Expected: All tests pass (services must be running)

# 3. Run full test suite
pdm run pytest-root services/cj_assessment_service/tests/ -v
pdm run pytest-root services/llm_provider_service/tests/ -v
# Expected: 801+ tests pass

# 4. Typecheck & Lint
pdm run typecheck-all
pdm run lint-fix --unsafe-fixes
# Expected: No new errors
```

### Delete Old Test Files

```bash
# Only delete after new tests pass
rm services/cj_assessment_service/tests/integration/test_llm_metadata_roundtrip_integration.py
rm services/cj_assessment_service/tests/integration/test_llm_provider_manifest_integration.py
```

### Documentation Updates

**Files to Update**:

1. **`services/cj_assessment_service/README.md`**
   - Section: "Testing Contract Validation"
   - Update: Note integration tests moved to root `tests/integration/`

2. **`services/llm_provider_service/README.md`**
   - Section: "API Endpoints"
   - Add: Document new `/api/v1/models` endpoint
   - Include: Query parameters, response schema, examples

3. **`.claude/HANDOFF.md`**
   - Add section: "Cross-Service Test Refactoring (2025-11-17)"
   - Document: Test relocation, new manifest endpoint, validation results

4. **`tests/README.md`** (create if doesn't exist)
   - Explain: Root `tests/` vs service `tests/` distinction
   - Document: Integration test requirements
   - Provide: Examples of running integration tests

## Expected Benefits

### Architectural Benefits

1. **Service Boundary Enforcement**: Zero cross-service implementation imports
2. **Test Fidelity**: Tests validate REAL infrastructure behavior (HTTP/Kafka serialization)
3. **DDD Compliance**: Services communicate only via published contracts

### Operational Benefits

1. **Containerization Ready**: Tests work in Docker (no file path dependencies)
2. **Refactoring Safety**: Internal LPS changes don't break CJ tests
3. **Model Discovery**: Clients can query available models at runtime (NEW)

### Development Experience

1. **Clear Test Organization**: Service-internal vs cross-service tests clearly separated
2. **Better Error Messages**: HTTP/Kafka errors show actual serialization failures
3. **Documentation Alignment**: Tests match documented architecture

## Risks & Mitigations

### Risk: Kafka Consumer Complexity

**Impact**: Medium - Tests may be flaky, harder to maintain

**Mitigation**:
- Provide clear fixtures and examples
- Add timeout protection (test fails fast, doesn't hang)
- Clearly document Kafka requirements and mark tests with `@pytest.mark.integration` so they can be skipped when Kafka/LPS are unavailable

### Risk: Integration Tests Require Running Services

**Impact**: Low - Standard for integration tests

**Mitigation**:
- Use `pytest.skip()` when services unavailable (graceful degradation)
- Document service requirements in test docstrings
- Mark tests with `@pytest.mark.integration` for selective running

### Risk: Test Migration Introduces Bugs

**Impact**: Medium - Could lose test coverage

**Mitigation**:
- Keep old tests until new tests pass
- Run full test suite before and after (compare coverage)
- Get principal dev review before deleting old tests

## Implementation Timeline

**Phase 1: Manifest Endpoint** - 2-3 hours
- Create API models (30 min)
- Implement route handler (1 hour)
- Add unit tests (1 hour)
- Manual testing (30 min)

**Phase 2: Metadata Round-Trip** - 4-5 hours
- Set up Kafka consumer fixture (1.5 hours)
- Implement HTTP request flow (1 hour)
- Implement callback validation (1 hour)
- Debugging/refinement (1.5 hours)

**Phase 3: Manifest Integration** - 2 hours
- Port existing tests to HTTP calls (1 hour)
- Add new filtering tests (30 min)
- Validation (30 min)

**Phase 4: Validation & Cleanup** - 1-2 hours
- Run full test suite (30 min)
- Update documentation (1 hour)
- Final validation & cleanup (30 min)

**Total Estimated Time**: 9-12 hours

## Success Criteria

### Functional Criteria

- [ ] Grep validation returns zero cross-service violations
- [ ] All new integration tests pass with services running
- [ ] All existing test suites pass (801+ tests)
- [ ] Manifest endpoint returns valid JSON with all providers
- [ ] Metadata round-trip test receives callback within 30s
- [ ] Zero new type errors or lint warnings

### Architectural Criteria

- [ ] No service imports internal implementations of other services
- [ ] Integration tests use only HTTP/Kafka boundaries
- [ ] Tests work in containerized environments
- [ ] Documentation updated to reflect new structure

## Open Questions for Review

1. **Manifest Response Format**: Single endpoint vs per-provider endpoints?
   - **Recommendation**: Single endpoint (simpler)

2. **Test Location**: Confirm root `tests/integration/` is correct for cross-service tests
   - **Recommendation**: Yes, aligns with monorepo patterns

3. **Review Timeline**: What's the expected review timeline for this plan?

4. **Implementation Approval**: Should implementation start after plan approval, or wait for phase-by-phase review?

## References

- `.agent/rules/020-architectural-mandates.md` - Service boundary principles
- `.agent/rules/075-test-creation-methodology.md` - Testing standards
- `.claude/HANDOFF.md` - Architectural refactor context (2025-11-17)
- `services/cj_assessment_service/README.md` - CJ↔LPS contract documentation
- `services/llm_provider_service/README.md` - LPS API documentation
