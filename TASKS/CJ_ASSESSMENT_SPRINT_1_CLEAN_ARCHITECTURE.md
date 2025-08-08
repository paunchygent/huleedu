# Sprint 1: CJ Assessment Clean Architecture with Dual Event Publishing

## Architecture Decision: Clean Event Separation

### Event Flow Design
```
CJ Assessment Service ─┬→ ELS (Thin phase completion event)
                       └→ RAS (Rich assessment results event)
```

- **To ELS**: Only phase tracking (successful/failed essay IDs for state transitions)
- **To RAS**: Full assessment results with grades, rankings, model tracking

## Required Reading

Before implementing this sprint, developers MUST review these architectural rules:

1. **[020.7-cj-assessment-service.mdc]** - CJ Assessment Service architecture and patterns
2. **[020.12-result-aggregator-service-architecture.mdc]** - RAS integration patterns
3. **[030-event-driven-architecture-eda-standards.mdc]** - Event envelope and dual publishing patterns
4. **[042.1-transactional-outbox-pattern.mdc]** - Outbox pattern for reliable event publishing
5. **[048-structured-error-handling-standards.mdc]** - Error handling for anchor essay operations
6. **[053-sqlalchemy-standards.mdc]** - Database model and migration patterns
7. **[085-docker-compose-v2-command-reference.mdc]** - Container rebuild commands for testing

## Prerequisites
**MUST READ BEFORE CREATING MIGRATION!!:**
.cursor/rules/085-database-migration-standards.mdc

### Task 0: Infrastructure Updates

#### 0.1 Add Missing Event Enum
```python
# File: libs/common_core/src/common_core/event_enums.py

# Add to ProcessingEvent enum:
ASSESSMENT_RESULT_PUBLISHED = "assessment.result.published"

# Add to _TOPIC_MAPPING:
ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED: "huleedu.assessment.results.v1",
```

#### 0.2 Rename Database Field for Consistency
```bash
# Generate migration from service directory
cd services/cj_assessment_service
pdm run alembic revision -m "Rename content_id to text_storage_id in anchor_essay_references"
```

```sql
# Edit the generated migration file to include:
def upgrade():
    op.alter_column('anchor_essay_references', 'content_id', 
                    new_column_name='text_storage_id')

def downgrade():
    op.alter_column('anchor_essay_references', 'text_storage_id', 
                    new_column_name='content_id')
```

```bash
# Apply migration
pdm run alembic upgrade head
```

#### 0.3 Add Grade Normalization Helper
```python
# File: services/cj_assessment_service/cj_core_logic/grade_utils.py (NEW)

def _grade_to_normalized(grade: str | None) -> float:
    """Convert letter grade to normalized score (0.0-1.0)."""
    grade_map = {
        "A": 1.0,
        "B": 0.8,
        "C": 0.6,
        "D": 0.4,
        "E": 0.2,
        "F": 0.0,
        "U": 0.0,  # Ungraded
    }
    return grade_map.get(grade, 0.0) if grade else 0.0
```

## Implementation Tasks

### Task 1: Create New Event Types

#### 1.1 Create Assessment Result Event for RAS
```python
# File: libs/common_core/src/common_core/events/assessment_result_events.py (NEW FILE)

from datetime import datetime, UTC
from typing import Any
from pydantic import BaseModel, Field
from common_core.events.base import BaseEventData
from common_core.event_enums import ProcessingEvent

class AssessmentResultV1(BaseEventData):
    """Rich assessment result event sent directly to Result Aggregator Service."""
    
    event_name: ProcessingEvent = Field(default=ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED)
    
    # Batch identification
    batch_id: str = Field(description="BOS batch ID")
    cj_assessment_job_id: str = Field(description="Internal CJ batch ID")
    
    # Assessment method tracking
    assessment_method: str = Field(description="Method used: cj_assessment, nlp_random_forest, etc")
    model_used: str = Field(description="Specific model: claude-3-opus, gpt-4, etc")
    model_provider: str = Field(description="Provider: anthropic, openai, internal")
    model_version: str | None = Field(default=None, description="Model version if applicable")
    
    # Essay results (excludes anchor essays)
    essay_results: list[dict[str, Any]] = Field(
        description="List of student essay assessment results",
        # Each dict contains:
        # - essay_id: str
        # - normalized_score: float (0.0-1.0)
        # - letter_grade: str (A, B, C, etc)
        # - confidence_score: float (0.0-1.0)
        # - confidence_label: str (HIGH, MID, LOW)
        # - bt_score: float (Bradley-Terry score)
        # - rank: int
        # - is_anchor: bool (always False for student essays)
    )
    
    # Assessment metadata
    assessment_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional assessment context",
        # Contains:
        # - anchor_essays_used: int
        # - calibration_method: str (anchor, default)
        # - comparison_count: int
        # - processing_duration_seconds: float
        # - llm_temperature: float
        # - assignment_id: str | None
    )
    
    # Timestamp
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

#### 1.2 Simplify CJ Assessment Completed Event for ELS
```python
# File: libs/common_core/src/common_core/events/cj_assessment_events.py
# MODIFY existing CJAssessmentCompletedV1

class CJAssessmentCompletedV1(ProcessingUpdate):
    """Thin completion event for ELS phase tracking - essay state management only."""
    
    event_name: ProcessingEvent = Field(default=ProcessingEvent.CJ_ASSESSMENT_COMPLETED)
    cj_assessment_job_id: str
    
    # Phase tracking with essay IDs for state transitions
    processing_summary: dict[str, Any] = Field(
        description="Summary for phase progression and state management",
        # Contains:
        # - successful_essay_ids: list[str] (excludes ANCHOR_* IDs)
        # - failed_essay_ids: list[str]
        # - total_processed: int (includes anchors)
        # - processing_duration_seconds: float
    )
    
    # KEEP for backward compatibility during transition:
    rankings: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Deprecated - will be removed after ELS refactor"
    )
    grade_projections_summary: GradeProjectionSummary = Field(
        default_factory=lambda: GradeProjectionSummary(
            projections_available=False,
            primary_grades={},
            confidence_labels={},
            confidence_scores={}
        ),
        description="Deprecated - will be removed after ELS refactor"
    )
```

### Task 2: Update Configuration

#### 2.1 Add RAS Topic and Settings
```python
# File: services/cj_assessment_service/config.py

class Settings(BaseSettings):
    # ... existing settings ...
    
    # Add new topic for RAS
    ASSESSMENT_RESULT_TOPIC: str = Field(
        default="huleedu.assessment.results.v1",
        description="Topic for publishing assessment results to RAS"
    )
```

### Task 3: Update Database Schema

**Relevant Rules**: [042-async-patterns-and-di.mdc], [053-sqlalchemy-standards.mdc]

#### 3.1 Update Protocol Signature
```python
# File: services/cj_assessment_service/protocols.py

async def create_or_update_cj_processed_essay(
    self,
    session: AsyncSession,
    cj_batch_id: int,
    els_essay_id: str,
    text_storage_id: str,
    assessment_input_text: str,
    processing_metadata: dict | None = None,  # ADD THIS PARAMETER
) -> Any:  # ProcessedEssay
```

#### 3.2 Update Implementation
```python
# File: services/cj_assessment_service/implementations/db_access_impl.py

async def create_or_update_cj_processed_essay(
    self,
    session: AsyncSession,
    cj_batch_id: int,
    els_essay_id: str,
    text_storage_id: str,
    assessment_input_text: str,
    processing_metadata: dict | None = None,  # ADD THIS PARAMETER
) -> ProcessedEssay:
    """Create or update a processed essay in CJ batch."""
    existing_essay = await session.get(ProcessedEssay, els_essay_id)
    
    if existing_essay:
        existing_essay.cj_batch_id = cj_batch_id
        existing_essay.text_storage_id = text_storage_id
        existing_essay.assessment_input_text = assessment_input_text
        existing_essay.processing_metadata = processing_metadata  # ADD THIS
        await session.flush()
        return existing_essay
    else:
        new_essay = ProcessedEssay(
            els_essay_id=els_essay_id,
            cj_batch_id=cj_batch_id,
            text_storage_id=text_storage_id,
            assessment_input_text=assessment_input_text,
            processing_metadata=processing_metadata or {},  # ADD THIS
            current_bt_score=0.0,
        )
        session.add(new_essay)
        await session.flush()
        return new_essay
```

#### 3.3 Add Model Tracking to GradeProjection

```bash
# Generate migration for new GradeProjection fields
cd services/cj_assessment_service
pdm run alembic revision -m "Add model tracking fields to grade_projections"
```

```python
# Edit the generated migration file to include:
def upgrade():
    op.add_column('grade_projections', 
        sa.Column('assessment_method', sa.String(50), nullable=False, server_default='cj_assessment'))
    op.add_column('grade_projections', 
        sa.Column('model_used', sa.String(100), nullable=True))
    op.add_column('grade_projections', 
        sa.Column('model_provider', sa.String(50), nullable=True))
    op.add_column('grade_projections', 
        sa.Column('normalized_score', sa.Float(), nullable=True))

def downgrade():
    op.drop_column('grade_projections', 'normalized_score')
    op.drop_column('grade_projections', 'model_provider')
    op.drop_column('grade_projections', 'model_used')
    op.drop_column('grade_projections', 'assessment_method')
```

```bash
# Apply migration
pdm run alembic upgrade head
```

### Task 4: Implement Anchor Essay Integration

#### 4.0 Define ContentClient Protocol Methods

```python
# File: services/cj_assessment_service/protocols.py
# Add to ContentClientProtocol:

async def store_content(
    self, 
    content: str,
    content_type: str = "text/plain"
) -> dict[str, str]:
    """Store content in Content Service.
    
    Args:
        content: The text content to store
        content_type: MIME type of content
        
    Returns:
        Dict with 'content_id' key containing the storage ID
    """
    ...
```

#### 4.1 Create Anchor Registration API (Minimal)
```python
# File: services/cj_assessment_service/api/anchor_management.py (NEW)

from quart import Blueprint, request, jsonify
from dishka import FromDishka
from dishka.integrations.quart import inject
from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
    ContentClientProtocol,
)
from services.cj_assessment_service.models_db import AnchorEssayReference
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("anchor_management")

bp = Blueprint("anchors", __name__, url_prefix="/api/v1/anchors")

@bp.post("/register")
@inject
async def register_anchor_essay(
    repository: FromDishka[CJRepositoryProtocol],
    content_client: FromDishka[ContentClientProtocol],
) -> tuple[dict, int]:
    """Register an anchor essay for calibration.
    
    Accepts raw text via JSON for simplicity (YAGNI).
    Future sprints can add file upload support.
    
    Request body:
    {
        "assignment_id": "assignment-123",
        "grade": "A",  # Valid grades: A, B, C, D, E, F
        "essay_text": "Full essay text here..."
    }
    
    Returns:
    {
        "anchor_id": 1,
        "storage_id": "content-abc123",
        "status": "registered"
    }
    """
    try:
        data = await request.json
        
        # Basic validation
        if not all(k in data for k in ["assignment_id", "grade", "essay_text"]):
            return {"error": "Missing required fields"}, 400
        
        if data["grade"] not in ["A", "B", "C", "D", "E", "F"]:
            return {"error": "Invalid grade"}, 400
        
        if len(data["essay_text"]) < 100:
            return {"error": "Essay text too short (min 100 chars)"}, 400
        
        # Note: Non-atomic operation - content storage and DB write are separate
        # If DB write fails, content will be orphaned in Content Service
        # Consider implementing cleanup or two-phase commit in future iteration
        
        # 1. Store content in Content Service
        storage_response = await content_client.store_content(
            content=data["essay_text"],
            content_type="text/plain"
        )
        storage_id = storage_response.get("content_id")
        
        if not storage_id:
            logger.error("Content Service did not return storage_id")
            return {"error": "Failed to store essay content"}, 500
        
        # 2. Create AnchorEssayReference record (separate transaction)
        async with repository.session() as session:
            anchor_ref = AnchorEssayReference(
                assignment_id=data["assignment_id"],
                grade=data["grade"],
                text_storage_id=storage_id,  # Using renamed field
            )
            session.add(anchor_ref)
            await session.commit()
            
            logger.info(
                f"Registered anchor essay {anchor_ref.id} for assignment {data['assignment_id']}",
                extra={
                    "anchor_id": anchor_ref.id,
                    "assignment_id": data["assignment_id"],
                    "grade": data["grade"],
                    "storage_id": storage_id,
                }
            )
            
            return {
                "anchor_id": anchor_ref.id,
                "storage_id": storage_id,
                "status": "registered"
            }, 201
            
    except Exception as e:
        logger.error(
            f"Failed to register anchor essay: {e}",
            exc_info=True
        )
        return {"error": "Internal server error"}, 500

# Register blueprint in app.py:
# from services.cj_assessment_service.api import anchor_management
# app.register_blueprint(anchor_management.bp)
```

#### 4.2 Mix Anchors in Batch Preparation
```python
# File: services/cj_assessment_service/cj_core_logic/batch_preparation.py

async def prepare_essays_for_assessment(
    request_data: dict[str, Any],
    cj_batch_id: int,
    database: CJRepositoryProtocol,
    content_client: ContentClientProtocol,
    correlation_id: UUID,
    log_extra: dict[str, Any],
) -> list[EssayForComparison]:
    """Prepare essays including anchor essays."""
    
    async with database.session() as session:
        # ... existing status update ...
        
        essays_for_api_model: list[EssayForComparison] = []
        
        # 1. Process student essays
        essays_to_process = request_data.get("essays_to_process", [])
        for essay_info in essays_to_process:
            # ... existing essay processing ...
            cj_processed_essay = await database.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=cj_batch_id,
                els_essay_id=els_essay_id,
                text_storage_id=text_storage_id,
                assessment_input_text=assessment_input_text,
                processing_metadata={"is_anchor": False}  # Mark as student essay
            )
            # ... rest of existing logic ...
        
        # 2. Add anchor essays if assignment_id present
        batch_upload = await database.get_cj_batch_upload(session, cj_batch_id)
        if batch_upload and batch_upload.assignment_id:
            anchors = await _fetch_and_add_anchors(
                session, batch_upload, content_client, database, correlation_id
            )
            essays_for_api_model.extend(anchors)
            
        return essays_for_api_model

async def _fetch_and_add_anchors(
    session: AsyncSession,
    batch_upload: CJBatchUpload,
    content_client: ContentClientProtocol,
    database: CJRepositoryProtocol,
    correlation_id: UUID,
) -> list[EssayForComparison]:
    """Fetch anchor essays and add to comparison pool."""
    
    anchors = []
    
    # Get anchor references for this assignment
    anchor_refs = await database.get_anchor_essay_references(
        session, batch_upload.assignment_id
    )
    
    for ref in anchor_refs:
        try:
            # Generate synthetic ID
            synthetic_id = f"ANCHOR_{ref.id}_{uuid4().hex[:8]}"
            
            # Fetch content using renamed field
            content = await content_client.fetch_content(ref.text_storage_id, correlation_id)
            
            # Store with metadata
            processed = await database.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=batch_upload.id,
                els_essay_id=synthetic_id,
                text_storage_id=ref.text_storage_id,
                assessment_input_text=content,
                processing_metadata={
                    "is_anchor": True,
                    "known_grade": ref.grade,
                    "anchor_ref_id": str(ref.id),
                }
            )
            
            # Ensure anchor is persisted before creating comparisons
            await session.flush()
            
            # Create API model
            anchor_for_api = EssayForComparison(
                id=synthetic_id,
                text_content=content,
                current_bt_score=0.0,
            )
            anchors.append(anchor_for_api)
            
        except Exception as e:
            logger.error(
                f"Failed to fetch anchor essay {ref.id}: {e}",
                extra={
                    "correlation_id": correlation_id,
                    "anchor_id": ref.id,
                    "exception_type": type(e).__name__,
                },
                exc_info=True,
            )
            # Continue with other anchors
    
    logger.info(f"Added {len(anchors)} anchor essays to batch {batch_upload.id}")
    return anchors
```

### Task 5: Implement Dual Event Publishing

**Relevant Rules**: [030-event-driven-architecture-eda-standards.mdc], [042.1-transactional-outbox-pattern.mdc]

#### 5.0 Update Event Publisher Protocol
```python
# File: services/cj_assessment_service/protocols.py
# Add new method to CJEventPublisherProtocol:

async def publish_assessment_result(
    self,
    result_data: Any,
    correlation_id: UUID,
) -> None:
    """Publish assessment results to RAS.
    
    This is a new method needed for dual event publishing.
    Implementation should use outbox pattern like publish_assessment_completed.
    """
    ...
```

#### 5.1 Create Dual Publishing Function
```python
# File: services/cj_assessment_service/event_processor.py

from services.cj_assessment_service.cj_core_logic.grade_utils import _grade_to_normalized

async def publish_assessment_completion(
    workflow_result: CJAssessmentWorkflowResult,
    grade_projections: GradeProjectionSummary,
    request_event_data: ELS_CJAssessmentRequestV1,
    settings: Settings,
    event_publisher: CJEventPublisherProtocol,
    correlation_id: UUID,
    processing_started_at: datetime,
) -> None:
    """Publish dual events: thin to ELS, rich to RAS."""
    
    # Separate student essays from anchors
    student_rankings = [r for r in workflow_result.rankings if not r["essay_id"].startswith("ANCHOR_")]
    anchor_rankings = [r for r in workflow_result.rankings if r["essay_id"].startswith("ANCHOR_")]
    
    # Build successful/failed lists for ELS (student essays only)
    successful_essay_ids = [r["essay_id"] for r in student_rankings if r.get("bt_score") is not None]
    failed_essay_ids = [r["essay_id"] for r in student_rankings if r.get("bt_score") is None]
    
    # 1. THIN EVENT TO ELS (Phase tracking with essay IDs)
    els_event = CJAssessmentCompletedV1(
        event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
        entity_id=request_event_data.entity_id,
        entity_type=request_event_data.entity_type,
        parent_id=request_event_data.parent_id,
        status=BatchStatus.COMPLETED_SUCCESSFULLY if successful_essay_ids else BatchStatus.FAILED,
        system_metadata=SystemProcessingMetadata(
            entity_id=request_event_data.entity_id,
            entity_type=request_event_data.entity_type,
            parent_id=request_event_data.parent_id,
            timestamp=datetime.now(UTC),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
        ),
        cj_assessment_job_id=workflow_result.batch_id,
        processing_summary={
            "successful_essay_ids": successful_essay_ids,
            "failed_essay_ids": failed_essay_ids,
            "total_processed": len(workflow_result.rankings),  # Includes anchors
            "processing_duration_seconds": (datetime.now(UTC) - processing_started_at).total_seconds(),
        },
        # Deprecated fields - kept for backward compatibility
        rankings=student_rankings,  # Will be removed after ELS refactor
        grade_projections_summary=grade_projections,
    )
    
    els_envelope = EventEnvelope[CJAssessmentCompletedV1](
        event_type=settings.CJ_ASSESSMENT_COMPLETED_TOPIC,
        source_service=settings.SERVICE_NAME,
        correlation_id=correlation_id,
        data=els_event,
    )
    
    # Publish thin event to ELS using existing method
    await event_publisher.publish_assessment_completed(
        completion_data=els_envelope,
        correlation_id=correlation_id,
    )
    
    # 2. RICH EVENT TO RAS (Full assessment results - students only)
    essay_results = []
    for ranking in student_rankings:
        essay_id = ranking["essay_id"]
        essay_results.append({
            "essay_id": essay_id,
            "normalized_score": _grade_to_normalized(grade_projections.primary_grades.get(essay_id)),
            "letter_grade": grade_projections.primary_grades.get(essay_id, "U"),
            "confidence_score": grade_projections.confidence_scores.get(essay_id, 0.0),
            "confidence_label": grade_projections.confidence_labels.get(essay_id, "LOW"),
            "bt_score": ranking.get("bt_score", 0.0),
            "rank": ranking.get("rank", 999),
            "is_anchor": False,
        })
    
    ras_event = AssessmentResultV1(
        event_name=ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED,
        entity_id=request_event_data.entity_id,
        entity_type="batch",
        batch_id=str(request_event_data.entity_id),
        cj_assessment_job_id=workflow_result.batch_id,
        assessment_method="cj_assessment",
        model_used=settings.DEFAULT_LLM_MODEL,
        model_provider=settings.DEFAULT_LLM_PROVIDER.value,
        model_version=getattr(settings, "DEFAULT_LLM_MODEL_VERSION", None),
        essay_results=essay_results,
        assessment_metadata={
            "anchor_essays_used": len(anchor_rankings),
            "calibration_method": "anchor" if anchor_rankings else "default",
            "comparison_count": len(workflow_result.comparisons) if hasattr(workflow_result, "comparisons") else 0,
            "processing_duration_seconds": (datetime.now(UTC) - processing_started_at).total_seconds(),
            "llm_temperature": settings.LLM_TEMPERATURE,
            "assignment_id": request_event_data.assignment_id,
            "course_code": request_event_data.course_code.value if hasattr(request_event_data.course_code, 'value') else request_event_data.course_code,
        },
        assessed_at=datetime.now(UTC),
    )
    
    ras_envelope = EventEnvelope[AssessmentResultV1](
        event_type=settings.ASSESSMENT_RESULT_TOPIC,
        source_service=settings.SERVICE_NAME,
        correlation_id=correlation_id,
        data=ras_event,
    )
    
    # Publish rich event to RAS using outbox pattern
    # Note: This requires extending publish_assessment_completed to handle dual events
    # or creating a new method publish_assessment_result for RAS events
    await event_publisher.publish_assessment_result(
        result_data=ras_envelope,
        correlation_id=correlation_id,
    )
    
    logger.info(
        f"Published dual events: ELS (thin) and RAS (rich) for batch {workflow_result.batch_id}",
        extra={
            "correlation_id": correlation_id,
            "batch_id": workflow_result.batch_id,
            "els_topic": settings.CJ_ASSESSMENT_COMPLETED_TOPIC,
            "ras_topic": settings.ASSESSMENT_RESULT_TOPIC,
            "student_essays": len(student_rankings),
            "anchor_essays": len(anchor_rankings),
        }
    )
```

#### 5.2 Update batch_callback_handler.py and batch_monitor.py
Apply the same dual publishing pattern to these integration points, ensuring they:
1. Separate student essays from anchors
2. Send thin event with essay IDs to ELS
3. Send rich event with full results to RAS

### Task 6: Refactor ELS Handler (Future Sprint)

```python
# File: services/essay_lifecycle_service/implementations/service_result_handler_impl.py
# TO BE REFACTORED in next sprint to use processing_summary instead of rankings

async def handle_cj_assessment_completed(
    self,
    result_data: CJAssessmentCompletedV1,
    correlation_id: UUID,
    confirm_idempotency: Any = None,
) -> bool:
    """Handle CJ assessment completion - state transitions only."""
    # Use processing_summary for state transitions
    for essay_id in result_data.processing_summary["successful_essay_ids"]:
        # Transition to success state (no business data storage)
        state_machine.trigger_event(EVT_CJ_ASSESSMENT_SUCCEEDED)
        await self.repository.update_essay_status_via_machine(
            essay_id,
            state_machine.current_status,
            {
                "current_phase": "cj_assessment",
                "phase_outcome_status": "CJ_ASSESSMENT_SUCCESS",
                # NO rankings, scores, or business data
            },
            session,
            correlation_id=correlation_id,
        )
    
    # Handle failed essays similarly...
```

## Testing Requirements

**Relevant Rules**: [070-testing-and-quality-assurance.mdc], [075-test-creation-methodology.mdc]

### Unit Tests
1. Test dual event publishing with correct filtering
2. Test anchor essay mixing with renamed fields
3. Test anchor filtering from student results
4. Test grade calibration with anchors
5. Test processing_metadata persistence

### Integration Tests
1. Full workflow with dual events
2. Verify ELS receives thin event with essay IDs
3. Verify RAS receives rich event without anchors
4. Test anchor essay flow with correct field names
5. Test backward compatibility with deprecated fields

## Success Criteria

1. **Clean Architecture**: Business data flows only to RAS, not through ELS
2. **Dual Events**: ELS gets state management data, RAS gets business results
3. **Anchor Integration**: Anchors participate in comparisons but excluded from student results
4. **Model Tracking**: Every assessment records model details
5. **Field Consistency**: All storage references use `text_storage_id`
6. **Backward Compatibility**: Deprecated fields maintained during transition

## Implementation Order

**Follow [080-repository-workflow-and-tooling.mdc] for PDM commands and Docker operations**

1. **Infrastructure updates** (45 min)
   - Add enum values and topic mappings
   - Database migration for field rename
   - Create helper functions

2. **Database changes** (30 min)
   - Update method signatures
   - Add processing_metadata support
   - Migration for GradeProjection fields

3. **Anchor essay integration** (45 min)
   - Use correct field names
   - Ensure DB persistence before comparisons
   - Add error handling

4. **Dual event publishing** (60 min)
   - Implement separation logic
   - Update all three integration points
   - Maintain backward compatibility

5. **Testing and validation** (60 min)
   - Unit tests for new functionality
   - Integration tests for event flow
   - Verify ELS compatibility

**Total Time: ~4 hours**

## Notes

- The ELS refactor to remove business data handling will be done in a separate sprint
- Deprecated fields in CJAssessmentCompletedV1 ensure backward compatibility during transition
- All anchor essays are filtered from student results but participate in comparisons
- Field rename (content_id → text_storage_id) improves consistency across the codebase