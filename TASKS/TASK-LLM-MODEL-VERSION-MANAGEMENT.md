# Task Plan: LLM Provider Model Version Management System

## Executive Summary
- **Purpose**: Build a minimal, maintainable system for tracking and updating LLM model versions across providers (Anthropic, OpenAI, Google, OpenRouter) with automated detection of new releases and API breaking changes.
- **Scope**: Centralized model registry, CLI-based version checker, compatibility validation, and clear manual update workflow.
- **Integration Context**: Improves maintainability of `llm_provider_service` by eliminating hardcoded model versions and providing automated alerts when providers release new models.

## Architectural Alignment
- **Core mandates**: `.claude/rules/020-architectural-mandates.mdc`, `.claude/rules/020.13-llm-provider-service-architecture.mdc`
- **Configuration**: `.claude/rules/043-service-configuration-and-logging.mdc`
- **Async/DI patterns**: `.claude/rules/042-async-patterns-and-di.mdc`
- **Error handling**: `.claude/rules/048-structured-error-handling-standards.mdc`
- **Testing & QA**: `.claude/rules/070-testing-and-quality-assurance.mdc`, `.claude/rules/075-test-creation-methodology.mdc`
- **Observability**: `.claude/rules/071-observability-index.mdc`
- **Python standards**: `.claude/rules/050-python-coding-standards.mdc`, `.claude/rules/051-pydantic-v2-standards.mdc`
- **Planning methodology**: `.claude/rules/110.7-task-creation-and-decomposition-methodology.mdc`

## Current State Analysis

### Problem Statement
**Model versions are hardcoded** across multiple locations in `llm_provider_service`:
- `services/llm_provider_service/config.py` lines 110-132: Model IDs hardcoded as string literals
- Provider implementations (`implementations/*_provider_impl.py`): API versions hardcoded
- No centralized tracking of model capabilities or API compatibility requirements
- Manual multi-file updates required when changing models
- No automated detection of new model releases or API changes

### Current Model Configuration
```python
# config.py (Current State - TO BE REFACTORED)
ANTHROPIC_MODEL_ID: str = "claude-3-5-haiku-20241022"  # Hardcoded
OPENAI_MODEL_ID: str = "gpt-5-mini-2025-08-07"         # Hardcoded
GOOGLE_MODEL_ID: str = "gemini-2.5-flash-preview-05-20" # Hardcoded
OPENROUTER_MODEL_ID: str = "anthropic/claude-3-5-haiku-20241022" # Hardcoded
```

### Provider-Specific Patterns
| Provider   | Current Model                          | Structured Output Method              | API Version     |
|------------|----------------------------------------|---------------------------------------|-----------------|
| Anthropic  | `claude-3-5-haiku-20241022`            | Tool use/function calling             | Hardcoded       |
| OpenAI     | `gpt-5-mini-2025-08-07`                | `response_format={"type": "json_object"}` | Hardcoded   |
| Google     | `gemini-2.5-flash-preview-05-20`       | `response_mime_type="application/json"` | Hardcoded     |
| OpenRouter | `anthropic/claude-3-5-haiku-20241022`  | Conditional based on model capabilities | Hardcoded     |

### Key Implementation Files
- `services/llm_provider_service/config.py`: Configuration and settings
- `services/llm_provider_service/implementations/anthropic_provider_impl.py`: Anthropic API integration
- `services/llm_provider_service/implementations/openai_provider_impl.py`: OpenAI API integration
- `services/llm_provider_service/implementations/google_provider_impl.py`: Google API integration
- `services/llm_provider_service/implementations/openrouter_provider_impl.py`: OpenRouter API integration
- `services/llm_provider_service/api_models.py`: Request/response models
- `services/llm_provider_service/internal_models.py`: Internal data structures

## Design Decisions

### User Requirements (Confirmed 2025-11-08)
1. **Update Strategy**: Lightweight weekly automated checks (transformable to CI/CD scheduled job post-deployment)
2. **Automation Level**: Alert only, manual updates (no auto-deployment)
3. **Breaking Changes**: Block updates, require manual intervention
4. **Focus**: Start with Anthropic (most straightforward), extend to other providers incrementally

### Architecture Pattern: Centralized Model Registry
**Single source of truth** using Pydantic models for:
- Model configuration and capabilities
- API compatibility requirements
- Structured output methods
- Release tracking

**Benefits**:
- DRY: One place to update model versions
- Type-safe: Pydantic validation prevents configuration errors
- Extensible: Easy to add new providers or capabilities
- Testable: Mock registry for unit tests

## Phase Breakdown

### Phase 1: Centralized Model Registry (Week 1)

#### Deliverables
- ✅ Pydantic-based model manifest with validation
- ✅ Refactored configuration to use manifest
- ✅ Updated Anthropic provider implementation
- ✅ Backward compatibility maintained

#### Steps

**1.1. Create Model Manifest Module**
- **File**: `services/llm_provider_service/model_manifest.py` (~200-250 LoC)
- **Contents**:
  ```python
  from pydantic import BaseModel, Field, ConfigDict
  from datetime import date
  from enum import Enum

  class StructuredOutputMethod(str, Enum):
      TOOL_USE = "tool_use"
      JSON_SCHEMA = "json_schema"
      JSON_MIME_TYPE = "json_mime_type"
      JSON_OBJECT = "json_object"

  class ProviderName(str, Enum):
      ANTHROPIC = "anthropic"
      OPENAI = "openai"
      GOOGLE = "google"
      OPENROUTER = "openrouter"

  class ModelConfig(BaseModel):
      """Configuration for a single LLM model."""
      model_config = ConfigDict(frozen=True)

      model_id: str = Field(..., description="Provider-specific model identifier")
      provider: ProviderName
      api_version: str = Field(..., description="API version string")
      structured_output_method: StructuredOutputMethod
      capabilities: dict[str, bool] = Field(default_factory=dict)
      release_date: date | None = Field(default=None)
      max_tokens: int = Field(default=4096)
      supports_streaming: bool = Field(default=True)

  class ModelRegistry(BaseModel):
      """Registry of all supported models."""
      models: dict[ProviderName, list[ModelConfig]]
      default_models: dict[ProviderName, str]  # Maps provider → default model_id

  # Singleton registry instance
  SUPPORTED_MODELS: ModelRegistry = ModelRegistry(
      models={
          ProviderName.ANTHROPIC: [
              ModelConfig(
                  model_id="claude-3-5-haiku-20241022",
                  provider=ProviderName.ANTHROPIC,
                  api_version="2023-06-01",
                  structured_output_method=StructuredOutputMethod.TOOL_USE,
                  capabilities={"tool_use": True, "vision": True},
                  release_date=date(2024, 10, 22),
                  max_tokens=8192,
              ),
          ],
          # Other providers to be added in Phase 3
      },
      default_models={
          ProviderName.ANTHROPIC: "claude-3-5-haiku-20241022",
      }
  )

  def get_model_config(provider: ProviderName, model_id: str | None = None) -> ModelConfig:
      """Retrieve model config by provider and ID (defaults to provider default)."""
      if model_id is None:
          model_id = SUPPORTED_MODELS.default_models[provider]

      for model in SUPPORTED_MODELS.models[provider]:
          if model.model_id == model_id:
              return model

      raise ValueError(f"Unknown model: {provider}/{model_id}")
  ```

**1.2. Refactor Configuration Layer**
- **File**: `services/llm_provider_service/config.py`
- **Changes**:
  - Import `get_model_config` from `model_manifest`
  - Replace hardcoded model strings with manifest lookups
  - Add environment variable overrides with validation
  - Maintain backward compatibility

  ```python
  from services.llm_provider_service.model_manifest import (
      get_model_config,
      ProviderName,
  )

  # Before: ANTHROPIC_MODEL_ID: str = "claude-3-5-haiku-20241022"
  # After:
  _anthropic_override = getenv("ANTHROPIC_MODEL_ID", None)
  ANTHROPIC_MODEL_CONFIG = get_model_config(
      ProviderName.ANTHROPIC,
      model_id=_anthropic_override
  )
  ANTHROPIC_MODEL_ID: str = ANTHROPIC_MODEL_CONFIG.model_id
  ANTHROPIC_API_VERSION: str = ANTHROPIC_MODEL_CONFIG.api_version
  ```

**1.3. Update Anthropic Provider Implementation**
- **File**: `services/llm_provider_service/implementations/anthropic_provider_impl.py`
- **Changes**:
  - Read API version from config (not hardcoded)
  - Validate structured output method matches expected value
  - Add logging for model configuration on initialization

**1.4. Unit Tests**
- **File**: `services/llm_provider_service/tests/unit/test_model_manifest.py` (~150-200 LoC)
- **Coverage**:
  - Registry validation (Pydantic schema enforcement)
  - Model lookup by provider and ID
  - Default model resolution
  - Error handling for unknown models
  - Config integration with manifest

#### Checkpoints
- ✅ `pdm run typecheck-all` passes after manifest introduction
- ✅ All existing tests pass (no behavioral changes)
- ✅ Registry contains complete Anthropic configuration
- ✅ Environment variable overrides work correctly

#### Done Definition
- Model manifest is the single source of truth for Anthropic models
- Configuration layer successfully refactored with backward compatibility
- Unit tests cover all manifest operations and edge cases
- Documentation updated in service README

---

### Phase 2: Model Version Checker ✅ COMPLETE

**Implementation Summary**:
- Protocol-based design with 4 async provider checkers (1,339 LoC total)
- Pydantic frozen models: `DiscoveredModel`, `ModelComparisonResult`
- CLI command with Rich table output and exit codes 0/1/2/3
- Comprehensive test suite: 120 tests across 7 files (2,586 LoC)
- Type-safe: `pdm run typecheck-all` passes (0 errors, 1186 files)

**Deliverables**:
- ✅ `model_checker/base.py` (230 LoC): `ModelCheckerProtocol`, data models
- ✅ `model_checker/anthropic_checker.py` (283 LoC): AsyncAnthropic SDK, Claude 3+ filter
- ✅ `model_checker/openai_checker.py` (264 LoC): AsyncOpenAI SDK, GPT-4+ filter
- ✅ `model_checker/google_checker.py` (272 LoC): google.genai async, Gemini 1.5+ filter
- ✅ `model_checker/openrouter_checker.py` (290 LoC): aiohttp REST, Anthropic models
- ✅ `cli_check_models.py` (308 LoC): Typer CLI with Rich formatting
- ✅ `cli_output_formatter.py` (224 LoC): Model table/tree output, comparison diffs
- ✅ Test suite: 7 files, 2,586 LoC, 120 tests (104 unit, 16 integration)
- ✅ Bug fix: `conftest.py` duplicate fixture imports resolved

**Test Coverage**:
```
tests/unit/test_model_checker_base.py              25 tests (Pydantic models, protocols)
tests/unit/test_anthropic_model_checker.py         21 tests (SDK, filters, comparison)
tests/unit/test_openai_model_checker.py            20 tests (SDK, filters, comparison)
tests/unit/test_google_model_checker.py            19 tests (SDK, filters, comparison)
tests/unit/test_openrouter_model_checker.py        19 tests (aiohttp, filters, comparison)
tests/integration/test_cli_check_models.py         12 tests (CLI integration, exit codes)
tests/integration/test_manifest_integration.py      4 tests (manifest validation)
```

**Validation**: 227/227 unit tests passing (100% pass rate)

**Architecture**:
- Provider-agnostic protocol design for extensibility
- SDK-native async implementations (AsyncAnthropic, AsyncOpenAI, google.genai)
- aiohttp fallback for OpenRouter (no official async SDK)
- Structured logging with correlation IDs
- Graceful error handling with API rate limits, auth failures

**CLI Command**:
```bash
pdm run llm-check-models --provider anthropic [--verbose]
```

**Exit Codes**:
- `0`: Up-to-date, no action needed
- `1`: New compatible models available
- `2`: API error or auth failure
- `3`: Breaking changes detected

---

### Phase 2.5: Integration Verification (Week 2)

#### Critical Finding: Zero Breaking Changes Required

**Analysis Result** (2025-11-08): The codebase is **already manifest-ready** with full support for model selection via API overrides.

**Key Discoveries:**
- ✅ API contract accepts `llm_config_overrides` with `model_override`, `provider_override`
- ✅ Response includes actual `model` and `provider` metadata
- ✅ Event contracts (`ELS_CJAssessmentRequestV1`) already support `llm_config_overrides`
- ✅ ENG5 batch runner has `--llm-model`, `--llm-provider` CLI flags
- ✅ CJ Assessment Service passes overrides through to LLM Provider Service
- ✅ All callback events include model metadata in `LLMComparisonResultV1`

**Conclusion**: Moving to manifest-based model selection is a **non-breaking enhancement** that requires only:
1. Populate `llm_config_overrides` with manifest values (instead of leaving null)
2. Add validation to ensure manifest is used
3. Update callers to extract models from manifest
4. Deprecate (not remove) hardcoded defaults over transition period

#### Deliverables
- ✅ Integration verification tests for CJ Assessment Service
- ✅ Integration verification tests for ENG5 batch runner
- ✅ Migration guide for hardcoded defaults
- ✅ Documentation of integration points

#### Steps

**2.5.1. Document Integration Architecture**
- **File**: `TASKS/TASK-LLM-MODEL-VERSION-MANAGEMENT.md` (this document)
- **Add Section**: "Integration Analysis" with complete call chain
- **Contents**:
  ```
  ENG5 Batch Runner (CLI)
      ↓ (--llm-provider, --llm-model flags)
      └→ ELS_CJAssessmentRequestV1(llm_config_overrides)
          ↓ (Kafka Event)
  CJ Assessment Service
      └→ LLMProviderServiceClient.generate_comparison()
          └→ LLMComparisonRequest(llm_config_overrides)
              ↓ (HTTP POST)
  LLM Provider Service
      └→ LLMComparisonResultV1(model, provider metadata)
          ↓ (Kafka Callback)
  CJ Assessment Service (consumes result)
  ```

**2.5.2. Verify CJ Assessment Service Integration**
- **File**: `services/cj_assessment_service/tests/integration/test_llm_provider_manifest_integration.py` (~150 LoC)
- **Purpose**: Verify CJ service correctly uses manifest-based model selection
- **Tests**:
  ```python
  @pytest.mark.integration
  async def test_cj_uses_manifest_model_when_no_override():
      """Verify CJ falls back to manifest default when no override specified."""
      # Given: Manifest specifies claude-3-5-haiku-20241022 as default
      # When: CJ initiates comparison without override
      # Then: Request uses manifest default model

  @pytest.mark.integration
  async def test_cj_respects_assignment_level_override():
      """Verify CJ uses assignment-specific model when configured."""
      # Given: Assignment metadata specifies gpt-5-mini
      # When: CJ processes batch for that assignment
      # Then: Request uses assignment-specific model override

  @pytest.mark.integration
  async def test_cj_callback_includes_actual_model_used():
      """Verify callback events include actual model metadata."""
      # Given: CJ initiates comparison
      # When: LLM Provider completes request
      # Then: Callback includes provider, model, cost metadata
  ```

**2.5.3. Verify ENG5 Batch Runner Integration**
- **File**: `.claude/research/scripts/tests/test_eng5_np_manifest_integration.py` (~100 LoC)
- **Purpose**: Verify ENG5 runner correctly builds LLM overrides from CLI flags
- **Tests**:
  ```python
  def test_eng5_runner_builds_overrides_from_cli_flags():
      """Verify CLI flags correctly populate llm_config_overrides."""
      # Given: --llm-model anthropic/claude-3-5-haiku
      # When: Runner composes ELS_CJAssessmentRequestV1
      # Then: Event includes llm_config_overrides with model_override

  def test_eng5_runner_validates_model_against_manifest():
      """Verify runner rejects invalid model IDs."""
      # Given: --llm-model invalid-model-id
      # When: Runner validates against manifest
      # Then: Raises validation error before publishing event
  ```

**2.5.4. Add Manifest Integration to CJ Config**
- **File**: `services/cj_assessment_service/config.py`
- **Changes** (minimal, backward compatible):
  ```python
  # Add import
  from services.llm_provider_service.model_manifest import (
      get_model_config,
      ProviderName,
  )

  # Add feature flag
  USE_MANIFEST_LLM_SELECTION: bool = Field(
      default=False,
      description="When enabled, log warning if llm_config_overrides is None"
  )

  # Update DEFAULT_LLM_MODEL comment
  DEFAULT_LLM_MODEL: str = Field(
      default="gpt-5-mini-2025-08-07",
      description="DEPRECATED: Fallback when no override specified. "
                  "New code should use manifest via llm_config_overrides."
  )
  ```

**2.5.5. Add Manifest Validation to ENG5 Runner**
- **File**: `scripts/cj_experiments_runners/eng5_np/cli.py`
- **Enhancement**: Validate `--llm-model` against manifest before publishing
  ```python
  def validate_llm_overrides(
      provider: str | None,
      model: str | None,
  ) -> None:
      """Validate LLM overrides against model manifest."""
      if model is None:
          logger.warning("No --llm-model specified; using service default")
          return

      # Import manifest and validate
      from services.llm_provider_service.model_manifest import (
          get_model_config,
          ProviderName,
      )

      try:
          provider_enum = ProviderName(provider.upper()) if provider else ProviderName.ANTHROPIC
          config = get_model_config(provider_enum, model)
          logger.info(
              "Using validated model from manifest",
              extra={
                  "provider": provider,
                  "model": model,
                  "api_version": config.api_version,
                  "release_date": config.release_date,
              }
          )
      except (ValueError, KeyError) as e:
          logger.error(f"Invalid model selection: {e}")
          raise typer.BadParameter(
              f"Model '{model}' not found in manifest for provider '{provider}'. "
              f"Run 'pdm run llm-check-models' to see available models."
          )
  ```

**2.5.6. Update Integration Call Chain Documentation**
- **File**: `services/llm_provider_service/README.md`
- **Add Section**: "Integration with Upstream Services"
- **Contents**: Document how CJ Assessment Service, ENG5 runner, and future callers should:
  1. Query manifest for available models
  2. Build `LLMConfigOverrides` with selected model
  3. Pass via event contract or HTTP API
  4. Parse model metadata from response/callback

#### Checkpoints
- ✅ CJ integration tests pass with manifest-based selection
- ✅ ENG5 runner validation rejects invalid model IDs
- ✅ All integration points documented with file:line references
- ✅ Backward compatibility maintained (hardcoded defaults still work)

#### Done Definition
- Integration tests prove end-to-end model selection works
- CJ service can optionally enforce manifest-based selection (feature flag)
- ENG5 runner validates CLI flags against manifest
- Documentation clearly explains integration patterns for future callers
- Zero breaking changes to existing functionality

---

### Phase 3: Compatibility Validation & Testing (Week 2)

#### Deliverables
- ✅ Integration test suite for model compatibility
- ✅ Validation report generation
- ✅ Update workflow documentation
- ✅ Extend to OpenAI, Google, OpenRouter

#### Steps

**3.1. Create Compatibility Test Suite**
- **File**: `services/llm_provider_service/tests/integration/test_model_compatibility.py` (~250-300 LoC)
- **Purpose**: Validate that models work with comparison prompt
- **Approach**:
  - Mark tests as `@pytest.mark.integration` and `@pytest.mark.financial` (incurs API costs)
  - Test actual LLM API calls with representative comparison prompt
  - Validate structured output parsing succeeds
  - Check response quality (winner, justification, confidence format)
  - Compare current model vs newly discovered models (when available)

  ```python
  import pytest
  from services.llm_provider_service.model_checker.anthropic_checker import AnthropicModelChecker
  from services.llm_provider_service.implementations.anthropic_provider_impl import AnthropicProviderImpl

  @pytest.mark.integration
  @pytest.mark.financial
  async def test_anthropic_current_model_compatibility(settings):
      """Validate current Anthropic model produces valid comparison responses."""
      provider = AnthropicProviderImpl(settings)

      # Use representative comparison prompt from CJ assessment
      request = ComparisonRequest(
          essay_a="Sample essay A content...",
          essay_b="Sample essay B content...",
          prompt="Evaluate which essay better addresses...",
          metadata={"test": "compatibility_check"}
      )

      response = await provider.generate_comparison(request)

      # Validate structured output
      assert response.winner in ["Essay A", "Essay B"]
      assert 50 <= len(response.justification) <= 500
      assert 1.0 <= response.confidence <= 5.0

  @pytest.mark.integration
  @pytest.mark.financial
  @pytest.mark.skipif("os.getenv('CHECK_NEW_MODELS') != '1'")
  async def test_anthropic_new_model_compatibility(settings):
      """Test newly discovered models (only when explicitly enabled)."""
      checker = AnthropicModelChecker(settings)
      new_models = await checker.check_latest_models()

      for model in new_models:
          if model.model_id == settings.ANTHROPIC_MODEL_ID:
              continue  # Skip current model

          # Test new model...
  ```

**3.2. Generate Compatibility Reports**
- **Enhancement**: CLI `--report` flag generates detailed validation report
- **Output**: JSON and human-readable markdown
  ```json
  {
    "check_date": "2025-11-08T14:30:00Z",
    "provider": "anthropic",
    "current_model": {
      "model_id": "claude-3-5-haiku-20241022",
      "status": "compatible",
      "last_tested": "2025-11-08T14:30:00Z"
    },
    "discovered_models": [
      {
        "model_id": "claude-3-5-sonnet-20241022",
        "compatibility_status": "compatible",
        "issues": [],
        "recommendation": "safe_upgrade"
      }
    ],
    "breaking_changes": []
  }
  ```

**3.3. Extend Registry to Other Providers**
- Add OpenAI, Google, OpenRouter to `model_manifest.py`
- Implement corresponding checker classes
- Update CLI to support `--provider all` flag
- Maintain focus on Anthropic as primary use case

**3.4. Document Manual Update Workflow**
- **File**: `services/llm_provider_service/README.md` (new section)
- **Contents**:
  ```markdown
  ## Updating LLM Models

  ### 1. Check for New Models
  ```bash
  pdm run llm-check-models --provider anthropic
  ```

  ### 2. Review Compatibility Report
  - Exit code 1 = new models available
  - Exit code 3 = breaking changes detected (manual intervention required)

  ### 3. Update Model Manifest
  Edit `model_manifest.py`:
  - Add new model to `SUPPORTED_MODELS.models[ProviderName.ANTHROPIC]`
  - Update `default_models` if switching default

  ### 4. Run Compatibility Tests
  ```bash
  CHECK_NEW_MODELS=1 pdm run pytest-root services/llm_provider_service/tests/integration/test_model_compatibility.py -v
  ```

  ### 5. Update Configuration
  - Update `.env` with new model ID (if needed)
  - Restart service and verify health endpoint

  ### 6. Monitor Initial Deployments
  - Check Grafana dashboards for error rates
  - Review structured output parsing success metrics
  - Monitor LLM provider circuit breaker state

  ### Rollback Procedure
  1. Revert model manifest changes
  2. Update `.env` to previous model ID
  3. Restart service
  4. Verify health and metrics return to baseline
  ```

#### Checkpoints
- ✅ Integration tests pass for current Anthropic model
- ✅ Compatibility report accurately identifies safe upgrades
- ✅ Documentation provides clear step-by-step update process
- ✅ All four providers represented in manifest

#### Done Definition
- Complete test coverage for model compatibility validation
- JSON compatibility reports enable automated analysis
- Update workflow documented with rollback procedure
- Registry supports all four providers (Anthropic, OpenAI, Google, OpenRouter)

---

### Phase 4: Scheduled Monitoring (Week 2 - Optional Background Worker)

**Note**: This phase is **deferred** until deployment/production readiness. Initial implementation uses manual CLI only.

#### Future Deliverables (Not Implemented in Initial Release)
- Background worker integration using Quart's `@app.before_serving`
- Configurable check interval (`MODEL_CHECK_INTERVAL_HOURS`)
- Prometheus metrics: `huleedu_llm_model_version_lag_days{provider, current_model}`
- Grafana alerts when model lag exceeds threshold
- Automatic structured logging of check results

#### Transformation Path
When ready to automate:
1. Add scheduled task to `app.py`
2. Implement metric collection during checker runs
3. Configure Grafana dashboard and alerts
4. Set `MODEL_CHECK_INTERVAL_HOURS=168` (weekly) in production `.env`

---

## File Structure

```
services/llm_provider_service/
├── model_manifest.py                   # Phase 1: Pydantic registry (200 LoC)
├── config.py                           # Phase 1: Modified to use manifest
├── model_checker/                      # Phase 2: Version checking module
│   ├── __init__.py                     # 17 LoC
│   ├── base.py                         # 230 LoC (protocol, models)
│   ├── anthropic_checker.py            # 283 LoC (AsyncAnthropic SDK)
│   ├── openai_checker.py               # 264 LoC (AsyncOpenAI SDK)
│   ├── google_checker.py               # 272 LoC (google.genai async)
│   └── openrouter_checker.py           # 290 LoC (aiohttp REST)
├── cli_check_models.py                 # Phase 2: 308 LoC (Typer CLI)
├── cli_output_formatter.py             # Phase 2: 224 LoC (Rich formatting)
├── implementations/
│   └── anthropic_provider_impl.py      # Phase 1: Modified for manifest
└── tests/
    ├── unit/
    │   ├── test_model_manifest.py                # Phase 1: 150 LoC
    │   ├── test_model_checker_base.py            # Phase 2: 389 LoC (25 tests)
    │   ├── test_anthropic_model_checker.py       # Phase 2: 533 LoC (21 tests)
    │   ├── test_openai_model_checker.py          # Phase 2: 488 LoC (20 tests)
    │   ├── test_google_model_checker.py          # Phase 2: 468 LoC (19 tests)
    │   └── test_openrouter_model_checker.py      # Phase 2: 470 LoC (19 tests)
    └── integration/
        ├── test_cli_check_models.py              # Phase 2: 189 LoC (12 tests)
        └── test_manifest_integration.py          # Phase 2: 99 LoC (4 tests)
```

**Implementation Stats**:
- Phase 1: 1 new file (200 LoC), 2 modified files
- Phase 2: 13 new files (3,925 LoC total), 1 bug fix
- Total: 14 new files, 3 modified files
- All files under **500 LoC hard limit**
- Test coverage: 120 tests, 2,586 LoC

---

## Testing Strategy

### Unit Tests
- **File**: `services/llm_provider_service/tests/unit/test_model_manifest.py`
- **Coverage**:
  - Registry validation (Pydantic schema)
  - Model lookup by provider and ID
  - Default model resolution
  - Error handling for unknown models
  - Capability validation logic
  - Frozen model config immutability

### Integration Tests
- **File**: `services/llm_provider_service/tests/integration/test_model_compatibility.py`
- **Markers**: `@pytest.mark.integration`, `@pytest.mark.financial`
- **Coverage**:
  - Real API calls to Anthropic (current model)
  - Structured output parsing validation
  - Response quality checks
  - New model testing (when `CHECK_NEW_MODELS=1`)

### Contract Tests
- Validate that checker implementations conform to `ModelCheckerProtocol`
- Ensure `DiscoveredModel` Pydantic schema matches provider API responses

### Manual Testing
- CLI command execution: `pdm run llm-check-models --provider anthropic`
- Verify exit codes for different scenarios
- Test with invalid API keys (error handling)
- Test with network failures (retry logic)

---

## Success Criteria

### Phase 1
✅ Single source of truth for model configurations (Pydantic manifest)
✅ Configuration layer refactored with backward compatibility
✅ All existing tests pass without modification
✅ Type checking passes (`pdm run typecheck-all`)

### Phase 2
✅ Manual CLI command works reliably (`pdm run llm-check-models`)
✅ Clear output guides manual update decisions
✅ Exit codes enable future automation
✅ Structured logging provides audit trail

### Phase 3
✅ Integration tests validate model compatibility
✅ JSON compatibility reports enable analysis
✅ Update workflow documented with rollback procedure
✅ All four providers represented in manifest

### Overall
✅ YAGNI compliance: No over-engineering, builds only what's needed now
✅ DRY compliance: Single source of truth for model configuration
✅ SOLID compliance: Clean protocol-based design for checkers
✅ Transformable: Easy path to scheduled automation in Phase 4
✅ <500 LoC per file: All files respect hard limit

---

## Migration Path

### Step 1: Anthropic Focus (Weeks 1-2)
1. Implement model manifest with Anthropic only
2. Build Anthropic checker and CLI
3. Validate with integration tests
4. Document manual update workflow

### Step 2: Multi-Provider Extension (Future)
1. Add OpenAI, Google, OpenRouter to manifest
2. Implement corresponding checkers
3. Test each provider independently
4. Update documentation

### Step 3: Automation (Production Readiness)
1. Add scheduled background worker
2. Implement Prometheus metrics
3. Configure Grafana alerts
4. Enable weekly automated checks

---

## Rollback Plan

If issues arise during implementation:

1. **Phase 1 Rollback**:
   - Revert `config.py` to hardcoded values
   - Remove `model_manifest.py` import
   - Git revert commits

2. **Phase 2 Rollback**:
   - Disable CLI command (no impact on runtime)
   - Remove checker implementations
   - Manifest remains as documentation

3. **Phase 3 Rollback**:
   - Skip integration tests (manual testing only)
   - Retain manifest for future use

---

## Dependencies

### External Libraries
- **anthropic**: SDK for Anthropic API (already in dependencies)
- **openai**: SDK for OpenAI API (already in dependencies)
- **google-generativeai**: SDK for Google API (already in dependencies)
- **typer**: CLI framework (to be added if not present)
- **rich**: CLI formatting (to be added if not present)

### Internal Dependencies
- `services/llm_provider_service/settings.py`: Settings/configuration
- `services/llm_provider_service/api_models.py`: Request/response models
- `libs/huleedu_service_libs/src/huleedu_service_libs/observability/`: Structured logging

---

## Timeline

### Week 1
- **Days 1-2**: Implement model manifest and refactor config (Phase 1.1-1.2)
- **Days 3-4**: Update provider implementations and add unit tests (Phase 1.3-1.4)
- **Day 5**: Start Anthropic checker implementation (Phase 2.1-2.2)

### Week 2
- **Days 1-2**: Complete CLI command and integration (Phase 2.3-2.5)
- **Days 3-4**: Build compatibility tests and validation (Phase 3.1-3.2)
- **Day 5**: Extend to other providers and finalize documentation (Phase 3.3-3.4)

**Total Estimated Effort**: 10 working days (2 weeks)

---

## Open Questions

1. **API Rate Limits**: Should checker implement rate limiting when querying multiple provider APIs?
   - **Decision**: Yes, add exponential backoff for all HTTP calls

2. **Model Cost Tracking**: Should manifest include cost per token for budgeting?
   - **Decision**: Defer to Phase 4, not needed for initial release

3. **Multi-Model Support**: Should service support A/B testing multiple models simultaneously?
   - **Decision**: No, out of scope. Single model per provider at a time.

4. **Notification Mechanism**: How to alert developers of new models in development?
   - **Decision**: Structured logs initially, Slack integration in Phase 4

---

## References

### Architecture Documents
- `.claude/rules/020.13-llm-provider-service-architecture.mdc`: Service architecture patterns
- `.claude/rules/051-pydantic-v2-standards.mdc`: Pydantic usage patterns
- `.claude/rules/070-testing-and-quality-assurance.mdc`: Testing strategy

### Implementation Examples
- `services/cj_assessment_service/models_db.py`: Pydantic model patterns
- `libs/common_core/src/common_core/grade_scales.py`: Registry pattern example
- `services/llm_provider_service/implementations/`: Current provider patterns

### External Documentation
- Anthropic API Reference: https://docs.anthropic.com/en/api/
- OpenAI API Reference: https://platform.openai.com/docs/api-reference
- Google AI API Reference: https://ai.google.dev/api
- OpenRouter API Reference: https://openrouter.ai/docs

---

## Appendix A: Comprehensive Integration Analysis

### A.1. API Contract Details

#### Request Schema (`LLMComparisonRequest`)
**File**: `services/llm_provider_service/api_models.py:20-40`

```python
class LLMComparisonRequest(BaseModel):
    user_prompt: str
    essay_a: str
    essay_b: str
    callback_topic: str
    llm_config_overrides: LLMConfigOverrides | None  # ← Model selection here
    correlation_id: UUID | None
    user_id: str | None
    metadata: Dict[str, Any]
```

#### LLM Config Overrides
**File**: `services/llm_provider_service/api_models.py:10-17`

```python
class LLMConfigOverrides(BaseModel):
    provider_override: LLMProviderType | None
    model_override: str | None              # ← Target model ID
    temperature_override: float | None
    system_prompt_override: str | None
    max_tokens_override: int | None
```

#### Response Schema (`LLMComparisonResponse`)
**File**: `services/llm_provider_service/api_models.py:43-65`

```python
class LLMComparisonResponse(BaseModel):
    winner: EssayComparisonWinner
    justification: str
    confidence: float
    provider: str                # ← Actual provider used (metadata)
    model: str                   # ← Actual model used (metadata)
    response_time_ms: int
    token_usage: Dict[str, int] | None
    cost_estimate: float | None
    correlation_id: UUID
    trace_id: str | None
    metadata: Dict[str, Any]
```

### A.2. Complete Integration Call Chain

```
┌─────────────────────────────────────────────────────────────────┐
│ ENG5 Batch Runner (.claude/research/scripts/)                   │
│   CLI: --llm-provider, --llm-model, --llm-temperature          │
│   Function: _build_llm_overrides() (lines 373-395)             │
│   Output: LLMConfigOverrides instance                           │
└────────────────────┬────────────────────────────────────────────┘
                     │ Kafka Event
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ Event: ELS_CJAssessmentRequestV1                                │
│   File: libs/common_core/.../cj_assessment_events.py:106-131   │
│   Field: llm_config_overrides: LLMConfigOverrides | None       │
└────────────────────┬────────────────────────────────────────────┘
                     │ Kafka Consumer
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ CJ Assessment Service - Event Processor                         │
│   File: services/cj_assessment_service/.../event_processor.py  │
│   Extracts: llm_config_overrides from event                    │
│   Passes to: LLMInteractionImpl.perform_comparisons()          │
└────────────────────┬────────────────────────────────────────────┘
                     │ Method Call
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ CJ Assessment Service - LLM Interaction                         │
│   File: services/cj_assessment_service/.../                    │
│         llm_interaction_impl.py:85-192                         │
│   Params: model_override, temperature_override, etc.           │
│   Calls: LLMProviderServiceClient.generate_comparison()        │
└────────────────────┬────────────────────────────────────────────┘
                     │ HTTP POST
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ CJ Assessment Service - HTTP Client                             │
│   File: services/cj_assessment_service/.../                    │
│         llm_provider_service_client.py:142-158                 │
│   Builds: LLMComparisonRequest with llm_config_overrides       │
│   Sends: POST http://llm_provider_service:8080/api/v1/comparison│
└────────────────────┬────────────────────────────────────────────┘
                     │ HTTP Request
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ LLM Provider Service - API Endpoint                             │
│   File: services/llm_provider_service/api/llm_routes.py:34-100 │
│   Validates: provider_override is specified (lines 79-90)      │
│   Routes: Request to appropriate provider implementation       │
│   Returns: 202 Accepted (async pattern)                        │
└────────────────────┬────────────────────────────────────────────┘
                     │ Async Processing
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ LLM Provider Service - Provider Implementation                  │
│   Files: services/llm_provider_service/implementations/        │
│   Uses: Model from llm_config_overrides.model_override         │
│   Calls: Actual LLM API (Anthropic, OpenAI, Google, etc.)     │
│   Publishes: LLMComparisonResultV1 to callback_topic          │
└────────────────────┬────────────────────────────────────────────┘
                     │ Kafka Callback
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ Event: LLMComparisonResultV1                                    │
│   File: libs/common_core/.../llm_provider_events.py:111-183   │
│   Includes: provider, model (actual values used)               │
│   Includes: cost_estimate, token_usage, response_time_ms       │
└────────────────────┬────────────────────────────────────────────┘
                     │ Kafka Consumer
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ CJ Assessment Service - Result Handler                          │
│   Processes: Comparison result                                  │
│   Records: Model metadata in assessment records                │
│   Publishes: CJAssessmentCompletedV1                           │
└─────────────────────────────────────────────────────────────────┘
```

### A.3. File:Line Integration Point Reference

| Component | File | Lines | Description |
|-----------|------|-------|-------------|
| **CJ Default Model** | `services/cj_assessment_service/config.py` | 118-121 | Hardcoded `DEFAULT_LLM_MODEL` (to be deprecated) |
| **CJ Client Build** | `services/cj_assessment_service/implementations/llm_provider_service_client.py` | 142-158 | Constructs `llm_config_overrides` from parameters |
| **CJ Orchestration** | `services/cj_assessment_service/implementations/llm_interaction_impl.py` | 85-192 | Accepts model/temp/tokens, passes to client |
| **Event Contract** | `libs/common_core/src/common_core/events/cj_assessment_events.py` | 106-131 | `ELS_CJAssessmentRequestV1.llm_config_overrides` |
| **ENG5 CLI Params** | `scripts/cj_experiments_runners/eng5_np/cli.py` | 32-210 | CLI parameter definitions |
| **ENG5 Override Build** | `scripts/cj_experiments_runners/eng5_np/cli.py` | 142-210 | `_build_llm_overrides()` function |
| **ENG5 Request Compose** | `scripts/cj_experiments_runners/eng5_np/requests.py` | 34-89 | Embeds overrides in CJ event |
| **LLM Provider API** | `services/llm_provider_service/api/llm_routes.py` | 34-100 | POST /comparison endpoint |
| **LLM Provider Validation** | `services/llm_provider_service/api/llm_routes.py` | 79-90 | Requires `provider_override` |
| **LLM Callback Event** | `libs/common_core/src/common_core/events/llm_provider_events.py` | 111-183 | `LLMComparisonResultV1` with model metadata |

### A.4. Configuration Dependencies

#### CJ Assessment Service Environment Variables
```bash
# Service Location
LLM_PROVIDER_SERVICE_URL="http://llm_provider_service:8080/api/v1"

# Defaults (to be deprecated)
DEFAULT_LLM_PROVIDER="OPENAI"              # Hardcoded in config.py:118
DEFAULT_LLM_MODEL="gpt-5-mini-2025-08-07"  # Hardcoded in config.py:119-121

# Callback Topic
LLM_PROVIDER_CALLBACK_TOPIC="huleedu.llm_provider.comparison_result.v1"
```

#### LLM Provider Service Environment Variables
```bash
# Provider Selection
DEFAULT_LLM_PROVIDER="ANTHROPIC"           # Default when no override
PROVIDER_SELECTION_STRATEGY="priority"     # priority|round-robin|least-cost
PROVIDER_PRIORITY_ORDER="anthropic,openai,google"

# API Keys
ANTHROPIC_API_KEY="sk-ant-..."
OPENAI_API_KEY="sk-..."
GOOGLE_API_KEY="..."
OPENROUTER_API_KEY="..."
```

### A.5. Backward Compatibility Matrix

| Aspect | Current Behavior | With Manifest | Breaking? |
|--------|-----------------|---------------|-----------|
| **No Override Specified** | Falls back to `DEFAULT_LLM_MODEL` | Same fallback | ❌ No |
| **Override Specified** | Uses override value | Same behavior | ❌ No |
| **Response Metadata** | Includes `model`, `provider` | Same metadata | ❌ No |
| **Event Contract** | `llm_config_overrides: None \| LLMConfigOverrides` | Same schema | ❌ No |
| **CJ Client** | Builds override from parameters | Same logic | ❌ No |
| **ENG5 Runner** | CLI flags → overrides | Same flow | ❌ No |
| **API Validation** | Requires `provider_override` | Same requirement | ❌ No |

**Conclusion**: Manifest integration is **100% backward compatible** when implemented as planned.

### A.6. Migration Checklist for Callers

When adding new services that call LLM Provider Service:

- [ ] Import `LLMConfigOverrides` from `libs/common_core/src/common_core/events/cj_assessment_events.py`
- [ ] Query model manifest for available models (via `get_model_config()`)
- [ ] Build `LLMConfigOverrides` with selected model/provider
- [ ] Pass via event field (`llm_config_overrides`) or HTTP API
- [ ] Parse model metadata from `LLMComparisonResultV1.model` and `.provider`
- [ ] Log model selection for audit trail
- [ ] Handle fallback if manifest lookup fails (use service default)
- [ ] Include model selection in integration tests

### A.7. Risk Assessment Summary

| Risk Category | Level | Mitigation |
|--------------|-------|------------|
| **Breaking Changes** | NONE | API already supports overrides; fallback preserved |
| **Data Loss** | NONE | Response includes model metadata; callbacks preserved |
| **Silent Failures** | LOW | Add validation in Phase 2.5; warn if manifest not used |
| **Performance Impact** | NONE | Model lookup is O(1); no additional latency |
| **Test Coverage Gap** | MEDIUM | Add integration tests in Phase 2.5 |

---

## Changelog

### 2025-11-08 - Initial Planning
- Created task document following ULTRATHINK minimal approach
- Defined three-phase implementation (2 weeks)
- Focus on Anthropic first, extend to other providers incrementally
- Alert-only automation (no auto-deployment)
- Pydantic-based model manifest for consistency with codebase patterns

### 2025-11-08 - Integration Analysis & Phase 2.5 Addition
- Conducted comprehensive integration analysis (via Explore agent)
- **Key Finding**: Architecture is already manifest-ready; zero breaking changes required
- Added Phase 2.5: Integration Verification with CJ Assessment Service and ENG5 runner
- Added Appendix A: Comprehensive Integration Analysis with:
  - Complete API contract details with file:line references
  - End-to-end integration call chain visualization
  - Configuration dependencies and environment variables
  - Backward compatibility matrix (100% compatible)
  - Migration checklist for future callers
  - Risk assessment summary (NONE/LOW risk across all categories)

### 2025-11-08 - Phase 2 Core Implementation Complete
**Implemented**: Model checker base protocol + 4 provider implementations (1,339 LoC)
- Created 6 model checker files (1,339 LoC): base protocol, 4 provider checkers, module init
- Type-safe: `pdm run typecheck-all` passes (0 errors, 1186 files)
- Bug fix: mypy union-attr assertions in result_aggregator_service tests

### 2025-11-09 - Phase 2 Complete: Test Suite Implementation
**Implemented**: CLI + comprehensive test suite (2,586 LoC, 120 tests)

**Files Created**:
- `cli_check_models.py` (308 LoC): Typer CLI with exit codes 0/1/2/3
- `cli_output_formatter.py` (224 LoC): Rich table/tree output, comparison diffs
- `tests/unit/test_model_checker_base.py` (389 LoC, 25 tests)
- `tests/unit/test_anthropic_model_checker.py` (533 LoC, 21 tests)
- `tests/unit/test_openai_model_checker.py` (488 LoC, 20 tests)
- `tests/unit/test_google_model_checker.py` (468 LoC, 19 tests)
- `tests/unit/test_openrouter_model_checker.py` (470 LoC, 19 tests)
- `tests/integration/test_cli_check_models.py` (189 LoC, 12 tests)
- `tests/integration/test_manifest_integration.py` (99 LoC, 4 tests)

**Bug Fix**: `conftest.py` duplicate `_settings_fixture` import causing test failures

**Test Results**: 227/227 unit tests passing (100% pass rate)

**Validation**: Type-safe, structured logging, comprehensive mocking for unit tests

### 2025-11-09 - Phase 2.5 Complete ✅

**Implementation**: Manifest integration verification with CJ Assessment and ENG5 batch runner

**Test Files Created**:
- `services/cj_assessment_service/tests/integration/test_llm_provider_manifest_integration.py` (471 LoC, 6 tests)
- `scripts/tests/test_eng5_np_manifest_integration.py` (311 LoC, 12 tests)

**Implementation Changes**:
- `scripts/cj_experiments_runners/eng5_np/cli.py:45-169` - CLI validation with manifest query, provider enum conversion fix (`.lower()` not `.upper()`)

**Test Results**: 18/18 passing (6 CJ integration + 12 ENG5 unit), 0 skips, no regressions (456 CJ tests passed)

**Documentation**:
- `services/llm_provider_service/README.md` - Added Model Manifest Integration section (33 LoC, compressed per Rule 090)
- `.claude/rules/020.13-llm-provider-service-architecture.mdc` - Added Section 1.5 Model Manifest patterns

**Compliance**: Architect review completed (lead-dev-code-reviewer), Rule 075/075.1 violations fixed (removed forbidden `capsys` log testing, added method call assertions), no new type errors
