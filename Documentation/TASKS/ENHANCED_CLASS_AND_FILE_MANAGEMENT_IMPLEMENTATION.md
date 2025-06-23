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

**Consequences**: Frontend must send this flag as part of multipart form data during file upload. File Service API endpoint updated to handle this parameter.

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

**Objective**: Implement file add/remove operations with proper batch state validation, ensuring files cannot be modified after spellcheck begins. This builds on the lean registration architecture where educational context is handled separately.

**Key Features**:

- File operations blocked when spellcheck has started
- User ownership validation via `user_id` from lean registration
- Real-time events published for file additions/removals  
- Batch state information available to clients
- Clear error messages for operation failures
- **Integration with lean registration**: File operations validate against lean batch context (no educational data required)

**Affected Files**:

- `services/file_service/api/file_routes.py`
- `services/file_service/implementations/batch_state_validator.py` (new)
- `services/file_service/implementations/event_publisher_impl.py` (enhanced)
- `services/file_service/protocols.py`

**Implementation Steps**:

1. **Batch State Validation Protocol**: Define protocol for validating batch modification permissions.

**File**: `services/file_service/protocols.py`

```python
from typing import Protocol
from datetime import datetime

class BatchStateValidatorProtocol(Protocol):
    """Protocol for validating batch state and modification permissions."""

    async def can_modify_batch_files(self, batch_id: str, user_id: str) -> tuple[bool, str]:
        """
        Check if batch files can be modified.

        Returns:
            tuple[bool, str]: (can_modify, reason_if_not)
        """
        ...

    async def get_batch_lock_status(self, batch_id: str) -> dict:
        """Get detailed batch lock status information."""
        ...

class FileEventPublisherProtocol(Protocol):
    """Enhanced protocol for publishing file management events."""

    async def publish_file_added_event(
        self,
        batch_id: str,
        essay_id: str,
        filename: str,
        user_id: str
    ) -> None:
        """Publish real-time update when file is added to batch."""
        ...

    async def publish_file_removed_event(
        self,
        batch_id: str,
        essay_id: str,
        filename: str,
        user_id: str
    ) -> None:
        """Publish real-time update when file is removed from batch."""
        ...

    async def publish_batch_locked_event(
        self,
        batch_id: str,
        locked_at: datetime,
        reason: str,
        user_id: str
    ) -> None:
        """Publish real-time update when batch becomes locked."""
        ...
```

2. **Batch State Validator Implementation**: Create validator that queries BOS for batch state.

**File**: `services/file_service/implementations/batch_state_validator.py`

```python
import aiohttp
from datetime import datetime
from huleedu_service_libs.logging_utils import create_service_logger
from ..protocols import BatchStateValidatorProtocol
from ..config import Settings

logger = create_service_logger("file_service.batch_state_validator")

class BOSBatchStateValidator:
    """Validates batch state by querying BOS for pipeline status."""

    def __init__(self, http_session: aiohttp.ClientSession, settings: Settings):
        self.http_session = http_session
        self.settings = settings

    async def can_modify_batch_files(self, batch_id: str, user_id: str) -> tuple[bool, str]:
        """
        Check if batch files can be modified by querying BOS pipeline state.

        Files cannot be modified if:
        - Spellcheck phase has started (IN_PROGRESS or COMPLETED)
        - Batch is in any processing state beyond READY_FOR_PIPELINE_EXECUTION
        """
        try:
            # Query BOS for current pipeline state
            bos_url = f"{self.settings.BOS_URL}/internal/v1/batches/{batch_id}/pipeline-state"

            async with self.http_session.get(bos_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 404:
                    return False, "Batch not found"
                elif response.status != 200:
                    logger.error(f"BOS query failed for batch {batch_id}: status {response.status}")
                    return False, "Unable to verify batch state"

                pipeline_data = await response.json()
                pipeline_state = pipeline_data.get("pipeline_state", {})

                # Verify user ownership
                batch_user_id = pipeline_data.get("user_id")
                if batch_user_id != user_id:
                    return False, "Access denied: You don't own this batch"

                # Check if spellcheck has started
                spellcheck_status = pipeline_state.get("SPELLCHECK", {}).get("status")
                if spellcheck_status in ["IN_PROGRESS", "COMPLETED"]:
                    return False, "Batch is locked: Spellcheck has started"

                # Check if any processing has started
                for phase, phase_data in pipeline_state.items():
                    if isinstance(phase_data, dict) and phase_data.get("status") in ["IN_PROGRESS", "COMPLETED"]:
                        return False, f"Batch is locked: {phase} processing has started"

                return True, "Batch can be modified"

        except Exception as e:
            logger.error(f"Error validating batch state for {batch_id}: {e}", exc_info=True)
            return False, "Unable to verify batch state"

    async def get_batch_lock_status(self, batch_id: str) -> dict:
        """Get detailed batch lock status for client information."""
        try:
            bos_url = f"{self.settings.BOS_URL}/internal/v1/batches/{batch_id}/pipeline-state"

            async with self.http_session.get(bos_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200:
                    return {"locked": True, "reason": "Unable to verify batch state"}

                pipeline_data = await response.json()
                pipeline_state = pipeline_data.get("pipeline_state", {})

                # Determine lock status and reason
                for phase, phase_data in pipeline_state.items():
                    if isinstance(phase_data, dict) and phase_data.get("status") in ["IN_PROGRESS", "COMPLETED"]:
                        return {
                            "locked": True,
                            "reason": f"{phase} processing has started",
                            "locked_at": phase_data.get("started_at"),
                            "current_phase": phase,
                            "phase_status": phase_data.get("status")
                        }

                return {
                    "locked": False,
                    "reason": "Batch is open for modifications",
                    "current_state": "READY_FOR_MODIFICATIONS"
                }

        except Exception as e:
            logger.error(f"Error getting batch lock status for {batch_id}: {e}", exc_info=True)
            return {"locked": True, "reason": "Unable to verify batch state"}
```

3. **Enhanced File Management Endpoints**: Add new endpoints for file operations with state validation.

**File**: `services/file_service/api/file_routes.py`

```python
from quart import Blueprint, request, jsonify
from quart_dishka import inject
from dishka import FromDishka
from ..protocols import BatchStateValidatorProtocol, FileEventPublisherProtocol
from ..core_logic import FileProcessingLogic
from huleedu_service_libs.logging_utils import create_service_logger

file_bp = Blueprint("file_routes", __name__)
logger = create_service_logger("file_service.file_routes")

@file_bp.route("/batch/<batch_id>/state", methods=["GET"])
@inject
async def get_batch_processing_state(
    batch_id: str,
    batch_validator: FromDishka[BatchStateValidatorProtocol],
):
    """Get current batch processing state and lock status."""
    try:
        lock_status = await batch_validator.get_batch_lock_status(batch_id)
        return jsonify({
            "batch_id": batch_id,
            "lock_status": lock_status,
            "can_modify_files": not lock_status.get("locked", True)
        }), 200

    except Exception as e:
        logger.error(f"Error getting batch state for {batch_id}: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@file_bp.route("/batch/<batch_id>/files", methods=["POST"])
@inject
async def add_files_to_batch(
    batch_id: str,
    batch_validator: FromDishka[BatchStateValidatorProtocol],
    file_processor: FromDishka[FileProcessingLogic],
    event_publisher: FromDishka[FileEventPublisherProtocol],
):
    """Add files to an existing batch with state validation."""
    try:
        # Get user_id from authenticated request (provided by API Gateway)
        user_id = request.headers.get("X-User-ID")
        if not user_id:
            return jsonify({"error": "User authentication required"}), 401

        # Validate batch can be modified
        can_modify, reason = await batch_validator.can_modify_batch_files(batch_id, user_id)
        if not can_modify:
            return jsonify({
                "error": "Cannot add files to batch",
                "reason": reason
            }), 409

        # Process uploaded files
        files = await request.files
        if not files:
            return jsonify({"error": "No files provided"}), 400

        uploaded_files = []
        for file_key, file_obj in files.items():
            if file_obj.filename:
                # Process file with existing logic
                essay_id, processed_content = await file_processor.process_uploaded_file(
                    file_obj, batch_id, user_id
                )

                uploaded_files.append({
                    "essay_id": essay_id,
                    "filename": file_obj.filename,
                    "status": "uploaded"
                })

                # Publish real-time update
                await event_publisher.publish_file_added_event(
                    batch_id, essay_id, file_obj.filename, user_id
                )

        logger.info(f"Added {len(uploaded_files)} files to batch {batch_id} for user {user_id}")

        return jsonify({
            "batch_id": batch_id,
            "files_added": uploaded_files,
            "total_files": len(uploaded_files)
        }), 201

    except Exception as e:
        logger.error(f"Error adding files to batch {batch_id}: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@file_bp.route("/batch/<batch_id>/files/<essay_id>", methods=["DELETE"])
@inject
async def remove_file_from_batch(
    batch_id: str,
    essay_id: str,
    batch_validator: FromDishka[BatchStateValidatorProtocol],
    file_processor: FromDishka[FileProcessingLogic],
    event_publisher: FromDishka[FileEventPublisherProtocol],
):
    """Remove a file from a batch with state validation."""
    try:
        # Get user_id from authenticated request
        user_id = request.headers.get("X-User-ID")
        if not user_id:
            return jsonify({"error": "User authentication required"}), 401

        # Validate batch can be modified
        can_modify, reason = await batch_validator.can_modify_batch_files(batch_id, user_id)
        if not can_modify:
            return jsonify({
                "error": "Cannot remove files from batch",
                "reason": reason
            }), 409

        # Remove file with existing logic
        filename = await file_processor.remove_file_from_batch(batch_id, essay_id, user_id)

        # Publish real-time update
        await event_publisher.publish_file_removed_event(
            batch_id, essay_id, filename, user_id
        )

        logger.info(f"Removed file {essay_id} from batch {batch_id} for user {user_id}")

        return jsonify({
            "batch_id": batch_id,
            "essay_id": essay_id,
            "filename": filename,
            "status": "removed"
        }), 200

    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        logger.error(f"Error removing file {essay_id} from batch {batch_id}: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
```

**Done When**:

- ✅ File operations are blocked when spellcheck has started
- ✅ User ownership is validated for all file operations
- ✅ Real-time events are published for file additions/removals
- ✅ Batch state information is available to clients
- ✅ Error messages provide clear reasons for operation failures

### Checkpoint 2.2: Class Management Service Foundation

**Objective**: Implement a new microservice for managing user classes, students, and their relationships with courses and essays.

**Key Features**:

- Complete service structure following HuleEdu patterns
- Database models supporting many-to-many relationships
- API models with comprehensive validation
- Service containerized and integrated with docker-compose

**Affected Files**:

- New service directory: `services/class_management_service/`
- `docker-compose.services.yml`
- `common_core/src/common_core/events/class_events.py` (new)

**Implementation Steps**:

1. **Service Structure and Database Models**: Create the complete service structure following HuleEdu patterns.

**File**: `services/class_management_service/models_db.py`

```python
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Float, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
from typing import Optional

Base = declarative_base()

# Association table for many-to-many relationship between classes and students
class_student_association = Table(
    'class_student_associations',
    Base.metadata,
    Column('class_id', String(36), ForeignKey('user_classes.id', ondelete='CASCADE'), primary_key=True),
    Column('student_id', String(36), ForeignKey('students.id', ondelete='CASCADE'), primary_key=True),
    Column('created_at', DateTime, default=datetime.utcnow)
)

# Note: Simplified one-to-one class-course relationship (each class belongs to exactly one course)

class Course(Base):
    """Predefined courses with language and skill level information."""
    __tablename__ = "courses"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)  # ENG5, SV1, etc.
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)  # "en", "sv"
    skill_level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-7
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships (one-to-many: one course can have multiple classes)
    classes = relationship("UserClass", back_populates="course")

class UserClass(Base):
    """Teacher-owned class designations with one-to-one course relationship."""
    __tablename__ = "user_classes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    class_designation: Mapped[str] = mapped_column(String(255), nullable=False)
    course_code: Mapped[str] = mapped_column(String(10), ForeignKey("courses.code"), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    students = relationship("Student", secondary=class_student_association, back_populates="classes")
    course = relationship("Course", back_populates="classes")

class Student(Base):
    """Student entities using PersonNameV1 pattern for consistency (ADL-01)."""
    __tablename__ = "students"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_full_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Full parsed name from file
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def full_name(self) -> str:
        """Combined name for display purposes (matches PersonNameV1.full_name)."""
        return f"{self.first_name} {self.last_name}"

    @property
    def last_first_name(self) -> str:
        """Last, First format for sorting (matches PersonNameV1.last_first_name)."""
        return f"{self.last_name}, {self.first_name}"
    
    def to_person_name_v1(self) -> "PersonNameV1":
        """Convert to PersonNameV1 for event publishing."""
        from common_core.person_models import PersonNameV1
        return PersonNameV1(first_name=self.first_name, last_name=self.last_name)

    # Relationships - students can belong to multiple classes
    classes = relationship("UserClass", secondary=class_student_association, back_populates="students")
    essay_associations = relationship("EssayStudentAssociation", back_populates="student")

class EssayStudentAssociation(Base):
    """Associates essays with students (manual or parsed)."""
    __tablename__ = "essay_student_associations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    essay_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    association_method: Mapped[str] = mapped_column(String(20), nullable=False)  # "parsed" or "manual"
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Relationships
    student = relationship("Student", back_populates="essay_associations")
```

2. **Service API Models**: Define request/response models for the class management API.

**File**: `services/class_management_service/api_models.py`

```python
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from common_core.enums import CourseCode

class CreateClassRequest(BaseModel):
    """Request to create a new class."""
    class_designation: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    course_codes: List[CourseCode] = Field(..., min_items=1, description="Courses this class is associated with")

class UpdateClassRequest(BaseModel):
    """Request to update an existing class."""
    class_designation: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    course_codes: Optional[List[CourseCode]] = Field(None, min_items=1)

class CreateStudentRequest(BaseModel):
    """Request to create a new student with separated name fields."""
    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr = Field(...)
    class_ids: Optional[List[str]] = Field(None, description="Classes to associate student with")

class UpdateStudentRequest(BaseModel):
    """Request to update an existing student."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=255)
    last_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = Field(None)

class EssayStudentAssociationRequest(BaseModel):
    """Request to associate an essay with a student."""
    student_id: str = Field(...)
    association_method: str = Field(default="manual", pattern="^(manual|parsed)$")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)

class StudentParsingResult(BaseModel):
    """Result of automatic student parsing following PersonNameV1 pattern (ADL-01)."""
    essay_id: str
    filename: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    legal_full_name: Optional[str] = None  # Original parsed full name from file
    student_email: Optional[str] = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    parsing_method: str
    raw_text_snippet: Optional[str] = None

    @property
    def full_name(self) -> Optional[str]:
        """Combined name if both parts are available (matches PersonNameV1.full_name)."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.last_name or self.legal_full_name
    
    def to_person_name_v1(self) -> Optional["PersonNameV1"]:
        """Convert to PersonNameV1 if both name parts are available."""
        if self.first_name and self.last_name:
            from common_core.person_models import PersonNameV1
            return PersonNameV1(first_name=self.first_name, last_name=self.last_name)
        return None

# Response models
class ClassResponse(BaseModel):
    """Response model for class information."""
    id: str
    class_designation: str
    description: Optional[str]
    user_id: str
    courses: List[dict]  # Course information
    student_count: int
    created_at: datetime
    updated_at: datetime

class StudentResponse(BaseModel):
    """Response model for student information with separated name fields."""
    id: str
    first_name: str
    last_name: str
    email: str
    created_by_user_id: str
    classes: List[dict]  # Class information
    essay_count: int
    created_at: datetime
    updated_at: datetime

    @property
    def full_name(self) -> str:
        """Combined name for display purposes."""
        return f"{self.first_name} {self.last_name}"

class EssayStudentAssociationResponse(BaseModel):
    """Response model for essay-student associations."""
    id: str
    batch_id: str
    essay_id: str
    student: StudentResponse
    association_method: str
    confidence_score: Optional[float]
    created_at: datetime
```

**Done When**:

- ✅ Class Management Service structure follows HuleEdu patterns
- ✅ Database models support many-to-many relationships
- ✅ API models provide comprehensive validation
- ✅ Service is containerized and integrated with docker-compose

## Part 3: Student Association and Parsing

### Checkpoint 2.4: Enhanced Student Parsing Integration

**Objective**: Enhance existing File Service parsing capabilities with confidence scoring, class roster matching, and separated name field support.

**Enhancement Strategy**:

- Extend existing `parse_student_info()` stub in File Service
- Add fuzzy matching against teacher's known students for specific course
- Implement confidence scoring (0.0-1.0) based on match quality
- Teacher-scoped parsing (only match against teacher's students)
- Parse names into separate first/last components for better data management

**Name Parsing Logic (ADL-01 & ADL-04)**:

```python
def parse_student_name(full_name: str) -> ParsedNameMetadata:
    """
    Parse full name into PersonNameV1-compatible components with confidence scoring.
    
    Handles Swedish/English naming patterns:
    - "Anna Andersson" → ParsedNameMetadata(first_name="Anna", last_name="Andersson", confidence=0.9)
    - "Erik Johan Svensson" → ParsedNameMetadata(first_name="Erik Johan", last_name="Svensson", confidence=0.8) 
    - "Anna Margareta Svensson-Andersson" → ParsedNameMetadata(first_name="Anna", last_name="Svensson-Andersson", confidence=0.7)
    
    Returns ParsedNameMetadata for two-stage workflow (ADL-04).
    """
    if not full_name or not full_name.strip():
        return ParsedNameMetadata(
            first_name=None, last_name=None, 
            full_name_from_file="", confidence_score=0.0,
            parsing_method="empty_input"
        )
    
    original_name = full_name.strip()
    name_parts = original_name.split()
    
    if len(name_parts) == 1:
        # Single name - treat as last name, lower confidence
        return ParsedNameMetadata(
            first_name=None, last_name=name_parts[0],
            full_name_from_file=original_name, confidence_score=0.4,
            parsing_method="single_name"
        )
    elif len(name_parts) == 2:
        # First Last - highest confidence
        return ParsedNameMetadata(
            first_name=name_parts[0], last_name=name_parts[1],
            full_name_from_file=original_name, confidence_score=0.9,
            parsing_method="two_part_name"
        )
    else:
        # Multiple parts - use first and last, preserve full name
        return ParsedNameMetadata(
            first_name=name_parts[0], last_name=name_parts[-1],
            full_name_from_file=original_name, confidence_score=0.8,
            parsing_method="multi_part_name"
        )
```

**CSV Export Benefits**:

With separated name fields, CSV exports become much cleaner and more useful:

```csv
first_name,last_name,email,class_designation,course_code
Anna,Andersson,anna.andersson@school.se,9A,ENG6
Erik,Svensson,erik.svensson@school.se,9A,ENG6
Maria,Johansson,maria.johansson@school.se,9B,SV2
```

This enables:

- **Better Sorting**: Sort by last name primarily
- **External System Integration**: Many LMS systems expect separated name fields
- **Data Analysis**: Easier to analyze name patterns and demographics
- **Mail Merge**: Direct use in communication templates
- **Name Preservation**: `legal_full_name` preserves complex Swedish names like "Anna Margareta Svensson-Andersson"
- **Fuzzy Matching**: Full name available for matching against student submissions with name variations

### Checkpoint 2.5: Student-Essay Association Management

**Objective**: Provide comprehensive student-essay association capabilities with both automatic and manual assignment.

## Part 4: Real-time Integration and Frontend Support

### Checkpoint 2.6: Enhanced WebSocket Event Publishing

**Objective**: Integrate with the enhanced WebSocket implementation from API Gateway Task Ticket 3 to provide real-time updates for all class and file management operations.

**Connection to API Gateway**: This checkpoint directly implements the enhanced event types defined in **Checkpoint 3.2: Enhanced WebSocket Implementation** from `API_GATEWAY_WEBSOCKET_SERVICE_TASK_TICKET_3.md`.

### Checkpoint 2.7: API Gateway Integration Endpoints

**Objective**: Create API Gateway endpoints that integrate with the Class Management Service and enhanced File Service capabilities.

## Implementation Timeline

**Phase 1 (Connected to API Gateway Checkpoint 1.4):**

- Checkpoint 2.0: Common Core Extensions
- Checkpoint 2.1: Enhanced Batch Registration
- Checkpoint 2.2: File Management with State Validation
- Checkpoint 2.3: Class Management Service Foundation

**Phase 2 (Connected to API Gateway Checkpoint 3.2):**

- Checkpoint 2.4: Student Parsing Integration
- Checkpoint 2.5: Student-Essay Association Management
- Checkpoint 2.6: Enhanced WebSocket Event Publishing

**Phase 3 (Frontend Integration):**

- Checkpoint 2.7: API Gateway Integration Endpoints
- Frontend implementation following FRONTEND_SKELETON.md enhanced plan

## Key Architectural Decisions

### **Service Communication Patterns**

1. **Thin Events**: Business workflows, state changes, cross-service notifications with focused data
2. **HTTP**: Simple queries, immediate validation, request/response patterns (File Service ↔ BOS)
3. **Common Core**: All cross-service definitions for strict compliance

### **Data Flow**

1. **File Service** → parses students → publishes thin events with results data
2. **Class Management Service** → consumes events → updates database models
3. **Real-time updates** → Redis pub/sub → WebSocket → Frontend

### **Future-Ready Design**

1. **Organization support** stubbed for class sharing between teachers
2. **Privacy compliance** fields stubbed for GDPR/FERPA requirements
3. **Course extensibility** designed for additional language/level support

## Key Benefits

1. **Seamless User Experience**: Teachers can manage files, classes, and students in one interface
2. **Intelligent Automation**: Automatic student parsing with manual override capabilities
3. **Real-time Feedback**: WebSocket updates for all file and class management operations
4. **Flexible Associations**: Support for complex class/student relationships
5. **Comprehensive Analytics**: Student progress tracking across multiple batches and courses
6. **Architectural Integrity**: Follows established HuleEdu patterns and event-driven principles

This enhanced implementation provides a complete educational management platform while maintaining the architectural integrity and event-driven patterns of the HuleEdu system.
