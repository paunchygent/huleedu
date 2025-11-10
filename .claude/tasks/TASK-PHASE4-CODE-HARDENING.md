# Task: Phase 4 Student Prompt API Code Hardening

## Objective

Methodically audit and harden the Phase 4 student prompt admin API implementation against common prototyping issues: missing imports, magic strings, pattern misalignment, unnecessary abstractions, and deviation from established service conventions.

**Principle**: Enforce alignment with existing patterns. Use what's already in service code, common_core, and service_libs. Do not invent new abstractions.

**Approach**: Slow, meticulous, phase-by-phase review. Each phase is a unit of work with clear completion criteria.

---

## Context

**Files Modified in Phase 4**:
- `libs/common_core/src/common_core/api_models/assessment_instructions.py:72-91` - Added Pydantic models
- `services/cj_assessment_service/api/admin_routes.py:7-24,343-576` - Added two admin endpoints
- `services/cj_assessment_service/config.py:115-117` - Type narrowing fix
- `services/language_tool_service/di.py:7` - Missing import fix

**Implementation Summary**:
- POST `/admin/v1/student-prompts` - Upload prompt, upsert instruction
- GET `/admin/v1/student-prompts/assignment/<id>` - Fetch prompt with context
- StudentPromptUploadRequest/Response models
- Type safety fixes (HuleEduError import, type narrowing assertions)

---

## Phase 1: Import & Dependency Audit

**Time**: ~30 minutes
**Objective**: Verify all imports are explicit, used, and sourced from existing shared modules.

### Actions

1. **Review admin_routes.py imports (lines 7-24)**:
   - Check every imported symbol is actually used in the file
   - Verify no missing imports that would cause runtime errors
   - Confirm HuleEduError imported (recently added fix)
   - Ensure ContentClientProtocol imported from protocols

2. **Check for reimplemented utilities**:
   - Search for any helper functions that duplicate existing utilities in:
     - `huleedu_service_libs.error_handling.*`
     - `huleedu_service_libs.logging_utils`
     - `common_core.api_models.*`
   - Verify validation logic doesn't duplicate Pydantic validators
   - Check serialization uses existing `_serialize_instruction()` helper

3. **Verify common_core usage**:
   - Confirm models imported from `common_core.api_models.assessment_instructions`
   - Check if any grade_scale references use `common_core.grade_scales`
   - Validate no hardcoded error enums (should use `common_core.error_enums` if applicable)

4. **Cross-service consistency**:
   - Compare import patterns with other admin endpoints (lines 114-340)
   - Ensure correlation context imported correctly
   - Verify metrics imports match existing patterns

### Success Criteria
- [ ] All imports documented as necessary or removed
- [ ] No reimplemented utilities found
- [ ] No missing imports that could cause runtime failures
- [ ] Import style matches existing admin endpoints

### References
- Existing imports pattern: `services/cj_assessment_service/api/admin_routes.py:1-40`
- Error handling imports: `.claude/rules/020-architectural-mandates.mdc:130-160`

---

## Phase 2: Pattern Alignment Audit

**Time**: ~45 minutes
**Objective**: Ensure new endpoints match established architectural patterns exactly.

### Actions

1. **Endpoint structure comparison** (lines 343-576):
   - Compare POST endpoint structure with existing `upsert_assessment_instruction` (lines 114-204)
   - Compare GET endpoint structure with existing `get_assignment_instruction` (lines 248-282)
   - Verify `@bp.post`, `@inject` decorator order matches
   - Check function signature pattern (repository, content_client, corr from Dishka)
   - Validate docstring placement and format

2. **Error handling pattern audit**:
   - Verify all error paths use `raise_*` functions from `huleedu_service_libs.error_handling`
   - Check for consistent error operation names ("upload_student_prompt", "get_student_prompt")
   - Validate HuleEduError caught explicitly with `except HuleEduError:` (not string comparison)
   - Ensure correlation_id passed to all error handlers
   - Check metrics recorded on both success and failure paths

3. **Logging pattern verification**:
   - Verify logger.info calls use `extra={}` dict consistently
   - Check all logs include: operation context, correlation_id, admin_user
   - Validate no log messages use f-strings for structured data (should be in extra)
   - Ensure log levels appropriate (info for success, error for failures)
   - Compare with existing patterns: lines 195-202, 265-272

4. **Metrics recording audit**:
   - Verify `_record_admin_metric()` called with operation name, status
   - Check operation names consistent: "prompt_upload", "prompt_get"
   - Ensure metrics on failure paths (not just success)
   - Validate no duplicate metric calls
   - Compare with existing: lines 144, 203, 244, 276

5. **DI injection pattern check**:
   - Confirm `FromDishka[...]` annotations correct
   - Verify protocols used (not implementations)
   - Check `@inject` decorator from `quart_dishka`
   - Validate async session handling via `repository.session()`

### Success Criteria
- [ ] Endpoint structure matches existing admin endpoints
- [ ] Error handling follows huleedu_service_libs patterns exactly
- [ ] Logging includes all required context fields
- [ ] Metrics recorded consistently on all paths
- [ ] DI follows Dishka patterns with protocols

### References
- Error handling patterns: `.claude/rules/020-architectural-mandates.mdc:130-190`
- DI patterns: `.claude/rules/042-async-patterns-and-di.mdc:40-100`
- Existing endpoint examples: `services/cj_assessment_service/api/admin_routes.py:114-340`

---

## Phase 3: Type Safety & Model Usage

**Time**: ~30 minutes
**Objective**: Verify Pydantic models used correctly, type hints complete, no magic strings.

### Actions

1. **Pydantic model audit** (assessment_instructions.py:72-91):
   - Verify `StudentPromptUploadRequest` uses Pydantic BaseModel (not dataclass)
   - Check `StudentPromptResponse` uses Pydantic BaseModel (not dataclass)
   - Validate Field() used for all constraints (min_length, descriptions)
   - Ensure ConfigDict includes `str_strip_whitespace` where appropriate
   - Compare with existing models in same file (lines 18-61)

2. **Type hint completeness**:
   - Check all function parameters have type hints
   - Verify return types specified: `tuple[dict[str, Any], int]`
   - Validate no `Any` types without justification
   - Ensure Optional/Union types explicit (not implicit None)

3. **Type narrowing patterns** (lines 451-459, 548-556):
   - Review assert statements for type narrowing
   - Verify assertions come after validation logic
   - Check comments explain invariants ("guaranteed non-None by validation above")
   - Ensure no `# type: ignore` comments remain
   - Compare with config.py fix (lines 115-117)

4. **Magic string elimination**:
   - Search for hardcoded strings that should be constants:
     - Operation names: "upload_student_prompt", "get_student_prompt"
     - Resource types: "AssessmentInstruction", "StudentPrompt"
     - Service name: "cj_assessment_service"
     - Content type: "text/plain"
   - Check if operation/resource names should use enums from common_core
   - Verify no hardcoded URLs or paths

5. **Content Service interaction types**:
   - Review `store_content()` call: content parameter type
   - Check `fetch_content()` call: storage_id, correlation_id types
   - Verify storage_response dict access patterns
   - Ensure correlation_id passed as UUID (corr.uuid)

### Success Criteria
- [ ] All boundary objects use Pydantic models
- [ ] Type hints complete on all functions
- [ ] Type narrowing assertions documented
- [ ] No unexplained magic strings found
- [ ] Content Service calls use correct types

### References
- Pydantic patterns: `.claude/rules/020-architectural-mandates.mdc:60-90`
- Type safety standards: Project uses strict mypy, all Pydantic models for boundaries
- Existing models: `libs/common_core/src/common_core/api_models/assessment_instructions.py:18-61`

---

## Phase 4: Code Duplication & Reuse

**Time**: ~30 minutes
**Objective**: Identify duplicated logic, verify shared utilities used, eliminate unnecessary code.

### Actions

1. **Validation logic review**:
   - Check POST endpoint validation (lines 358-381)
   - Compare with existing validation in `upsert_assessment_instruction` (lines 128-150)
   - Verify pattern: JSON check → Pydantic validation → error handling
   - Look for any custom validation that duplicates Pydantic validators
   - Ensure no inline validation that should be in model validators

2. **Response building patterns**:
   - Review StudentPromptResponse construction (lines 461-468, 558-565)
   - Check if response building can use `_serialize_instruction()` helper
   - Verify no manual dict construction where models exist
   - Compare with existing response patterns (lines 190-204, 238-245)

3. **Error handling duplication**:
   - Look for repeated try/except patterns
   - Check if error context building is duplicated
   - Verify all raise_* calls use consistent parameters
   - Look for any error handling that should be centralized

4. **Session management patterns**:
   - Review `async with repository.session()` usage (lines 383, 488)
   - Check consistency with existing session handling
   - Verify no session leaks or missing cleanup
   - Compare with patterns in lines 153-203, 220-276

5. **Settings and configuration**:
   - Check if any hardcoded values should use Settings
   - Verify Content Service URL comes from settings (via ContentClient)
   - Look for any timeouts, limits, or thresholds that should be configurable
   - Compare with existing settings usage

6. **Content Service client usage**:
   - Review if content_client calls follow existing patterns
   - Check if any Content Service logic duplicated from anchor_management.py
   - Verify storage_id extraction pattern (storage_response.get("content_id"))
   - Ensure error handling around Content Service consistent

### Success Criteria
- [ ] No validation logic duplicates Pydantic validators
- [ ] Response building uses existing helpers where possible
- [ ] No duplicated error handling patterns
- [ ] Session management consistent with existing code
- [ ] No hardcoded configuration values

### References
- Existing helpers: `services/cj_assessment_service/api/admin_routes.py:91-112`
- Content Service patterns: `services/cj_assessment_service/api/anchor_management.py:60-140`
- Session patterns: `.claude/rules/042-async-patterns-and-di.mdc:120-150`

---

## Phase 5: Documentation & Comment Quality

**Time**: ~15 minutes
**Objective**: Ensure documentation follows standards, comments justify non-obvious decisions.

### Actions

1. **Docstring audit** (lines 350-356, 480-486):
   - Verify docstrings follow Rule 090: succinct, intent-focused
   - Check no verbose parameter/return documentation (rely on type hints)
   - Ensure docstrings explain "why" not "what"
   - Compare with existing docstrings (lines 120-126, 213-214)
   - Remove any placeholder or TODO comments

2. **Inline comment review**:
   - Check comments justify non-obvious decisions
   - Verify type narrowing comments explain invariants (lines 451, 548)
   - Look for redundant comments that restate code
   - Ensure no debug or temporary comments remain
   - Validate comment grammar and clarity

3. **API model documentation** (assessment_instructions.py:72-91):
   - Review model docstrings match existing style (lines 18-20)
   - Check Field descriptions add value beyond field names
   - Verify no verbose explanations in model docstrings
   - Ensure consistency with existing models in file

4. **Module-level documentation**:
   - Check file-level docstring in admin_routes.py (line 1)
   - Verify no stale references in module docs
   - Ensure imports section clear and organized

### Success Criteria
- [ ] All docstrings follow Rule 090 standards
- [ ] Comments justify non-obvious decisions only
- [ ] No placeholder or debug comments
- [ ] Model documentation consistent with existing
- [ ] Module-level docs accurate

### References
- Documentation standards: `.claude/rules/090-documentation-standards.mdc`
- Existing docstring examples: `services/cj_assessment_service/api/admin_routes.py:120-126, 213-214`

---

## Final Validation

After completing all phases, perform final checks:

1. **Run typecheck**: `pdm run typecheck-all` (must pass with no new errors)
2. **Review HANDOFF.md**: Verify Phase 4 documentation accurate
3. **Cross-reference patterns**: Spot-check 3-5 patterns against existing endpoints
4. **Read code fresh**: Review with fresh eyes for obvious issues

### Deliverable

Create summary document: `.claude/tasks/TASK-PHASE4-CODE-HARDENING-RESULTS.md`

Include:
- Issues found per phase (if any)
- Fixes applied with before/after snippets
- Patterns verified as correct
- Recommendations for future phases
- Typecheck results

---

## Success Criteria (Overall)

- [ ] All 5 phases completed
- [ ] Findings documented with evidence
- [ ] Any issues fixed and verified
- [ ] Typecheck passes (no new errors)
- [ ] Code aligns with existing service patterns
- [ ] No new abstractions introduced
- [ ] Results document created

---

## Key References

**Rules**:
- `.claude/rules/020-architectural-mandates.mdc` - Error handling, service boundaries
- `.claude/rules/042-async-patterns-and-di.mdc` - DI and async patterns
- `.claude/rules/090-documentation-standards.mdc` - Documentation standards

**Existing Patterns**:
- `services/cj_assessment_service/api/admin_routes.py:114-340` - Existing admin endpoints
- `services/cj_assessment_service/api/anchor_management.py:60-140` - Content Service usage
- `libs/common_core/src/common_core/api_models/assessment_instructions.py:18-61` - Model patterns

**Context**:
- `.claude/HANDOFF.md:40-64` - Phase 4 implementation summary

---

## Execution Notes

- Work methodically through each phase
- Document findings as you go
- Fix issues immediately when found
- Re-run typecheck after each fix
- Prioritize alignment over speed
- Don't skip phases even if no issues found (document verification)
