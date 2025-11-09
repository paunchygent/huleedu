# Task Plan: LLM Provider Model Family Filtering System

## Executive Summary

- **Purpose**: Implement model family filtering for the LLM model checker CLI to distinguish between updates within tracked model families versus entirely new model families, reducing noise and focusing on actionable model updates.
- **Scope**: Add family-aware comparison logic, configuration management, refined exit codes, and two-tier output display (tracked family updates vs untracked families).
- **Integration Context**: Enhances `llm_provider_service` model checking workflow by filtering 85+ new models down to relevant subsets based on explicitly managed model families (e.g., `gpt-5`, `claude-haiku`).

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

**Model checker CLI flags all new models indiscriminately**, creating excessive noise:

- **OpenAI**: 85 new models detected (including `dall-e-2`, `whisper-1`, `o3-mini`, `sora-2`)
- **Anthropic**: 7 new models detected (including deprecated Claude 3.0 variants)
- **Issue**: Cannot distinguish between:
  - **Relevant**: New `gpt-5-turbo` variant in tracked `gpt-5` family
  - **Irrelevant**: Entirely new `dall-e-3` model family we don't use

### Current Behavior

```bash
$ pdm run llm-check-models --provider openai
# Output: 85 new models (exit code 1)
# Problem: Includes models from families we don't track (dalle, whisper, sora, o3, etc.)
# Result: Signal-to-noise ratio makes CLI output unusable for monitoring
```

### Current Comparison Logic

`services/llm_provider_service/model_checker/openai_checker.py:148-151`

```python
# Identifies new models (in API but not in manifest)
new_models = [
    model for model_id, model in discovered_by_id.items()
    if model_id not in manifest_by_id
]
# Problem: No family filtering - flags ALL new models
```

### Tracked Model Families (Current Manifest)

Based on analysis of `services/llm_provider_service/model_manifest.py`:

**Anthropic (2 models)**:

- `claude-haiku` family: `claude-haiku-4-5-20251001`
- `claude-sonnet` family: `claude-sonnet-4-5-20250929`

**OpenAI (8 models)**:

- `gpt-5` family: `gpt-5-2025-08-07`, `gpt-5-mini-2025-08-07`, `gpt-5-nano-2025-08-07`
- `gpt-4.1` family: `gpt-4.1-2025-04-14`, `gpt-4.1-mini-2025-04-14`, `gpt-4.1-nano-2025-04-14`
- `gpt-4o` family: `gpt-4o-2024-11-20`, `gpt-4o-mini-2024-07-18`

**Google (1 model)**:

- `gemini-2.5-flash` family: `gemini-2.5-flash-preview-05-20`

**OpenRouter (1 model)**:

- `claude-haiku-openrouter` family: `anthropic/claude-haiku-4-5-20251001`

## Design Decisions

### User Requirements (Confirmed 2025-11-09)

1. **New Family Handling**: Show as informational section (don't hide, don't block execution)
2. **Configuration Strategy**: Explicit Settings configuration with environment variable override
3. **Schema Backfilling**: Yes, add `model_family` field to all 12 existing ModelConfigs
4. **Family Update Priority**: Separate exit code (4) for in-family updates vs untracked families (5)

### Architecture Pattern: Family-Aware Model Tracking

**Family Definition**: String-based prefix matching extracted from model_id

- Example: `gpt-5-mini-2025-08-07` → family `gpt-5`
- Example: `claude-haiku-4-5-20251001` → family `claude-haiku`
- Example: `gemini-2.5-flash-preview-05-20` → family `gemini-2.5-flash`

**Comparison Categories**:

1. **In-family updates**: New variants within tracked families (actionable, exit code 4)
2. **Untracked families**: Models from families not in active tracking (informational, exit code 5)
3. **Breaking changes**: API incompatibilities (blocking, exit code 3)
4. **Deprecated models**: Removed from API (informational)

**Benefits**:

- **Focus**: Only track updates to models we actually use
- **Discovery**: Still see new families for evaluation (informational)
- **Actionable**: Clear distinction between must-review vs nice-to-know
- **Configurable**: Easy to add/remove families from tracking

## Phase Breakdown

### Phase 1: Schema & Configuration Updates (Week 1, Day 1-2)

#### Deliverables

- ✅ ModelConfig schema extended with `model_family` field
- ✅ All 12 existing models backfilled with family metadata
- ✅ Settings configuration with `ACTIVE_MODEL_FAMILIES`
- ✅ Environment variable override support

#### Implementation Steps

**1.1. Update ModelConfig Schema**

- **File**: `services/llm_provider_service/manifest/types.py`
- **Location**: Lines 60-110 (ModelConfig class)
- **Change**:

  ```python
  class ModelConfig(BaseModel):
      model_id: str = Field(...)
      provider: ProviderName = Field(...)
      display_name: str = Field(...)

      # NEW FIELD
      model_family: str = Field(
          ...,
          description="Model family identifier for grouping related models "
          "(e.g., 'gpt-5', 'claude-haiku', 'gemini-2.5-flash')"
      )

      # ... existing fields
  ```

**1.2. Backfill Existing Models**

- **Files**:
  - `services/llm_provider_service/manifest/anthropic.py`
  - `services/llm_provider_service/manifest/openai.py`
  - `services/llm_provider_service/manifest/google.py`
  - `services/llm_provider_service/manifest/openrouter.py`

**Anthropic Models** (`manifest/anthropic.py:31-75`):

```python
ModelConfig(
    model_id="claude-haiku-4-5-20251001",
    model_family="claude-haiku",  # ADD
    provider=ProviderName.ANTHROPIC,
    # ... rest of config
),
ModelConfig(
    model_id="claude-sonnet-4-5-20250929",
    model_family="claude-sonnet",  # ADD
    provider=ProviderName.ANTHROPIC,
    # ... rest of config
),
```

**OpenAI Models** (`manifest/openai.py:31-153`):

```python
# GPT-5 Family (3 models)
ModelConfig(model_id="gpt-5-2025-08-07", model_family="gpt-5", ...),
ModelConfig(model_id="gpt-5-mini-2025-08-07", model_family="gpt-5", ...),
ModelConfig(model_id="gpt-5-nano-2025-08-07", model_family="gpt-5", ...),

# GPT-4.1 Family (3 models)
ModelConfig(model_id="gpt-4.1-2025-04-14", model_family="gpt-4.1", ...),
ModelConfig(model_id="gpt-4.1-mini-2025-04-14", model_family="gpt-4.1", ...),
ModelConfig(model_id="gpt-4.1-nano-2025-04-14", model_family="gpt-4.1", ...),

# GPT-4o Family (2 models)
ModelConfig(model_id="gpt-4o-2024-11-20", model_family="gpt-4o", ...),
ModelConfig(model_id="gpt-4o-mini-2024-07-18", model_family="gpt-4o", ...),
```

**Google Models** (`manifest/google.py:31-60`):

```python
ModelConfig(
    model_id="gemini-2.5-flash-preview-05-20",
    model_family="gemini-2.5-flash",  # ADD
    provider=ProviderName.GOOGLE,
    # ... rest of config
),
```

**OpenRouter Models** (`manifest/openrouter.py:31-60`):

```python
ModelConfig(
    model_id="anthropic/claude-haiku-4-5-20251001",
    model_family="claude-haiku-openrouter",  # ADD
    provider=ProviderName.OPENROUTER,
    # ... rest of config
),
```

**1.3. Add Settings Configuration**

- **File**: `services/llm_provider_service/config.py`
- **Location**: After line 180 (in Settings class)
- **Change**:

  ```python
  class Settings(SecureServiceSettings):
      # ... existing fields ...

      # Model Family Tracking Configuration
      ACTIVE_MODEL_FAMILIES: Dict[ProviderName, List[str]] = Field(
          default_factory=lambda: {
              ProviderName.ANTHROPIC: ["claude-haiku", "claude-sonnet"],
              ProviderName.OPENAI: ["gpt-5", "gpt-4.1", "gpt-4o"],
              ProviderName.GOOGLE: ["gemini-2.5-flash"],
              ProviderName.OPENROUTER: ["claude-haiku-openrouter"],
          },
          description="Model families to actively track per provider. "
          "New models within these families trigger actionable alerts (exit code 4). "
          "Models from other families are shown as informational only (exit code 5)."
      )

      FLAG_NEW_MODEL_FAMILIES: bool = Field(
          default=True,
          description="If True, new model families are shown in informational section. "
          "If False, untracked families are silently ignored."
      )
  ```

**Environment Variable Override**:

```bash
# .env or environment
LLM_PROVIDER_SERVICE_ACTIVE_MODEL_FAMILIES='{"anthropic":["claude-haiku","claude-sonnet"],"openai":["gpt-5","gpt-4.1","gpt-4o"]}'
```

#### Validation Steps

1. Run `pdm run typecheck-all` from repository root
2. Verify all 12 models have `model_family` field
3. Verify Settings loads `ACTIVE_MODEL_FAMILIES` correctly
4. Test environment variable override with temporary config

---

### Phase 2: Comparison Logic Updates (Week 1, Day 3-4)

#### Deliverables

- ✅ ModelComparisonResult extended with family-aware fields
- ✅ Family extraction logic in all 4 checkers
- ✅ Updated comparison algorithms
- ✅ Backward compatibility maintained

#### Implementation Steps

**2.1. Update ModelComparisonResult**

- **File**: `services/llm_provider_service/model_checker/base.py`
- **Location**: Lines 124-169 (ModelComparisonResult class)
- **Change**:

  ```python
  class ModelComparisonResult(BaseModel):
      model_config = ConfigDict(frozen=True)

      provider: ProviderName = Field(...)

      # NEW FIELDS for family-based filtering
      new_models_in_tracked_families: list[DiscoveredModel] = Field(
          default_factory=list,
          description="New models within families we're actively tracking (actionable)",
      )
      new_untracked_families: list[DiscoveredModel] = Field(
          default_factory=list,
          description="Models from entirely new families not in active tracking (informational)",
      )

      # DEPRECATED but maintained for backward compatibility
      new_models: list[DiscoveredModel] = Field(
          default_factory=list,
          description="[DEPRECATED] Use new_models_in_tracked_families + new_untracked_families",
      )

      # Existing fields
      deprecated_models: list[str] = Field(default_factory=list, ...)
      updated_models: list[tuple[str, DiscoveredModel]] = Field(default_factory=list, ...)
      breaking_changes: list[str] = Field(default_factory=list, ...)
      is_up_to_date: bool = Field(...)
      checked_at: date = Field(default_factory=date.today, ...)
  ```

**2.2. Implement Family Extraction Logic**

Add to each checker implementation:

- `services/llm_provider_service/model_checker/openai_checker.py`
- `services/llm_provider_service/model_checker/anthropic_checker.py`
- `services/llm_provider_service/model_checker/google_checker.py`
- `services/llm_provider_service/model_checker/openrouter_checker.py`

**OpenAI Family Extraction** (`openai_checker.py`):

```python
def _extract_family(self, model_id: str) -> str:
    """Extract model family from OpenAI model_id.

    Examples:
        gpt-5-mini-2025-08-07 → gpt-5
        gpt-4.1-2025-04-14 → gpt-4.1
        gpt-4o-mini-2024-07-18 → gpt-4o
        dall-e-3 → dall-e
        whisper-1 → whisper

    Args:
        model_id: Full model identifier from OpenAI API

    Returns:
        Family identifier (prefix before first variant indicator)
    """
    # Pattern: Extract base family name before version/date suffix
    # gpt-5-mini-2025-08-07 → gpt-5
    # gpt-4.1-nano-2025-04-14 → gpt-4.1
    # gpt-4o-mini-2024-07-18 → gpt-4o

    parts = model_id.split("-")

    # Special case: gpt-4.1 (decimal version)
    if len(parts) >= 2 and parts[0] == "gpt" and "." in parts[1]:
        return f"{parts[0]}-{parts[1]}"  # e.g., "gpt-4.1"

    # Standard case: gpt-5, gpt-4o
    if len(parts) >= 2 and parts[0] == "gpt":
        return f"{parts[0]}-{parts[1]}"  # e.g., "gpt-5", "gpt-4o"

    # Other families: dall-e, whisper, o1, o3, o4
    # Use first token as family
    return parts[0]

def _get_active_families(self) -> set[str]:
    """Get configured active families for OpenAI from settings."""
    return set(self.settings.ACTIVE_MODEL_FAMILIES.get(ProviderName.OPENAI, []))
```

**Anthropic Family Extraction** (`anthropic_checker.py`):

```python
def _extract_family(self, model_id: str) -> str:
    """Extract model family from Anthropic model_id.

    Examples:
        claude-haiku-4-5-20251001 → claude-haiku
        claude-sonnet-4-5-20250929 → claude-sonnet
        claude-opus-4-20250514 → claude-opus

    Args:
        model_id: Full model identifier from Anthropic API

    Returns:
        Family identifier (claude-{tier})
    """
    # Pattern: claude-{tier}-{version}-{date}
    # Extract first two tokens: claude-haiku, claude-sonnet, claude-opus
    parts = model_id.split("-")
    if len(parts) >= 2 and parts[0] == "claude":
        return f"{parts[0]}-{parts[1]}"  # e.g., "claude-haiku"

    # Fallback: use first token
    return parts[0]

def _get_active_families(self) -> set[str]:
    """Get configured active families for Anthropic from settings."""
    return set(self.settings.ACTIVE_MODEL_FAMILIES.get(ProviderName.ANTHROPIC, []))
```

**Google Family Extraction** (`google_checker.py`):

```python
def _extract_family(self, model_id: str) -> str:
    """Extract model family from Google model_id.

    Examples:
        gemini-2.5-flash-preview-05-20 → gemini-2.5-flash
        gemini-2.0-pro → gemini-2.0-pro
        gemini-1.5-flash → gemini-1.5-flash

    Args:
        model_id: Full model identifier from Google API

    Returns:
        Family identifier (gemini-{version}-{tier})
    """
    # Pattern: gemini-{version}-{tier}-{variant}
    # Extract first three tokens: gemini-2.5-flash
    parts = model_id.split("-")
    if len(parts) >= 3 and parts[0] == "gemini":
        return f"{parts[0]}-{parts[1]}-{parts[2]}"  # e.g., "gemini-2.5-flash"

    # Fallback: use full id
    return model_id

def _get_active_families(self) -> set[str]:
    """Get configured active families for Google from settings."""
    return set(self.settings.ACTIVE_MODEL_FAMILIES.get(ProviderName.GOOGLE, []))
```

**OpenRouter Family Extraction** (`openrouter_checker.py`):

```python
def _extract_family(self, model_id: str) -> str:
    """Extract model family from OpenRouter model_id.

    OpenRouter uses provider-prefixed IDs: provider/model-id

    Examples:
        anthropic/claude-haiku-4-5-20251001 → claude-haiku-openrouter
        openai/gpt-5-mini → gpt-5-openrouter

    Args:
        model_id: Full model identifier from OpenRouter API

    Returns:
        Family identifier with -openrouter suffix
    """
    # Pattern: {provider}/{model-id}
    if "/" in model_id:
        provider, base_id = model_id.split("/", 1)

        # Extract family from base_id using provider-specific logic
        if provider == "anthropic":
            parts = base_id.split("-")
            if len(parts) >= 2 and parts[0] == "claude":
                return f"{parts[0]}-{parts[1]}-openrouter"

        elif provider == "openai":
            parts = base_id.split("-")
            if len(parts) >= 2 and parts[0] == "gpt":
                return f"{parts[0]}-{parts[1]}-openrouter"

    # Fallback: use full id
    return model_id

def _get_active_families(self) -> set[str]:
    """Get configured active families for OpenRouter from settings."""
    return set(self.settings.ACTIVE_MODEL_FAMILIES.get(ProviderName.OPENROUTER, []))
```

**2.3. Update Comparison Logic**

Update `compare_with_manifest()` in all 4 checkers:

**Example for OpenAI** (`openai_checker.py:138-189`):

```python
async def compare_with_manifest(self) -> ModelComparisonResult:
    """Compare discovered models with manifest and identify changes."""
    discovered = await self.check_latest_models()
    manifest_models = list_models(self.provider)

    # Build lookup maps
    discovered_by_id = {m.model_id: m for m in discovered}
    manifest_by_id = {m.model_id: m for m in manifest_models}
    active_families = self._get_active_families()

    # Categorize new models by family
    new_in_tracked = []
    new_untracked = []

    for model_id, discovered_model in discovered_by_id.items():
        if model_id not in manifest_by_id:
            family = self._extract_family(model_id)

            if family in active_families:
                new_in_tracked.append(discovered_model)
            else:
                new_untracked.append(discovered_model)

    # Deprecated models (in manifest but not in API)
    deprecated_models = [
        model_id for model_id in manifest_by_id.keys()
        if model_id not in discovered_by_id
    ]

    # Updated models (metadata changes)
    updated_models: list[tuple[str, DiscoveredModel]] = []
    breaking_changes: list[str] = []

    for model_id, manifest_model in manifest_by_id.items():
        if model_id in discovered_by_id:
            discovered_model = discovered_by_id[model_id]
            if self._has_capability_changes(manifest_model, discovered_model):
                updated_models.append((model_id, discovered_model))

    # Determine up-to-date status
    is_up_to_date = (
        len(new_in_tracked) == 0
        and len(new_untracked) == 0
        and len(deprecated_models) == 0
        and len(updated_models) == 0
        and len(breaking_changes) == 0
    )

    # Populate both new and legacy fields
    all_new = new_in_tracked + new_untracked

    return ModelComparisonResult(
        provider=self.provider,
        new_models_in_tracked_families=new_in_tracked,
        new_untracked_families=new_untracked,
        new_models=all_new,  # Deprecated but maintained for compatibility
        deprecated_models=deprecated_models,
        updated_models=updated_models,
        breaking_changes=breaking_changes,
        is_up_to_date=is_up_to_date,
    )
```

Apply similar changes to:

- `anthropic_checker.py`
- `google_checker.py`
- `openrouter_checker.py`

#### Validation Steps

1. Run `pdm run typecheck-all` from repository root
2. Verify family extraction logic with unit tests
3. Test comparison categorization with mock data
4. Ensure backward compatibility (old `new_models` field still populated)

---

### Phase 3: CLI & Exit Code Updates (Week 1, Day 5)

#### Deliverables

- ✅ New exit codes (4 and 5) defined
- ✅ Updated exit code determination logic
- ✅ Two-tier output formatting
- ✅ Updated CLI docstrings

#### Implementation Steps

**3.1. Update Exit Codes**

- **File**: `services/llm_provider_service/cli_check_models.py`
- **Location**: Lines 74-80 (ExitCode enum)
- **Change**:

  ```python
  class ExitCode(int, Enum):
      """CLI exit codes."""

      UP_TO_DATE = 0
      # NEW_MODELS_AVAILABLE = 1  # DEPRECATED - removed
      API_ERROR = 2
      BREAKING_CHANGES = 3
      IN_FAMILY_UPDATES = 4  # NEW - new variants in tracked families
      UNTRACKED_FAMILIES = 5  # NEW - informational only
  ```

**3.2. Update determine_exit_code()**

- **File**: `services/llm_provider_service/cli_check_models.py`
- **Location**: Lines 186-205
- **Change**:

  ```python
  def determine_exit_code(results: list[ModelComparisonResult]) -> ExitCode:
      """Determine appropriate exit code based on results.

      Priority order:
      1. BREAKING_CHANGES (3): API incompatibilities requiring manual intervention
      2. IN_FAMILY_UPDATES (4): New variants in tracked families (actionable)
      3. UNTRACKED_FAMILIES (5): New families detected (informational)
      4. UP_TO_DATE (0): No changes

      Args:
          results: List of comparison results

      Returns:
          Exit code enum value
      """
      # Highest priority: Breaking changes
      has_breaking = any(len(r.breaking_changes) > 0 for r in results)
      if has_breaking:
          return ExitCode.BREAKING_CHANGES

      # Second priority: In-family updates (actionable)
      has_in_family = any(len(r.new_models_in_tracked_families) > 0 for r in results)
      if has_in_family:
          return ExitCode.IN_FAMILY_UPDATES

      # Third priority: Untracked families (informational)
      has_untracked = any(len(r.new_untracked_families) > 0 for r in results)
      if has_untracked:
          return ExitCode.UNTRACKED_FAMILIES

      # Deprecated or updated models don't trigger warnings
      return ExitCode.UP_TO_DATE
  ```

**3.3. Update CLI Exit Messages**

- **File**: `services/llm_provider_service/cli_check_models.py`
- **Location**: Lines 373-383
- **Change**:

  ```python
  # Determine exit code
  exit_code = determine_exit_code(results)

  if exit_code == ExitCode.BREAKING_CHANGES:
      console.print(
          "\n[red]⛔ Breaking changes detected! Update the manifest before proceeding.[/red]"
      )
  elif exit_code == ExitCode.IN_FAMILY_UPDATES:
      console.print(
          "\n[yellow]🔄 New variants detected in tracked families. "
          "Consider updating manifest.[/yellow]"
      )
  elif exit_code == ExitCode.UNTRACKED_FAMILIES:
      console.print(
          "\n[blue]ℹ️  New model families detected. "
          "Review separately if needed.[/blue]"
      )
  else:
      console.print("\n[green]✅ All providers are up-to-date![/green]")

  raise typer.Exit(code=exit_code.value)
  ```

**3.4. Update CLI Docstring**

- **File**: `services/llm_provider_service/cli_check_models.py`
- **Location**: Lines 19-23
- **Change**:

  ```python
  Exit Codes:
      0: All up-to-date (no changes needed)
      2: API error or authentication failure
      3: Breaking changes detected (requires manifest update)
      4: In-family updates (new variants in tracked families)
      5: Untracked families detected (informational only)
  ```

**3.5. Update Output Formatter**

- **File**: `services/llm_provider_service/cli_output_formatter.py`
- **Function**: `format_comparison_table()`
- **Change**: Add two-section table display

```python
def format_comparison_table(
    result: ModelComparisonResult,
    verbose: bool = False,
) -> Table:
    """Format comparison result as Rich table with family-aware sections.

    Args:
        result: Comparison result to format
        verbose: Include detailed metadata

    Returns:
        Rich Table with two sections: tracked families and untracked families
    """
    table = Table(
        title=f"{result.provider.value.upper()} Models",
        show_header=True,
        header_style="bold magenta",
    )

    table.add_column("Status", style="cyan", no_wrap=True)
    table.add_column("Model ID", style="white")
    table.add_column("Display Name", style="white")

    # Section 1: Tracked Family Updates (actionable)
    if result.new_models_in_tracked_families:
        table.add_row("[bold yellow]Tracked Family Updates[/bold yellow]", "", "")
        for model in result.new_models_in_tracked_families:
            table.add_row(
                "🔄 In-family",
                model.model_id,
                model.display_name,
            )

    # Section 2: Untracked Families (informational)
    if result.new_untracked_families:
        table.add_row("[bold blue]Untracked Families (Informational)[/bold blue]", "", "")
        for model in result.new_untracked_families:
            table.add_row(
                "ℹ️  Untracked",
                model.model_id,
                model.display_name,
            )

    # Existing sections: deprecated, updated, breaking
    # ... (keep existing logic)

    return table
```

**3.6. Update Summary Formatter**

- **File**: `services/llm_provider_service/cli_output_formatter.py`
- **Function**: `format_summary()`
- **Change**: Display separate counts

```python
def format_summary(results: list[ModelComparisonResult]) -> None:
    """Display summary of comparison results with family-aware counts."""
    console.print("\n[bold]Summary[/bold]")
    console.print("=" * 50)

    total_in_family = sum(len(r.new_models_in_tracked_families) for r in results)
    total_untracked = sum(len(r.new_untracked_families) for r in results)
    total_updated = sum(len(r.updated_models) for r in results)
    total_deprecated = sum(len(r.deprecated_models) for r in results)
    total_breaking = sum(len(r.breaking_changes) for r in results)

    console.print(f"🔄 In-family updates: {total_in_family}")
    console.print(f"ℹ️  Untracked families: {total_untracked}")
    console.print(f"⚠️  Updated models: {total_updated}")
    console.print(f"🗑️  Deprecated models: {total_deprecated}")
    console.print(f"⛔ Breaking changes: {total_breaking}")
```

#### Validation Steps

1. Run `pdm run typecheck-all` from repository root
2. Test CLI with real API calls:

   ```bash
   pdm run llm-check-models --provider openai
   pdm run llm-check-models --provider anthropic
   ```

3. Verify exit codes:
   - Exit code 4 when new in-family models exist
   - Exit code 5 when only untracked families exist
   - Exit code 0 when up-to-date
4. Verify output formatting shows two sections

---

### Phase 4: Testing (Week 1, Day 6-7)

#### Deliverables

- ✅ Family extraction unit tests (60-80 LoC)
- ✅ Comparison categorization unit tests (100-120 LoC)
- ✅ Exit code logic unit tests (60-80 LoC)
- ✅ Configuration loading unit tests (40-60 LoC)
- ✅ All existing tests updated for backward compatibility

#### Implementation Steps

**4.1. Create Family Extraction Tests**

- **File**: `services/llm_provider_service/tests/unit/test_model_family_extraction.py` (NEW)
- **Test Count**: ~15 tests
- **Coverage**:

  ```python
  class TestOpenAIFamilyExtraction:
      """Tests for OpenAI model family extraction logic."""

      @pytest.mark.parametrize("model_id, expected_family", [
          ("gpt-5-2025-08-07", "gpt-5"),
          ("gpt-5-mini-2025-08-07", "gpt-5"),
          ("gpt-5-nano-2025-08-07", "gpt-5"),
          ("gpt-4.1-2025-04-14", "gpt-4.1"),
          ("gpt-4.1-mini-2025-04-14", "gpt-4.1"),
          ("gpt-4o-2024-11-20", "gpt-4o"),
          ("gpt-4o-mini-2024-07-18", "gpt-4o"),
          ("dall-e-3", "dall-e"),
          ("whisper-1", "whisper"),
          ("o3-mini-2025-01-31", "o3"),
      ])
      def test_extract_family_openai_patterns(self, model_id, expected_family):
          """OpenAI family extraction handles various naming patterns."""
          checker = OpenAIModelChecker(...)
          assert checker._extract_family(model_id) == expected_family


  class TestAnthropicFamilyExtraction:
      """Tests for Anthropic model family extraction logic."""

      @pytest.mark.parametrize("model_id, expected_family", [
          ("claude-haiku-4-5-20251001", "claude-haiku"),
          ("claude-sonnet-4-5-20250929", "claude-sonnet"),
          ("claude-opus-4-20250514", "claude-opus"),
          ("claude-3-haiku-20240307", "claude-3-haiku"),
      ])
      def test_extract_family_anthropic_patterns(self, model_id, expected_family):
          """Anthropic family extraction handles tier-based naming."""
          checker = AnthropicModelChecker(...)
          assert checker._extract_family(model_id) == expected_family


  class TestGoogleFamilyExtraction:
      """Tests for Google model family extraction logic."""

      @pytest.mark.parametrize("model_id, expected_family", [
          ("gemini-2.5-flash-preview-05-20", "gemini-2.5-flash"),
          ("gemini-2.0-pro", "gemini-2.0-pro"),
          ("gemini-1.5-flash", "gemini-1.5-flash"),
      ])
      def test_extract_family_google_patterns(self, model_id, expected_family):
          """Google family extraction handles version-tier naming."""
          checker = GoogleModelChecker(...)
          assert checker._extract_family(model_id) == expected_family
  ```

**4.2. Create Comparison Categorization Tests**

- **File**: `services/llm_provider_service/tests/unit/test_model_family_comparison.py` (NEW)
- **Test Count**: ~12 tests
- **Coverage**:

  ```python
  class TestFamilyAwareComparison:
      """Tests for family-aware model comparison logic."""

      async def test_new_model_in_tracked_family_categorized_correctly(self):
          """New model in tracked family goes to in_tracked list."""
          # Setup: manifest has gpt-5-2025-08-07, API returns gpt-5-turbo
          # Expected: gpt-5-turbo in new_models_in_tracked_families

      async def test_new_model_in_untracked_family_categorized_correctly(self):
          """New model in untracked family goes to untracked list."""
          # Setup: manifest has no dalle models, API returns dall-e-3
          # Expected: dall-e-3 in new_untracked_families

      async def test_backward_compatibility_new_models_field_populated(self):
          """Deprecated new_models field contains both categories."""
          # Expected: new_models = in_tracked + untracked

      async def test_empty_active_families_treats_all_as_untracked(self):
          """When no active families configured, all new models are untracked."""
  ```

**4.3. Create Exit Code Logic Tests**

- **File**: `services/llm_provider_service/tests/unit/test_model_family_exit_codes.py` (NEW)
- **Test Count**: ~8 tests
- **Coverage**:

  ```python
  class TestExitCodeDetermination:
      """Tests for exit code logic with family filtering."""

      def test_exit_code_in_family_updates(self):
          """Exit code 4 when in-family updates exist."""
          result = ModelComparisonResult(
              provider=ProviderName.OPENAI,
              new_models_in_tracked_families=[mock_model],
              new_untracked_families=[],
              # ...
          )
          assert determine_exit_code([result]) == ExitCode.IN_FAMILY_UPDATES

      def test_exit_code_untracked_families(self):
          """Exit code 5 when only untracked families exist."""
          result = ModelComparisonResult(
              provider=ProviderName.OPENAI,
              new_models_in_tracked_families=[],
              new_untracked_families=[mock_model],
              # ...
          )
          assert determine_exit_code([result]) == ExitCode.UNTRACKED_FAMILIES

      def test_exit_code_priority_breaking_over_in_family(self):
          """Breaking changes take priority over in-family updates."""
          result = ModelComparisonResult(
              breaking_changes=["API version change"],
              new_models_in_tracked_families=[mock_model],
              # ...
          )
          assert determine_exit_code([result]) == ExitCode.BREAKING_CHANGES

      def test_exit_code_priority_in_family_over_untracked(self):
          """In-family updates take priority over untracked families."""
          result = ModelComparisonResult(
              new_models_in_tracked_families=[mock_model1],
              new_untracked_families=[mock_model2],
              # ...
          )
          assert determine_exit_code([result]) == ExitCode.IN_FAMILY_UPDATES
  ```

**4.4. Create Configuration Loading Tests**

- **File**: `services/llm_provider_service/tests/unit/test_config_env_loading.py` (UPDATE)
- **Add Tests**: ~5 new tests
- **Coverage**:

  ```python
  class TestModelFamilyConfiguration:
      """Tests for model family configuration loading."""

      def test_active_families_loads_from_settings(self):
          """ACTIVE_MODEL_FAMILIES loads default configuration."""
          settings = Settings()
          assert ProviderName.OPENAI in settings.ACTIVE_MODEL_FAMILIES
          assert "gpt-5" in settings.ACTIVE_MODEL_FAMILIES[ProviderName.OPENAI]

      def test_active_families_env_override(self):
          """Environment variable can override ACTIVE_MODEL_FAMILIES."""
          with patch.dict(os.environ, {
              "LLM_PROVIDER_SERVICE_ACTIVE_MODEL_FAMILIES":
              '{"openai":["gpt-4o"]}'
          }):
              settings = Settings()
              assert settings.ACTIVE_MODEL_FAMILIES[ProviderName.OPENAI] == ["gpt-4o"]

      def test_flag_new_model_families_default_true(self):
          """FLAG_NEW_MODEL_FAMILIES defaults to True."""
          settings = Settings(_env_file=None)
          assert settings.FLAG_NEW_MODEL_FAMILIES is True
  ```

**4.5. Update Existing Tests**

- **Files to Update**:
  - `test_anthropic_checker.py`: Update assertions for new fields
  - `test_openai_checker.py`: Update assertions for new fields
  - `test_google_checker.py`: Update assertions for new fields
  - `test_openrouter_checker.py`: Update assertions for new fields
  - `test_model_manifest.py`: Add tests for `model_family` field

- **Changes Needed**:

  ```python
  # OLD assertion (deprecated)
  assert len(result.new_models) == expected_count

  # NEW assertions
  assert len(result.new_models_in_tracked_families) == expected_tracked
  assert len(result.new_untracked_families) == expected_untracked
  # Verify backward compatibility
  assert len(result.new_models) == expected_tracked + expected_untracked
  ```

#### Validation Steps

1. Run `pdm run typecheck-all` from repository root
2. Run all unit tests:

   ```bash
   pdm run pytest-root services/llm_provider_service/tests/unit/ -v
   ```

3. Verify 100% pass rate
4. Check test coverage for new code:

   ```bash
   pdm run pytest-root services/llm_provider_service/tests/unit/ --cov=services/llm_provider_service/model_checker --cov-report=term-missing
   ```

5. Ensure no regressions in existing tests

---

## Success Criteria

### Functional Requirements

1. ✅ CLI correctly categorizes models into tracked/untracked families
2. ✅ Exit code 4 for in-family updates (e.g., `gpt-5-turbo` when `gpt-5` family tracked)
3. ✅ Exit code 5 for untracked families (e.g., `dall-e-3` when no dalle family tracked)
4. ✅ Output shows two distinct sections with appropriate styling
5. ✅ Configuration can be overridden via environment variables

### Technical Requirements

1. ✅ All 12 existing models have `model_family` field
2. ✅ `ACTIVE_MODEL_FAMILIES` configuration loads correctly
3. ✅ Family extraction logic works for all 4 providers
4. ✅ Backward compatibility maintained (`new_models` field populated)
5. ✅ 100% test pass rate
6. ✅ Type checking passes (`pdm run typecheck-all`)

### User Experience

**Before**:

```bash
$ pdm run llm-check-models --provider openai
# 85 new models (exit code 1)
# Noise: dall-e-2, whisper-1, o3-mini, sora-2, etc.
```

**After**:

```bash
$ pdm run llm-check-models --provider openai

Checking OPENAI models...

                      OPENAI Models
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Status         ┃ Model ID            ┃ Display Name ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ Tracked Family Updates                              │
│ 🔄 In-family   │ gpt-5-turbo         │ GPT-5 Turbo  │
│ 🔄 In-family   │ gpt-4.1-pro         │ GPT-4.1 Pro  │
│                                                      │
│ Untracked Families (Informational)                  │
│ ℹ️  Untracked   │ dall-e-3            │ DALL-E 3     │
│ ℹ️  Untracked   │ whisper-1           │ Whisper 1    │
│ ℹ️  Untracked   │ o3-mini             │ O3 Mini      │
│ ... (80 more)                                        │
└──────────────────────────────────────────────────────┘

Summary
==================================================
🔄 In-family updates: 2
ℹ️  Untracked families: 83
⚠️  Updated models: 0
🗑️  Deprecated models: 0
⛔ Breaking changes: 0

🔄 New variants detected in tracked families. Consider updating manifest.

# Exit code: 4
```

### Performance

- CLI execution time: < 5 seconds per provider
- Family extraction: O(1) string operations
- No additional API calls required

---

## Risk Mitigation

### Backward Compatibility

- **Risk**: Breaking existing workflows relying on `new_models` field
- **Mitigation**: Maintain `new_models` field populated with combined results
- **Validation**: Test existing code paths still work

### Configuration Management

- **Risk**: Users accidentally disable family tracking
- **Mitigation**: Sensible defaults, clear documentation, env var override
- **Validation**: Test with empty configuration

### False Categorization

- **Risk**: Model incorrectly categorized as tracked/untracked
- **Mitigation**: Comprehensive unit tests for family extraction logic
- **Validation**: Test with edge cases (special characters, unusual patterns)

---

## Documentation Updates

### Files to Update

1. `services/llm_provider_service/README.md`:
   - Add section on model family filtering
   - Document `ACTIVE_MODEL_FAMILIES` configuration
   - Update CLI usage examples

2. `services/llm_provider_service/ENVIRONMENT_VARIABLES.md`:
   - Document `ACTIVE_MODEL_FAMILIES` env var format
   - Document `FLAG_NEW_MODEL_FAMILIES` flag

3. `.claude/rules/020.13-llm-provider-service-architecture.mdc`:
   - Update with family filtering architecture
   - Document exit code meanings

4. CLI docstrings:
   - Update exit codes in module docstring
   - Update command help text

---

## Timeline

### Week 1

- **Day 1-2**: Phase 1 (Schema & Configuration)
- **Day 3-4**: Phase 2 (Comparison Logic)
- **Day 5**: Phase 3 (CLI & Exit Codes)
- **Day 6-7**: Phase 4 (Testing)

### Total Effort: 5-7 days

---

## Dependencies

### Internal

- Model manifest modularization (completed)
- Model checker CLI infrastructure (completed)
- Pydantic v2 settings configuration (completed)

### External

- None (all changes internal to llm_provider_service)

---

## Follow-up Tasks

### Future Enhancements

1. **Auto-add to manifest**: CLI option to automatically add in-family models
2. **Family-based manifest updates**: Bulk update all models in a family
3. **CI/CD integration**: Scheduled checks with family filtering
4. **Family deprecation tracking**: Track when entire families become deprecated
5. **Provider-specific family patterns**: More sophisticated extraction logic

### Documentation

1. Architecture decision record (ADR) for family filtering approach
2. Operational runbook for managing model families
3. User guide for configuring active families

---

## Appendix

### Model Family Patterns

**OpenAI**:

- `gpt-{major}-{variant?}-{date}` → `gpt-{major}`
- `gpt-{major}.{minor}-{variant?}-{date}` → `gpt-{major}.{minor}`
- Examples: `gpt-5`, `gpt-4.1`, `gpt-4o`

**Anthropic**:

- `claude-{tier}-{version}-{date}` → `claude-{tier}`
- Examples: `claude-haiku`, `claude-sonnet`, `claude-opus`

**Google**:

- `gemini-{version}-{tier}-{variant?}` → `gemini-{version}-{tier}`
- Examples: `gemini-2.5-flash`, `gemini-2.0-pro`

**OpenRouter**:

- `{provider}/{model-id}` → `{family}-openrouter`
- Examples: `claude-haiku-openrouter`, `gpt-5-openrouter`

### Configuration Examples

**Minimal (only production models)**:

```python
ACTIVE_MODEL_FAMILIES = {
    ProviderName.OPENAI: ["gpt-5"],
    ProviderName.ANTHROPIC: ["claude-haiku"],
}
```

**Comprehensive (all current families)**:

```python
ACTIVE_MODEL_FAMILIES = {
    ProviderName.ANTHROPIC: ["claude-haiku", "claude-sonnet"],
    ProviderName.OPENAI: ["gpt-5", "gpt-4.1", "gpt-4o"],
    ProviderName.GOOGLE: ["gemini-2.5-flash"],
    ProviderName.OPENROUTER: ["claude-haiku-openrouter"],
}
```

**Environment Variable**:

```bash
export LLM_PROVIDER_SERVICE_ACTIVE_MODEL_FAMILIES='{"openai":["gpt-5"],"anthropic":["claude-haiku"]}'
```

---

**Task Document Version**: 1.0
**Created**: 2025-11-09
**Author**: Claude Code (Sonnet 4.5)
**Status**: Ready for Implementation
