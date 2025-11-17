# Test Plan for Dual Event Publishing

## Testing Strategy Based on Rule 075

### Pre-Implementation Checklist
- [x] Rule compliance review (000-rule-index.md)
- [x] Service architecture understanding (020.7-cj-assessment-service.md)
- [x] Domain analysis (CJ Assessment bounded context)
- [x] Pattern study from existing tests
- [ ] Run typecheck-all before implementation

## Test Files to Create

### 1. Unit Tests (services/cj_assessment_service/tests/unit/)

#### test_dual_event_publishing.py
**Purpose**: Test the centralized dual event publishing function
**Focus**: Core logic of event separation and construction
**Test Cases**:
- Test correct separation of student vs anchor rankings
- Test ELS event contains only student rankings
- Test RAS event contains all rankings with is_anchor flags
- Test anchor_grade_distribution calculation correctness
- Test handling of empty rankings
- Test handling of only anchor rankings
- Test handling of only student rankings
- Test metadata field population
- Test display_name generation for anchors
- Test normalized score calculation

#### test_anchor_filtering.py
**Purpose**: Test anchor essay identification and filtering logic
**Focus**: Correct identification based on ANCHOR_ prefix
**Test Cases**:
- Test ANCHOR_ prefix detection
- Test mixed student/anchor rankings separation
- Test case sensitivity (ANCHOR_ vs anchor_)
- Test edge cases (empty IDs, null values)
- Test synthetic ID format (ANCHOR_123_uuid)
- Test filtering preserves all student essays
- Test filtering removes all anchor essays
- Test order preservation after filtering

#### test_assessment_result_event.py
**Purpose**: Test AssessmentResultV1 event construction
**Focus**: Event schema compliance and field mapping
**Test Cases**:
- Test all required fields present
- Test essay_results array structure
- Test is_anchor flag setting for each essay
- Test display_name only set for anchors
- Test bt_score mapping from "score" field
- Test confidence score and label mapping
- Test letter grade assignment
- Test normalized score calculation (0.0-1.0 range)
- Test assessment_metadata structure
- Test anchor_grade_distribution format

### 2. Integration Tests (services/cj_assessment_service/tests/integration/)

#### test_dual_event_workflow_integration.py
**Purpose**: End-to-end workflow from assessment to dual event publishing
**Focus**: Complete data flow and event routing
**Test Cases**:
- Test full workflow from CJ request to dual events
- Test both events reach outbox
- Test transaction atomicity (both succeed or both fail)
- Test rollback on publishing failure
- Test correlation ID propagation
- Test trace context injection
- Test event envelope structure
- Test topic routing correctness

#### test_anchor_essay_integration.py
**Purpose**: End-to-end anchor essay handling
**Focus**: Anchor essay participation and filtering
**Test Cases**:
- Test anchor essays participate in comparisons
- Test anchor essays included in grade projections
- Test anchor essays filtered from ELS event
- Test anchor essays included in RAS event
- Test grade calibration with anchors
- Test anchor_grade_distribution generation
- Test calibration_method setting (anchor vs default)
- Test confidence scoring with anchor calibration

#### test_outbox_pattern_dual_events.py
**Purpose**: Verify outbox pattern for dual events
**Focus**: Atomic consistency and reliability
**Test Cases**:
- Test both events stored atomically in outbox
- Test outbox relay processes both events
- Test failure recovery scenarios
- Test idempotency of event publishing
- Test event ordering guarantees
- Test partial failure handling
- Test outbox cleanup after successful relay

### 3. Contract Tests (services/cj_assessment_service/tests/contracts/)

#### test_els_backward_compatibility.py
**Purpose**: Ensure ELS event contract maintained
**Focus**: No breaking changes to existing consumers
**Test Cases**:
- Test CJAssessmentCompletedV1 schema compliance
- Test deprecated fields still present
- Test rankings structure unchanged
- Test els_essay_id field name (not essay_id)
- Test score field contains BT score
- Test rank field present and correct
- Test grade_projections_summary format
- Test event envelope format
- Test metadata fields preserved

#### test_ras_event_contract.py
**Purpose**: Verify new RAS event contract
**Focus**: Complete and correct assessment data
**Test Cases**:
- Test AssessmentResultV1 schema compliance
- Test all required fields present
- Test essay_results array format
- Test each essay has all required fields
- Test is_anchor boolean field
- Test display_name optional field
- Test assessment_metadata required fields
- Test anchor_grade_distribution structure
- Test event envelope format

## Testing Patterns to Follow

### From Rule 075:
1. Use @pytest.mark.parametrize for comprehensive coverage
2. Test actual behavior, not implementation details
3. Keep test files under 500 LoC
4. Use AsyncMock with spec for protocol mocking
5. Test Swedish characters where applicable (åäöÅÄÖ)
6. Include domain-specific edge cases
7. Run typecheck-all after each test file

### From Existing CJ Tests:
1. Use fixtures from conftest.py for common setup
2. Mock protocols using Dishka DI patterns
3. Use database_fixtures.py for test data
4. Follow naming convention: test_[component]_[aspect].py
5. Include both success and failure scenarios
6. Test idempotency where applicable

## Validation Sequence

For each test file:
1. Write test implementation
2. Run `pdm run typecheck-all` from repository root
3. Run `pdm run pytest [test_file] -v`
4. Achieve 100% pass rate
5. Fix any implementation issues found
6. Update todo list

## Coverage Targets

- **Unit Tests**: ~30 test cases across 3 files
- **Integration Tests**: ~20 test cases across 3 files  
- **Contract Tests**: ~15 test cases across 2 files
- **Total**: ~65 test cases minimum
- **Quality**: 100% pass rate required

## Dependencies to Mock

### Protocols to Mock:
- CJEventPublisherProtocol
- CJRepositoryProtocol
- ContentClientProtocol
- LLMInteractionProtocol

### External Services:
- Kafka (via EventEnvelope)
- PostgreSQL (via AsyncSession)
- Redis (if caching involved)

## Success Criteria

1. All three publishing locations use identical logic
2. anchor_grade_distribution present in all RAS events
3. ELS backward compatibility maintained
4. 100% test coverage for dual event publishing
5. All tests passing with typecheck-all clean