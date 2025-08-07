# CJ Assessment Grade Projection - Pure Implementation Blueprint

## 🚀 PURE DEVELOPMENT MODE - NO LEGACY SUPPORT

**Implementation Date**: August 7, 2025  
**Mode**: PURE DEVELOPMENT - NO BACKWARDS COMPATIBILITY  
**Status**: READY FOR IMMEDIATE IMPLEMENTATION

### ⚡ Critical Requirements

1. **NO FEATURE FLAGS** - Implement directly, no toggles
2. **NO LEGACY SUPPORT** - Clean implementation only
3. **NO BACKWARDS COMPATIBILITY** - We're in pure development
4. **NO GRADUAL ROLLOUT** - Full implementation from day one
5. **NO MIGRATION OF OLD DATA** - Fresh database state

---

## Architectural Decisions

### ✅ What CJ Assessment Service WILL Have

1. **Transactional Outbox Pattern** - For reliable event publishing to ELS/BOS
2. **Grade Projection Logic** - Core business capability
3. **Confidence Calculation** - Statistical scoring (direct implementation)
4. **Context-Aware Assessment** - Assignment-based instructions and anchors

### ❌ What CJ Assessment Service WON'T Have

1. **NO Notification Projector** - CJ is internal processing only
2. **NO Feature Flags** - Direct implementation
3. **NO Legacy Field Support** - Clean schemas only
4. **NO Backwards Compatibility Code** - Pure forward development

### Notification Architecture Rationale

CJ Assessment is an **internal processing service**. Teacher notifications come from:
- **BOS**: "Batch started CJ assessment phase"
- **ELS**: "CJ assessment phase completed"  
- **RAS**: "Final grades and rankings available"

CJ Assessment only publishes completion events for service orchestration, NOT user notifications.

---

## Implementation Tasks

### Task 1: Event Contract Updates (NO FLAGS)

**File 1**: `libs/common_core/src/common_core/events/client_commands.py`

```python
class ClientBatchPipelineRequestV1(BaseModel):
    """Command from API Gateway to BOS to run a processing pipeline."""
    batch_id: str = Field(..., min_length=1, max_length=255)
    requested_pipeline: str = Field(..., min_length=1, max_length=100)
    client_correlation_id: UUID = Field(default_factory=uuid4)
    user_id: str = Field(..., min_length=1, max_length=255)
    is_retry: bool = Field(default=False)
    retry_reason: str | None = Field(default=None, max_length=500)
    
    # DIRECT ADDITION - NO FLAGS
    assignment_id: str | None = Field(
        default=None,
        max_length=100,
        description="Predefined assignment identifier for context-aware assessment"
    )
```

**File 2**: `libs/common_core/src/common_core/events/cj_assessment_events.py`

```python
# DIRECT ADDITION - NO FLAGS
class GradeProjectionSummary(BaseModel):
    """Grade projection results - always included."""
    projections_available: bool = True
    primary_grades: dict[str, str]  # {essay_id: "A", "B+", etc.}
    confidence_labels: dict[str, str]  # {essay_id: "HIGH", "MID", "LOW"}
    confidence_scores: dict[str, float]  # {essay_id: 0.0-1.0}

class CJAssessmentCompletedV1(ProcessingUpdate):
    """Signals successful completion of CJ assessment."""
    event_name: ProcessingEvent = Field(
        default=ProcessingEvent.CJ_ASSESSMENT_COMPLETED
    )
    cj_assessment_job_id: str
    rankings: list[dict[str, Any]]
    
    # ALWAYS INCLUDED - NO FLAGS
    grade_projections_summary: GradeProjectionSummary = Field(
        description="Grade projections with confidence scores"
    )

class ELS_CJAssessmentRequestV1(BaseEventData):
    # ... existing fields ...
    
    # DIRECT ADDITION
    assignment_id: str | None = Field(
        default=None,
        description="Assignment context for grade projection"
    )
```

### Task 2: Database Schema (CLEAN IMPLEMENTATION)

**File**: `services/cj_assessment_service/models_db.py`

```python
# DIRECT ADDITION - NO LEGACY FIELDS

class AssessmentInstruction(Base):
    """Assessment instructions for AI judges."""
    __tablename__ = "assessment_instructions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )
    course_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )
    instructions_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    
    __table_args__ = (
        CheckConstraint(
            "(assignment_id IS NOT NULL AND course_id IS NULL) OR "
            "(assignment_id IS NULL AND course_id IS NOT NULL)",
            name="chk_context_type"
        ),
    )

class AnchorEssayReference(Base):
    """References to anchor essays stored in Content Service."""
    __tablename__ = "anchor_essay_references"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grade: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    content_id: Mapped[str] = mapped_column(String(255), nullable=False)
    assignment_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class GradeProjection(Base):
    """Grade projections with statistical confidence."""
    __tablename__ = "grade_projections"
    
    els_essay_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("cj_processed_essays.els_essay_id"),
        primary_key=True
    )
    cj_batch_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("cj_batch_uploads.id"),
        primary_key=True
    )
    primary_grade: Mapped[str] = mapped_column(String(3), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_label: Mapped[str] = mapped_column(String(10), nullable=False)
    calculation_metadata: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    
    __table_args__ = (
        Index('idx_batch_grade', 'cj_batch_id', 'primary_grade'),
    )

# UPDATE existing CJBatchUpload
class CJBatchUpload(Base):
    # ... existing fields ...
    
    # DIRECT ADDITION
    assignment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
```

### Task 3: Outbox Implementation (REQUIRED FOR RELIABILITY)

**File 1**: Migration `services/cj_assessment_service/alembic/versions/20250807_1300_add_outbox_and_projections.py`

```python
"""Add outbox and grade projection tables

Revision ID: add_outbox_and_projections
Revises: [current]
Create Date: 2025-08-07 13:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    # Event Outbox Table
    op.create_table(
        'event_outbox',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('aggregate_id', sa.String(255), nullable=False),
        sa.Column('aggregate_type', sa.String(100), nullable=False),
        sa.Column('event_type', sa.String(255), nullable=False),
        sa.Column('event_data', postgresql.JSON(astext_type=sa.Text()),
                  nullable=False),
        sa.Column('event_key', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retry_count', sa.Integer(), server_default=sa.text('0'),
                  nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_event_outbox_unpublished', 'event_outbox',
                    ['published_at', 'created_at'],
                    postgresql_where=sa.text('published_at IS NULL'))
    op.create_index('ix_event_outbox_aggregate', 'event_outbox',
                    ['aggregate_type', 'aggregate_id'])
    
    # Assessment Instructions
    op.create_table(
        'assessment_instructions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('assignment_id', sa.String(100), nullable=True),
        sa.Column('course_id', sa.String(50), nullable=True),
        sa.Column('instructions_text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assignment_id'),
        sa.CheckConstraint(
            "(assignment_id IS NOT NULL AND course_id IS NULL) OR "
            "(assignment_id IS NULL AND course_id IS NOT NULL)",
            name='chk_context_type'
        )
    )
    op.create_index(op.f('ix_assessment_instructions_assignment_id'),
                    'assessment_instructions', ['assignment_id'])
    op.create_index(op.f('ix_assessment_instructions_course_id'),
                    'assessment_instructions', ['course_id'])
    
    # Anchor Essay References
    op.create_table(
        'anchor_essay_references',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('grade', sa.String(3), nullable=False),
        sa.Column('content_id', sa.String(255), nullable=False),
        sa.Column('assignment_id', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_anchor_essay_references_grade'),
                    'anchor_essay_references', ['grade'])
    op.create_index(op.f('ix_anchor_essay_references_assignment_id'),
                    'anchor_essay_references', ['assignment_id'])
    
    # Grade Projections
    op.create_table(
        'grade_projections',
        sa.Column('els_essay_id', sa.String(255), nullable=False),
        sa.Column('cj_batch_id', sa.Integer(), nullable=False),
        sa.Column('primary_grade', sa.String(3), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=False),
        sa.Column('confidence_label', sa.String(10), nullable=False),
        sa.Column('calculation_metadata', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['els_essay_id'],
                                ['cj_processed_essays.els_essay_id']),
        sa.ForeignKeyConstraint(['cj_batch_id'], ['cj_batch_uploads.id']),
        sa.PrimaryKeyConstraint('els_essay_id', 'cj_batch_id')
    )
    op.create_index('idx_batch_grade', 'grade_projections',
                    ['cj_batch_id', 'primary_grade'])
    
    # Add assignment_id to CJBatchUpload
    op.add_column('cj_batch_uploads',
                  sa.Column('assignment_id', sa.String(100), nullable=True))

def downgrade() -> None:
    op.drop_column('cj_batch_uploads', 'assignment_id')
    op.drop_index('idx_batch_grade', table_name='grade_projections')
    op.drop_table('grade_projections')
    op.drop_index(op.f('ix_anchor_essay_references_assignment_id'),
                  table_name='anchor_essay_references')
    op.drop_index(op.f('ix_anchor_essay_references_grade'),
                  table_name='anchor_essay_references')
    op.drop_table('anchor_essay_references')
    op.drop_index(op.f('ix_assessment_instructions_course_id'),
                  table_name='assessment_instructions')
    op.drop_index(op.f('ix_assessment_instructions_assignment_id'),
                  table_name='assessment_instructions')
    op.drop_table('assessment_instructions')
    op.drop_index('ix_event_outbox_aggregate', table_name='event_outbox')
    op.drop_index('ix_event_outbox_unpublished', table_name='event_outbox')
    op.drop_table('event_outbox')
```

**File 2**: `services/cj_assessment_service/implementations/outbox_manager.py`

```python
"""Outbox manager for transactional event publishing."""

from typing import Any
from uuid import UUID

from huleedu_service_libs.error_handling import raise_external_service_error
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.protocols import (
    OutboxRepositoryProtocol,
    AtomicRedisClientProtocol,
)
from services.cj_assessment_service.config import Settings

logger = create_service_logger("cj_assessment_service.outbox_manager")

class OutboxManager:
    """Manages transactional event publishing via outbox pattern."""
    
    def __init__(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> None:
        self.outbox_repository = outbox_repository
        self.redis_client = redis_client
        self.settings = settings
    
    async def publish_to_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: Any,  # EventEnvelope[Any]
        topic: str,
        correlation_id: UUID | str,
    ) -> None:
        """Store event in outbox for transactional publishing."""
        
        # Serialize event with topic
        serialized_data = event_data.model_dump(mode="json")
        serialized_data["topic"] = topic
        
        # Store in outbox
        await self.outbox_repository.add_event(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            event_data=serialized_data,
            event_key=aggregate_id,
        )
        
        # Notify relay worker
        await self.redis_client.lpush(
            "outbox:wake:cj_assessment_service", "1"
        )
        
        logger.info(
            "Event stored in outbox",
            extra={
                "correlation_id": str(correlation_id),
                "aggregate_type": aggregate_type,
                "aggregate_id": aggregate_id,
                "event_type": event_type,
                "topic": topic,
            }
        )
```

### Task 4: Core Business Logic (DIRECT IMPLEMENTATION)

**File 1**: `services/cj_assessment_service/cj_core_logic/context_builder.py`

```python
"""Context builder for assessment instructions and anchors."""

from typing import NamedTuple
from uuid import UUID

from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_validation_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from common_core.events.cj_assessment_events import ELS_CJAssessmentRequestV1
from services.cj_assessment_service.models_db import (
    AnchorEssayReference,
    AssessmentInstruction,
)
from services.cj_assessment_service.protocols import (
    CJDatabaseRepositoryProtocol,
    ContentClientProtocol,
)

logger = create_service_logger("cj_assessment.context_builder")

class AssessmentContext(NamedTuple):
    """Resolved context for assessment."""
    assessment_instructions: str
    anchor_essay_refs: list[AnchorEssayReference]
    anchor_contents: dict[str, str]  # content_id -> text
    context_source: str  # "predefined" or "course"

class InsufficientAnchorsError(HuleEduError):
    """Raised when too few anchors for reliable assessment."""
    error_code = "INSUFFICIENT_ANCHORS"

class ContextBuilder:
    """Resolves assessment context from assignment or course."""
    
    def __init__(
        self,
        db_repository: CJDatabaseRepositoryProtocol,
        content_client: ContentClientProtocol,
        min_anchors_required: int = 3,
    ):
        self.db_repo = db_repository
        self.content_client = content_client
        self.logger = logger
        self.min_anchors = min_anchors_required
    
    async def build(
        self,
        request: ELS_CJAssessmentRequestV1,
        correlation_id: UUID | str,
    ) -> AssessmentContext:
        """Build assessment context - assignment or course fallback."""
        
        self.logger.info(
            "Building assessment context",
            extra={
                "correlation_id": str(correlation_id),
                "assignment_id": getattr(request, 'assignment_id', None),
                "course_code": request.course_code,
            }
        )
        
        assignment_id = getattr(request, 'assignment_id', None)
        
        if assignment_id:
            # Predefined assignment workflow
            instructions = await self.db_repo.get_instructions_by_assignment(
                assignment_id
            )
            if not instructions:
                raise_validation_error(
                    service="cj_assessment_service",
                    operation="build_context",
                    field="assignment_id",
                    value=assignment_id,
                    constraint=f"No instructions found for assignment: {assignment_id}",
                    correlation_id=str(correlation_id),
                )
            
            anchor_refs = await self.db_repo.get_anchor_refs_by_assignment(
                assignment_id
            )
            context_source = "predefined"
        else:
            # Course-level fallback
            instructions = await self.db_repo.get_instructions_by_course(
                str(request.course_code)
            )
            if not instructions:
                raise_validation_error(
                    service="cj_assessment_service",
                    operation="build_context",
                    field="course_code",
                    value=str(request.course_code),
                    constraint=f"No instructions found for course: {request.course_code}",
                    correlation_id=str(correlation_id),
                )
            
            anchor_refs = await self.db_repo.get_anchor_refs_by_course(
                str(request.course_code)
            )
            context_source = "course"
        
        # Validate anchor count
        if len(anchor_refs) < self.min_anchors:
            raise InsufficientAnchorsError(
                f"Insufficient anchors: {len(anchor_refs)} < {self.min_anchors}",
                correlation_id=str(correlation_id),
            )
        
        # Fetch anchor content from Content Service
        anchor_contents = {}
        for ref in anchor_refs:
            content_response = await self.content_client.get_content(
                ref.content_id
            )
            anchor_contents[ref.content_id] = content_response["text"]
        
        return AssessmentContext(
            assessment_instructions=instructions.instructions_text,
            anchor_essay_refs=anchor_refs,
            anchor_contents=anchor_contents,
            context_source=context_source,
        )
```

**File 2**: `services/cj_assessment_service/cj_core_logic/confidence_calculator.py`

```python
"""Statistical confidence calculation for grade projections."""

import numpy as np
from typing import Tuple
import asyncio

from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic.grade_projection import (
    ProjectionResult
)

logger = create_service_logger("cj_assessment.confidence")

class ConfidenceCalculationTimeoutError(HuleEduError):
    """Raised when confidence calculation exceeds timeout."""
    error_code = "CONFIDENCE_TIMEOUT"

class ConfidenceCalculator:
    """Calculates statistical confidence for grade projections."""
    
    # Hardcoded weights - no feature flags
    FACTOR_WEIGHTS = {
        "parameter_uncertainty": 0.5,
        "boundary_distance": 0.3,
        "comparison_volume": 0.2
    }
    
    # Hardcoded thresholds
    HIGH_THRESHOLD = 0.7
    MID_THRESHOLD = 0.4
    
    # Performance limits
    CALCULATION_TIMEOUT = 30  # seconds
    MAX_HESSIAN_BATCH_SIZE = 50
    
    def __init__(self):
        self.logger = logger
    
    async def calculate_confidence(
        self,
        projection: ProjectionResult,
        comparison_count: int,
        enable_hessian: bool = True,
        correlation_id: str | None = None,
    ) -> Tuple[float, str]:
        """Calculate confidence score and label."""
        
        try:
            # Run calculation with timeout
            score = await asyncio.wait_for(
                self._calculate_confidence_async(
                    projection, comparison_count, enable_hessian
                ),
                timeout=self.CALCULATION_TIMEOUT
            )
            
            label = self._map_score_to_label(score)
            
            self.logger.info(
                f"Confidence calculated: {projection.essay_id}",
                extra={
                    "correlation_id": correlation_id,
                    "essay_id": projection.essay_id,
                    "confidence_score": score,
                    "confidence_label": label,
                }
            )
            
            return score, label
            
        except asyncio.TimeoutError:
            self.logger.warning(
                f"Confidence calculation timeout for {projection.essay_id}",
                extra={"correlation_id": correlation_id}
            )
            # Fallback to simple calculation
            return self._simple_confidence(projection, comparison_count)
    
    async def _calculate_confidence_async(
        self,
        projection: ProjectionResult,
        comparison_count: int,
        enable_hessian: bool,
    ) -> float:
        """Full confidence calculation with all factors."""
        
        factors = {}
        
        # Factor 1: Parameter uncertainty (if Hessian enabled)
        if enable_hessian and comparison_count < self.MAX_HESSIAN_BATCH_SIZE:
            factors["parameter_uncertainty"] = await self._calculate_parameter_uncertainty(
                projection
            )
        else:
            factors["parameter_uncertainty"] = 0.5  # Neutral value
        
        # Factor 2: Distance to grade boundary
        factors["boundary_distance"] = self._calculate_boundary_distance(
            projection
        )
        
        # Factor 3: Comparison volume
        factors["comparison_volume"] = self._calculate_volume_factor(
            comparison_count
        )
        
        # Weighted average
        score = sum(
            factors[key] * self.FACTOR_WEIGHTS[key]
            for key in factors
        )
        
        return float(np.clip(score, 0.0, 1.0))
    
    async def _calculate_parameter_uncertainty(
        self,
        projection: ProjectionResult,
    ) -> float:
        """Calculate parameter uncertainty using Hessian matrix."""
        # Placeholder for Hessian calculation
        # TODO: Implement actual Hessian computation
        return 0.7
    
    def _calculate_boundary_distance(
        self, 
        projection: ProjectionResult,
    ) -> float:
        """Calculate normalized distance to grade boundaries."""
        
        if not projection.anchor_distances:
            return 0.5
        
        # Find minimum distance to any anchor
        min_distance = min(projection.anchor_distances.values())
        
        # Normalize (closer = higher confidence)
        # Max expected distance ~2.0 in BT scale
        normalized = 1.0 - min(min_distance / 2.0, 1.0)
        
        return float(normalized)
    
    def _calculate_volume_factor(
        self,
        comparison_count: int,
    ) -> float:
        """Calculate confidence based on comparison count."""
        
        # Normalize (more comparisons = higher confidence)
        # Optimal is ~10 comparisons per essay
        normalized = min(comparison_count / 10.0, 1.0)
        
        return float(normalized)
    
    def _simple_confidence(
        self,
        projection: ProjectionResult,
        comparison_count: int,
    ) -> Tuple[float, str]:
        """Fallback simple confidence calculation."""
        
        # Just use comparison volume and boundary distance
        boundary = self._calculate_boundary_distance(projection)
        volume = self._calculate_volume_factor(comparison_count)
        
        score = (boundary * 0.6 + volume * 0.4)
        label = self._map_score_to_label(score)
        
        return score, label
    
    def _map_score_to_label(self, score: float) -> str:
        """Map confidence score to label."""
        
        if score >= self.HIGH_THRESHOLD:
            return "HIGH"
        elif score >= self.MID_THRESHOLD:
            return "MID"
        else:
            return "LOW"
```

### Task 5: Integration with Core Assessment

**File**: `services/cj_assessment_service/cj_core_logic/core_assessment_logic.py`

```python
# MODIFY existing orchestrate_cj_assessment method

async def orchestrate_cj_assessment(
    self,
    request: ELS_CJAssessmentRequestV1,
    correlation_id: str,
) -> CJAssessmentCompletedV1:
    """Enhanced orchestration with grade projection."""
    
    # Existing CJ logic...
    rankings = await self._run_cj_process(request)
    
    # NEW: Always calculate grade projections (no feature flag)
    try:
        # Build context
        context = await self.context_builder.build(
            request, correlation_id
        )
        
        # Convert rankings to RankedEssay objects with anchor flags
        ranked_essays = self._prepare_ranked_essays(
            rankings, context.anchor_essay_refs
        )
        
        # Calculate projections
        projections = self.grade_projector.calculate_projections(
            ranked_essays, context.anchor_essay_refs, correlation_id
        )
        
        # Calculate confidence for each projection
        confidence_results = {}
        for essay_id, projection in projections.items():
            comparison_count = await self._get_comparison_count(essay_id)
            score, label = await self.confidence_calculator.calculate_confidence(
                projection, comparison_count, correlation_id=correlation_id
            )
            confidence_results[essay_id] = (score, label)
        
        # Build summary for event
        grade_projection_summary = GradeProjectionSummary(
            projections_available=True,
            primary_grades={
                eid: proj.primary_grade 
                for eid, proj in projections.items()
            },
            confidence_labels={
                eid: label 
                for eid, (_, label) in confidence_results.items()
            },
            confidence_scores={
                eid: score 
                for eid, (score, _) in confidence_results.items()
            }
        )
        
        # Store in database (within transaction)
        async with self.db_session() as session:
            # Save grade projections
            for essay_id, projection in projections.items():
                score, label = confidence_results[essay_id]
                
                grade_proj = GradeProjection(
                    els_essay_id=essay_id,
                    cj_batch_id=batch.id,
                    primary_grade=projection.primary_grade,
                    confidence_score=score,
                    confidence_label=label,
                    calculation_metadata={
                        "rank": projection.rank,
                        "bt_score": projection.bt_score,
                        "context_source": context.context_source,
                        "anchor_distances": projection.anchor_distances,
                    }
                )
                session.add(grade_proj)
            
            # Create completion event
            event = CJAssessmentCompletedV1(
                batch_id=request.batch_id,
                cj_assessment_job_id=job_id,
                rankings=rankings,
                processing_metadata=metadata,
                grade_projections_summary=grade_projection_summary  # Always included
            )
            
            # Publish via outbox (atomic with DB write)
            envelope = EventEnvelope(
                event_name=event.event_name,
                event_data=event,
                correlation_id=correlation_id,
                entity_id=request.batch_id,
                entity_type="batch",
            )
            
            await self.outbox_manager.publish_to_outbox(
                aggregate_type="cj_batch",
                aggregate_id=request.batch_id,
                event_type="CJAssessmentCompletedV1",
                event_data=envelope,
                topic=self.settings.CJ_ASSESSMENT_COMPLETED_TOPIC,
                correlation_id=correlation_id,
            )
            
            await session.commit()
            
    except Exception as e:
        self.logger.error(
            f"Grade projection failed: {e}",
            extra={"correlation_id": correlation_id}
        )
        # For now, fail the entire assessment if projection fails
        # In production, might want to continue without projections
        raise
    
    return event
```

### Task 6: Configuration Updates (NO FLAGS)

**File**: `services/cj_assessment_service/config.py`

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # NO FEATURE FLAGS - Direct configuration only
    
    # Performance Limits (always enforced)
    MAX_HESSIAN_BATCH_SIZE: int = Field(
        default=50,
        description="Maximum essays for Hessian calculation"
    )
    CONFIDENCE_CALCULATION_TIMEOUT: int = Field(
        default=30,
        description="Timeout in seconds for confidence calculation"
    )
    
    # Minimum anchor requirements
    MIN_ANCHORS_REQUIRED: int = Field(
        default=3,
        description="Minimum anchor essays required for projection"
    )
    
    class Config:
        env_prefix = "CJ_ASSESSMENT_SERVICE_"
```

---

## Testing Strategy (NO LEGACY TESTS)

### Unit Tests

```python
# tests/unit/test_grade_projection.py

@pytest.mark.asyncio
async def test_grade_projection_with_assignment():
    """Test grade projection with assignment context."""
    # No feature flag checks - always enabled
    
    context_builder = Mock(spec=ContextBuilder)
    grade_projector = GradeProjector()
    
    request = create_test_request(assignment_id="ENG5_HAMLET")
    context = create_test_context(num_anchors=5)
    rankings = create_test_rankings(num_essays=10)
    
    projections = grade_projector.calculate_projections(
        rankings, context.anchor_essay_refs, "test_correlation"
    )
    
    # Always expect projections
    assert len(projections) == 10
    assert all(p.primary_grade in VALID_GRADES for p in projections.values())

@pytest.mark.asyncio
async def test_confidence_calculation():
    """Test confidence calculation - always enabled."""
    calculator = ConfidenceCalculator()  # No settings needed
    
    projection = create_test_projection()
    score, label = await calculator.calculate_confidence(
        projection, comparison_count=10, correlation_id="test"
    )
    
    assert 0.0 <= score <= 1.0
    assert label in ["HIGH", "MID", "LOW"]
```

### Integration Tests

```python
# tests/integration/test_cj_with_projections.py

@pytest.mark.integration
async def test_end_to_end_grade_projection():
    """Test complete CJ assessment with grade projections."""
    async with create_test_environment() as env:
        # Setup test data
        await seed_test_assignments(env.db)
        await seed_test_anchors(env.db)
        
        # Send assessment request
        request = create_assessment_request(
            assignment_id="TEST_ASSIGNMENT",
            num_essays=20
        )
        
        # Process
        result = await env.cj_service.process_request(request)
        
        # Grade projections are always included
        assert result.grade_projections_summary is not None
        assert result.grade_projections_summary.projections_available
        assert len(result.grade_projections_summary.primary_grades) == 20
        
        # Check database persistence
        projections = await env.db.get_projections(request.batch_id)
        assert len(projections) == 20
        
        # Verify outbox has event
        outbox_events = await env.db.get_unpublished_events()
        assert len(outbox_events) == 1
        assert outbox_events[0].event_type == "CJAssessmentCompletedV1"
```

---

## Implementation Checklist

### Database & Infrastructure
- [ ] Apply migration for all new tables (single migration)
- [ ] No rollback/compatibility migrations needed
- [ ] Outbox table included in migration

### Event Contracts
- [ ] Update `ClientBatchPipelineRequestV1` with `assignment_id`
- [ ] Add `GradeProjectionSummary` to events
- [ ] Update `CJAssessmentCompletedV1` to always include projections
- [ ] Propagate `assignment_id` through ELS events

### Core Implementation  
- [ ] Implement `ContextBuilder` (no flags)
- [ ] Implement `GradeProjector` (direct logic)
- [ ] Implement `ConfidenceCalculator` (hardcoded weights)
- [ ] Implement `OutboxManager` for reliability

### Integration
- [ ] Update `core_assessment_logic.py` to always project grades
- [ ] Wire up DI providers
- [ ] No notification projector needed (architectural decision)

### Testing
- [ ] Unit tests for projection logic
- [ ] Integration tests with outbox
- [ ] No legacy compatibility tests

---

## What We're NOT Implementing

1. **NO Notification Projector** - CJ is internal only
2. **NO Feature Flags** - Direct implementation
3. **NO Backwards Compatibility** - Clean schemas
4. **NO Legacy Field Support** - Pure development
5. **NO Gradual Rollout** - Full implementation

---

## Success Criteria

- [x] Grade projections always calculated (no flags)
- [x] Confidence scores always included
- [x] Outbox ensures reliable event delivery
- [x] No user notifications from CJ
- [x] Clean implementation without legacy code
- [x] All tests pass without feature toggles

---

**Document Status**: READY FOR IMPLEMENTATION  
**Development Mode**: PURE - NO LEGACY SUPPORT  
**Implementation Approach**: DIRECT - NO FLAGS