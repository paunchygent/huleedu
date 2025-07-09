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

**Published**: `ClassCreatedV1`, `ClassUpdatedV1`, `StudentCreatedV1`, `StudentUpdatedV1`

**Channels**:
1. Kafka: Durable via EventEnvelope
2. Redis: Real-time via `ws:{user_id}`

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