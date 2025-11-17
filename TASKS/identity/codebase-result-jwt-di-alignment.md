---
id: "codebase-result-jwt-di-alignment"
title: "Codebase Alignment: Result Monad, JWT Helpers, Content Client DI"
type: "task"
status: "research"
priority: "medium"
domain: "identity"
service: ""
owner_team: "agents"
owner: ""
program: ""
created: "2025-11-16"
last_updated: "2025-11-17"
related: []
labels: []
---
# Codebase Alignment: Result Monad, JWT Helpers, Content Client DI

## Objective

Realign shared patterns by consolidating the Result monad, centralizing JWT test helpers, and restoring Dishka-based injection for the CJ content client. Execute in three phases; run the validation commands at the end of each phase before moving on.

---

## Phase 1 – Result[T, E] Consolidation & Documentation ✅ COMPLETE

**Status**: Completed 2025-11-12

**Goal:** One canonical `Result[T, E]` helper in `huleedu_service_libs`; remove bespoke versions; document official usage.

**Scope Revision**: Research revealed only CJ Assessment Service used the Result monad. Result Aggregator and Spellchecker services have domain classes with similar names but no Result monad implementations.

### Implementation Summary

1. **Shared helper created** ✅
   - Created `libs/huleedu_service_libs/src/huleedu_service_libs/utils/result.py` with complete Result[T, E] implementation
   - Exported via `utils/__init__.py` and `huleedu_service_libs/__init__.py`
   - Added 15 comprehensive unit tests in `tests/utils/test_result.py` (all passing)
   - Tests cover: success/error paths, type safety, frozen dataclass, edge cases (empty strings, None values)

2. **CJ Assessment Service migrated** ✅
   - Deleted Result class from `models_api.py` (lines 154-196)
   - Updated `event_processor.py:43` to `from huleedu_service_libs import Result`
   - Cleaned up unused Generic/TypeVar imports
   - Kept `PromptHydrationFailure` (domain-specific error type)

3. **Documentation** ✅
   - No changes required - all documentation already referenced target path:
     - `.claude/rules/048-structured-error-handling-standards.mdc` already shows `from huleedu_service_libs import Result`
     - `.claude/rules/060-data-and-metadata-management.mdc` already documents typed metadata overlay pattern
     - `.claude/rules/000-rule-index.mdc` already indexes Result monad correctly

4. **Validation** ✅
   ```bash
   pdm run typecheck-all                                    # PASS (pre-existing errors unrelated to Result)
   pdm run pytest-root libs/huleedu_service_libs/tests/utils/test_result.py -v  # 15/15 PASS
   pdm run pytest-root services/cj_assessment_service/tests -q                   # 519 PASS
   rg "^class Result" services/ --type py                   # 0 matches
   rg "from huleedu_service_libs import.*Result" services/cj_assessment_service  # 1 match (event_processor.py)
   ```

**Files Created**:
- `libs/huleedu_service_libs/src/huleedu_service_libs/utils/result.py`
- `libs/huleedu_service_libs/src/huleedu_service_libs/utils/__init__.py`
- `libs/huleedu_service_libs/tests/utils/__init__.py`
- `libs/huleedu_service_libs/tests/utils/test_result.py`

**Files Modified**:
- `libs/huleedu_service_libs/src/huleedu_service_libs/__init__.py` (added Result export)
- `services/cj_assessment_service/event_processor.py` (updated import)
- `services/cj_assessment_service/models_api.py` (removed Result class, cleaned imports)

---

## Phase 2 – JWT Test Helpers Centralization ✅ COMPLETE

**Status**: Completed 2025-11-12

**Goal:** Shared JWT token builders for tests; remove duplicated helpers; document authentication testing patterns.

### Implementation Summary

1. **Shared helper module** ✅
   - Created `libs/huleedu_service_libs/src/huleedu_service_libs/testing/jwt_helpers.py` with:
     - `build_jwt_headers(settings, subject, *, roles, extra_claims, expires_in, omit_claims)` - Returns complete HTTP headers dict for integration tests
     - `create_jwt(secret, payload, *, algorithm)` - Returns raw JWT token string for validator testing
   - Added 21 comprehensive unit tests in `libs/huleedu_service_libs/tests/test_jwt_helpers.py` (all passing)
   - Tests cover: standard tokens, expired tokens, missing claims, custom claims, roles, org_id extraction

2. **Service migrations** ✅
   - **CJ Assessment Service** (12 tests migrated):
     - Fixed missing imports from previous migration (uuid4, datetime)
     - Updated `test_admin_prompt_endpoints.py` and `test_admin_routes.py`
     - Tests use `build_jwt_headers()` with admin roles and email claims

   - **API Gateway Service** (23 tests migrated):
     - Removed 4 local helper methods (~40 lines) from `test_auth.py`
     - Eliminated cross-file import dependency in `test_auth_org.py`
     - Migrated all tests to use `build_jwt_headers()` and `create_jwt()`
     - Added type safety assertions for `SecretStr.get_secret_value()` calls

   - **WebSocket Service** (8 tests migrated):
     - Added settings fixture to `TestJWTValidator` class
     - Migrated validator tests to use `create_jwt()` with settings-based configuration
     - Replaced hardcoded secrets with settings object

3. **Documentation** ✅
   - Added section 6.3 "JWT Authentication Testing" to `.claude/rules/075-test-creation-methodology.mdc`
   - Documented `build_jwt_headers()` patterns for HTTP integration tests
   - Documented `create_jwt()` patterns for raw token validation
   - Provided examples for: admin tokens, expired tokens, missing claims, custom claims
   - Referenced `AuthTestManager` for functional/integration tests

4. **Validation** ✅
   ```bash
   pdm run typecheck-all                        # PASS (Success: no issues found in 1236 source files)
   pdm run pytest-root libs/huleedu_service_libs/tests/test_jwt_helpers.py -v  # 21/21 PASS
   pdm run pytest-root services/cj_assessment_service/tests/unit/test_admin_*.py -q  # 12/12 PASS
   pdm run pytest-root services/api_gateway_service/tests/test_auth*.py -q           # 23/23 PASS
   pdm run pytest-root services/websocket_service/tests/test_implementations.py::TestJWTValidator -q  # 8/8 PASS
   ```

**Code Reduction**: Removed ~150 lines of duplicated JWT test helper code across services

**Files Created**:
- `libs/huleedu_service_libs/src/huleedu_service_libs/testing/__init__.py`
- `libs/huleedu_service_libs/src/huleedu_service_libs/testing/jwt_helpers.py`
- `libs/huleedu_service_libs/tests/test_jwt_helpers.py`

**Files Modified**:
- `services/cj_assessment_service/tests/unit/test_admin_prompt_endpoints.py` (added missing imports)
- `services/cj_assessment_service/tests/unit/test_admin_routes.py` (added missing imports)
- `services/api_gateway_service/tests/test_auth.py` (migrated 15 tests, removed 4 local helpers)
- `services/api_gateway_service/tests/test_auth_org.py` (migrated 8 tests, removed cross-file import)
- `services/websocket_service/tests/test_implementations.py` (migrated 8 tests, added settings fixture)
- `.claude/rules/075-test-creation-methodology.mdc` (added JWT authentication testing patterns)

---

## Phase 3 – CJ Content Client DI Re-alignment

**Goal:** Remove manual `content_client` threading; use Dishka injection with a test-friendly `_impl` helper; document the pattern.

1. **Introduce `_impl` helper**
   - In `services/cj_assessment_service/cj_core_logic/batch_preparation.py`, move the existing logic into `_create_cj_batch_impl(..., content_client: ContentClientProtocol, ...)`.
   - Keep `create_cj_batch` as a Dishka-injected wrapper (`FromDishka[ContentClientProtocol]`) that calls `_impl`.

2. **Update DI provider**
   - Ensure `services/cj_assessment_service/di.py` registers `ContentClientProtocol` (app scope) so Dishka can inject it.

3. **Adjust tests**
   - Unit tests call `_create_cj_batch_impl` directly with their mock content client fixture.
   - Integration tests that rely on Dishka continue to call `create_cj_batch` (override the provider if they need a mock client).

4. **Documentation**
   - Update `.claude/rules/042-async-patterns-and-di.mdc` with a short “pure implementation + wrapper” testing pattern.

5. **Validation**
   ```bash
   pdm run typecheck-all
   pdm run pytest-root services/cj_assessment_service/tests/unit -q
   pdm run pytest-root services/cj_assessment_service/tests/integration -q
   rg "_create_cj_batch_impl" services/cj_assessment_service --type py  # ensure tests use the helper
   ```

---

## Documentation Cleanup (Post-Phases)

After code changes land:

1. Compress `.claude/HANDOFF.md` to include only active work.
2. Update `.claude/README_FIRST.md` sections 10 and 15 with brief “Completed” summaries referencing the consolidated patterns.
3. Mark `TASKS/CJ_PROMPT_CONTEXT_PERSISTENCE_PLAN.md` as completed with a status banner.

Commit message suggestion: `docs: compress handoff and mark CJ prompt plan complete`.

---

## Rollback Notes

- Revert each phase independently with `git revert <commit>` if required.
- Phase 1 rollback restores local Result implementations; services continue working but lose consistency.
- Phase 2 rollback reintroduces duplicated JWT helpers; no production impact.
- Phase 3 rollback reinstates manual `content_client` threading; tests still pass but DI inconsistency returns.

