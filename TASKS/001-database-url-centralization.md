# TASK-001: Centralize Database URL Construction with Password Encoding

**Status**: 🟢 IN PROGRESS - Batch 1 Complete, 5/12 Services Migrated
**Priority**: CRITICAL
**Blocks**: TASK-002 (ENG5 CLI Validation)
**Created**: 2025-11-11
**Updated**: 2025-11-11 (Batch 1 completed and validated)
**Assigned**: Current session

## Implementation Status

**✅ Phase 1 COMPLETE**: Shared utility created, tested (7/7 tests passing), and exported
**✅ Phase 2 COMPLETE**: Unit tests passing with comprehensive coverage
**✅ Phase 5 COMPLETE**: Identity Service schema auto-init confirmed (startup_setup.py:57-59)
**✅ Phase 1 Service Migration COMPLETE**: Identity Service migrated to uppercase `DATABASE_URL` and validated
**✅ Batch 1 Migration COMPLETE**: 4 services migrated, validated, and running healthy (file, result_aggregator, class_management, email)
**🟡 Phase 3 IN PROGRESS**: Batch 2-3 service migrations (7 services remaining)
**🟡 Phase 4 IN PROGRESS**: 7 docker-compose DATABASE_URL overrides remain (4 removed in Batch 1)
**📊 Migration Progress**: 5/12 services complete (42%), Batch 1 validated

**Critical Decision**: Enforce uppercase `DATABASE_URL` per Rule 043 - all services will use uppercase property name during migration.

**Phase 1 Validation Results** (2025-11-11):
- ✅ Identity Service unit tests: 534/535 passed (33.23s)
- ✅ Type checking: 1,222 files, no issues
- ✅ Container test: Successful startup with special character password (`#` encoded correctly)
- ✅ Health endpoint: Database healthy, all dependencies operational
- ✅ Schema auto-init: Tables created successfully on fresh database

**Batch 1 Validation Results** (2025-11-11):
- ✅ **File Service**: 212 tests passed (189 unit + 23 integration), alembic simplified, container validated
- ✅ **Result Aggregator**: 288 tests passed (225 unit + 63 integration), container validated
- ✅ **Class Management**: 155 tests passed (4 pre-existing failures unrelated), container validated
- ✅ **Email Service**: 142 unit tests passed, property renamed to uppercase, 3 files updated (alembic + 2 tests + app.py)
- ✅ **Type checking**: 1,222 files, no new issues
- ✅ **All 4 services running healthy** in Docker with special character password (`omT9VJ#1cvqPjuMzP5exdGp9h#m3zmQn`)
- ✅ **Code reduction**: ~180 lines of duplicate code eliminated across Batch 1
- ✅ **Docker overrides**: 4 DATABASE_URL overrides removed successfully

## Problem Statement

### Root Cause Identified
Database password containing special characters (`#`, `@`, `%`, etc.) causes authentication failures across services due to improper URL encoding.

### Current State
- **16 of 17 services** have duplicate database URL construction logic (~75 lines each)
- **Only 1 service (CJ Assessment)** correctly uses `urllib.parse.quote_plus()` for password encoding
- **16 services vulnerable** to authentication failure if `HULEEDU_DB_PASSWORD` contains special characters
- **Identity Service**: Failed to start with password `omT9VJ#1cvqPjuMzP5exdGp9h#m3zmQn` (truncated at first `#`)
- **Massive code duplication**: ~1,200 lines of identical logic across services

### Impact
- **Immediate**: Identity Service cannot start, blocking ENG5 CLI validation
- **Systemic**: All services except CJ Assessment will fail with special character passwords
- **Maintenance**: Bug fixes require changes to 17 different files

## Architectural Decision

### Option A: Shared Library Utility (RECOMMENDED)
Centralize database URL construction in `huleedu_service_libs` to eliminate duplication and fix all services at once.

**Pros**:
- Fixes bug in all 17 services simultaneously
- Reduces duplication from ~1,200 lines to ~150 lines total
- Single source of truth for database configuration
- Consistent error messages
- Easy to enhance (connection pooling, SSL, etc.)
- Aligns with DRY and SOLID principles

**Cons**:
- More files to change (17 service configs + docker-compose)
- Requires shared library changes first
- Longer to complete than quick-fix

### Option B: Quick Fix (NOT RECOMMENDED)
Add `quote_plus()` to 11 individual service config.py files.

**Pros**:
- Faster to implement
- Smaller blast radius

**Cons**:
- Perpetuates code duplication
- Doesn't fix the architectural issue
- Still requires 11+ file changes
- Technical debt remains

**Decision**: Implement Option A (Shared Library)

## Implementation Plan

### Phase 1: Create Shared Database Utility

**File**: `libs/huleedu_service_libs/src/huleedu_service_libs/config/database_utils.py`

Create standalone function:
```python
from urllib.parse import quote_plus

def build_database_url(
    *,
    database_name: str,
    service_env_var_prefix: str,
    is_production: bool,
    dev_port: int,
    dev_host: str = "localhost",
    url_encode_password: bool = True,
) -> str:
    """Build environment-aware PostgreSQL database URL.

    Constructs database URLs following HuleEdu standards:
    1. Check for service-specific override env var
    2. Production: Use HULEEDU_PROD_DB_* variables with proper encoding
    3. Development: Use localhost with service-specific port and proper encoding

    Args:
        database_name: Full database name (e.g., 'huleedu_class_management')
        service_env_var_prefix: Service prefix for override (e.g., 'CLASS_MANAGEMENT_SERVICE')
        is_production: Whether running in production environment
        dev_port: Development database port (e.g., 5435)
        dev_host: Development database host (default: 'localhost')
        url_encode_password: Whether to URL-encode passwords (default: True, RECOMMENDED)

    Returns:
        PostgreSQL connection URL with asyncpg driver and properly encoded password

    Raises:
        ValueError: If required credentials are missing
    """
    import os

    # 1. Check for explicit override
    override_var = f"{service_env_var_prefix}_DATABASE_URL"
    env_url = os.getenv(override_var)
    if env_url:
        return env_url

    db_user = os.getenv("HULEEDU_DB_USER", "huleedu_user")

    if is_production:
        prod_host = os.getenv("HULEEDU_PROD_DB_HOST")
        prod_port = os.getenv("HULEEDU_PROD_DB_PORT", "5432")
        prod_password = os.getenv("HULEEDU_PROD_DB_PASSWORD")

        if not all([prod_host, prod_password]):
            raise ValueError(
                "Production environment requires HULEEDU_PROD_DB_HOST and "
                "HULEEDU_PROD_DB_PASSWORD environment variables"
            )

        password = quote_plus(prod_password) if url_encode_password else prod_password
        return (
            f"postgresql+asyncpg://{db_user}:{password}@"
            f"{prod_host}:{prod_port}/{database_name}"
        )
    else:
        db_password = os.getenv("HULEEDU_DB_PASSWORD")

        if not db_password:
            raise ValueError(
                "Missing required database credentials. Ensure HULEEDU_DB_USER and "
                "HULEEDU_DB_PASSWORD are set in .env file."
            )

        password = quote_plus(db_password) if url_encode_password else db_password
        return (
            f"postgresql+asyncpg://{db_user}:{password}@"
            f"{dev_host}:{dev_port}/{database_name}"
        )
```

**File**: `libs/huleedu_service_libs/src/huleedu_service_libs/config/secure_base.py`

Add convenience method to `SecureServiceSettings`:
```python
def build_database_url(
    self,
    *,
    database_name: str,
    service_env_var_prefix: str,
    dev_port: int,
    dev_host: str = "localhost",
    url_encode_password: bool = True,
) -> str:
    """Build environment-aware PostgreSQL database URL.

    Convenience wrapper around database_utils.build_database_url.
    See database_utils module for full documentation.
    """
    from .database_utils import build_database_url

    return build_database_url(
        database_name=database_name,
        service_env_var_prefix=service_env_var_prefix,
        is_production=self.is_production(),
        dev_port=dev_port,
        dev_host=dev_host,
        url_encode_password=url_encode_password,
    )
```

**File**: `libs/huleedu_service_libs/src/huleedu_service_libs/config/__init__.py`

Export new utility:
```python
from .database_utils import build_database_url

__all__ = [
    "SecureServiceSettings",
    "build_database_url",
    # ... existing exports
]
```

### Phase 2: Add Comprehensive Tests

**File**: `libs/huleedu_service_libs/tests/config/test_database_utils.py`

Test coverage:
- ✅ Production environment with special characters in password
- ✅ Development environment with special characters in password
- ✅ Override via SERVICE_DATABASE_URL env var
- ✅ Missing credentials raise ValueError
- ✅ URL encoding disabled (url_encode_password=False)
- ✅ Custom dev_host
- ✅ Password with all URL-unsafe characters: `@`, `#`, `%`, `:`, `/`, `?`, `&`, `=`

### Phase 3: Migrate All 12 Services (Batch Strategy)

**Migration Approach**: Batch migration (3-4 services per batch) for manageable risk and validation.

**CRITICAL**: All services MUST use uppercase `DATABASE_URL` property per Rule 043.

Update each service's config.py to use shared utility:

**Before** (~40-75 lines):
```python
@property
def database_url(self) -> str:  # ❌ Lowercase violates Rule 043
    import os
    env_url = os.getenv("SERVICE_DATABASE_URL")
    if env_url:
        return env_url
    # ... 40-70 more lines of duplicate logic without password encoding
```

**After** (~10-15 lines):
```python
@property
def DATABASE_URL(self) -> str:  # ✅ Uppercase per Rule 043
    """Return the PostgreSQL database URL for both runtime and migrations."""
    import os
    env_type = os.getenv("ENV_TYPE", "development").lower()
    dev_host = "service_db" if env_type == "docker" else "localhost"

    return self.build_database_url(
        database_name="huleedu_service_name",
        service_env_var_prefix="SERVICE_NAME_SERVICE",
        dev_port=5XXX,  # Service-specific port
        dev_host=dev_host,
    )
```

**Services to Migrate** (12 total with database dependencies):

**✅ Phase 1 Complete:**
1. ✅ identity_service (VALIDATED - uppercase `DATABASE_URL`, helper migration complete, container tested)

**✅ Batch 1 Complete (2025-11-11):**
2. ✅ file_service (212 tests passed, alembic simplified, container validated, override removed)
3. ✅ result_aggregator_service (288 tests passed, container validated, override removed)
4. ✅ class_management_service (155 tests passed, container validated, override removed)
5. ✅ email_service (142 tests passed, uppercase rename + alembic + 2 test files updated, override removed)

**❌ Batch 2 - Complex Patterns (4 services):**
6. ❌ essay_lifecycle_service (uppercase ✅, needs helper, 2 containers)
7. ❌ nlp_service (lowercase ❌, needs helper + uppercase rename)
8. ❌ batch_orchestrator_service (lowercase ❌, needs helper + uppercase rename)
9. ❌ spellchecker_service (lowercase ❌, needs helper + uppercase rename)

**❌ Batch 3 - Final Services (3 services):**
10. ❌ entitlements_service (lowercase ❌, needs helper + uppercase rename)
11. ❌ batch_conductor_service (lowercase ❌, needs helper + uppercase rename)
12. ❌ cj_assessment_service (lowercase ❌, HAS password encoding but needs helper migration + uppercase rename)

**Note**: Services without database dependencies (api_gateway, content_service, llm_provider, etc.) are not included in migration scope.

**Port Mapping Reference**:
| Service | Dev Port |
|---------|----------|
| essay_lifecycle_service | 5433 |
| cj_assessment_service | 5434 |
| class_management_service | 5435 |
| result_aggregator_service | 5436 |
| spellchecker_service | 5437 |
| batch_orchestrator_service | 5438 |
| file_service | 5439 |
| nlp_service | 5440 |
| batch_conductor_service | 5441 |
| identity_service | 5442 |
| email_service | 5443 |
| entitlements_service | 5444 |

### Phase 4: Remove Docker-Compose DATABASE_URL Overrides

**File**: `docker-compose.services.yml`

Remove explicit DATABASE_URL overrides for 11 services (let config.py construct URL with proper encoding):

**✅ Batch 1 Overrides Removed (4 services):**
1. ✅ result_aggregator_service (REMOVED: `RESULT_AGGREGATOR_SERVICE_DATABASE_URL`)
2. ✅ file_service (REMOVED: `FILE_SERVICE_DATABASE_URL`)
3. ✅ class_management_service (REMOVED: `CLASS_MANAGEMENT_SERVICE_DATABASE_URL`)
4. ✅ email_service (REMOVED: `EMAIL_SERVICE_DATABASE_URL`)

**❌ Batch 2 Overrides to Remove (4 services):**
5. ❌ spellchecker_service (line 175: `SPELLCHECKER_SERVICE_DATABASE_URL`)
6. ❌ essay_lifecycle_service API (line 272: `ESSAY_LIFECYCLE_SERVICE_DATABASE_URL`)
7. ❌ essay_lifecycle_service API (line 273: `ELS_DATABASE_URL` - duplicate)
8. ❌ essay_lifecycle_service worker (line 323: `ESSAY_LIFECYCLE_SERVICE_DATABASE_URL`)
9. ❌ essay_lifecycle_service worker (line 324: `ELS_DATABASE_URL` - duplicate)
10. ❌ nlp_service (line 656: `NLP_SERVICE_DATABASE_URL`)

**❌ Batch 3 Overrides to Remove (2 services):**
11. ❌ entitlements_service (line 806: `ENTITLEMENTS_SERVICE_DATABASE_URL`)

**Note**: Identity Service and Batch Orchestrator Service do NOT have docker-compose overrides (already removed or never existed).

**Pattern - REMOVE**:
```yaml
- SERVICE_DATABASE_URL=postgresql+asyncpg://${HULEEDU_DB_USER}:${HULEEDU_DB_PASSWORD}@service_db:5432/huleedu_service
```

**Pattern - KEEP** (individual component vars):
```yaml
- SERVICE_DB_HOST=service_db
- SERVICE_DB_PORT=5432
- SERVICE_DB_NAME=huleedu_service_name
- HULEEDU_DB_USER=${HULEEDU_DB_USER}
- HULEEDU_DB_PASSWORD=${HULEEDU_DB_PASSWORD}
```

### Phase 5: Identity Service Schema Auto-Initialization

**Status**: ✅ COMPLETE - Already implemented

**File**: `services/identity_service/startup_setup.py` (lines 57-59)

Schema initialization is already implemented:

```python
# Initialize database schema (safety net for fresh databases)
async with database_engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

**Implementation Details**:
- Engine obtained from DI container (AsyncEngine)
- Schema auto-created on service startup
- Stored in `app.database_engine` for health checks
- Follows same pattern as class_management, cj_assessment, essay_lifecycle services

**No action required** - This phase was completed in a previous session.

### Phase 6: Restore Original Password and Recreate Services

1. **Restore .env password**:
   - Restore: `HULEEDU_DB_PASSWORD=omT9VJ#1cvqPjuMzP5exdGp9h#m3zmQn`

2. **Recreate Identity Service**:
   ```bash
   pdm run dev-stop identity_service
   docker volume rm huledu-reboot_identity_db_data
   pdm run dev-start identity_service
   ```

3. **Verify healthy startup** with special character password

4. **Run integration tests** to confirm all services work with new utility

## Testing Strategy

### Unit Tests
- ✅ Test `build_database_url()` function directly
- ✅ Test all edge cases and error conditions
- ✅ Test password encoding with various special characters

### Integration Tests
1. **Identity Service Priority**:
   - Start with fresh database
   - Verify schema auto-created
   - Verify connection works with password containing `#`

2. **Service Migration Validation**:
   - Migrate pilot service (class_management_service recommended)
   - Run Alembic migrations
   - Run service tests
   - Verify Docker container startup
   - Verify local development works

3. **Full System Validation**:
   - Start all services with shared utility
   - Run cross-service integration tests
   - Verify no authentication failures

### Validation Checklist
- [ ] Shared utility created and tested
- [ ] All 17 services migrated to use utility
- [ ] Docker-compose overrides removed
- [ ] Identity Service schema auto-initialization added
- [ ] All services start successfully with password containing `#`
- [ ] Alembic migrations work for all services
- [ ] No breaking changes to existing functionality

## Files Modified

**New Files** (2):
1. `libs/huleedu_service_libs/src/huleedu_service_libs/config/database_utils.py`
2. `libs/huleedu_service_libs/tests/config/test_database_utils.py`

**Phase 1 Modified Files** (5):
1. `.env` (restore password)
2. `libs/huleedu_service_libs/src/huleedu_service_libs/config/__init__.py` (export)
3. `libs/huleedu_service_libs/src/huleedu_service_libs/config/secure_base.py` (add method)
4. `services/identity_service/config.py` (uppercase + helper migration)
5. `services/identity_service/startup_setup.py` (add schema init)

**Batch 1 Modified Files** (13):
6. `services/file_service/config.py` (helper migration, 53 lines → 21 lines)
7. `services/file_service/alembic/env.py` (simplified pattern)
8. `services/result_aggregator_service/config.py` (helper migration, 50 lines → 21 lines)
9. `services/class_management_service/config.py` (helper migration, 51 lines → 21 lines)
10. `services/email_service/config.py` (helper migration + uppercase rename, 51 lines → 21 lines)
11. `services/email_service/alembic/env.py` (uppercase reference)
12. `services/email_service/app.py` (uppercase reference)
13. `services/email_service/tests/integration/test_database_operations.py` (uppercase property)
14. `services/email_service/tests/integration/test_outbox_publishing.py` (uppercase property)
15. `docker-compose.services.yml` (removed 4 DATABASE_URL overrides: result_aggregator, file, class_management, email)

**Batch 2 Pending** (4 service configs + alembic files + docker-compose)
**Batch 3 Pending** (3 service configs + alembic files + docker-compose)

**Total Modified So Far**: 20 files (Phase 1 + Batch 1)

## Success Criteria

- [x] Shared utility function created with comprehensive tests (Phase 1)
- [x] Identity Service migrated and validated (Phase 1)
- [x] Batch 1 services migrated (4/12 services: file, result_aggregator, class_management, email)
- [x] Password encoding works for all URL-unsafe characters (validated in Batch 1)
- [x] Identity Service starts successfully with password `omT9VJ#1cvqPjuMzP5exdGp9h#m3zmQn`
- [x] Batch 1 services healthy with special character password
- [x] Code duplication reduced by ~180 lines in Batch 1 services
- [x] Zero breaking changes to existing functionality (Batch 1 validated)
- [x] 4 Docker overrides removed successfully (Batch 1)
- [ ] Batch 2 services migrated (essay_lifecycle, nlp, batch_orchestrator, spellchecker)
- [ ] Batch 3 services migrated (entitlements, batch_conductor, cj_assessment)
- [ ] All 12 services use centralized database URL construction
- [ ] All 11 docker-compose overrides removed
- [ ] Rule 085 updated with new pattern

## Documentation Updates

**Update**: `.claude/rules/085-database-migration-standards.md`

Add section on database URL construction:
```markdown
## Database URL Construction (As of 2025-11-11)

### Standard Pattern

All services MUST use the shared `build_database_url()` utility from `huleedu_service_libs`:

```python
from huleedu_service_libs.config import SecureServiceSettings

class Settings(SecureServiceSettings):
    @property
    def DATABASE_URL(self) -> str:
        return self.build_database_url(
            database_name="huleedu_service_name",
            service_env_var_prefix="SERVICE_NAME",
            dev_port=5435,  # Assigned service port
        )
```

### Password Encoding

The shared utility automatically URL-encodes passwords using `urllib.parse.quote_plus()`.
This handles special characters like `#`, `@`, `%`, `:`, `/`, etc.

**DO NOT** construct database URLs manually - use the shared utility.
```

## Rollback Plan

If issues arise during migration:

1. **Per-Service Rollback**: Revert individual service config.py to previous version
2. **Docker Rollback**: Re-add DATABASE_URL override for affected service
3. **Full Rollback**: Revert shared library changes (non-breaking, old pattern still works)

## Notes

- **Non-Breaking Change**: Existing services continue to work during migration
- **Incremental Migration**: Services can be migrated one at a time
- **Backward Compatible**: Old pattern still functions if needed for rollback
- **Password Security**: URL encoding does NOT expose password (still in connection string)
- **CJ Assessment Service**: Already correct - use as validation baseline

## Related Tasks

- **TASK-002**: ENG5 CLI Validation (BLOCKED by this task)

## References

- Research findings: Agent research report 2025-11-11
- CJ Assessment Service: `services/cj_assessment_service/config.py` (reference implementation)
- Rule 085: `.claude/rules/085-database-migration-standards.md`
