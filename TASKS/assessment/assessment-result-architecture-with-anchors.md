---
id: "assessment-result-architecture-with-anchors"
title: "Assessment Result Architecture with Anchor Essay Integration"
type: "task"
status: "research"
priority: "medium"
domain: "assessment"
service: ""
owner_team: "agents"
owner: ""
program: ""
created: "2025-08-08"
last_updated: "2025-11-17"
related: []
labels: []
---
# Assessment Result Architecture with Anchor Essay Integration

## Overview
This document defines the implementation of a multi-method assessment architecture that supports anchor essay integration, A/B testing of assessment models, and comprehensive audit trails. The design prioritizes extensibility while avoiding premature optimization.

## Core Architectural Decisions

### 1. Assessment Method Tracking
Multiple assessment methods can evaluate the same essay, enabling cross-validation and quality assurance.

```python
class AssessmentMethodEnum(str, Enum):
    CJ_ASSESSMENT = "cj_assessment"
    NLP_RANDOM_FOREST = "nlp_random_forest"
    HYBRID_ENSEMBLE = "hybrid_ensemble"
    HUMAN_GRADER = "human_grader"      # Regular human grading
    BAYESIAN_GRADE = "bayesian_grade"  # High-value anchor essays from Bayesian sessions
```

### 2. Result Storage Pattern
All assessment results flow to the existing Result Aggregator Service via events. No unique constraints block multiple assessments of the same essay.

## Sprint 1: Critical Implementation Tasks

### Task 1: Database Schema Updates

#### 1.1 Remove Rubric Field from AssessmentInstruction
```sql
-- In CJ Assessment Service
ALTER TABLE assessment_instructions 
DROP COLUMN IF EXISTS rubric;
```

#### 1.2 Add Model Tracking to GradeProjection
```sql
-- Immediate change to existing table
ALTER TABLE grade_projections
ADD COLUMN assessment_method VARCHAR(50) DEFAULT 'cj_assessment',
ADD COLUMN model_used VARCHAR(100),
ADD COLUMN model_provider VARCHAR(50),
ADD COLUMN normalized_score FLOAT;

CREATE INDEX idx_grade_proj_method ON grade_projections(assessment_method, cj_batch_id);
```

### Task 2: Anchor Essay Pool Integration

#### 2.1 Modify Batch Preparation Flow
**File**: `services/cj_assessment_service/cj_core_logic/workflow_orchestrator.py`

```python
async def _prepare_essays_with_anchors(
    batch_upload: CJBatchUpload,
    student_essays: list[EssayInput],
    session: AsyncSession,
    content_client: ContentClientProtocol,
) -> list[ProcessedEssay]:
    """Mix student essays with anchor essays for comparison."""
    all_essays = []
    
    # Process student essays
    for essay in student_essays:
        processed = await database.create_or_update_cj_processed_essay(
            session=session,
            els_essay_id=essay.essay_id,
            cj_batch_id=batch_upload.batch_id,
            content=essay.content,
            processing_metadata={"is_anchor": False}
        )
        all_essays.append(processed)
    
    # Add anchor essays if assignment_id present
    if batch_upload.assignment_id:
        instruction = await database.get_assessment_instruction(
            session, batch_upload.assignment_id
        )
        if instruction:
            anchors = await database.get_anchor_essay_references(
                session, instruction.instruction_id
            )
            
            for anchor in anchors:
                # Generate synthetic ID
                synthetic_id = f"ANCHOR_{anchor.reference_id}_{uuid4()}"
                
                # Fetch content
                content = await content_client.fetch_essay_content(
                    anchor.essay_storage_id
                )
                
                # Add to pool with metadata
                processed = await database.create_or_update_cj_processed_essay(
                    session=session,
                    els_essay_id=synthetic_id,
                    cj_batch_id=batch_upload.batch_id,
                    content=content,
                    processing_metadata={
                        "is_anchor": True,
                        "known_grade": anchor.grade,
                        "reference_id": str(anchor.reference_id),
                        "is_bayesian": anchor.assessment_method == "bayesian_grade"
                    }
                )
                all_essays.append(processed)
    
    return all_essays
```

#### 2.2 Filter Anchors from Student Rankings
**File**: `services/cj_assessment_service/cj_core_logic/scoring_ranking.py`

```python
async def get_essay_rankings(
    session: AsyncSession,
    batch_id: int,
    correlation_id: UUID,
    include_anchors: bool = False,
) -> list[dict[str, Any]]:
    """Get rankings, optionally filtering anchor essays."""
    
    essays = await database.get_essays_for_cj_batch(session, batch_id)
    
    rankings = []
    for essay in sorted(essays, key=lambda e: e.current_bt_score, reverse=True):
        metadata = essay.processing_metadata or {}
        
        # Skip anchors unless explicitly requested
        if metadata.get("is_anchor") and not include_anchors:
            continue
            
        rankings.append({
            "essay_id": essay.els_essay_id,
            "rank": essay.rank,
            "bt_score": essay.current_bt_score,
        })
    
    return rankings
```

### Task 3: Enhanced Grade Calibration

#### 3.1 Use Anchor Scores for Boundary Calibration
**File**: `services/cj_assessment_service/cj_core_logic/grade_projector.py`

```python
async def _calibrate_grade_boundaries(
    self,
    session: AsyncSession,
    batch_id: int,
) -> dict[str, float]:
    """Calibrate grade boundaries using anchor essay scores."""
    
    # Get scored anchor essays from this batch
    stmt = select(ProcessedEssay).where(
        and_(
            ProcessedEssay.cj_batch_id == batch_id,
            ProcessedEssay.processing_metadata["is_anchor"].as_boolean() == True
        )
    )
    anchors = await session.execute(stmt)
    anchor_essays = anchors.scalars().all()
    
    if not anchor_essays:
        return self.DEFAULT_BOUNDARIES
    
    # Build boundaries from anchor scores
    boundaries = {}
    for anchor in anchor_essays:
        grade = anchor.processing_metadata.get("known_grade")
        if grade and anchor.current_bt_score is not None:
            if grade not in boundaries:
                boundaries[grade] = []
            boundaries[grade].append(anchor.current_bt_score)
    
    # Average scores for each grade
    calibrated = {}
    for grade, scores in boundaries.items():
        calibrated[grade] = sum(scores) / len(scores)
    
    return calibrated
```

### Task 4: Event Publishing to Result Aggregator

#### 4.1 Enhance CJAssessmentCompletedV1 Event
**File**: `services/cj_assessment_service/event_processor.py`

```python
# Modify grade projection summary to include model info
grade_projections = await grade_projector.calculate_projections(...)

# Add model tracking to event
event_data = CJAssessmentCompletedV1(
    # ... existing fields ...
    grade_projections_summary=GradeProjectionSummary(
        projections_available=grade_projections.projections_available,
        primary_grades=grade_projections.primary_grades,
        confidence_scores=grade_projections.confidence_scores,
        confidence_labels=grade_projections.confidence_labels,
        # New fields for Result Aggregator
        assessment_metadata={
            "assessment_method": "cj_assessment",
            "model_used": settings.DEFAULT_LLM_MODEL,
            "model_provider": settings.DEFAULT_LLM_PROVIDER,
            "anchors_used": len([e for e in essays if e.processing_metadata.get("is_anchor")]),
            "batch_id": workflow_result.batch_id,
        }
    )
)
```

### Task 5: Store Assessment Results Locally

#### 5.1 Save Results After Grade Projection
**File**: `services/cj_assessment_service/cj_core_logic/grade_projector.py`

```python
# After calculating projections, store results
for essay_id, grade in grade_projections.primary_grades.items():
    # Skip storing anchor essay results
    essay = await database.get_processed_essay(session, essay_id)
    if essay.processing_metadata.get("is_anchor"):
        continue
        
    projection = GradeProjection(
        els_essay_id=essay_id,
        cj_batch_id=batch_id,
        primary_grade=grade,
        confidence_score=grade_projections.confidence_scores[essay_id],
        confidence_label=grade_projections.confidence_labels[essay_id],
        # New fields
        assessment_method="cj_assessment",
        model_used=settings.DEFAULT_LLM_MODEL,
        normalized_score=self._grade_to_normalized_score(grade),
        calculation_metadata={
            "bt_score": essay.current_bt_score,
            "rank": essay.rank,
            "anchors_in_batch": anchor_count,
        }
    )
    session.add(projection)
```

## Sprint 2: Future Enhancements (Deferred)

### Enhancement 1: Result Selection Logic
- Implement in Result Aggregator Service when needed
- Priority: is_primary_result → preferred_method → confidence → recency
- No implementation until multiple assessment methods active

### Enhancement 2: Predefined Assignment Catalog
- Create UI/API for managing assessment instructions
- Enable selection of predefined assignments with anchors
- Link to batch orchestrator pipeline requests

### Enhancement 3: NLP Assessment Integration
- Add NLP Random Forest assessment service
- Publish results to Result Aggregator
- Enable ensemble grading methods

### Enhancement 4: A/B Testing Framework
- Experiment tracking with experiment_id
- Model performance comparison
- Automated primary result selection

## Implementation Checklist

### Immediate (Sprint 1)
- [ ] Remove rubric field from AssessmentInstruction
- [ ] Add model tracking fields to GradeProjection
- [ ] Implement anchor essay mixing in batch preparation
- [ ] Update comparison pair generation to include anchors
- [ ] Modify ranking functions to filter anchors
- [ ] Implement anchor-based grade calibration
- [ ] Add assessment metadata to events
- [ ] Store results with model tracking

### Deferred (Future Sprints)
- [ ] Result selection service in RAS
- [ ] Predefined assignment management
- [ ] NLP assessment service
- [ ] A/B testing framework
- [ ] Bayesian grader integration UI

## Testing Requirements

### Unit Tests
1. Test anchor essay mixing logic
2. Test anchor filtering from rankings
3. Test grade calibration with anchors
4. Test model tracking in events

### Integration Tests
1. Full workflow with anchor essays
2. Grade projection with/without anchors
3. Event publishing to Result Aggregator
4. Multiple assessment storage

## Migration Notes

1. No backwards compatibility required (pure development)
2. Direct schema modifications allowed
3. Existing data can be migrated with default values
4. No feature flags needed

## Key Design Principles

1. **Extensibility**: Easy to add new assessment methods
2. **No Lock-in**: Avoid premature constraints
3. **Audit Trail**: Track model, version, provider for every assessment
4. **Service Boundaries**: Result Aggregator owns results, CJ publishes events
5. **Anchor Integration**: Transparent mixing, separate handling in results

## Success Criteria

1. Anchor essays participate in all comparisons
2. Grades calibrated using anchor scores
3. Model tracking present in all assessments
4. Result Aggregator receives enriched events
5. Multiple assessments per essay supported
6. Bayesian-graded anchors marked as high-value