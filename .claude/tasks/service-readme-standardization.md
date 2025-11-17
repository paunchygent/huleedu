# Task: Service README Standardization - Session 2

**Status**: 🔄 IN PROGRESS
**Date Started**: 2025-11-11
**Session**: Documentation Session 2

## Objective

Standardize all service READMEs following common_core documentation patterns, ensuring consistency in error handling, testing, migrations, and CLI tool documentation.

## Scope

- **Total services**: 18
- **Services to standardize**: 13
- **Services excluded** (already excellent): 5
  - batch_conductor_service
  - batch_orchestrator_service
  - llm_provider_service
  - cj_assessment_service
  - spellchecker_service
- **Services deferred**: 1
  - eng5_np_runner (no README, create in future session)

## Standard Sections Template

Each README should include:

### 1. Error Handling
- Use of libs/huleedu_service_libs/error_handling
- ErrorCode enum usage (base vs service-specific)
- Error propagation patterns
- Reference: libs/common_core/docs/error-patterns.md

### 2. Testing
- Test structure (tests/unit/, tests/integration/)
- Common markers (@pytest.mark.asyncio, @pytest.mark.integration)
- How to run tests (pdm run pytest-root services/<service>/tests/)
- Fixture patterns (explicit imports, no conftest)
- Test database patterns (testcontainers if applicable)

### 3. Migration Workflow (for database services)
- Alembic migration commands
- Migration file naming conventions
- When to create migrations
- Reference: .claude/rules/085-database-migration-standards.md

### 4. CLI Tools (where applicable)
- Available commands
- Common usage examples
- Authentication requirements

## Progress Tracker

### High Priority (2/2)
- [x] entitlements_service - Added error handling, testing, migration sections ✅
- [x] email_service - Added error handling, testing, migration sections ✅

### Medium Priority (11/11)
- [x] api_gateway_service - Added error handling, enhanced testing ✅
- [x] class_management_service - Added error handling, testing, migration sections ✅
- [x] content_service - Added error handling, testing sections ✅
- [x] essay_lifecycle_service - Added testing, migration sections ✅
- [x] file_service - Added error handling, testing, migration sections ✅
- [x] identity_service - Added error handling, testing, migration sections ✅ (2025-11-16)
- [ ] language_tool_service - Add error handling, enhance testing
- [x] nlp_service - Added error handling, migration, enhance testing ✅
- [ ] result_aggregator_service - Add error handling, migration, enhance testing
- [ ] websocket_service - Add error handling, enhance testing

### Services with Databases Needing Migration Docs (6)
- [ ] email_service
- [ ] class_management_service
- [ ] file_service
- [x] identity_service - Added migration workflow guidance (2025-11-16)
- [ ] nlp_service
- [ ] result_aggregator_service
- [ ] batch_conductor_service (LOW PRIORITY - already excellent)

## Documentation Standards

Following `.claude/rules/090-documentation-standards.md`:
- Machine-intelligence focused (no marketing language)
- Technical decision rules prominent
- Canonical examples from real implementations
- Pattern selection tables where applicable
- Cross-references to common_core docs and rules

## References

- `.claude/rules/090-documentation-standards.md` - Documentation requirements
- `libs/common_core/README.md` - Template pattern
- `libs/common_core/docs/error-patterns.md` - Error handling patterns
- `.claude/rules/085-database-migration-standards.md` - Migration standards
- `.claude/rules/075-test-creation-methodology.md` - Testing patterns
- `.claude/results/common-core-documentation-session-1-results.md` - Session 1 lessons

## Session Timeline

**Phase 1: Discovery** ✅ COMPLETE
- Survey all 18 service READMEs
- Identify missing sections
- Present findings and get user approval

**Phase 2: Standardization** 🔄 IN PROGRESS
- Standardize 13 services one at a time
- Follow approved template
- Track progress in todo list

**Phase 3: Results** ⏸️ PENDING
- Create results document
- Update HANDOFF.md
- Document lessons learned

## Success Criteria

- ✅ All 13 target service READMEs have consistent sections
- ✅ All documentation follows machine-intelligence language standards
- ✅ All cross-references to common_core docs and rules are accurate
- ✅ User approval obtained for standardization approach
- ✅ Task tracking document created
- ⏸️ Results document created
- ⏸️ HANDOFF.md updated

## Current Status

**Services Completed**: 8/13 (62%)
**Services Remaining**: 5/13 (38%)

**Last Updated**: 2025-11-16

**Commits**:
- Commit 1 (13650e7): 6 services (entitlements, email, api_gateway, class_management, content, essay_lifecycle)
- Commit 2 (c0cb0cf): 1 service (file_service)
- Commit 3 (pending): 1 service (identity_service)

Working on: Session paused - handoff for next session
