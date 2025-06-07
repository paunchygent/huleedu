# File Service Validation Improvements - Implementation Report

**Date**: 2025-01-16  
**Status**: ✅ **PARTIALLY COMPLETED** - BOS Pipeline Progression Fix Implemented
**Priority**: 🔧 **HIGH** - Critical Business Logic Issue Resolved

## Root Cause Analysis Summary

**Problem Identified**: 24/25 essays completed spellcheck successfully, but 1 essay failed due to Content Service connection issue during storage. BOS treated `COMPLETED_WITH_FAILURES` as complete failure and skipped CJ assessment entirely for all essays.

**Business Impact**: 24 successful essays were blocked from proceeding to CJ assessment due to 1 unrelated service failure.

---

## ✅ IMPLEMENTED: BOS Resilient Pipeline Progression

### Problem Resolved

Fixed the critical architectural issue where BOS incorrectly handled `COMPLETED_WITH_FAILURES` status, violating the documented enum semantics in `common_core/enums.py`.

### Implementation Details

#### 1. Core Logic Fix in `pipeline_phase_coordinator_impl.py`

**File**: `services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py`

**BEFORE (Problematic Logic)**:

```python
# Only proceed with next phase if current phase completed successfully
if phase_status != "COMPLETED_SUCCESSFULLY":
    logger.info(f"Phase {completed_phase} for batch {batch_id} did not complete successfully, skipping next phase initiation")
    return
```

**AFTER (Fixed Logic)**:

```python
# Allow progression for both COMPLETED_SUCCESSFULLY and COMPLETED_WITH_FAILURES
# COMPLETED_WITH_FAILURES indicates partial success and should proceed with successful essays
if phase_status not in ["COMPLETED_SUCCESSFULLY", "COMPLETED_WITH_FAILURES"]:
    logger.info(f"Phase {completed_phase} for batch {batch_id} did not complete successfully (status: {phase_status}), skipping next phase initiation")
    return

# Log progression decision for COMPLETED_WITH_FAILURES cases
if phase_status == "COMPLETED_WITH_FAILURES":
    successful_count = len(processed_essays_for_next_phase) if processed_essays_for_next_phase else 0
    logger.info(f"Phase {completed_phase} completed with partial failures for batch {batch_id}. Proceeding to next phase with {successful_count} successful essays.", extra={"correlation_id": correlation_id})
```

#### 2. Status Mapping Fix

**BEFORE (Incorrect Mapping)**:

```python
await self.update_phase_status(
    batch_id, completed_phase,
    "COMPLETED_SUCCESSFULLY" if phase_status == "COMPLETED_SUCCESSFULLY" else "FAILED",
    datetime.now(timezone.utc).isoformat(),
)
```

**AFTER (Correct Mapping)**:

```python
# COMPLETED_WITH_FAILURES is treated as success for progression purposes
# (per common_core/enums.py - it's a terminal success state with partial failures)
if phase_status in ["COMPLETED_SUCCESSFULLY", "COMPLETED_WITH_FAILURES"]:
    updated_status = "COMPLETED_SUCCESSFULLY"
else:
    updated_status = "FAILED"
    
await self.update_phase_status(batch_id, completed_phase, updated_status, datetime.now(timezone.utc).isoformat())
```

### Test Coverage Added

#### New Integration Tests in `test_pipeline_state_management.py`

1. **`test_completed_with_failures_phase_handling`**
   - **Purpose**: Test general `COMPLETED_WITH_FAILURES` handling
   - **Validates**: Progression to next phase with partial success
   - **Result**: ✅ PASS

2. **`test_real_world_24_of_25_essays_scenario`**
   - **Purpose**: Test the specific root cause scenario (24/25 essays succeed)
   - **Validates**: Exactly 24 essays proceed to CJ assessment
   - **Result**: ✅ PASS

#### Test Results Summary

- ✅ **8/8 integration tests pass** (6 existing + 2 new)
- ✅ **30/30 BOS unit tests pass**
- ✅ **3/3 BOS integration tests pass**
- ✅ **No regressions introduced**

### Validation Results

#### Test Output Validation

```
2025-06-07 20:27:03 [info] Handling phase conclusion: batch=..., phase=spellcheck, status=COMPLETED_WITH_FAILURES
2025-06-07 20:27:03 [info] Updated spellcheck status to COMPLETED_SUCCESSFULLY for batch ...
2025-06-07 20:27:03 [info] Phase spellcheck completed with partial failures for batch .... Proceeding to next phase with 24 successful essays.
2025-06-07 20:27:03 [info] Initiating next phase 'cj_assessment' for batch ...
2025-06-07 20:27:03 [info] Successfully initiated cj_assessment pipeline for batch ...
```

#### Business Impact Achieved

- ✅ **Before Fix**: 1 essay failure → entire batch halted, 24 essays blocked
- ✅ **After Fix**: 1 essay failure → isolated, 24 essays proceed to CJ assessment
- ✅ **Architectural Compliance**: `COMPLETED_WITH_FAILURES` now correctly treated as terminal success state
- ✅ **Audit Trail**: Clear logging for progression decisions and essay counts

### Architecture Compliance Validated

- ✅ **Enum Semantics**: Aligns with `common_core/enums.py` definition of `COMPLETED_WITH_FAILURES` as terminal success
- ✅ **Service Autonomy**: No cross-service dependencies introduced
- ✅ **Event-Driven Architecture**: Uses existing event patterns
- ✅ **Explicit Contracts**: Maintains proper state transitions

---

## 📋 REVISED PLAN: File Service Validation Layer with Event-Driven Coordination

**Status**: 🔧 **READY FOR IMPLEMENTATION** - Comprehensive Analysis Complete with BOS/ELS Coordination  
**Priority**: 🔧 **HIGH** - Quality Improvement with Critical Architectural Integration

### Problem Analysis

#### Root Cause: Problematic Content Reaching Downstream Services

The current File Service processes all uploaded content without validation, causing:
- **Empty files** (0 bytes) → Spell checker hangs/failures
- **Very short content** (< 50 characters) → Poor processing results
- **Malformed text** → Service errors and timeouts
- **Poor user feedback** → No actionable error messages

#### Critical Discovery: BOS/ELS Slot Assignment Impact

**MAJOR ISSUE IDENTIFIED**: File Service validation will break existing BOS/ELS coordination:

**Current Flow**:

1. BOS registers batch with `expected_essay_count: 25`
2. ELS expects exactly 25 `EssayContentProvisionedV1` events
3. File Service processes all 25 files → ELS receives 25 events → Batch complete

**With Validation (BROKEN)**:

1. BOS registers batch with `expected_essay_count: 25`
2. ELS expects exactly 25 `EssayContentProvisionedV1` events
3. File Service validates: 22 valid, 3 rejected → ELS receives only 22 events
4. **ELS waits indefinitely for 3 missing events → 5-minute timeout → Batch failure**

#### Solution: Event-Driven Validation Coordination

**Implement Option 1**: Publish validation failure events to maintain BOS/ELS slot synchronization.

### Comprehensive Implementation Plan

#### Phase 1: Common Core Event Models *(Day 1)*

**1.1 New Validation Event Model**  
**File**: `common_core/src/common_core/events/file_events.py`

```python
class EssayValidationFailedV1(BaseModel):
    """
    Event published when file content validation fails.
    
    Enables ELS to adjust slot expectations and BOS to track
    actual vs expected essay counts for informed pipeline decisions.
    """
    
    batch_id: str = Field(description="Batch identifier")
    original_file_name: str = Field(description="Name of the failed file")
    validation_error_code: str = Field(description="Specific validation error code")
    validation_error_message: str = Field(description="Human-readable error message")
    file_size_bytes: int = Field(description="Size of the failed file for metrics")
    correlation_id: Optional[UUID] = Field(default=None, description="Request correlation ID")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Validation failure timestamp"
    )
```

**1.2 Update ProcessingEvent Enum**  
**File**: `common_core/src/common_core/enums.py`

```python
class ProcessingEvent(str, Enum):
    # ... existing events ...
    ESSAY_VALIDATION_FAILED = "essay_validation_failed"
```

**1.3 Update Topic Mapping**  
**File**: `common_core/src/common_core/enums.py`

```python
def topic_name(event: ProcessingEvent) -> str:
    mapping = {
        # ... existing mappings ...
        ProcessingEvent.ESSAY_VALIDATION_FAILED: "huleedu.file.essay.validation.failed.v1",
    }
```

#### Phase 2: File Service Validation Framework *(Days 2-3)*

**2.1 Enhanced Content Validation Protocol**  
**File**: `services/file_service/protocols.py`

```python
class ContentValidatorProtocol(Protocol):
    """Protocol for validating extracted file content."""

    async def validate_content(self, text: str, file_name: str) -> ValidationResult:
        """Validate extracted text content against business rules."""
        ...

class EventPublisherProtocol(Protocol):
    """Extended protocol for publishing validation events."""
    
    # ... existing methods ...
    
    async def publish_essay_validation_failed(
        self, event_data: EssayValidationFailedV1, correlation_id: Optional[uuid.UUID]
    ) -> None:
        """Publish EssayValidationFailedV1 event to Kafka."""
        ...
```

**2.2 Validation Models and Implementation**  
**New File**: `services/file_service/validation_models.py`

```python
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, ConfigDict

class ValidationResult(BaseModel):
    """Result of content validation with error details."""
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
    )
    
    is_valid: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    warnings: List[str] = []
```

**New File**: `services/file_service/content_validator.py`

```python
class FileContentValidator(ContentValidatorProtocol):
    """Validates file content against business rules."""
    
    def __init__(self, min_length: int = 50, max_length: int = 50000):
        self.min_length = min_length
        self.max_length = max_length
        
    async def validate_content(self, text: str, file_name: str) -> ValidationResult:
        """Validate extracted text content against business rules."""
        
        # Empty content check
        if not text or not text.strip():
            return ValidationResult(
                is_valid=False,
                error_code="EMPTY_CONTENT",
                error_message=f"File '{file_name}' contains no readable text content."
            )
        
        # Length validation
        content_length = len(text.strip())
        if content_length < self.min_length:
            return ValidationResult(
                is_valid=False,
                error_code="CONTENT_TOO_SHORT",
                error_message=f"File '{file_name}' contains only {content_length} characters. Essays must contain at least {self.min_length} characters."
            )
            
        # Additional validation logic...
        return ValidationResult(is_valid=True)
```

**2.3 Enhanced Configuration**  
**File**: `services/file_service/config.py`

```python
class Settings(BaseSettings):
    # ... existing settings ...
    
    # Content validation settings
    CONTENT_VALIDATION_ENABLED: bool = True
    MIN_CONTENT_LENGTH: int = 50
    MAX_CONTENT_LENGTH: int = 50000
    VALIDATION_LOG_LEVEL: str = "INFO"
    
    # New Kafka topic for validation failures
    ESSAY_VALIDATION_FAILED_TOPIC: str = topic_name(ProcessingEvent.ESSAY_VALIDATION_FAILED)
```

#### Phase 3: Core Logic Integration with Event Coordination *(Day 4)*

**3.1 Enhanced File Processing with Event Publishing**  
**File**: `services/file_service/core_logic.py`

**Integration Point** (lines 58-68):

```python
async def process_single_file_upload(
    # ... existing params ...
    content_validator: ContentValidatorProtocol,  # NEW parameter
) -> Dict[str, Any]:
    # ... existing logic until text extraction ...
    
    # Extract text content from file
    text = await text_extractor.extract_text(file_content, file_name)
    if not text:
        logger.warning(f"Text extraction failed or returned empty for {file_name}")
        return {"file_name": file_name, "status": "extraction_failed_or_empty"}

    # NEW: Validate extracted content
    validation_result = await content_validator.validate_content(text, file_name)
    if not validation_result.is_valid:
        logger.warning(
            f"Content validation failed for {file_name}: {validation_result.error_message}",
            extra={"correlation_id": str(main_correlation_id), "error_code": validation_result.error_code}
        )
        
        # NEW: Publish validation failure event for ELS/BOS coordination
        validation_failure_event = EssayValidationFailedV1(
            batch_id=batch_id,
            original_file_name=file_name,
            validation_error_code=validation_result.error_code,
            validation_error_message=validation_result.error_message,
            file_size_bytes=len(file_content),
            correlation_id=main_correlation_id
        )
        
        await event_publisher.publish_essay_validation_failed(
            validation_failure_event, main_correlation_id
        )
        
        return {
            "file_name": file_name, 
            "status": "content_validation_failed",
            "error_code": validation_result.error_code,
            "error_message": validation_result.error_message
        }

    # Continue with existing storage logic for valid content...
```

#### Phase 4: ELS Validation Event Handling *(Days 5-6)*

**4.1 Enhanced ELS Batch Tracker**  
**File**: `services/essay_lifecycle_service/batch_tracker.py`

```python
class BatchEssayTracker:
    """Enhanced to handle validation failures and prevent infinite waits."""
    
    def __init__(self) -> None:
        self.batch_expectations: dict[str, BatchExpectation] = {}
        self.validation_failures: dict[str, list[EssayValidationFailedV1]] = {}  # NEW
        self._event_callbacks: dict[str, Callable[[Any], Awaitable[None]]] = {}

    async def handle_validation_failure(self, event: EssayValidationFailedV1) -> None:
        """
        Handle validation failure by adjusting batch expectations.
        
        Prevents ELS from waiting indefinitely for content that will never arrive.
        """
        batch_id = event.batch_id
        
        # Track validation failure
        if batch_id not in self.validation_failures:
            self.validation_failures[batch_id] = []
        self.validation_failures[batch_id].append(event)
        
        # Check if we should trigger early batch completion
        if batch_id in self.batch_expectations:
            expectation = self.batch_expectations[batch_id]
            failure_count = len(self.validation_failures[batch_id])
            assigned_count = len(expectation.slot_assignments)
            total_processed = assigned_count + failure_count
            
            # If processed count meets expectation, complete batch early
            if total_processed >= expectation.expected_count:
                logger.info(
                    f"Batch {batch_id} completing early: "
                    f"{assigned_count} assigned + {failure_count} failed = {total_processed}"
                )
                
                if assigned_count > 0:
                    await self._complete_batch_with_failures(batch_id, expectation)
```

**4.2 Enhanced BatchEssaysReady Event Model**  
**File**: `common_core/src/common_core/events/batch_coordination_events.py`

```python
class BatchEssaysReady(BaseModel):
    """Enhanced to include validation failure information for BOS coordination."""
    
    # ... existing fields ...
    
    validation_failures: Optional[List[EssayValidationFailedV1]] = Field(
        default=None,
        description="List of validation failures that occurred during batch processing"
    )
    
    total_files_processed: Optional[int] = Field(
        default=None,
        description="Total number of files processed (successful + failed)"
    )
```

#### Phase 5: Enhanced API Response & Error Handling *(Day 7)*

**5.1 Comprehensive API Response with Validation Summary**  
**File**: `services/file_service/api/file_routes.py`

```python
@file_bp.route("/batch", methods=["POST"])
@inject
async def upload_batch_files(
    # ... existing parameters ...
) -> tuple[Response, int]:
    # ... existing logic until task processing ...
    
    # Collect and categorize results
    processing_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    successful_files = []
    validation_failures = []
    processing_errors = []
    
    for result in processing_results:
        if isinstance(result, dict):
            status = result.get("status")
            if status == "processing_initiated":
                successful_files.append(result)
            elif status == "content_validation_failed":
                validation_failures.append(result)
            else:
                processing_errors.append(result)
    
    # Build comprehensive response for user feedback
    response_data = {
        "batch_id": batch_id,
        "correlation_id": str(main_correlation_id),
        "total_files": len(uploaded_files),
        "successful_files": len(successful_files),
        "validation_failures": len(validation_failures),
        "processing_errors": len(processing_errors)
    }
    
    if validation_failures:
        response_data["validation_errors"] = validation_failures
        response_data["message"] = f"Batch {batch_id} processed with {len(validation_failures)} validation failures"
        
        if successful_files:
            return jsonify(response_data), 422  # Partial success
        else:
            return jsonify(response_data), 400   # All files failed
    else:
        response_data["message"] = f"{len(successful_files)} files received for batch {batch_id} and are being processed."
        return jsonify(response_data), 202
```

#### Phase 6: Comprehensive Testing with BOS/ELS Coordination *(Days 8-9)*

**6.1 Unit Tests for Validation Logic**  
**New File**: `services/file_service/tests/test_content_validation.py`

```python
class TestFileContentValidator:
    async def test_validate_empty_content(self):
        """Test rejection of empty content."""
        validator = FileContentValidator()
        result = await validator.validate_content("", "empty.txt")
        assert not result.is_valid
        assert result.error_code == "EMPTY_CONTENT"
        
    async def test_validate_short_content(self):
        """Test rejection of content below minimum length."""
        validator = FileContentValidator(min_length=50)
        result = await validator.validate_content("Short text", "short.txt")
        assert not result.is_valid
        assert result.error_code == "CONTENT_TOO_SHORT"
        
    async def test_validate_valid_content(self):
        """Test acceptance of valid essay content."""
        validator = FileContentValidator()
        essay_text = "This is a valid essay with sufficient content and meaningful structure for processing that meets all validation requirements."
        result = await validator.validate_content(essay_text, "valid.txt")
        assert result.is_valid
```

**6.2 Integration Tests for Event Coordination**  
**New File**: `services/file_service/tests/test_validation_event_coordination.py`

```python
class TestValidationEventCoordination:
    async def test_validation_failure_publishes_event(self, file_service_client, mock_event_publisher):
        """Test that validation failures publish EssayValidationFailedV1 events."""
        # Test with mock verification of event publishing
        
    async def test_mixed_validation_batch_coordination(self, file_service_client):
        """Test batch with both successful and failed validations publishes correct events."""
        # Verify proper event coordination for mixed results
```

**6.3 End-to-End BOS/ELS Coordination Tests**  
**New File**: `tests/functional/test_validation_batch_coordination.py`

```python
@pytest.mark.asyncio
async def test_batch_completion_with_validation_failures():
    """Test that batches complete properly when some files fail validation."""
    
    # 1. Register batch expecting 5 essays with BOS
    batch_id = await register_batch_with_bos(expected_essay_count=5)
    
    # 2. Upload 5 files: 3 valid, 2 invalid (empty/short content)
    upload_results = await upload_mixed_validation_batch(batch_id)
    
    # 3. Verify File Service response shows validation summary
    assert upload_results["successful_files"] == 3
    assert upload_results["validation_failures"] == 2
    
    # 4. Wait for ELS processing and coordination
    await asyncio.sleep(5)
    
    # 5. Verify BatchEssaysReady event published with correct coordination data
    batch_ready_events = await get_batch_ready_events(batch_id)
    assert len(batch_ready_events) == 1
    
    ready_event = batch_ready_events[0]
    assert len(ready_event["ready_essays"]) == 3
    assert len(ready_event["validation_failures"]) == 2
    assert ready_event["total_files_processed"] == 5
    
    # 6. Verify BOS receives proper batch information for pipeline decisions
    bos_batch_status = await get_bos_batch_status(batch_id)
    assert bos_batch_status["ready_essays"] == 3
    assert bos_batch_status["expected_essays"] == 5

@pytest.mark.asyncio 
async def test_all_files_fail_validation_scenario():
    """Test batch where all files fail validation."""
    
    # Register batch expecting 3 essays
    batch_id = await register_batch_with_bos(expected_essay_count=3)
    
    # Upload 3 files: all empty (invalid)
    upload_results = await upload_all_invalid_batch(batch_id)
    
    # Verify File Service response
    assert upload_results["successful_files"] == 0
    assert upload_results["validation_failures"] == 3
    
    # Wait for ELS processing
    await asyncio.sleep(5)
    
    # Verify ELS handles gracefully (no infinite wait)
    # Should either timeout gracefully or complete with zero essays
    batch_ready_events = await get_batch_ready_events(batch_id)
    if batch_ready_events:
        assert len(batch_ready_events[0]["ready_essays"]) == 0
        assert len(batch_ready_events[0]["validation_failures"]) == 3
```

#### Phase 7: Monitoring & Documentation *(Day 10)*

**7.1 Enhanced Metrics with Coordination Tracking**  
**File**: `services/file_service/startup_setup.py`

```python
def _create_metrics(registry: CollectorRegistry) -> Dict[str, Any]:
    return {
        # ... existing metrics ...
        "validation_results": Counter(
            "file_service_validation_results_total",
            "Content validation results by type and error code",
            ["result_type", "error_code"],  # valid, empty_content, content_too_short, etc.
            registry=registry
        ),
        "validation_duration": Histogram(
            "file_service_validation_duration_seconds",
            "Content validation processing time",
            registry=registry
        ),
        "batch_coordination_events": Counter(
            "file_service_coordination_events_total",
            "Events published for BOS/ELS batch coordination",
            ["event_type"],  # essay_content_provisioned, essay_validation_failed
            registry=registry
        ),
        "batch_validation_summary": Histogram(
            "file_service_batch_validation_ratio",
            "Ratio of successful to failed validations per batch",
            registry=registry
        ),
    }
```

### Architecture Compliance Validation

#### Service Autonomy ✅

- **File Service owns content quality gates**: Maintains bounded context principles
- **Event-driven coordination**: No direct cross-service dependencies
- **Clear responsibility**: File Service responsible for content validation and coordination signaling

#### Event-Driven Architecture ✅

- **Maintains existing event patterns**: Uses established EventEnvelope structure
- **New coordination events**: EssayValidationFailedV1 enables proper batch coordination
- **Backward compatibility**: Existing successful flow unchanged

#### Dependency Injection Pattern ✅

- **Protocol-based design**: ContentValidatorProtocol for abstraction
- **Dishka integration**: Validation service injected via DI container
- **Enhanced publisher protocol**: Extended for validation event publishing

### Risk Assessment and Mitigation

#### Risk 1: Event Ordering and Timing

**Impact**: Validation events could arrive after ELS timeout
**Mitigation**:

- **Immediate publishing**: Validation events published synchronously after validation
- **Event ordering**: Use same Kafka partition key (batch_id) for ordering
- **Timeout adjustment**: Consider ELS timeout settings for validation processing time

#### Risk 2: All Files Fail Validation  

**Impact**: Batch with zero successful essays
**Mitigation**:

- **Graceful handling**: ELS detects zero-essay batches and completes appropriately
- **Clear user feedback**: API response clearly indicates complete validation failure
- **BOS awareness**: BatchEssaysReady event with empty ready_essays list

#### Risk 3: Performance Impact of Additional Events

**Impact**: Increased Kafka load and processing overhead
**Mitigation**:

- **Efficient serialization**: Use proven EventEnvelope serialization patterns
- **Async publishing**: Non-blocking event publication
- **Metrics monitoring**: Track event publishing performance

### Expected Benefits with Coordination

#### Immediate Impact

- **Empty file failures eliminated**: 100% reduction in empty content reaching downstream services
- **Clear user feedback**: Immediate actionable error messages in API responses
- **No infinite waits**: ELS completes batches promptly regardless of validation failures
- **Proper batch coordination**: BOS receives accurate essay counts for pipeline decisions

#### Long-term Benefits

- **Improved success rate**: Higher percentage of essays successfully complete entire pipeline
- **Enhanced debugging**: Clear validation failure audit trail in Kafka events
- **Better user experience**: Immediate feedback with detailed validation error information
- **Operational efficiency**: Reduced support overhead from processing failures and timeouts

### Success Criteria

- **Validation accuracy**: < 1% false positive rate on valid content
- **Performance impact**: < 50ms validation overhead per file
- **Coordination reliability**: 100% of validation failures result in proper ELS batch completion
- **User satisfaction**: Reduction in "processing failed" and "batch timeout" support tickets
- **Pipeline efficiency**: Increase in successful end-to-end processing rate with partial batches

### Implementation Phases Summary

1. **Phase 1** (Day 1): Common core event models and enum updates
2. **Phase 2** (Days 2-3): File Service validation framework with event publishing
3. **Phase 3** (Day 4): Core logic integration with validation and coordination events
4. **Phase 4** (Days 5-6): ELS validation event handling and batch coordination
5. **Phase 5** (Day 7): Enhanced API responses with comprehensive validation feedback
6. **Phase 6** (Days 8-9): Comprehensive testing including BOS/ELS coordination scenarios
7. **Phase 7** (Day 10): Monitoring, metrics, and documentation completion

---

## Summary

✅ **COMPLETED**: BOS pipeline progression issue resolved - `COMPLETED_WITH_FAILURES` now correctly allows progression with successful essays

📋 **REVISED PLAN**: File Service validation layer with complete event-driven BOS/ELS coordination to prevent slot assignment mismatches and infinite timeouts

**Critical Enhancement**: The plan now includes comprehensive event-driven coordination to ensure File Service validation integrates seamlessly with existing BOS/ELS slot assignment architecture while providing superior content quality gates and user feedback.

**Next Steps**: Begin Phase 1 implementation with common core event models, followed by iterative development and testing of the complete coordination solution.
