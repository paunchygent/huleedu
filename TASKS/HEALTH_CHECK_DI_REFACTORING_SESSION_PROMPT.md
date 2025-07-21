---
id: ARCH-001-SESSION
title: "Health Check DI Refactoring - Session Continuation Prompt"
author: "Claude Code Assistant"
status: "Ready for Next Session"
created_date: "2025-07-21"
updated_date: "2025-07-21"
---

# Session Prompt: Health Check Dependency Injection Refactoring

## Context Summary

### Previous Session Accomplishments

In the previous session, we successfully:

1. **Fixed all test failures** across multiple services (SpellChecker, Essay Lifecycle, WebSocket)
2. **Identified architectural inconsistency**: 4 services still use singleton/hardcoded values in health endpoints instead of dependency injection
3. **Created comprehensive refactoring task**: `TASKS/HEALTH_CHECK_DI_REFACTORING.md` with 5 implementation phases
4. **Validated compatibility**: Confirmed that `DatabaseHealthChecker` and `HuleEduApp` utilities are fully compatible with DI patterns

### Current State

- **6 services already use DI** for settings in health endpoints (good pattern)
- **4 services need refactoring**: Content Service, Spellchecker Service, CJ Assessment Service, API Gateway Service
- **WebSocket Service**: Already fixed in previous session as a test case

## Session Instructions

### ULTRATHINK Methodology

Use ULTRATHINK approach for all analysis and implementation:

1. **Analyze** existing patterns thoroughly before making changes
2. **Validate** assumptions by reading actual code
3. **Follow** established patterns in the codebase
4. **Test** all changes with appropriate test coverage

### Required Reading

Start by reading these foundational rules using the rule index:

```
.cursor/rules/000-rule-index.mdc  # Navigate to all rules
.cursor/rules/010-foundational-principles.mdc
.cursor/rules/020-architectural-mandates.mdc
.cursor/rules/041-http-service-blueprint.mdc  # Quart service patterns
.cursor/rules/042-async-patterns-and-di.mdc  # DI patterns
.cursor/rules/070-testing-and-quality-assurance.mdc
.cursor/rules/080-repository-workflow-and-tooling.mdc
```

### Key Files to Review

1. **Task Document**: `TASKS/HEALTH_CHECK_DI_REFACTORING.md` - Contains detailed implementation plan
2. **Example of Correct Pattern**:
   - `services/essay_lifecycle_service/api/health_routes.py` - Uses DI correctly
   - `services/batch_orchestrator_service/api/health_routes.py` - Uses DI correctly
3. **Services Needing Updates**:
   - `services/content_service/api/health_routes.py` - Uses singleton import
   - `services/spellchecker_service/api/health_routes.py` - Hardcodes values
   - `services/cj_assessment_service/api/health_routes.py` - Hardcodes values
   - `services/api_gateway_service/routers/health_routes.py` - Hardcodes values

### Subagent Tasks

#### ULTRATHINK Task 1: Verify Current State

Launch a subagent to:

1. Check if any changes have been made to the 4 services' health routes since task creation
2. Verify that all DI providers have Settings available
3. Confirm Docker environment is ready for rebuilds
4. Check for any new architectural rules about health endpoints

#### ULTRATHINK Task 2: Phase 1 - Content Service Implementation

Launch a subagent to implement Phase 1 from the task document:

1. Add Settings provider to `services/content_service/di.py`
2. Update `services/content_service/api/health_routes.py` to use DI
3. Create `services/content_service/tests/test_health_routes.py`
4. Run: `docker compose build --no-cache content_service && docker compose up -d content_service`
5. Execute: `pdm run -p services/content_service test`

#### ULTRATHINK Task 3: Phase 2 - Spellchecker Service Implementation  

Launch a subagent to implement Phase 2:

1. Update `services/spellchecker_service/api/health_routes.py` to use injected Settings
2. Create `services/spellchecker_service/tests/test_health_routes.py`
3. Ensure VERSION and ENVIRONMENT are available in Settings
4. Run: `docker compose build --no-cache spellchecker_service && docker compose up -d spellchecker_service`
5. Execute: `pdm run -p services/spellchecker_service test`

#### ULTRATHINK Task 4: Phase 3 - CJ Assessment Service Implementation

Launch a subagent to implement Phase 3:

1. Update `services/cj_assessment_service/api/health_routes.py` to use injected Settings
2. Verify existing tests in `services/cj_assessment_service/tests/test_health_api.py` still pass
3. Run: `docker compose build --no-cache cj_assessment_service && docker compose up -d cj_assessment_service`
4. Execute: `pdm run -p services/cj_assessment_service test`

#### ULTRATHINK Task 5: Phase 4 - API Gateway Service Implementation

Launch a subagent to implement Phase 4:

1. Update `services/api_gateway_service/routers/health_routes.py` to use injected Settings
2. Verify existing tests in `services/api_gateway_service/tests/test_health_routes.py` still pass
3. Run: `docker compose build --no-cache api_gateway_service && docker compose up -d api_gateway_service`
4. Execute: `pdm run -p services/api_gateway_service test`

#### ULTRATHINK Task 6: Phase 5 - Integration Verification

Launch a subagent to:

1. Rebuild all 4 services together
2. Test all health endpoints return correct service names
3. Verify no environment variable conflicts
4. Update task document with completion status

### Important Patterns to Follow

#### Correct DI Pattern for Health Routes

```python
# Imports
from dishka import FromDishka
from quart_dishka import inject  # or dishka.integrations.fastapi for FastAPI
from services.{service_name}.config import Settings  # NOT singleton

# Health endpoint
@health_bp.route("/healthz")  # or @router.get for FastAPI
@inject
async def health_check(settings: FromDishka[Settings]) -> Response:
    """Health check using dependency injection."""
    # Use settings.SERVICE_NAME, settings.ENVIRONMENT, etc.
```

#### Testing Pattern

```python
# Override settings in test fixtures
provider = ServiceProvider()
provider.provide_settings = lambda: test_settings_instance
```

### Architecture Considerations

1. **DatabaseHealthChecker** accepts service name as parameter - works with any source
2. **HuleEduApp** provides `database_engine` via `current_app` - no conflict with DI
3. **Quart services** use `@inject` from `quart_dishka`
4. **FastAPI services** use `@inject` from `dishka.integrations.fastapi`

### Success Metrics

- [ ] All 4 services use DI for Settings in health endpoints
- [ ] No singleton imports in health route files  
- [ ] All tests pass (including new health tests)
- [ ] Docker rebuilds succeed
- [ ] Integration test shows correct service names
- [ ] Task document updated with completion status

### Common Pitfalls to Avoid

1. **Don't** import settings singleton (`from config import settings`)
2. **Don't** forget to add `@inject` decorator
3. **Don't** miss adding Settings to DI provider if not present
4. **Do** create health tests even if they don't exist
5. **Do** verify existing tests still pass after changes

### Session Start Commands

```bash
# Verify environment
cd /Users/olofs_mba/Documents/Repos/huledu-reboot
docker compose ps
pdm run lint-all

# Review current state
cat TASKS/HEALTH_CHECK_DI_REFACTORING.md
```

Begin by reading the rule index and understanding the current state, then proceed with the ULTRATHINK tasks in order.
