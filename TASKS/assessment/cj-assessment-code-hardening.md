---
id: cj-assessment-code-hardening
title: Cj Assessment Code Hardening
type: task
status: in_progress
priority: high
domain: assessment
owner_team: agents
created: '2025-11-21'
last_updated: '2025-11-21'
service: cj_assessment_service
owner: ''
program: ''
related: []
labels: []
---

# Task: CJ Assessment Service Code Hardening

Related reference: docs/operations/cj-assessment-runbook.md

> **Autonomous Claude Execution Prompt**
>
> 1. **Cloud VM Context** — You are operating inside the HuleEdu Claude cloud VM. Before taking any action, review and comply with `.claude/rules/111-cloud-vm-execution-standards.md`, including PATH setup for `pdm` and the prohibition on Docker/service startups.
>
> 2. **Plan, Then Execute Sequentially** — Produce an explicit plan first. Execute exactly one planned task at a time to 100% completion before moving to the next. Re-plan if new information appears.
>
> 3. **Targeted Validation** — After completing each task, run the narrowest relevant `pdm run` quality checks or pytest nodes (include `-s` when debugging) to validate the change, and document the command and outcome.
>
> 4. **Task Document Updates** — Before ending the session, update this task document with clear progress notes so the next contributor can resume seamlessly. Follow Rule `090-documentation-standards.md` for concise, intent-focused updates.
>
> 5. **Rule Adherence** — Apply all referenced architecture, DI, testing, and documentation standards in this file without introducing new patterns or fallbacks.

## Objective

Systematically audit and harden the entire CJ Assessment Service against drift arising from fast-paced prototyping and team coordination gaps.

**Target Drift Patterns**:

- Missing imports discovered at runtime
- Magic strings instead of shared constants/enums
- Dataclasses for boundary objects (should be Pydantic)
- Reimplemented utilities (should use common_core/service_libs)
- Inconsistent error handling patterns
- Unaligned logging (missing correlation_id, structured data)
- Type narrowing gaps (MyPy ignores)
- Code duplication across files

**Principle**: Enforce alignment with established patterns. Use existing shared code. Eliminate drift through systematic review.

**Approach**: 5 focused phases, each targeting specific drift patterns across all service files. Methodical, file-by-file coverage with immediate fixes.

---

## Scope

**Service**: `services/cj_assessment_service/`

**File Inventory** (~50 files to review):

```
api/
  ├── admin_routes.py          # Admin endpoints (instructions, prompts)
  ├── anchor_management.py     # Anchor registration
  ├── callback_routes.py       # LLM Provider callbacks
  └── health.py                # Health check

cj_core_logic/
  ├── batch_preparation.py     # Batch metadata construction
  ├── callback_state_manager.py # Callback state tracking
  ├── single_essay_completion.py # Single essay finalization
  └── workflow_continuation.py  # Multi-essay workflow

implementations/
  ├── db_access_impl.py        # Repository implementation
  ├── content_client_impl.py   # Content Service client
  ├── llm_provider_service_client.py # LLM Provider client
  └── ...

Root files:
  ├── models_db.py             # SQLAlchemy models
  ├── protocols.py             # Service protocols
  ├── config.py                # Settings
  ├── di.py                    # Dishka providers
  ├── app.py                   # Quart app setup
  └── metrics.py               # Prometheus metrics

tests/ (spot-check for common issues)
```

---

## Phase 1: Import & Dependency Drift (~2 hours)

**Objective**: Ensure all imports are explicit, used, and source from shared modules (not reimplemented).

### Systematic Review

**Step 1: Scan for missing imports** (30 min)
- Check each file for imported symbols actually used
- Look for runtime import errors (e.g., `HuleEduError` not imported but used)
- Verify exception types imported before caught
- Check Protocol imports from `typing` or `collections.abc`

**Example Issues**:
```python
# BAD: Using without import
except HuleEduError:  # NameError at runtime

# GOOD: Explicit import
from huleedu_service_libs.error_handling import HuleEduError
except HuleEduError:
```

**Step 2: Find reimplemented utilities** (45 min)
- Search for helper functions duplicating common_core utilities
- Check for custom validators duplicating Pydantic patterns
- Look for manual JSON parsing (should use Pydantic)
- Find serialization logic that could use existing helpers

**Checklist**:
- [ ] Error handling: All using `raise_*` from `huleedu_service_libs.error_handling`?
- [ ] Logging: All using `create_service_logger` from `huleedu_service_libs.logging_utils`?
- [ ] Correlation: All using `CorrelationContext` from `huleedu_service_libs.error_handling.correlation`?
- [ ] API models: All importing from `common_core.api_models.*`?
- [ ] Grade scales: References using `common_core.grade_scales`?

**Step 3: Unused imports cleanup** (30 min)
- Find imports never referenced in file
- Remove or document why kept (e.g., re-exports)
- Check for wildcard imports (`from x import *`)

**Step 4: Import organization** (15 min)
- Standard library → third-party → internal (each group alphabetized)
- `from __future__ import annotations` at top if used
- Type-only imports in TYPE_CHECKING block if applicable

### Deliverable

Document: `.claude/tasks/results/phase1-import-audit.md`

Contents:
```markdown
## Files Reviewed: [count]

## Issues Found

### Missing Imports
- File: api/foo.py:45
  - Issue: HuleEduError used but not imported
  - Fix: Added import

### Reimplemented Utilities
- File: implementations/bar.py:100-120
  - Issue: Custom JSON validation (duplicates Pydantic)
  - Fix: Replaced with Pydantic model

### Unused Imports
- File: config.py:10
  - Issue: Import never used
  - Fix: Removed

## Metrics
- Files with issues: X
- Imports added: Y
- Imports removed: Z
- Utilities replaced: N
```

### Success Criteria

- [ ] All files scanned
- [ ] Missing imports added
- [ ] Reimplemented utilities replaced with shared code
- [ ] Unused imports removed
- [ ] Import organization consistent
- [ ] `pdm run typecheck-all` passes
- [ ] Results document created

---

## Phase 2: Type Safety & Model Boundaries (~2 hours)

**Objective**: Ensure Pydantic models for all boundaries, complete type hints, no magic strings.

### Systematic Review

**Step 1: Boundary object audit** (45 min)
- Review all API request/response objects
- Check all event models (Kafka payloads)
- Verify database models use SQLAlchemy (not Pydantic)
- Find dataclasses used for boundaries (should be Pydantic)

**Files to focus**: `api/*.py`, `common_core/api_models/*.py`, `common_core/events/*.py`

**Rule**:
- **Pydantic**: API boundaries, event payloads, configuration
- **Dataclass**: Internal utilities, scripts, non-boundary DTOs
- **SQLAlchemy**: Database models only

**Example Issues**:
```python
# BAD: Dataclass for API boundary
@dataclass
class StudentPromptRequest:
    assignment_id: str
    prompt_text: str

# GOOD: Pydantic for API boundary
class StudentPromptRequest(BaseModel):
    assignment_id: str = Field(min_length=1)
    prompt_text: str = Field(min_length=10)
```

**Step 2: Magic string elimination** (30 min)
- Search for hardcoded operation names in error handlers
- Find hardcoded resource types
- Look for service name strings (should use constant)
- Check for content types, statuses hardcoded

**Common locations**: Error handling, logging, metrics

**Example Fixes**:
```python
# BAD: Magic strings
raise_validation_error(
    service="cj_assessment_service",  # Magic string
    operation="do_thing",             # Magic string
    ...
)

# GOOD: Constants (if created)
raise_validation_error(
    service=SERVICE_NAME,           # From constants
    operation="do_thing",           # Could use enum
    ...
)
```

**Note**: Check if service name constant exists in service, otherwise document need for one.

**Step 3: Type hint completeness** (30 min)
- Check all function signatures have return types
- Verify all parameters have type hints
- Look for `Any` without justification
- Find Optional types not using `| None` (modern syntax)

**Files**: All `.py` files

**Step 4: Type narrowing review** (15 min)
- Find places where `| None` types used without narrowing
- Check for assertions after validation
- Verify comments explain invariants
- Look for remaining `# type: ignore` (should be minimal)

**Example**:
```python
# BAD: Type narrowing gap
def foo(x: str | None) -> str:
    return x.upper()  # MyPy error

# GOOD: Assertion for narrowing
def foo(x: str | None) -> str:
    assert x is not None, "x validated non-None"
    return x.upper()
```

### Deliverable

Document: `.claude/tasks/results/phase2-type-safety-audit.md`

Contents:
- Boundary violations (dataclasses → Pydantic conversions)
- Magic strings cataloged
- Type hint gaps filled
- Type narrowing assertions added

### Success Criteria

- [ ] All boundary objects use Pydantic
- [ ] Magic strings documented (with recommendation for constants if needed)
- [ ] Type hints complete
- [ ] Type narrowing assertions where needed
- [ ] `pdm run typecheck-all` passes with no new ignores
- [ ] Results document created

---

## Phase 3: Error Handling & Logging Alignment (~2 hours)

**Objective**: Standardize error handling and logging across all files using established patterns.

### Systematic Review

**Step 1: Error handling pattern audit** (60 min)
- Review all `raise` statements
- Check all try/except blocks
- Verify `raise_*` helpers used consistently
- Find custom error responses (should use helpers)

**Files**: All files with error handling (focus on `api/`, `cj_core_logic/`)

**Pattern to enforce**:
```python
# Standard pattern
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_validation_error,
    raise_processing_error,
    raise_resource_not_found,
)

try:
    # Operation
    ...
except HuleEduError:
    raise  # Re-raise HuleEdu errors
except Exception as exc:
    raise_processing_error(
        service="cj_assessment_service",
        operation="operation_name",
        message="Clear error message",
        correlation_id=corr.uuid,
        error=str(exc),
    )
```

**Common violations**:
- String comparison for exception types: `if exc.__class__.__name__ == "HuleEduError"`
- Manual error dict construction: `{"error": "message"}, 400`
- Catching `Exception` without re-raising HuleEduError
- Missing correlation_id in error calls

**Step 2: Logging pattern standardization** (45 min)
- Review all `logger.info/error/warning` calls
- Check for structured logging with `extra={}`
- Verify correlation_id included
- Ensure admin_user logged where applicable (admin endpoints)

**Pattern to enforce**:
```python
logger.info(
    "Clear action description",
    extra={
        "key_field": value,
        "correlation_id": str(corr.uuid),
        "admin_user": getattr(g, "admin_payload", {}).get("sub"),  # If admin endpoint
    },
)
```

**Common violations**:
- F-strings for structured data: `logger.info(f"User {user_id} did thing")`
- Missing correlation_id
- Missing admin_user in admin endpoints
- Inconsistent field names

**Step 3: Operation name consistency** (15 min)
- Collect all operation names from error handlers, logs, metrics
- Check for consistency across error/log/metric for same operation
- Document standard naming convention

**Example**:
```python
# In endpoint: upload_student_prompt
raise_validation_error(operation="upload_student_prompt")
logger.info("...", extra={"operation": "upload_student_prompt"})
_record_admin_metric("prompt_upload", "success")  # Different! Document standard.
```

### Deliverable

Document: `.claude/tasks/results/phase3-error-logging-audit.md`

Contents:
- Error handling violations fixed
- Logging patterns standardized
- Operation name convention documented
- Before/after examples

### Success Criteria

- [ ] All error handling uses `raise_*` helpers
- [ ] HuleEduError caught explicitly (not string comparison)
- [ ] All logs use structured `extra={}`
- [ ] Correlation_id in all logs/errors
- [ ] Admin_user in admin endpoint logs
- [ ] Operation names consistent (or convention documented)
- [ ] Results document created

---

## Phase 4: Code Duplication & Pattern Drift (~2.5 hours)

**Objective**: Eliminate duplicated logic, enforce DI patterns, consolidate repeated code.

### Systematic Review

**Step 1: Validation duplication** (45 min)
- Find repeated JSON validation code
- Check for duplicated Pydantic validation
- Look for inline checks that should be in models
- Identify repeated XOR/constraint logic

**Files**: All `api/*.py` endpoints

**Example**:
```python
# DUPLICATION across multiple endpoints
payload = await request.get_json()
if not isinstance(payload, dict):
    raise_validation_error(...)

try:
    req = ModelClass.model_validate(payload)
except ValidationError as exc:
    # Same handling repeated everywhere
    ...
```

**Fix**: Consider helper function if pattern repeated >3 times.

**Step 2: Session management review** (30 min)
- Check all `async with repository.session()` patterns
- Verify consistent error handling around sessions
- Look for session leaks (missing cleanup)
- Find repeated session patterns that could be helpers

**Files**: All files using repository

**Step 3: Response building patterns** (30 min)
- Find duplicated response construction
- Check if serialization helpers exist and are used
- Look for manual dict building that could use models
- Verify `.model_dump()` used consistently

**Example**:
```python
# DUPLICATION: Manual response building
return {
    "id": model.id,
    "assignment_id": model.assignment_id,
    "created_at": model.created_at.isoformat(),
}, 200

# BETTER: Use existing helper if available
response = _serialize_instruction(model)
return response.model_dump(), 200
```

**Step 4: DI pattern alignment** (45 min)
- Review all `@inject` decorator usage
- Check `FromDishka[...]` annotations
- Verify protocols used (not implementations)
- Find manual dependency construction (should use DI)

**Files**: All files using Dishka

**Pattern to verify**:
```python
@bp.post("/endpoint")
@inject
async def handler(
    repository: FromDishka[RepositoryProtocol],  # Protocol, not impl
    client: FromDishka[ClientProtocol],
    corr: FromDishka[CorrelationContext],
) -> tuple[dict[str, Any], int]:
    async with repository.session() as session:  # Standard pattern
        ...
```

### Deliverable

Document: `.claude/tasks/results/phase4-duplication-audit.md`

Contents:
- Duplication patterns identified
- Helper functions created (if warranted)
- DI violations fixed
- Refactoring summary

### Success Criteria

- [ ] Validation duplication documented (helpers created if >3 occurrences)
- [ ] Session patterns consistent
- [ ] Response building uses helpers
- [ ] DI patterns aligned
- [ ] `pdm run typecheck-all` passes
- [ ] Results document created

---

## Phase 5: Documentation & Configuration Drift (~1.5 hours)

**Objective**: Align docstrings with standards, eliminate hardcoded config, clean stale comments.

### Systematic Review

**Step 1: Docstring standardization** (45 min)
- Review all function/class docstrings
- Check against Rule 090: succinct, intent-focused
- Remove verbose parameter descriptions (rely on type hints)
- Ensure "why" explained, not "what"

**Files**: All `.py` files

**Rule 090 pattern**:
```python
# BAD: Verbose, restates signature
def upload_prompt(assignment_id: str, prompt_text: str) -> dict:
    """Upload a prompt.

    Args:
        assignment_id: The assignment identifier
        prompt_text: The prompt text to upload

    Returns:
        dict: Response with storage_id
    """

# GOOD: Succinct, intent-focused
def upload_prompt(assignment_id: str, prompt_text: str) -> dict:
    """Upload student prompt, store reference in instruction.

    Requires pre-existing instruction. Preserves grade_scale and instructions_text.
    """
```

**Step 2: Hardcoded configuration** (30 min)
- Find hardcoded URLs, timeouts, limits
- Check for magic numbers (should be constants)
- Verify Settings class used for configuration
- Look for environment variable access outside config

**Files**: All files, focus on `implementations/`, `api/`

**Example**:
```python
# BAD: Hardcoded config
timeout = 30  # Magic number
url = "http://localhost:8080"  # Hardcoded URL

# GOOD: Use Settings
timeout = settings.request_timeout
url = settings.content_service_url
```

**Step 3: Comment cleanup** (15 min)
- Remove TODO/FIXME comments (create issues if needed)
- Delete debug/print statements commented out
- Remove placeholder comments
- Keep only justifying comments (non-obvious decisions)

**Files**: All `.py` files

### Deliverable

Document: `.claude/tasks/results/phase5-documentation-audit.md`

Contents:
- Docstrings updated (count)
- Hardcoded config moved to Settings (list)
- Comments cleaned
- Summary of documentation improvements

### Success Criteria

- [ ] All docstrings follow Rule 090
- [ ] Hardcoded config moved to Settings
- [ ] Stale comments removed
- [ ] Only justifying comments remain
- [ ] Results document created

---

## Final Validation

After completing all 5 phases:

1. **Run full typecheck**: `pdm run typecheck-all`
2. **Run service tests**: `pdm run pytest-root services/cj_assessment_service/tests/unit/ -v`
3. **Review all phase results**: Consolidate findings
4. **Create summary report**: See format below

### Summary Report Format

File: `.claude/tasks/results/CJ-ASSESSMENT-HARDENING-SUMMARY.md`

```markdown
# CJ Assessment Service Code Hardening Summary

## Execution Date
[Date]

## Phases Completed
- [x] Phase 1: Import & Dependency Drift
- [x] Phase 2: Type Safety & Model Boundaries
- [x] Phase 3: Error Handling & Logging Alignment
- [x] Phase 4: Code Duplication & Pattern Drift
- [x] Phase 5: Documentation & Configuration Drift

## Metrics
- Files reviewed: X
- Issues found: Y
- Fixes applied: Z
- Lines changed: N

## Key Findings

### Critical Issues
[List any critical issues found and fixed]

### Pattern Improvements
[Patterns established or reinforced]

### Recommendations
[Suggestions for preventing future drift]

## Validation
- Typecheck: PASS/FAIL
- Unit tests: X passed, Y failed
- Integration impact: [Notes on changes affecting integration]

## Files Modified
[List of files with significant changes]
```

---

## Success Criteria (Overall)

- [ ] All 5 phases completed with results documents
- [ ] Typecheck passes with no new errors
- [ ] Unit tests pass (or failures documented with plan)
- [ ] Summary report created
- [ ] Code aligned with established patterns
- [ ] No new abstractions introduced
- [ ] Drift patterns eliminated

---

## Key References

**Rules** (read before starting):
- `.claude/rules/020-architectural-mandates.md` - Error handling, service boundaries, architectural principles
- `.claude/rules/042-async-patterns-and-di.md` - DI patterns, async session management
- `.claude/rules/090-documentation-standards.md` - Docstring standards (succinct, intent-focused)

**Pattern Examples** (reference throughout):
- `services/cj_assessment_service/api/admin_routes.py` - Admin endpoint patterns
- `services/cj_assessment_service/implementations/db_access_impl.py` - Repository patterns
- `libs/common_core/src/common_core/api_models/` - Pydantic model patterns
- `huleedu_service_libs/error_handling/` - Error handling utilities

**Project Standards**:
- Pydantic for all boundaries (API, events)
- Strict typing (no `Any` without justification)
- Structured logging with `extra={}`
- DI via Dishka with protocols
- Error handling via `raise_*` helpers

---

## Execution Notes

- Work methodically: one phase at a time
- Document findings immediately
- Fix issues as discovered (don't batch)
- Run typecheck after each phase
- Prioritize alignment over innovation
- When in doubt, follow existing patterns
- Ask for clarification before creating new patterns
