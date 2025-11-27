---
id: "filename-propagation-flow-mapping"
type: "investigation"
created: 2025-11-27
scope: "cross-service"
---

# Filename Propagation Flow Investigation

## Executive Summary

**Problem**: Teachers cannot identify which student wrote which essay in CJ results because `essay_results.filename` is empty in Result Aggregator Service database.

**Root Cause**: **COMPLETE FILENAME PROPAGATION GAP** - Filename never reaches RAS because:
1. File Service publishes filename in `EssayContentProvisionedV1` event ✅
2. ELS stores filename in `slot_assignments.original_file_name` ✅  
3. **BUT**: ELS does NOT include filename in `EssaySlotAssignedV1` event ❌
4. RAS consumes `EssaySlotAssignedV1` but receives NO filename ❌
5. Result: `essay_results.filename` remains NULL ❌

**Investigation Date**: 2025-11-27  
**Services Analyzed**: File Service, ELS, Spellcheck, CJ Assessment, RAS

---

## Event Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FILENAME PROPAGATION FLOW                           │
└─────────────────────────────────────────────────────────────────────────────┘

[File Service]
    │ 
    │ Event: EssayContentProvisionedV1
    │ Fields: ✅ original_file_name
    │         ✅ file_upload_id  
    │         ✅ text_storage_id
    │         ✅ batch_id
    │ Topic: huleedu.file.essay.content.provisioned.v1
    ▼
[Essay Lifecycle Service (ELS)]
    │
    ├─ Stores in DB: ✅ slot_assignments.original_file_name
    │                ✅ slot_assignments.text_storage_id
    │
    │ Event: EssaySlotAssignedV1  
    │ Fields: ✅ essay_id (assigned from pre-generated slots)
    │         ✅ file_upload_id
    │         ✅ text_storage_id
    │         ❌ original_file_name (MISSING!)
    │ Topic: huleedu.essay.slot.assigned.v1
    ▼
[Result Aggregator Service (RAS)]
    │
    ├─ Receives: ✅ file_upload_id
    │            ✅ text_storage_id  
    │            ❌ filename (NOT IN EVENT!)
    │
    ├─ Updates: essay_results.file_upload_id = file_upload_id ✅
    │           essay_results.original_text_storage_id = text_storage_id ✅
    │           essay_results.filename = NULL ❌ (no data to populate)
    │
    └─ Result: Filename gap persists through entire pipeline

[Spellcheck Service] - Does NOT propagate filename
    │ Event: SpellcheckPhaseCompletedV1
    │ Fields: entity_id, batch_id, corrected_text_storage_id
    │ ❌ No filename reference

[CJ Assessment Service] - Does NOT receive filename  
    │ Event: AssessmentResultV1
    │ Fields: essay_results[] with essay_id, scores, grades
    │ ❌ No filename in CJ request or response

[Final State]
    └─ RAS essay_results.filename = NULL
       Teachers see essays without student names (filename is proxy for identity)
```

---

## Breakpoint Analysis

| Service | Receives filename? | Stores filename? | Propagates filename? | Gap? |
|---------|-------------------|------------------|---------------------|------|
| **File Service** | N/A (origin) | ✅ file_uploads.filename | ✅ EssayContentProvisionedV1.original_file_name | ✅ |
| **ELS** | ✅ From File Service event | ✅ slot_assignments.original_file_name | ❌ **NOT in EssaySlotAssignedV1** | **🔴 BREAKPOINT** |
| **RAS** | ❌ **NOT in slot assigned event** | ❌ filename column exists but stays NULL | N/A (no downstream) | **🔴 MISSING** |
| **Spellcheck** | N/A (processes text_storage_id only) | N/A | N/A | N/A |
| **CJ Assessment** | N/A (processes text_storage_id only) | N/A | N/A | N/A |

---

## Schema Analysis

### File Service Database (`file_uploads`)
**Location**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/file_service/models_db.py:45`

```python
filename: Mapped[str] = mapped_column(String(500), nullable=False)
file_upload_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
text_storage_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
```

**Status**: ✅ Stores filename correctly

---

### ELS Database (`slot_assignments`)
**Location**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/essay_lifecycle_service/models_db.py:188`

```python
internal_essay_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
text_storage_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
original_file_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
```

**Status**: ✅ Stores filename correctly but does NOT propagate it

---

### RAS Database (`essay_results`)
**Location**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/result_aggregator_service/models_db.py:111`

```python
filename: Mapped[Optional[str]] = mapped_column(String(255))
file_upload_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
original_text_storage_id: Mapped[Optional[str]] = mapped_column(String(255))
```

**Status**: ❌ Column exists but remains NULL - no source data

---

### CJ Assessment Database (`cj_processed_essays`)
**Location**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/cj_assessment_service/models_db.py:104`

```python
els_essay_id: Mapped[str] = mapped_column(String(36), primary_key=True)
text_storage_id: Mapped[str] = mapped_column(String(256), nullable=False)
# No filename field
```

**Status**: ✅ Correctly does NOT store filename (CJ processes text_storage_id)

---

## Event Contract Analysis

### 1. EssayContentProvisionedV1 (File Service → ELS)
**Location**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/libs/common_core/src/common_core/events/file_events.py:20-52`

```python
class EssayContentProvisionedV1(BaseModel):
    event: str = "essay.content.provisioned"
    entity_id: str                          # batch_id
    file_upload_id: str                     # ✅ File tracking ID
    original_file_name: str                 # ✅ FILENAME PRESENT
    raw_file_storage_id: str
    text_storage_id: str                    # ✅ Content reference
    file_size_bytes: int
    content_md5_hash: str | None
    correlation_id: UUID
    timestamp: datetime
```

**Status**: ✅ Contains filename

---

### 2. EssaySlotAssignedV1 (ELS → RAS) 
**Location**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/libs/common_core/src/common_core/events/essay_lifecycle_events.py:21-37`

```python
class EssaySlotAssignedV1(BaseModel):
    """Critical mapping between file_upload_id and essay_id."""
    
    event: str = "essay.slot.assigned"
    batch_id: str
    essay_id: str                           # ✅ Assigned from pre-generated slots
    file_upload_id: str                     # ✅ Original upload tracking
    text_storage_id: str                    # ✅ Storage reference
    # ❌ original_file_name MISSING!
    correlation_id: UUID
    timestamp: datetime
```

**Status**: ❌ **FILENAME FIELD MISSING** - This is the breakpoint!

---

### 3. EssayProcessingInputRefV1 (ELS → Processing Services)
**Location**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/libs/common_core/src/common_core/metadata_models.py:129-152`

```python
class EssayProcessingInputRefV1(BaseModel):
    """Standard essay reference for processing services (CJ, Spellcheck, NLP)."""
    
    essay_id: str
    text_storage_id: str
    # ❌ No filename field
    spellcheck_metrics: SpellcheckMetricsV1 | None = None
```

**Status**: ✅ Correctly minimal - processing services work with text_storage_id only

---

### 4. SpellcheckPhaseCompletedV1 (Spellcheck → ELS)
**Location**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/libs/common_core/src/common_core/events/spellcheck_models.py:49-76`

```python
class SpellcheckPhaseCompletedV1(BaseModel):
    """Thin event for state management."""
    
    entity_id: str                          # Essay ID
    batch_id: str
    correlation_id: str
    status: ProcessingStatus
    corrected_text_storage_id: str | None
    # ❌ No filename (not needed - ELS already has it)
```

**Status**: ✅ Correctly minimal - no filename needed

---

### 5. AssessmentResultV1 (CJ → RAS)
**Location**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/libs/common_core/src/common_core/events/cj_assessment_events.py:227-273`

```python
class AssessmentResultV1(BaseEventData):
    """Rich assessment result event."""
    
    batch_id: str
    cj_assessment_job_id: str
    assessment_method: str
    model_used: str
    essay_results: list[EssayResultV1]      # Each contains essay_id, scores, grades
    # ❌ No filename in essay results
```

**Status**: ✅ Correctly minimal - CJ assesses text_storage_id, not files

---

## Critical Code Locations

### File Service: Publishes filename
**File**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/file_service/core_logic.py:135,200,265,332`

```python
# File Service creates event with filename
event_data = EssayContentProvisionedV1(
    entity_id=batch_id,
    file_upload_id=file_upload_id,
    original_file_name=file_name,  # ✅ INCLUDED
    text_storage_id=text_storage_id,
    # ...
)
```

---

### ELS: Receives and stores filename but does NOT forward it
**File**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/essay_lifecycle_service/domain_services/content_assignment_service.py:98`

```python
# ELS stores filename from event
await self.slot_manager.assign_content_to_slot(
    batch_id=batch_id,
    text_storage_id=text_storage_id,
    original_file_name=content_metadata.get("original_file_name", "unknown"),  # ✅ STORED
    # ...
)
```

**But then ELS publishes slot assignment WITHOUT filename**:

```python
# ELS publishes slot assigned event (event creation location not shown but defined in event contract)
event_data = EssaySlotAssignedV1(
    batch_id=batch_id,
    essay_id=essay_id,
    file_upload_id=file_upload_id,
    text_storage_id=text_storage_id,
    # ❌ original_file_name NOT INCLUDED
)
```

---

### RAS: Receives slot assignment but gets NO filename
**File**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/result_aggregator_service/implementations/assessment_event_handler.py:58-62`

```python
async def process_essay_slot_assigned(self, envelope, data):
    """Process EssaySlotAssignedV1 - data has no filename field."""
    
    await self.batch_repository.update_essay_file_mapping(
        essay_id=data.essay_id,
        file_upload_id=data.file_upload_id,
        text_storage_id=data.text_storage_id,
        # ❌ No filename parameter - not in event!
    )
```

**File**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/result_aggregator_service/implementations/essay_result_updater.py:290-308`

```python
async def update_essay_file_mapping(
    self, essay_id: str, file_upload_id: str, text_storage_id: Optional[str] = None
):
    """Update essay with file mapping - NO filename parameter."""
    
    if essay:
        essay.file_upload_id = file_upload_id
        if text_storage_id:
            essay.original_text_storage_id = text_storage_id
        # ❌ essay.filename is NEVER set - no data source!
```

---

## Solution Requirements

### Flow 1: GUEST BATCH (No Class Association)
**Current State**: Filename lost at ELS → RAS boundary  
**Requirements**:
1. Add `original_file_name` to `EssaySlotAssignedV1` event contract
2. Update ELS to include filename when publishing slot assignment
3. Update RAS to consume filename and populate `essay_results.filename`

### Flow 2: REGULAR BATCH (Class Association)
**Current State**: Same filename gap as GUEST  
**Requirements**: Same as Flow 1 (no class-specific changes needed)

### Flow 3: FUTURE STATE (Optional Spellcheck)
**Current State**: N/A (spellcheck always runs)  
**Requirements**:
- No filename changes needed
- When spellcheck becomes optional, CJ will use either:
  - `original text_storage_id` (no spellcheck), OR  
  - `spellcheck_corrected_text_storage_id` (with spellcheck)
- Filename tracking is independent of spellcheck path

---

## Implementation Tasks

### Task 1: Update Event Contract
**File**: `libs/common_core/src/common_core/events/essay_lifecycle_events.py`

```python
class EssaySlotAssignedV1(BaseModel):
    event: str = "essay.slot.assigned"
    batch_id: str
    essay_id: str
    file_upload_id: str
    text_storage_id: str
    original_file_name: str  # ⬅️ ADD THIS FIELD
    correlation_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

---

### Task 2: Update ELS Event Publishing
**Location**: Find where ELS constructs `EssaySlotAssignedV1` (likely in slot assignment service)

```python
# ELS needs to pass filename from slot_assignments.original_file_name
event_data = EssaySlotAssignedV1(
    batch_id=batch_id,
    essay_id=essay_id,
    file_upload_id=file_upload_id,
    text_storage_id=text_storage_id,
    original_file_name=original_file_name,  # ⬅️ ADD THIS
)
```

---

### Task 3: Update RAS Event Handler
**File**: `services/result_aggregator_service/implementations/assessment_event_handler.py:58`

```python
async def process_essay_slot_assigned(self, envelope, data):
    await self.batch_repository.update_essay_file_mapping(
        essay_id=data.essay_id,
        file_upload_id=data.file_upload_id,
        text_storage_id=data.text_storage_id,
        filename=data.original_file_name,  # ⬅️ ADD THIS PARAMETER
    )
```

---

### Task 4: Update RAS Repository Protocol
**File**: `services/result_aggregator_service/protocols.py:122`

```python
async def update_essay_file_mapping(
    self,
    essay_id: str,
    file_upload_id: str,
    text_storage_id: Optional[str] = None,
    filename: Optional[str] = None,  # ⬅️ ADD THIS PARAMETER
) -> None:
    """Update essay with file_upload_id and filename for traceability."""
```

---

### Task 5: Update RAS Essay Updater Implementation
**File**: `services/result_aggregator_service/implementations/essay_result_updater.py:270`

```python
async def update_essay_file_mapping(
    self,
    essay_id: str,
    file_upload_id: str,
    text_storage_id: Optional[str] = None,
    filename: Optional[str] = None,  # ⬅️ ADD THIS PARAMETER
):
    if essay:
        essay.file_upload_id = file_upload_id
        if text_storage_id:
            essay.original_text_storage_id = text_storage_id
        if filename:  # ⬅️ ADD THIS
            essay.filename = filename
    else:
        essay = EssayResult(
            essay_id=essay_id,
            file_upload_id=file_upload_id,
            original_text_storage_id=text_storage_id,
            filename=filename,  # ⬅️ ADD THIS
        )
```

---

### Task 6: Update RAS Batch Repository Implementation
**File**: `services/result_aggregator_service/implementations/batch_repository_postgres_impl.py:291`

```python
async def update_essay_file_mapping(
    self,
    essay_id: str,
    file_upload_id: str,
    text_storage_id: Optional[str] = None,
    filename: Optional[str] = None,  # ⬅️ ADD THIS PARAMETER
):
    await self.essay_updater.update_essay_file_mapping(
        essay_id, file_upload_id, text_storage_id, filename  # ⬅️ PASS THROUGH
    )
```

---

## Testing Strategy

### 1. Event Contract Tests
```python
def test_essay_slot_assigned_includes_filename():
    """Verify EssaySlotAssignedV1 contains original_file_name field."""
    event = EssaySlotAssignedV1(
        batch_id="batch-123",
        essay_id="essay-456",
        file_upload_id="upload-789",
        text_storage_id="text-abc",
        original_file_name="student_essay.docx",  # ⬅️ TEST THIS
    )
    assert event.original_file_name == "student_essay.docx"
```

---

### 2. ELS Event Publishing Tests
```python
@pytest.mark.asyncio
async def test_els_publishes_filename_in_slot_assigned():
    """Verify ELS includes filename when publishing slot assignment."""
    # Arrange: Simulate content provisioned event with filename
    # Act: Trigger slot assignment
    # Assert: Published event contains original_file_name
```

---

### 3. RAS Integration Tests
```python
@pytest.mark.asyncio  
async def test_ras_populates_filename_from_slot_assignment():
    """Verify RAS stores filename when receiving slot assignment."""
    # Arrange: Create EssaySlotAssignedV1 with filename
    # Act: Process event
    # Assert: essay_results.filename is populated
```

---

### 4. End-to-End Functional Tests
```python
@pytest.mark.e2e
async def test_guest_batch_filename_propagation():
    """GUEST batch: Filename flows File → ELS → RAS → CJ results."""
    # Upload file with specific name
    # Process through pipeline
    # Query RAS results
    # Assert: filename appears in essay_results
```

```python
@pytest.mark.e2e
async def test_regular_batch_filename_propagation():
    """REGULAR batch: Filename flows through student matching."""
    # Same as guest but with class_id
```

---

## Database Migration Strategy

**No migrations needed!** The `essay_results.filename` column already exists in RAS:

```python
# services/result_aggregator_service/models_db.py:111
filename: Mapped[Optional[str]] = mapped_column(String(255))
```

The column is present but NULL because no code populates it. Once event changes are deployed, existing NULL values will be populated on next batch processing.

### Backfill Strategy (Optional)

If historical filename data is needed:

**Option 1: File Service Lookup API**
```python
GET /v1/files/batch/{batch_id}/assignments
# Returns list of {essay_id, file_upload_id, filename}
# RAS can query and backfill
```

**Option 2: Event Replay**
- Republish historical `EssaySlotAssignedV1` events with filename
- RAS consumers will update existing records

**Option 3: Direct Database Join** (one-time script)
```sql
-- Join file_service.file_uploads with result_aggregator_service.essay_results
UPDATE essay_results er
SET filename = fu.filename
FROM file_service.file_uploads fu
WHERE er.file_upload_id = fu.file_upload_id
  AND er.filename IS NULL;
```

---

## Recommendations

### Priority 1: Fix Core Propagation Gap
1. Add `original_file_name` to `EssaySlotAssignedV1` event
2. Update ELS to populate filename in event
3. Update RAS to consume and store filename
4. **Impact**: Solves GUEST and REGULAR batch flows

### Priority 2: Add Contract Tests
1. Validate event schema includes filename
2. Test ELS→RAS filename propagation
3. **Impact**: Prevent regression

### Priority 3: Functional Test Coverage
1. E2E test for GUEST batch filename visibility
2. E2E test for REGULAR batch filename visibility
3. **Impact**: Validate complete flow

### Priority 4: Backfill Historical Data (Optional)
1. Create File Service lookup endpoint
2. Implement RAS backfill job
3. **Impact**: Teachers can see student names for past batches

---

## Architecture Compliance Notes

### Event Design Principles ✅
- File Service correctly publishes rich event with filename
- ELS correctly stores filename internally
- Spellcheck and CJ correctly use minimal contracts (text_storage_id only)
- **Issue**: ELS→RAS boundary event is too minimal (missing filename)

### Separation of Concerns ✅
- File Service owns file metadata
- ELS owns slot assignment and essay lifecycle
- RAS owns result aggregation
- **Issue**: RAS needs filename for display, but current boundary doesn't provide it

### Data Ownership ✅
- File Service is authoritative source for filename
- ELS is correct to store filename (needs it for context)
- RAS is correct to expect filename (needs it for teacher UX)
- **Issue**: Communication between ELS and RAS incomplete

---

## Conclusion

**Root Cause**: `EssaySlotAssignedV1` event contract is missing `original_file_name` field.

**Impact**: 
- GUEST batches: Teachers cannot identify essays (filename is ONLY identifier)
- REGULAR batches: Teachers cannot identify essays before student matching completes

**Solution Complexity**: **LOW** - Single event contract addition + handler updates

**Files to Modify**: 6 files
1. Event contract definition
2. ELS event publisher
3. RAS event handler  
4. RAS protocol
5. RAS repository implementation
6. RAS essay updater implementation

**Risk**: **LOW** - Additive change, no breaking changes if filename is optional field

**Estimated Effort**: 2-3 hours (implementation + tests)

---

## Appendix: Service Architecture References

### File Service
- **Rule**: `.claude/rules/020.6-file-service-architecture.md`
- **Database**: `services/file_service/models_db.py`
- **Core Logic**: `services/file_service/core_logic.py`

### Essay Lifecycle Service
- **Rule**: `.claude/rules/020.5-essay-lifecycle-service-architecture.md`
- **Database**: `services/essay_lifecycle_service/models_db.py`
- **Slot Assignment**: `services/essay_lifecycle_service/domain_services/content_assignment_service.py`

### Result Aggregator Service
- **Rule**: `.claude/rules/020.12-result-aggregator-service-architecture.md`
- **Database**: `services/result_aggregator_service/models_db.py`
- **Event Handler**: `services/result_aggregator_service/implementations/assessment_event_handler.py`

### CJ Assessment Service
- **Rule**: `.claude/rules/020.7-cj-assessment-service.md`
- **Database**: `services/cj_assessment_service/models_db.py`

### Event Contracts
- **Rule**: `.claude/rules/052-event-contract-standards.md`
- **File Events**: `libs/common_core/src/common_core/events/file_events.py`
- **ELS Events**: `libs/common_core/src/common_core/events/essay_lifecycle_events.py`
- **CJ Events**: `libs/common_core/src/common_core/events/cj_assessment_events.py`
