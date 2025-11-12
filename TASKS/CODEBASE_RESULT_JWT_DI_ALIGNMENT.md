# Codebase Alignment: Result Monad, JWT Helpers, Content Client DI

## Objective

Realign shared patterns by consolidating the Result monad, centralizing JWT test helpers, and restoring Dishka-based injection for the CJ content client. Execute in three phases; run the validation commands at the end of each phase before moving on.

---

## Phase 1 – Result[T, E] Consolidation & Documentation

**Goal:** One canonical `Result[T, E]` helper in `huleedu_service_libs`; remove bespoke versions; document official usage.

1. **Add shared helper**
   - Create `libs/huleedu_service_libs/src/huleedu_service_libs/utils/result.py` with the minimal Result implementation (`ok`, `err`, `is_ok`, `is_err`, `value`, `error`).
   - Export the helper via `utils/__init__.py` and `huleedu_service_libs/__init__.py`.
   - Add a small unit test (e.g., `tests/utils/test_result.py`) to cover success and error paths.

2. **Replace local copies**
   - CJ Assessment: delete the inline Result dataclass from `models_api.py`; import the shared helper in modules/tests that currently reference the local version.
   - Result Aggregator: search `rg "^class Result" services/result_aggregator_service` and swap any local definitions for the shared helper.
   - Spellchecker: update `protocols.py` (and related tests) to import the shared helper.

3. **Documentation**
   - Update `.claude/rules/048-structured-error-handling-standards.mdc` with a “Result monad” section describing when to use Result versus raising `HuleEduError` exceptions.
   - Update `.claude/rules/060-data-and-metadata-management.mdc` with the typed metadata overlay pattern used in CJ.
   - Update `.claude/rules/000-rule-index.mdc` to reference the new sections.

4. **Validation**
   ```bash
   pdm run typecheck-all
   pdm run pytest-root services/cj_assessment_service/tests -q
   pdm run pytest-root services/result_aggregator_service/tests -q
   pdm run pytest-root services/spellchecker_service/tests -q
   rg "^class Result" services/ --type py  # should return no matches
   ```

---

## Phase 2 – JWT Test Helpers Centralization

**Goal:** Shared JWT token builders for tests; remove duplicated helpers; document authentication testing patterns.

1. **Create helper module**
   - Add `libs/huleedu_service_libs/tests/jwt_helpers.py` with:
     - `create_hs_token(secret, payload, *, algorithm="HS256")`
     - `create_rs_token(private_key, payload, *, algorithm="RS256")`
     - `create_default_test_token(user_id, *, roles=None, org_id=None, ...)`
   - Provide reusable fixtures (e.g., `jwt_test_secret`) in `libs/huleedu_service_libs/tests/conftest.py`.

2. **Refactor tests**
   - API Gateway: remove local token builders in `tests/test_auth*.py`; import the shared helper instead.
   - Run `rg "jwt\.encode" services/*/tests` to find other suites and switch them to the shared helper unless there is a service-specific reason not to.

3. **Documentation**
   - Add an “Authentication Testing Patterns” section to `.claude/rules/075-test-creation-methodology.mdc` referencing the new helper module and common usage.

4. **Validation**
   ```bash
   pdm run typecheck-all
   pdm run pytest-root services/api_gateway_service/tests -q
   pdm run pytest-root services/cj_assessment_service/tests -q
   rg "from huleedu_service_libs.tests.jwt_helpers import" services/*/tests --type py
   rg "jwt\.encode" services/*/tests --type py  # remaining hits should be reviewed manually
   ```

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

