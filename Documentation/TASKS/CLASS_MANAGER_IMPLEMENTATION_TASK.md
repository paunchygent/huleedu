# Class Management Service Implementation

## Objective

Implement a new microservice for managing user classes, students, and their relationships with courses and essays, following established HuleEdu architectural patterns.

## Dependencies

### ✅ Blocking Dependencies Resolved

- **Common Core Extensions (Checkpoint 2.0)**: Provides PersonNameV1 model, CourseCode enum, and class management event contracts
- **Enhanced File Management (Checkpoints 2.1 & 2.2)**: Establishes event publishing patterns and service integration approaches

### 🔄 Enables Future Tasks

- **API Gateway Enhanced Endpoints** (API_GATEWAY_WEBSOCKET_SERVICE_TASK_TICKET_2.md, Checkpoint 2.3)
- **Frontend Class Management Features** (FRONTEND_SKELETON.md, Phase 2)
- **Student Parsing Integration** (File Service will consume CMS events)

## Architectural Considerations

## Type Safety Patterns Reference

### Core Enums (`common_core/src/common_core/`)

**Status & Processing:**

- `status_enums.py`: `EssayStatus`, `BatchStatus`, `ProcessingStatus`, `ValidationStatus`, `OperationStatus`
- `pipeline_models.py`: `PhaseName`, `PipelineExecutionStatus`
- `domain_enums.py`: `ContentType`, `CourseCode`, `Language`
- `error_enums.py`: `ErrorCode`, `FileValidationErrorCode`

**Events & Configuration:**

- `event_enums.py`: `ProcessingEvent` (topic generation)
- `config_enums.py`: `Environment`
- `observability_enums.py`: `MetricName`, `OperationType`, `CacheOperation`

### Event Contracts (`common_core/src/common_core/events/`)

**Core Pattern:**

- `envelope.py`: `EventEnvelope[T]` - typed event wrapper
- `base_event_models.py`: Base event structures

**Domain Events:**

- `class_events.py`: `ClassCreatedV1`, `StudentCreatedV1`, `EssayStudentAssociationUpdatedV1`
- `file_events.py`: `EssayContentProvisionedV1`, `EssayValidationFailedV1`
- `file_management_events.py`: `BatchFileAddedV1`, `BatchFileRemovedV1`
- `batch_coordination_events.py`: `BatchEssaysReady`, `BatchEssaysRegistered`
- `client_commands.py`: `ClientBatchPipelineRequestV1`

### Pydantic Models (`common_core/src/common_core/`)

**Metadata Patterns:**

- `metadata_models.py`: `StorageReferenceMetadata`, `PersonNameV1`, `ParsedNameMetadata`
- `batch_service_models.py`: Batch processing models
- `essay_service_models.py`: Essay lifecycle models

### Service-Specific Enums

**File Service:**

- `services/file_service/validation_models.py`: `FileValidationStatus`, `FileProcessingStatus`

**BOS:**

- `services/batch_orchestrator_service/enums_db.py`: `PhaseStatusEnum`

**CJ Assessment:**

- `services/cj_assessment_service/enums_db.py`: `CJBatchStatusEnum`

### Usage Patterns

**Event Publishing:**

```python
from common_core.events.envelope import EventEnvelope
from common_core.events.class_events import ClassCreatedV1

envelope = EventEnvelope[ClassCreatedV1](
    event_type="huleedu.class.created.v1",
    source_service="class_management_service",
    data=class_event_data
)
```

**Status Handling:**

```python
from common_core.status_enums import EssayStatus, BatchStatus
from common_core.domain_enums import CourseCode

# Use enum objects in business logic
if essay.status == EssayStatus.SPELLCHECK_COMPLETED:
    # Process next phase
```

**Metadata Models:**

```python
from common_core.metadata_models import PersonNameV1, StorageReferenceMetadata

# Standardized name handling
person = PersonNameV1(first_name="Anna", last_name="Andersson")

# File references in events
storage_ref = StorageReferenceMetadata(
    storage_type="content_service",
    reference_id=content_id
)
```

### Service Autonomy

- Class Management Service owns all class/student data
- Other services reference classes/students via IDs only
- No direct database access from external services

### Event-Driven Integration

- Publishes thin events following established patterns
- Uses KafkaBus from service library for event publishing
- Follows event naming conventions: `huleedu.class.{entity}.{action}.v1`

### Data Standards Compliance

- **PersonNameV1 Pattern**: All name handling follows ADL-01 standards
- **User Scoping**: All data isolated by user_id (teacher scope)
- **Course Integration**: Uses CourseCode enum from Common Core

### Privacy & Security

- Student data scoped by creating teacher
- Cascade deletion policies for data integrity
- Unique email constraints per teacher scope

## Implementation Checkpoints

### Checkpoint 2.3: Service Foundation & Database Models

**Objective**: Create complete service structure with database models supporting many-to-many class/student relationships.

**Implementation Requirements**:

1. **Service Structure**: Follow established HuleEdu HTTP service pattern
   - `app.py`: Quart application with Blueprint registration
   - `api/`: Health and class management routes
   - `startup_setup.py`: DI container and metrics initialization
   - `protocols.py`: Service-specific behavioral contracts
   - `implementations/`: Protocol implementations

2. **Database Models** (`models_db.py`):
   - `Course`: Predefined courses (code, name, language, skill_level)
   - `UserClass`: Teacher-owned classes with course relationships
   - `Student`: PersonNameV1-compliant student entities
   - `EssayStudentAssociation`: Essay-student relationship tracking
   - `class_student_association`: Many-to-many association table

3. **Key Model Requirements**:
   - PersonNameV1 integration with `first_name`, `last_name`, `legal_full_name`
   - User scoping via `created_by_user_id` fields
   - Proper SQLAlchemy relationships and constraints
   - `to_person_name_v1()` methods for event publishing

**Done When**:

- ✅ Service directory structure follows HuleEdu patterns
- ✅ Database models support all required relationships
- ✅ PersonNameV1 integration is properly implemented
- ✅ Service starts successfully with health endpoint

### Checkpoint 2.4: API Models & Validation

**Objective**: Define comprehensive request/response models with validation for class and student management operations.

**Implementation Requirements**:

1. **Request Models** (`api_models.py`):
   - `CreateClassRequest`: Class creation with course associations
   - `UpdateClassRequest`: Class modification
   - `CreateStudentRequest`: Student creation with PersonNameV1 fields
   - `UpdateStudentRequest`: Student modification
   - `EssayStudentAssociationRequest`: Manual essay-student linking

2. **Response Models**:
   - `ClassResponse`: Class information with student count
   - `StudentResponse`: Student information with class associations
   - `EssayStudentAssociationResponse`: Association details

3. **Parsing Models**:
   - `StudentParsingResult`: Automatic parsing results with confidence scoring
   - `ParsedNameMetadata`: Name parsing workflow support

4. **Validation Requirements**:
   - Email format validation
   - Name length constraints
   - Course code validation against Common Core enums
   - Confidence score ranges (0.0-1.0)

**Done When**:

- ✅ All API models defined with proper validation
- ✅ PersonNameV1 compatibility maintained
- ✅ Request/response models support all planned operations
- ✅ Validation catches common input errors

### Checkpoint 2.5: Event Publishing Integration

**Objective**: Integrate with Common Core event contracts and establish real-time update publishing.

**Implementation Requirements**:

1. **Event Publisher Protocol**:
   - `ClassEventPublisherProtocol`: Interface for class management events
   - Support for `ClassCreatedV1`, `ClassUpdatedV1`, `StudentCreatedV1`, `StudentUpdatedV1`
   - `EssayStudentAssociationUpdatedV1` event publishing

2. **Event Publisher Implementation**:
   - Use KafkaBus from service library
   - Follow topic naming: `huleedu.class.{entity}.{action}.v1`
   - Include proper correlation ID tracking
   - Error handling and retry logic

3. **DI Integration**:
   - Register event publisher in `di.py`
   - Inject into service implementations
   - Follow established Dishka patterns

4. **Event Publishing Points**:
   - Class creation/update operations
   - Student creation/update operations
   - Essay-student association changes
   - Batch student parsing completion

**Done When**:

- ✅ Event publisher protocol and implementation complete
- ✅ All required events are published at appropriate points
- ✅ Events follow Common Core contracts exactly
- ✅ DI integration follows service library patterns

### Checkpoint 2.6: Docker Integration & Testing

**Objective**: Containerize service and implement comprehensive testing following established patterns.

**Implementation Requirements**:

1. **Docker Configuration**:
   - `Dockerfile` with `PYTHONPATH=/app` environment
   - `docker-compose.services.yml` integration
   - Health check configuration
   - Proper service networking

2. **Testing Implementation**:
   - Unit tests for all protocol implementations
   - Integration tests for API endpoints
   - Database integration tests
   - Event publishing tests with KafkaBus mocking

3. **Testing Patterns**:
   - Follow established Quart+Dishka testing patterns
   - Protocol mocking for dependencies
   - Comprehensive error scenario coverage
   - PersonNameV1 compliance validation

4. **Configuration Management**:
   - `config.py` with Pydantic settings
   - Environment variable configuration
   - Database connection settings
   - Kafka topic configuration

**Done When**:

- ✅ Service builds and runs in Docker container
- ✅ All tests pass with comprehensive coverage
- ✅ Service integrates properly with docker-compose
- ✅ Health checks and metrics endpoints functional

## Implementation Notes

### Name Parsing Logic (ADL-01 Compliance)

```python
def parse_student_name(full_name: str) -> ParsedNameMetadata:
    """
    Parse full name into PersonNameV1-compatible components.
    
    Handles Swedish/English naming patterns:
    - "Anna Andersson" → first_name="Anna", last_name="Andersson", confidence=0.9
    - "Erik Johan Svensson" → first_name="Erik Johan", last_name="Svensson", confidence=0.8
    - Single names treated as last_name with lower confidence
    """
```

### Database Constraints

- **Unique email per teacher**: Students must have unique emails within teacher scope
- **Cascade deletion**: Removing teacher removes all associated classes and students
- **Foreign key integrity**: Proper relationships between courses, classes, and students
- **Soft deletion**: Maintain audit trails for educational data

### CSV Export Benefits

With separated name fields, CSV exports become more useful:

- Better sorting capabilities (by last name)
- External system integration compatibility
- Mail merge template support
- Name pattern analysis capabilities

## Testing Requirements

### Unit Tests

- Protocol implementation testing with mocks
- Database model validation
- Name parsing logic verification
- Event publishing functionality

### Integration Tests

- API endpoint testing with authentication (use file_service integration tests as reference)
- Database operations with real connections
- Event publishing with Kafka integration
- PersonNameV1 compliance verification

### Performance Considerations

- Database indexing on user_id and email fields
- Efficient many-to-many relationship queries
- Event publishing performance under load
- Memory usage with large class rosters

## Future Enhancements

Document in `documentation/SERVICE_FUTURE_ENHANCEMENTS/class_management_service_roadmap.md`:

- Organization support for multi-teacher classes
- Privacy compliance features (GDPR/FERPA)
- Advanced student analytics
- Bulk import/export capabilities
- Integration with external student information systems
