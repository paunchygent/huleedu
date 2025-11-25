---
id: 'remove-cjrepositoryprotocol-shim-and-deprecated-mocks'
title: 'Remove CJRepositoryProtocol shim and deprecated mocks'
type: 'task'
status: 'in_progress'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-25'
last_updated: '2025-11-25'
related: []
labels: []
---
# Remove CJRepositoryProtocol shim and deprecated mocks

## Objective
Delete the deprecated CJRepositoryProtocol shim, its db_access_impl implementation, and legacy MockDatabase test helpers while moving tests to per-aggregate repository/session-provider mocks.

## Context
Per-aggregate repositories are now the only supported path; the shim adds dead code and encourages incorrect mocking patterns in tests. Cleaning it up aligns tests with current DI patterns and removes obsolete helpers.

## Plan
1. Replace MockDatabase usage with MockSessionProvider + per-aggregate repo mocks in unit tests and conftest fixtures.
2. Repoint integration tests to PostgresDataAccess/per-aggregate repositories instead of db_access_impl helpers.
3. Remove CJRepositoryProtocol definition and delete implementations/db_access_impl.py; ensure no remaining imports.
4. Run format, lint, typecheck, and targeted pytest for touched suites.

## Success Criteria
- No references to CJRepositoryProtocol or db_access_impl.py in code/tests.
- Deprecated MockDatabase removed; unit tests rely on session_provider/repo mocks.
- Targeted pytest suites pass; typecheck-all/lint/format are clean.

## Related
- TASKS/assessment/cj-db-per-aggregate-repository-refactor.md
- services/cj_assessment_service/tests/integration/REAL_DATABASE_TESTING_GUIDE.md
