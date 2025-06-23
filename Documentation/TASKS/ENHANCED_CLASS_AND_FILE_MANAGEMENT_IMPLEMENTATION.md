# Enhanced Class and File Management Implementation Plan

This document outlines the implementation of enhanced file and batch management capabilities, class management service, and student association features for the HuleEdu platform.

**CRITICAL DEPENDENCIES:**

- ✅ **Checkpoint 1.4: User ID Propagation** (API_GATEWAY_WEBSOCKET_SERVICE_TASK_TICKET_1.md) - MUST be completed first
- ✅ **Checkpoint 3.2: Enhanced WebSocket Implementation** (API_GATEWAY_WEBSOCKET_SERVICE_TASK_TICKET_3.md) - For real-time updates
- ✅ **User authentication and ownership validation** - Foundation for all enhanced features

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

## Part 1: Common Core Extensions

**CRITICAL DEPENDENCIES:**

- ✅ **Checkpoint 1.4: User ID Propagation** (API_GATEWAY_WEBSOCKET_SERVICE_TASK_TICKET_1.md) - MUST be completed first
- ✅ **Checkpoint 3.2: Enhanced WebSocket Implementation** (API_GATEWAY_WEBSOCKET_SERVICE_TASK_TICKET_3.md) - For real-time updates
- ✅ **User authentication and ownership validation** - Foundation for all enhanced features

**Architecture Alignment:**
This implementation follows the established HuleEdu microservice patterns:

- Event-driven communication via Kafka with thin, focused events
- Protocol-based dependency injection with Dishka
- Pydantic contracts for all inter-service communication in `common_core`
- User ownership validation for all operations
- Real-time updates via Redis pub/sub and WebSocket
- Pragmatic HTTP calls for simple request/response patterns

## Part 1: Common Core Extensions

### Checkpoint 2.0: Extend Common Core with Course and Event Definitions

**Objective**: Add course definitions and new event contracts to `common_core` following established patterns for cross-service compliance.

**Affected Files**:

- `common_core/src/common_core/enums.py`
- `common_core/src/common_core/events/class_events.py` (new)
- `common_core/src/common_core/events/file_management_events.py` (new)

**Implementation Steps**:

1. **Add Course Definitions to Common Core**: Extend existing enum structure with course codes.

    **File**: `common_core/src/common_core/enums.py`

    ```python
    from enum import Enum
    from typing import Dict, Tuple

    class CourseCode(str, Enum):
        """Predefined course codes for HuleEdu platform."""
        ENG5 = "ENG5"
        ENG6 = "ENG6" 
        ENG7 = "ENG7"
        SV1 = "SV1"
        SV2 = "SV2"
        SV3 = "SV3"

    class Language(str, Enum):
        """Supported languages inferred from course codes."""
        ENGLISH = "en"
        SWEDISH = "sv"

    # Course metadata mapping for language inference
    COURSE_METADATA: Dict[CourseCode, Tuple[str, Language, int]] = {
        CourseCode.ENG5: ("English 5", Language.ENGLISH, 5),
        CourseCode.ENG6: ("English 6", Language.ENGLISH, 6),
        CourseCode.ENG7: ("English 7", Language.ENGLISH, 7),
        CourseCode.SV1: ("Svenska 1", Language.SWEDISH, 1),
        CourseCode.SV2: ("Svenska 2", Language.SWEDISH, 2),
        CourseCode.SV3: ("Svenska 3", Language.SWEDISH, 3),
    }

    def get_course_language(course_code: CourseCode) -> Language:
        """Get language for a course code."""
        return COURSE_METADATA[course_code][1]

    def get_course_name(course_code: CourseCode) -> str:
        """Get display name for a course code."""
        return COURSE_METADATA[course_code][0]

    def get_course_level(course_code: CourseCode) -> int:
        """Get skill level for a course code."""
        return COURSE_METADATA[course_code][2]

    # Additional ProcessingEvent entries
    class ProcessingEvent(str, Enum):
        # ... existing events ...
        
        # Enhanced file and class management events
        STUDENT_PARSING_COMPLETED = "STUDENT_PARSING_COMPLETED"
        ESSAY_STUDENT_ASSOCIATION_UPDATED = "ESSAY_STUDENT_ASSOCIATION_UPDATED"
        BATCH_FILE_ADDED = "BATCH_FILE_ADDED"
        BATCH_FILE_REMOVED = "BATCH_FILE_REMOVED"
        CLASS_CREATED = "CLASS_CREATED"
        STUDENT_CREATED = "STUDENT_CREATED"

    # Topic mapping additions (implement in future checkpoint)
    _TOPIC_MAPPING.update({
        ProcessingEvent.STUDENT_PARSING_COMPLETED: "huleedu.file.student.parsing.completed.v1",
        ProcessingEvent.ESSAY_STUDENT_ASSOCIATION_UPDATED: "huleedu.class.essay.association.updated.v1",
        ProcessingEvent.BATCH_FILE_ADDED: "huleedu.file.batch.file.added.v1",
        ProcessingEvent.BATCH_FILE_REMOVED: "huleedu.file.batch.file.removed.v1",
        ProcessingEvent.CLASS_CREATED: "huleedu.class.created.v1",
        ProcessingEvent.STUDENT_CREATED: "huleedu.class.student.created.v1",
    })
    ```

2. **Create Thin Event Contracts Following Established Patterns**: Add new event models that follow the thin event principle.

    **File**: `common_core/src/common_core/events/file_management_events.py`

    ```python
    """
    File management event models for enhanced file operations.
    
    These events support file addition/removal operations and student parsing
    following the thin event principle with focused, essential data.
    """

    from __future__ import annotations

    from datetime import UTC, datetime
    from uuid import UUID

    from pydantic import BaseModel, Field

    class StudentParsingCompletedV1(BaseModel):
        """Event published when File Service completes student parsing for a batch."""
        event: str = Field(default="student.parsing.completed")
        batch_id: str = Field(description="Batch identifier")
        # Direct data - parsing results populate Class Management Service DB
        parsing_results: list[dict] = Field(
            description="List of parsing results: [{essay_id, filename, first_name, last_name, student_email, confidence}]"
        )
        parsed_count: int = Field(description="Number of essays with parsed student info")
        total_count: int = Field(description="Total number of essays processed")
        correlation_id: UUID | None = Field(default=None)
        timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class BatchFileAddedV1(BaseModel):
        """Event published when file is added to existing batch."""
        event: str = Field(default="batch.file.added")
        batch_id: str = Field(description="Batch identifier")
        essay_id: str = Field(description="New essay identifier")
        filename: str = Field(description="Original filename")
        user_id: str = Field(description="User who added the file")
        correlation_id: UUID | None = Field(default=None)
        timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class BatchFileRemovedV1(BaseModel):
        """Event published when file is removed from batch."""
        event: str = Field(default="batch.file.removed")
        batch_id: str = Field(description="Batch identifier")
        essay_id: str = Field(description="Removed essay identifier")
        filename: str = Field(description="Original filename")
        user_id: str = Field(description="User who removed the file")
        correlation_id: UUID | None = Field(default=None)
        timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ```

    **File**: `common_core/src/common_core/events/class_events.py`

    ```python
    """
    Class management event models for student and class operations.
    
    These events support class creation, student management, and essay-student
    associations following the thin event principle.
    """

    from __future__ import annotations

    from datetime import UTC, datetime
    from uuid import UUID

    from pydantic import BaseModel, Field

    class ClassCreatedV1(BaseModel):
        """Event published when new class is created."""
        event: str = Field(default="class.created")
        class_id: str = Field(description="New class identifier")
        class_designation: str = Field(description="Class designation name")
        course_codes: list[str] = Field(description="Associated course codes")
        user_id: str = Field(description="Teacher who created the class")
        correlation_id: UUID | None = Field(default=None)
        timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class StudentCreatedV1(BaseModel):
    """Event published when new student is created."""
    event: str = Field(default="student.created")
    student_id: str = Field(description="New student identifier")
    first_name: str = Field(description="Student first name")
    last_name: str = Field(description="Student last name")
    student_email: str = Field(description="Student email address")
    class_ids: list[str] = Field(description="Associated class identifiers")
    created_by_user_id: str = Field(description="User who created the student")
    correlation_id: UUID | None = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class EssayStudentAssociationUpdatedV1(BaseModel):
    """Event published when student-essay association is created/updated."""
    event: str = Field(default="essay.student.association.updated")
    batch_id: str = Field(description="Batch identifier")
    essay_id: str = Field(description="Essay identifier")
    student_id: str | None = Field(description="Student identifier (None if association removed)")
    first_name: str | None = Field(description="Student first name for display")
    last_name: str | None = Field(description="Student last name for display")
    student_email: str | None = Field(description="Student email for display")
    association_method: str = Field(description="Association method: 'parsed' or 'manual'")
    confidence_score: float | None = Field(description="Confidence score for parsed associations")
    created_by_user_id: str = Field(description="User who created the association")
    correlation_id: UUID | None = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ```

**Done When**:

- ✅ Course codes are defined in `common_core/enums.py`
- ✅ New ProcessingEvent entries are added
- ✅ Topic mappings are documented (implementation in future checkpoint)
- ✅ Thin event contracts follow established patterns
- ✅ All event models use focused, essential data only

## Part 2: Enhanced File and Batch Management

### Checkpoint 2.1: Enhanced Batch Registration with Course Validation

**Objective**: Extend batch registration to support predefined courses, class associations, and enhanced metadata management while maintaining backward compatibility.

**Key Features**:

- Course validation enforces only ENG5/6/7 and SV1/2/3 codes
- Language is automatically inferred from course code
- Enhanced metadata is stored in batch context
- Backward compatibility is maintained with V1 endpoint
- All validation errors provide clear feedback

**Affected Files**:

- `services/batch_orchestrator_service/api_models.py`
- `services/batch_orchestrator_service/implementations/batch_context_operations.py`
- `services/batch_orchestrator_service/api/batch_routes.py`
- `common_core/src/common_core/enums.py`

**Implementation Steps**:

1. **Enhanced Batch Registration Model**: Extend the existing model with course validation and class association.

    **File**: `services/batch_orchestrator_service/api_models.py`

    ```python
    from common_core.enums import CourseCode, get_course_language
    from pydantic import BaseModel, Field, model_validator
    from typing import Optional

    class BatchRegistrationRequestV2(BaseModel):
        """Enhanced batch registration with course validation and class support."""
        expected_essay_count: int = Field(..., gt=0)
        essay_ids: list[str] | None = None
        
        # Enhanced course and class fields
        course_code: CourseCode = Field(..., description="Must be one of: ENG5,ENG6,ENG7,SV1,SV2,SV3")
        class_id: str | None = Field(None, description="Optional existing class ID")
        class_designation: str = Field(..., description="Class designation name")
        
        # Existing fields
        teacher_name: str = Field(...)
        essay_instructions: str = Field(...)
        user_id: str = Field(..., description="Authenticated user ID from API Gateway")
        
        # New fields for enhanced functionality
        enable_student_parsing: bool = Field(default=True, description="Enable automatic student parsing")
        expected_student_names: list[str] | None = Field(None, description="Optional list of expected student names")

        @model_validator(mode="after")
        def validate_and_enrich(self) -> "BatchRegistrationRequestV2":
            """Validate course code and enrich with language information."""
            # Course validation is handled by CourseCode enum
            # Add derived language to the model for downstream services
            self._language = get_course_language(self.course_code)
            return self

        @property
        def language(self) -> str:
            """Get the language code for this batch."""
            return self._language.value if hasattr(self, '_language') else get_course_language(self.course_code).value

    # Maintain backward compatibility
    BatchRegistrationRequestV1 = BatchRegistrationRequestV2  # Alias for existing code
    ```

2. **Enhanced Batch Context Storage**: Update context operations to store course and class information.

    **File**: `services/batch_orchestrator_service/implementations/batch_context_operations.py`

    ```python
    async def store_enhanced_batch_context(
        self,
        batch_id: str,
        registration_data: BatchRegistrationRequestV2,
        session: AsyncSession,
    ) -> None:
        """Store enhanced batch context with course and class information."""
        try:
            # Check if batch already exists
            stmt = select(Batch).where(Batch.id == batch_id)
            result = await session.execute(stmt)
            batch = result.scalar_one_or_none()

            # Prepare enhanced metadata
            enhanced_metadata = registration_data.model_dump()
            enhanced_metadata.update({
                "language": registration_data.language,
                "course_name": get_course_name(registration_data.course_code),
                "course_level": get_course_level(registration_data.course_code),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "version": "v2"  # Version tracking for migrations
            })

            if batch is None:
                # Create new batch record with enhanced metadata
                batch = Batch(
                    id=batch_id,
                    expected_essay_count=registration_data.expected_essay_count,
                    essay_ids=registration_data.essay_ids,
                    processing_metadata=enhanced_metadata,
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
                session.add(batch)
                self.logger.info(f"Created enhanced batch context: batch_id='{batch_id}', course='{registration_data.course_code}', class='{registration_data.class_designation}'")
            else:
                # Update existing batch with enhanced context
                stmt = (
                    update(Batch)
                    .where(Batch.id == batch_id)
                    .values(
                        expected_essay_count=registration_data.expected_essay_count,
                        essay_ids=registration_data.essay_ids,
                        processing_metadata=enhanced_metadata,
                        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    )
                )
                await session.execute(stmt)
                self.logger.info(f"Updated enhanced batch context: batch_id='{batch_id}', course='{registration_data.course_code}'")

        except Exception as e:
            self.logger.error(f"Failed to store enhanced batch context: batch_id='{batch_id}', error='{e}'", exc_info=True)
            raise
    ```

3. **Enhanced Batch Registration Endpoint**: Add new endpoint with backward compatibility.

    **File**: `services/batch_orchestrator_service/api/batch_routes.py`

    ```python
    @batch_bp.route("/v2/register", methods=["POST"])
    @inject
    async def register_enhanced_batch(
        registration_data: BatchRegistrationRequestV2,
        batch_ops: FromDishka[BatchContextOperationsProtocol],
        event_publisher: FromDishka[BatchEventPublisherProtocol],
    ) -> tuple[dict, int]:
        """Enhanced batch registration with course validation and class support."""
        try:
            batch_id = str(uuid4())
            correlation_id = uuid4()

            # Store enhanced context
            await batch_ops.store_enhanced_batch_context(batch_id, registration_data)

            # Publish enhanced registration event
            await event_publisher.publish_batch_registered_event(
                batch_id=batch_id,
                registration_data=registration_data,
                correlation_id=correlation_id,
            )

            logger.info(
                f"Enhanced batch registered: batch_id='{batch_id}', "
                f"course='{registration_data.course_code}', "
                f"class='{registration_data.class_designation}', "
                f"user_id='{registration_data.user_id}'"
            )

            return {
                "batch_id": batch_id,
                "status": "registered",
                "course_code": registration_data.course_code,
                "language": registration_data.language,
                "class_designation": registration_data.class_designation,
                "enable_student_parsing": registration_data.enable_student_parsing,
            }, 201

        except ValueError as e:
            logger.warning(f"Enhanced batch registration validation error: {e}")
            return {"error": f"Validation error: {str(e)}"}, 400
        except Exception as e:
            logger.error(f"Enhanced batch registration failed: {e}", exc_info=True)
            return {"error": "Internal server error"}, 500
    ```

**Done When**:

- ✅ Course validation enforces only ENG5/6/7 and SV1/2/3 codes
- ✅ Language is automatically inferred from course code
- ✅ Enhanced metadata is stored in batch context
- ✅ Backward compatibility is maintained with V1 endpoint
- ✅ All validation errors provide clear feedback

### Checkpoint 2.2: File Management with Batch State Validation

**Objective**: Implement file add/remove operations with proper batch state validation, ensuring files cannot be modified after spellcheck begins.

**Key Features**:

- File operations blocked when spellcheck has started
- User ownership validation for all file operations
- Real-time events published for file additions/removals
- Batch state information available to clients
- Clear error messages for operation failures

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

### Checkpoint 2.3: Class Management Service Foundation

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
        """Student entities with separated name fields for better data management and CSV export."""
        __tablename__ = "students"
        
        id: Mapped[str] = mapped_column(String(36), primary_key=True)
        first_name: Mapped[str] = mapped_column(String(255), nullable=False)
        last_name: Mapped[str] = mapped_column(String(255), nullable=False)
        legal_full_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Full parsed name for reference
        email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
        created_by_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
        created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
        updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        
        @property
        def full_name(self) -> str:
            """Combined name for display purposes."""
            return f"{self.first_name} {self.last_name}"
        
        @property
        def last_first_name(self) -> str:
            """Last, First format for sorting."""
            return f"{self.last_name}, {self.first_name}"
        
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
        """Result of automatic student parsing with separated name components."""
        essay_id: str
        filename: str
        first_name: Optional[str] = None
        last_name: Optional[str] = None
        legal_full_name: Optional[str] = None  # Original parsed full name
        student_email: Optional[str] = None
        confidence_score: float = Field(ge=0.0, le=1.0)
        parsing_method: str
        raw_text_snippet: Optional[str] = None
        
        @property
        def full_name(self) -> Optional[str]:
            """Combined name if both parts are available."""
            if self.first_name and self.last_name:
                return f"{self.first_name} {self.last_name}"
            return self.first_name or self.last_name or self.legal_full_name

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

**Name Parsing Logic**:

```python
def parse_student_name(full_name: str) -> tuple[str, str, str]:
    """
    Parse full name into first, last, and original full name components.
    
    Handles Swedish/English naming patterns:
    - "Anna Andersson" → ("Anna", "Andersson", "Anna Andersson")
    - "Erik Johan Svensson" → ("Erik Johan", "Svensson", "Erik Johan Svensson") 
    - "Anna Margareta Svensson-Andersson" → ("Anna", "Svensson-Andersson", "Anna Margareta Svensson-Andersson")
    """
    if not full_name or not full_name.strip():
        return "", "", ""
    
    original_name = full_name.strip()
    name_parts = original_name.split()
    
    if len(name_parts) == 1:
        # Single name - treat as last name
        return "", name_parts[0], original_name
    elif len(name_parts) == 2:
        # First Last
        return name_parts[0], name_parts[1], original_name
    else:
        # Multiple parts - use first name and last surname, preserve full name
        # This handles Swedish double surnames and multiple given names
        return name_parts[0], name_parts[-1], original_name
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
