# Class Management Service

## Service Identity
- **Port**: 5002
- **Purpose**: Authoritative source for classes/students
- **Stack**: HuleEduApp, PostgreSQL, Kafka, Redis

## Architecture

```
app.py                  # HuleEduApp setup
api/
  health_routes.py      # /healthz, /metrics
  class_routes.py       # Class CRUD
  student_routes.py     # Student CRUD
protocols.py            # ClassRepositoryProtocol, ClassEventPublisherProtocol
di.py                   # Dishka providers
implementations/        # Concrete implementations
models_db.py           # SQLAlchemy models
```

## API Endpoints

**Base**: `/v1/classes` (requires `X-User-ID` header)

- `POST /`: Create class
- `GET /<id>`: Get class
- `PUT /<id>`: Update class
- `DELETE /<id>`: Delete class
- `POST /students`: Create student
- `GET /students/<id>`: Get student
- `PUT /students/<id>`: Update student
- `DELETE /students/<id>`: Delete student

## Database Schema

- `Course`: Reference data (ENG5, ENG6, ENG7, SV1, SV2, SV3)
- `UserClass`: One course per class
- `Student`: Email+user_id unique
- `class_student_association`: M2M
- `EssayStudentAssociation`: Essay->Student

## Events

**Published**: `ClassCreatedV1`, `ClassUpdatedV1`, `StudentCreatedV1`, `StudentUpdatedV1`, `StudentAssociationsConfirmedV1`

**Channels**:
1. Kafka: Durable via EventEnvelope
2. Redis: Real-time via `ws:{user_id}`

**Consumed**: `BatchAuthorMatchesSuggestedV1` (Phase 1 student matching)

## Key Patterns

**Repository-Managed Sessions**:
```python
class PostgreSQLClassRepositoryImpl:
    def __init__(self, engine: AsyncEngine):
        self.session = async_sessionmaker(engine, expire_on_commit=False)
```

**HuleEduApp Guaranteed Contract**:
```python
app = HuleEduApp(__name__)
app.container = container  # Non-optional
app.database_engine = engine  # Non-optional
```

**Single Course Validation**:
```python
if len(course_codes) > 1:
    raise MultipleCourseError(course_codes)
```

## Phase 1 Student Matching

**Association Timeout Monitor**: Auto-confirms pending student-essay associations after 24 hours:
- **High confidence (≥0.7)**: Confirms with original student
- **Low confidence (<0.7)**: Creates UNKNOWN student with email `unknown.{class_id}@huleedu.system`
- **Check interval**: Hourly
- **Validation method**: `TIMEOUT`

**Database Fields** (`EssayStudentAssociation`):
```python
batch_id: UUID              # FK to batch
class_id: UUID              # FK to class
confidence_score: float     # NLP matching confidence
validation_status: str      # pending_validation/confirmed/rejected/timeout_confirmed
validation_method: str      # human/timeout/auto
```

## Configuration

Environment prefix: `CLASS_MANAGEMENT_SERVICE_`
- `DATABASE_URL`
- `KAFKA_BOOTSTRAP_SERVERS`
- `REDIS_URL`
- `USE_MOCK_REPOSITORY`

## Performance

- 500+ students/second
- 10ms queries (P95: 27ms)
- 30→300 DB connections scaling path

## Development

```bash
# Run service
pdm run -p services/class_management_service dev

# Tests
pdm run pytest services/class_management_service/tests/

# Type check
pdm run mypy services/class_management_service/
```

## Error Handling

Uses `libs/huleedu_service_libs/error_handling` for structured error responses.

### ErrorCode Usage

- **Base ErrorCode**: Service uses base `ErrorCode` from `common_core.error_enums`:
  - `VALIDATION_ERROR` - Invalid class/student data, multiple course codes
  - `RESOURCE_NOT_FOUND` - Class or student not found
  - `EXTERNAL_SERVICE_ERROR` - Kafka/database failures
  - `PROCESSING_ERROR` - Student association processing failures

- No service-specific ErrorCode enum (uses base errors only)

### Error Propagation

- **HTTP Endpoints**: Raise `HuleEduError` with correlation_id and ErrorCode
- **Event Processing**: Kafka consumer catches exceptions, logs with correlation context
- **Repository Operations**: Database errors wrapped in `HuleEduError`
- **Timeout Monitor**: Association processing failures logged, UNKNOWN student created as fallback

### Error Response Structure

All errors follow standard structure:

```python
from huleedu_service_libs.error_handling import HuleEduError
from common_core.error_enums import ErrorCode

raise HuleEduError(
    error_code=ErrorCode.VALIDATION_ERROR,
    message="Multiple course codes detected in batch, expected single course per class",
    correlation_id=correlation_context.uuid
)
```

Reference: `libs/common_core/docs/error-patterns.md`

## Testing

### Test Structure

```
tests/
├── unit/                          # Unit tests with mocked dependencies
│   ├── test_batch_author_matches_handler.py
│   ├── test_timeout_monitor_*.py
│   ├── test_repository_*.py
│   ├── test_kafka_circuit_breaker_di.py
│   └── ...
├── integration/                   # Integration tests with testcontainers
│   ├── test_batch_author_matches_database_*.py
│   ├── test_batch_author_matches_kafka_integration.py
│   ├── test_internal_routes_integration.py
│   └── ...
├── performance/                   # Performance tests (bulk operations)
│   ├── test_concurrent_teacher_performance.py
│   ├── test_database_bulk_performance.py
│   ├── test_single_operation_performance.py
│   └── conftest.py
├── test_core_logic.py            # Core business logic tests
├── test_contract_compliance.py   # Event contract tests
├── test_api_integration.py       # API endpoint tests
└── conftest.py                   # Shared fixtures
```

### Running Tests

```bash
# All tests
pdm run pytest-root services/class_management_service/tests/ -v

# Unit tests only
pdm run pytest-root services/class_management_service/tests/unit/ -v

# Integration tests (requires testcontainers)
pdm run pytest-root services/class_management_service/tests/integration/ -v -m integration

# Performance tests
pdm run pytest-root services/class_management_service/tests/performance/ -v
```

### Common Test Markers

- `@pytest.mark.asyncio` - Async unit tests
- `@pytest.mark.integration` - Integration tests requiring external dependencies
- `@pytest.mark.performance` - Performance tests (bulk operations, concurrency)

### Test Patterns

- **Protocol-based mocking**: Use `AsyncMock(spec=ProtocolName)` for dependencies
- **Testcontainers**: PostgreSQL containers for integration tests
- **Performance fixtures**: Bulk data fixtures in `performance/conftest.py`
- **Explicit fixtures**: Import test utilities from shared conftest.py
- **Timeout monitor testing**: Mock sleep for timer-based logic

Reference: `.claude/rules/075-test-creation-methodology.mdc`

## Migration Workflow

### Creating Migrations

From service directory:

```bash
cd services/class_management_service/

# Generate migration from model changes
alembic revision --autogenerate -m "description_of_change"

# Review generated migration in alembic/versions/
# Edit if needed (constraints, indexes, data migrations)

# Apply migration
alembic upgrade head
```

### Migration Standards

- **Naming**: `YYYYMMDD_HHMM_short_description.py`
- **Class tables**: UserClass, Student, class_student_association, EssayStudentAssociation
- **Reference data**: Course table (seeded via `20250708_0002_seed_courses.py`)
- **Outbox alignment**: Use shared `EventOutbox` model from `huleedu_service_libs.outbox.models`
- **Indexes**: Add indexes for query patterns (batch_id, class_id, validation_status)
- **Verification**: Run `alembic history --verbose` after creating migrations

### Existing Migrations

- `20250706_0001_initial_schema.py` - Initial tables (UserClass, Student, Course)
- `20250708_0002_seed_courses.py` - Course reference data (ENG5, ENG6, ENG7, SV1, SV2, SV3)
- `20250801_1536_8ad1e604aea6_remove_deprecated_skill_level_field_.py` - Cleanup
- `20250802_1853_220aebb1348a_add_event_outbox_table_for_.py` - Outbox pattern
- `20250804_0017_7d21f7fdd41e_add_batch_id_to_essay_student_.py` - Phase 1 matching
- `20250805_0031_20ba9223a723_add_validation_fields_to_essay_student_.py` - Association validation
- `20250808_1011_59d16918f933_add_explicit_topic_column_to_event_.py` - Outbox improvement
- `20250818_1500_add_composite_index_for_batch_queries.py` - Query optimization

### Critical Notes

- Class Management Service owns class, student, and association tables
- Course table is reference data (never modified after seed)
- EssayStudentAssociation critical for Phase 1 student matching
- Outbox table owned by shared library
- Never modify pushed migrations - create new migration to fix issues
- Test migrations against testcontainer database before pushing

Reference: `.claude/rules/085-database-migration-standards.md`