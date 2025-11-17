Entitlements Service
====================

Purpose

- Central authority for credit policies and accounting with org-first identity attribution. Provides advisory preflight and post-usage consumption.

Key Notes

- Outbox schema ownership: This service uses the shared Transactional Outbox model from `libs/huleedu_service_libs.outbox.models.EventOutbox`. Do not define or modify a service-local outbox model. All migrations for the outbox table must align with the shared library conventions (index names, columns, partial index on `published_at IS NULL`).
- Migrations: Create Alembic migrations from this service directory. Avoid modifying pushed versions. Use `.cursor/rules/085-database-migration-standards.md` for guidance.

CorrelationContext (Mandatory)

- Middleware: The service registers `setup_correlation_middleware(app)` to normalize inbound correlation IDs.
- DI: `CorrelationContext` is provided with `Scope.REQUEST` and injected into routes.
- Usage:
  - Errors: pass `corr.uuid` to error factories; include `original_correlation_id=corr.original`.
  - Responses: echo `corr.original` in successful responses.
  - Events: use `corr.uuid` for event envelope `correlation_id`.
  - See `.cursor/rules/043-service-configuration-and-logging.md` for details.

Outbox Index Alignment

- Shared index names used by the library:
  - `ix_event_outbox_unpublished` on (`published_at`, `created_at`) with predicate `published_at IS NULL`.
  - `ix_event_outbox_aggregate` on (`aggregate_type`, `aggregate_id`).
- A migration is provided to align legacy aliases to these names: `alembic/versions/20250907_1415_align_outbox_index_names.py`.

Verification

- Alembic chain check (from `services/entitlements_service/`):
  - `pdm run alembic heads`
  - `pdm run alembic history --verbose`
- Index verification script:
  - `python services/entitlements_service/scripts/verify_outbox_indexes.py --database-url postgresql+asyncpg://user:pass@host:port/db`
  - Returns non-zero exit code on missing/mismatched indexes.

## Error Handling

Uses `libs/huleedu_service_libs/error_handling` for structured error responses.

### ErrorCode Usage

- **Base ErrorCode**: Service uses base `ErrorCode` from `common_core.error_enums` for generic errors:
  - `VALIDATION_ERROR` - Invalid request data
  - `RESOURCE_NOT_FOUND` - Credit balance or policy not found
  - `EXTERNAL_SERVICE_ERROR` - Kafka/database failures
  - `PROCESSING_ERROR` - Credit consumption failures

- No service-specific ErrorCode enum (uses base errors only)

### Error Propagation

- **HTTP Endpoints**: Raise `HuleEduError` with correlation_id and ErrorCode
- **Event Processing**: Failures logged with correlation context, transactional outbox ensures event consistency
- **Transactional Outbox**: Events published via outbox pattern to prevent data loss

### Error Response Structure

All errors follow standard structure:

```python
from huleedu_service_libs.error_handling import HuleEduError
from common_core.error_enums import ErrorCode

raise HuleEduError(
    error_code=ErrorCode.VALIDATION_ERROR,
    message="Insufficient credits",
    correlation_id=correlation_context.uuid,
    original_correlation_id=correlation_context.original
)
```

Reference: `libs/common_core/docs/error-patterns.md`

## Testing

### Test Structure

```
tests/
├── unit/                          # Unit tests with mocked dependencies
│   ├── test_credit_consumption_logic.py
│   ├── test_entitlements_routes.py
│   ├── test_repository_impl.py
│   └── ...
├── integration/                   # Integration tests with testcontainers
│   ├── test_credit_consumption_integration.py
│   ├── test_credit_attribution.py
│   ├── test_outbox_publisher_integration.py
│   └── ...
└── contract/                      # Event contract validation tests
    ├── test_resource_consumption_events.py
    └── test_credit_manager_contract.py
```

### Running Tests

```bash
# All tests
pdm run pytest-root services/entitlements_service/tests/ -v

# Unit tests only
pdm run pytest-root services/entitlements_service/tests/unit/ -v

# Integration tests (requires testcontainers)
pdm run pytest-root services/entitlements_service/tests/integration/ -v -m integration

# Contract tests
pdm run pytest-root services/entitlements_service/tests/contract/ -v
```

### Common Test Markers

- `@pytest.mark.asyncio` - Async unit tests
- `@pytest.mark.integration` - Integration tests requiring external dependencies
- `@pytest.mark.contract` - Event contract validation tests

### Test Patterns

- **Protocol-based mocking**: Use `AsyncMock(spec=ProtocolName)` for dependencies
- **Dishka DI in tests**: Create test containers with mock providers
- **Explicit fixtures**: Import test utilities explicitly (no conftest.py)
- **Testcontainers**: PostgreSQL containers for integration tests

Reference: `.claude/rules/075-test-creation-methodology.md`

## Migration Workflow

### Creating Migrations

From service directory:

```bash
cd services/entitlements_service/

# Generate migration from model changes
alembic revision --autogenerate -m "description_of_change"

# Review generated migration in alembic/versions/
# Edit if needed (constraints, indexes, data migrations)

# Apply migration
alembic upgrade head
```

### Migration Standards

- **Naming**: `YYYYMMDD_HHMM_short_description.py`
- **Outbox alignment**: Use shared `EventOutbox` model from `huleedu_service_libs.outbox.models`
- **Index names**: Follow library conventions:
  - `ix_event_outbox_unpublished` for outbox publishing
  - `ix_event_outbox_aggregate` for aggregate tracking
- **Verification**: Run `alembic history --verbose` after creating migrations

### Critical Notes

- Entitlements service owns credit balance and policy tables
- Outbox table owned by shared library - align index names only
- Never modify pushed migrations - create new migration to fix issues
- Test migrations against testcontainer database before pushing

Reference: `.claude/rules/085-database-migration-standards.md`
