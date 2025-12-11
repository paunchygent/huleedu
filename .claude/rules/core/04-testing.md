# Testing Standards

## Requirements
- All code changes require tests (run and verified)
- Run `pdm run typecheck-all` from root after implementation
- **100% pass rate** before proceeding — fix failures, don't skip

## Test Execution
```bash
pdm run pytest-root <path-or-nodeid> [pytest args]
pdm run pytest-root <path> -s  # Debug mode
```

## Critical Constraints

| Rule | Description |
|------|-------------|
| **Timeout** | ≤60s per test (prefer 30s for event-driven) |
| **File size** | <500 LoC per test file |
| **Isolation** | Tests must be independent |
| **Root cause** | Fix implementation, not tests |

## Forbidden
- Simplifying tests to make them pass
- `try/except pass` hiding failures
- Mocking at wrong abstraction levels
- `@patch` for protocol dependencies — use DI injection
- Fragile log assertions (`assert "text" in caplog.text`)

## DI/Protocol Testing
```python
# ✅ Protocol-based mocking
mock_dep = AsyncMock(spec=DependencyProtocol)
service = ServiceImpl(dependency=mock_dep)
```

## Test Location
- **Service tests**: `services/<service>/tests/`
- **Cross-service**: `tests/integration/`
- **Full docker/E2E**: `tests/functional/` (CI Lane C only)

**Detailed**: `.agent/rules/070-testing-and-quality-assurance.md`, `.agent/rules/075-test-creation-methodology.md`
