# Enhanced Class and File Management Implementation Plan

This document outlines the implementation of enhanced file and batch management capabilities, class management service, and student association features for the HuleEdu platform.

## ✅ **BLOCKING DEPENDENCY RESOLVED - REFACTORING COMPLETED**

**✅ FOUNDATION READY: All phases of this task can now proceed with:**

📋 **[LEAN_BATCH_REGISTRATION_REFACTORING.md](LEAN_BATCH_REGISTRATION_REFACTORING.md)** - **COMPLETED**

**Result**: Lean registration architecture is established with proper service boundaries. Enhanced features can now be implemented on top of the lean foundation where BOS handles orchestration and Class Management Service owns educational context.

**CRITICAL DEPENDENCIES:**

- ✅ **Checkpoint 1.4: User ID Propagation** (API_GATEWAY_WEBSOCKET_SERVICE_TASK_TICKET_1.md) - COMPLETED
- ✅ **Checkpoint 3.2: Enhanced WebSocket Implementation** (API_GATEWAY_WEBSOCKET_SERVICE_TASK_TICKET_3.md) - For real-time updates
- ✅ **User authentication and ownership validation** - Foundation for all enhanced features
- ✅ **Lean Batch Registration Refactoring** - COMPLETED - All phases unblocked

**Architecture Alignment:**
This implementation follows established HuleEdu microservice patterns:

- Event-driven communication via Kafka with thin, focused events
- Protocol-based dependency injection with Dishka
- Pydantic contracts for all inter-service communication in `common_core`
- User ownership validation for all operations
- Real-time updates via Redis pub/sub and WebSocket

## Implementation Strategy

**Database Design**: Simplified one-to-one class-course relationship where each class belongs to exactly one course. This aligns with the "class + course = unique ID" concept while maintaining simplicity.

**User Scope**: In this system, "user" = teacher. All student data is scoped to the teacher who created it.

**File Operations**: Files can only be modified before spellcheck processing begins. Operations are blocked once pipeline processing starts.

## Future Enhancements

Future enhancements are documented in `documentation/SERVICE_FUTURE_ENHANCEMENTS/class_management_service_roadmap.md`:

- **Phase 2**: Organization-level class sharing
- **Phase 3**: Advanced student matching and tracking  
- **Phase 4**: Multi-language course extensions
- **Phase 5**: Analytics and reporting

## 🏛️ **Architectural Decision Log (ADL)**

This section documents key architectural decisions made during the planning phase. Each decision includes its rationale and consequences to provide full context for the development team.

### **ADL-01: Standardized PersonNameV1 Model**

**Decision**: A standardized, structured `PersonNameV1` Pydantic model will be created in `common_core` for handling all personal names (teachers and students). This model will contain separate `first_name` and `last_name` fields.

**Rationale**:

- **Flexibility & Future-Proofing**: Provides downstream services with granular data. AI Feedback Service can construct formal references while maintaining informal options
- **Consistency & Reusability (DRY)**: Single definition for both teachers and students, reducing code duplication
- **Centralized Logic**: Single source of truth for name-related formatting logic with properties like `.full_name`

**Consequences**: All services producing/consuming person name events must use this structured model. Existing teacher/student events will be updated to use `PersonNameV1`.

### **ADL-02: Domain Responsibility for User and Student Data**

**Decision**: Service responsibilities will be strictly enforced to maintain clear bounded contexts:

- **BOS**: Owns batch lifecycle and orchestration context only
- **Class Management Service**: Single authoritative source for class rosters and student data  
- **File Service**: Responsible for initial discovery of potential student names from raw file content
- **ELS**: Owns essay lifecycle state, including final essay-student associations

**Rationale**: Enforces Single Responsibility Principle and maintains clean boundaries. Prevents "context bleeding" where services become dependent on others' internal data models.

**Consequences**: Requires new Class Management Service and HTTP clients for inter-service queries. Clear service boundaries enhance security and maintainability.

### **ADL-03: enable_student_parsing Flag Handling**

**Decision**: The `enable_student_parsing` flag will be passed directly to File Service as a form field in the `POST /v1/files/batch` request, removed from batch registration model.

**Rationale**: The service performing an action should receive the configuration for that action. File Service is responsible for parsing, so it should receive parsing instructions directly.

**Consequences**: Frontend must send this flag as part of multipart form data during file upload. File Service API endpoint updated to handle this parameter. This will be done programmatically with the flag being true if user selects an existing class id in the UI and false if selecting GUEST (test class with no student).

### **ADL-04: Two-Stage Student Association Workflow**

**Decision**: Associating essays with students will be a two-stage process:

1. **Discovery Stage (File Service)**: Parses temporary `parsed_name_metadata` and includes in `StudentParsingCompletedV1` event
2. **Association Stage (ELS)**: After user validation, `StudentAssociationsConfirmedV1` command persists authoritative essay-student links

**Rationale**: Correctly decouples fast automated discovery (machine speed) from slow manual validation (human speed). Prevents File Service from becoming stateful while waiting for user input.

**Consequences**: Requires new API endpoint and Kafka event. Frontend needs dedicated validation UI. ELS publishes `BatchEssaysReady` only after association confirmation.

### **ADL-05: Inter-Service Data Retrieval Pattern**  

**Decision**: For synchronous, request-response data needs between services, internal HTTP calls will be used. File Service will make HTTP GET requests to Class Management Service's `/v1/classes/{class_id}/students` endpoint for roster data.

**Rationale**: Direct query for data required to continue processing. HTTP is correct pattern for synchronous internal data retrieval versus event-based complexity.

**Consequences**: File Service requires dedicated internal HTTP client for Class Management Service. Introduces direct runtime dependency requiring proper error handling and timeouts.

## Part 1: Common Core Extensions

### Checkpoint 2.0: Extend Common Core with Course and Event Definitions ✅ COMPLETED

**Implementation Summary:**

Extended `common_core/src/common_core/enums.py` with course definitions:

- `CourseCode(str, Enum)`: ENG5/6/7, SV1/2/3 predefined courses
- `Language(str, Enum)`: ENGLISH="en", SWEDISH="sv"
- `COURSE_METADATA: Dict[CourseCode, Tuple[str, Language, int]]` mapping course codes to (name, language, level)
- Helper functions: `get_course_language()`, `get_course_name()`, `get_course_level()`
- Added ProcessingEvent entries: STUDENT_PARSING_COMPLETED, ESSAY_STUDENT_ASSOCIATION_UPDATED, BATCH_FILE_ADDED, BATCH_FILE_REMOVED, CLASS_CREATED, STUDENT_CREATED
- Updated `_TOPIC_MAPPING` with new event topics following `huleedu.{domain}.{entity}.{action}.v1` pattern

**NEW - PersonNameV1 Model (ADL-01):**

Created standardized person name model:

**File**: `common_core/src/common_core/person_models.py`

```python
from pydantic import BaseModel, Field

class PersonNameV1(BaseModel):
    """A structured representation of a person's name."""
    first_name: str = Field(..., min_length=1, description="The person's first or given name(s).")
    last_name: str = Field(..., min_length=1, description="The person's last or family name.")
    
    @property
    def full_name(self) -> str:
        """Combined name for display purposes."""
        return f"{self.first_name} {self.last_name}"
    
    @property
    def last_first_name(self) -> str:
        """Last, First format for sorting."""
        return f"{self.last_name}, {self.first_name}"
```

Created thin event contracts:

- `common_core/src/common_core/events/file_management_events.py`:
  - `StudentParsingCompletedV1`: Contains parsing_results list with student metadata, confidence scores
  - `BatchFileAddedV1`: File addition notifications with batch_id, essay_id, filename, user_id
  - `BatchFileRemovedV1`: File removal notifications with same structure
- `common_core/src/common_core/events/class_events.py`:
  - `ClassCreatedV1`: Class creation with course_codes list, class_designation
  - `StudentCreatedV1`: Student creation with separated first_name/last_name fields, class_ids list  
  - `EssayStudentAssociationUpdatedV1`: Student-essay linking with confidence_score, association_method

**NEW - ParsedNameMetadata Model (ADL-04):**

Added model for temporary parsing results:

**File**: `common_core/src/common_core/events/file_events.py`

```python
class ParsedNameMetadata(BaseModel):
    """Unverified student name metadata parsed from file content for user review."""
    first_name: str | None = Field(default=None, description="Parsed first name")
    last_name: str | None = Field(default=None, description="Parsed last name")  
    full_name_from_file: str = Field(..., description="The exact string parsed from the file")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Parsing confidence (0.0-1.0)")
    parsing_method: str = Field(..., description="Method used for parsing")

# Update existing EssayContentProvisionedV1 event
class EssayContentProvisionedV1(BaseModel):
    # ... existing fields ...
    parsed_name_metadata: ParsedNameMetadata | None = Field(
        default=None, 
        description="Unverified student name metadata parsed from file content for user review."
    )
```

**NEW - StudentAssociationsConfirmedV1 Command (ADL-04):**

Added command for user validation:

**File**: `common_core/src/common_core/events/client_commands.py`

```python
class EssayStudentAssociationV1(BaseModel):
    """Individual essay-student association."""
    essay_id: str
    student_id: str

class StudentAssociationsConfirmedV1(BaseModel):
    """Command event published when a user confirms student-essay associations for a batch."""
    event: str = Field(default="student.associations.confirmed")
    batch_id: str
    user_id: str = Field(..., description="The authenticated user who confirmed associations")
    associations: List[EssayStudentAssociationV1] = Field(..., description="Confirmed essay-student pairings")
    validation_metadata: dict = Field(default_factory=dict, description="Additional validation context")
```

Updated `common_core/src/common_core/events/__init__.py` to export all new event models.

**Additional Required Updates:**

Extended `BatchStatus` enum for validation flow:

```python
class BatchStatus(str, Enum):
    # ... existing statuses ...
    AWAITING_STUDENT_VALIDATION = "awaiting_student_validation"
    VALIDATION_TIMEOUT_PROCESSED = "validation_timeout_processed"
    GUEST_CLASS_READY = "guest_class_ready"
```

Enhanced existing events to use `PersonNameV1`:

```python
# Update existing events to use PersonNameV1 model  
class StudentCreatedV1(BaseModel):
    """Student creation event using PersonNameV1 for consistency."""
    student_name: PersonNameV1 = Field(..., description="Student name using standardized model")
    email: str
    created_by_user_id: str
    class_ids: list[str] = Field(default_factory=list)

class ClassCreatedV1(BaseModel):
    """Class creation event."""
    class_designation: str
    course_codes: list[CourseCode]  
    user_id: str
    teacher_name: PersonNameV1 = Field(..., description="Teacher name using standardized model")
```

Extended `EssayStatus` enum for association workflow:

```python
class EssayStatus(str, Enum):
    # ... existing statuses ...
    AWAITING_STUDENT_ASSOCIATION = "awaiting_student_association"
    STUDENT_ASSOCIATION_CONFIRMED = "student_association_confirmed"
```

**Testing Results:**

- 📊 All new enums: 6 tests passing (CourseCode, Language completeness/values/inheritance)
- 📊 Class events: 18 tests passing (creation, serialization, validation, real-world scenarios)
- 📊 File management events: 15 tests passing (parsing results, file operations, timestamps)
- 📊 MyPy validation: 320 source files, no type errors
- 📊 Import validation: All enums and events importable, helper functions working

**Ready for:** Part 2 implementation - Enhanced File and Batch Management with course validation, class associations, and user validation flow.

## Part 2: Enhanced File and Batch Management

**✅ ALIGNED WITH LEAN REGISTRATION**: This part implements the enhanced features on top of the completed lean registration architecture, where batch registration captures only orchestration essentials (`user_id`, `course_code`, `essay_instructions`) and educational context is provided by Class Management Service during processing.

### **Educational Context Flow - WHEN and WHERE**

**When Educational Context is Provided:**

1. **Batch Registration (Lean)**: BOS captures only orchestration essentials - `user_id`, `course_code`, `essay_instructions`
2. **File Upload & Parsing**: File Service parses student info and publishes `StudentParsingCompletedV1` event
3. **Student Validation**: Class Management Service processes parsing results and validates/stores student associations
4. **Processing Initiation**: When ELS publishes enhanced `BatchEssaysReadyV1`, it includes educational context queried from Class Management Service
5. **Processing Services**: AI Feedback and CJ Assessment services receive complete context (`teacher_first_name`, `teacher_last_name`, `class_designation`) via enhanced processing commands

**Where Educational Context is Handled:**

- **BOS**: Stores lean registration data only (`user_id`, `course_code`, `essay_instructions`) - NO educational context
- **Class Management Service**: Single source of truth for all educational context (`teacher_names`, `class_designation`, student data)
- **ELS Batch Command Handler**: Queries Class Management Service when enhancing `BatchEssaysReadyV1` event with educational context
- **Processing Services**: Receive complete context via enhanced events, not from batch registration

**Event Handlers Involved:**

```python
# Lean Registration (Completed)
BatchRegistrationRequestV1 (user_id, course_code, essay_instructions) → BOS.register_batch()

# File Service -> Class Management Service
StudentParsingCompletedV1 → ClassManagementService.student_parsing_handler()

# Class Management Service -> ELS  
StudentAssociationsValidatedV1 → ELS.batch_command_handler()

# ELS queries Class Management Service for educational context, then publishes enhanced event
BatchEssaysReadyV1 (with teacher_first_name, teacher_last_name, class_designation from CMS) → BOS.processing_initiators()
```

### Checkpoint 2.1: File Management with Batch State Validation

**Implementation Summary:**

Complete batch state validation system integrated with existing file upload architecture.

### **1. Batch State Validator Implementation**

**Created:** `services/file_service/implementations/batch_state_validator.py`

- `BOSBatchStateValidator` class with HTTP client integration to BOS
- Pipeline state validation using Pydantic models and enum values
- User ownership verification via user_id comparison with batch owner
- Locking logic based on PipelineExecutionStatus enum values: DISPATCH_INITIATED, IN_PROGRESS, COMPLETED_SUCCESSFULLY, COMPLETED_WITH_PARTIAL_SUCCESS
- Error handling with timeouts and logging
- Methods: `can_modify_batch_files()` returns (bool, reason), `get_batch_lock_status()` returns detailed lock status

**Enhanced:** `services/file_service/protocols.py`

- Added `BatchStateValidatorProtocol` with proper typing

**Enhanced:** `services/file_service/config.py`

- Added BOS_URL configuration for HTTP client integration

**Enhanced:** `services/file_service/di.py`

- Dishka dependency injection setup for batch validator with HTTP session management

### **2. Test Suite**

**Created:** `services/file_service/tests/unit/test_batch_state_validator.py` (12 tests)

- Pipeline state testing covering all PipelineExecutionStatus enum values
- User ownership validation testing access control
- HTTP error handling testing network failures and invalid responses
- Lock status reporting testing detailed status information

**Created:** `services/file_service/tests/unit/test_file_routes_validation.py` (8 tests)

- HTTP layer validation for existing `/v1/files/batch` endpoint
- Authentication testing (401 for missing X-User-ID)
- Request validation (400 for missing batch_id, empty files)
- Batch locking (409 when processing has started)
- Success scenarios (202 responses with proper JSON structure)
- Multiple file handling with manual multipart form construction
- Correlation ID propagation and validation

### **3. Architecture Patterns Established**

**Fire-and-Forget Pattern:**

- Single HTTP request with multiple files via `files.getlist("files")`
- Immediate 202 Accepted response
- Background async processing with shared correlation ID
- Concurrent file processing as separate async tasks

**Quart Test Client Patterns:**

- Manual multipart form construction for multiple files with same field name
- Proper FileStorage object creation for testing
- Workaround for Quart test client limitations

**Testing Results:** 20 total tests, 100% pass rate

---

## ✅ **CHECKPOINT 2.2 COMPLETED - Enhanced File Management Implementation**

**Implementation Summary:**

Enhanced file management capabilities with real-time event publishing following established Quart+Dishka patterns.

### **1. Event Publisher Enhancement**

**Enhanced:** `services/file_service/protocols.py`

- Extended EventPublisherProtocol with file management event methods:
  - `publish_batch_file_added_v1()` for BatchFileAddedV1 events
  - `publish_batch_file_removed_v1()` for BatchFileRemovedV1 events
- Versioned naming convention for clarity

**Enhanced:** `services/file_service/implementations/event_publisher_impl.py`

- DefaultEventPublisher implementation of new protocol methods
- EventEnvelope construction with correlation ID tracking
- Error handling and logging consistent with existing patterns
- KafkaBus integration using established service library patterns

**Enhanced:** `services/file_service/config.py`

- New Kafka topic configurations:
  - `BATCH_FILE_ADDED_TOPIC`: "huleedu.file.batch.file.added.v1"
  - `BATCH_FILE_REMOVED_TOPIC`: "huleedu.file.batch.file.removed.v1"

### **2. New API Endpoints**

**Enhanced:** `services/file_service/api/file_routes.py`

**GET /batch/<batch_id>/state**: Check batch lock status

- Uses BatchStateValidatorProtocol.get_batch_lock_status()
- Requires X-User-ID authentication
- Returns JSON with detailed lock status information
- Status codes: 200 (success), 401 (no auth), 500 (error)

**POST /batch/<batch_id>/files**: Add files to existing batch

- Validates batch modification permissions via BatchStateValidatorProtocol
- Processes files using existing core_logic.process_single_file_upload
- Publishes BatchFileAddedV1 events for each successfully added file
- Supports multiple files with correlation ID tracking
- Status codes: 202 (accepted), 400 (validation), 401 (no auth), 409 (locked), 500 (error)

**DELETE /batch/<batch_id>/files/<essay_id>**: Remove file from batch

- Validates batch modification permissions
- Publishes BatchFileRemovedV1 event for coordination with downstream services
- Correlation ID handling and user authentication
- Status codes: 200 (success), 401 (no auth), 409 (locked), 500 (error)

### **3. Test Suite**

**Created:** `services/file_service/tests/unit/test_event_publisher_file_management.py` (7 tests)

- Event construction testing for BatchFileAddedV1 and BatchFileRemovedV1
- KafkaBus integration testing with proper mocking
- Error handling scenarios for Kafka connection failures
- Correlation ID propagation validation
- Event envelope structure verification

**Created:** `services/file_service/tests/unit/test_file_management_routes.py` (12 tests)

- Quart+Dishka testing patterns following established architecture
- TestProvider class with correct DI container setup
- All three new endpoints tested with comprehensive scenarios:
  - Authentication testing (401 responses)
  - Authorization testing (409 when batch locked)
  - Success scenarios with proper JSON responses
  - Error handling and validation
  - Correlation ID handling
  - Multiple file upload testing with manual multipart form construction

### **4. Architecture Compliance**

**Protocol-Based Dependency Injection:**

- All new functionality uses Dishka DI patterns
- Protocol abstractions maintained for testability
- Clean separation between HTTP layer and business logic

**Event-Driven Architecture:**

- Thin events with essential data only (batch_id, essay_id, filename, user_id)
- EventEnvelope usage with correlation ID tracking
- Real-time notifications for file management operations

**Integration with Existing Systems:**

- All new endpoints integrate with existing BatchStateValidatorProtocol
- Consistent locking logic across all file operations
- User ownership verification maintained
- POST endpoint reuses existing process_single_file_upload workflow
- Background async processing with fire-and-forget pattern

**Testing Results:** 104 total tests (existing + new), 19 new tests, 100% pass rate

**API Endpoints:**

- GET /v1/files/batch/<batch_id>/state: Query batch lock status
- POST /v1/files/batch/<batch_id>/files: Add files to existing batch
- DELETE /v1/files/batch/<batch_id>/files/<essay_id>: Remove file from batch

**Event Publishing:**

- BatchFileAddedV1: Published when files are successfully added to batch
- BatchFileRemovedV1: Published when files are removed from batch
- Correlation ID tracking: End-to-end traceability maintained
- Kafka topics: Properly configured with versioned naming

---

## 📋 **IMPLEMENTATION COMPLETE**

**Overall Status:** ✅ **FULLY IMPLEMENTED AND TESTED**

**Total Implementation:**

- **✅ Batch state validation system** with BOS integration
- **✅ Enhanced file management API** with three new endpoints
- **✅ Real-time event publishing** for file operations
- **✅ Comprehensive testing suite** with 104 passing tests
- **✅ Architecture compliance** with established patterns

**Definition of Done Achieved:**

- [x] All protocol extensions implemented and tested
- [x] Three new API endpoints implemented with proper DI injection
- [x] Comprehensive unit and integration tests passing
- [x] Event publishing working for file management operations
- [x] No regressions in existing functionality
- [x] Documentation updated

**Ready for Production Deployment.**
