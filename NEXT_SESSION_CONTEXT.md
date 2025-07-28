# HuleEdu Idempotency Test Quality Improvement Session

## CRITICAL: Read These First

**MANDATORY READING ORDER**:
1. `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/000-rule-index.mdc` - Start here for navigation
2. `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/110.1-planning-mode.mdc` - Understand planning requirements
3. `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/110.2-coding-mode.mdc` - Understand coding requirements
4. `/Users/olofs_mba/Documents/Repos/huledu-reboot/Documentation/TASKS/fix_idempotency_test_shortcuts.md` - THE MAIN TASK
5. `/Users/olofs_mba/Documents/Repos/huledu-reboot/IDEMPOTENCY_CONSOLIDATION_STATUS.md` - Background context

## Session Context

### What Has Been Done

<ULTRATHINK>
We successfully completed a major idempotency system consolidation that unified two different idempotency patterns into one. The consolidation:
- Deleted the old `idempotent_consumer_v2` decorator
- Renamed `idempotent_consumer_transaction_aware` to `idempotent_consumer`
- Fixed all 37 failing tests (went from 69% failure rate to 100% passing)
- Identified critical architectural bug in fail-open scenario (missing confirm_idempotency parameter)

However, during the test fixing process, we discovered that while tests pass, they contain dangerous shortcuts and unrealistic mocking that could hide production issues.
</ULTRATHINK>

### Current Task Status

We are working on **Issue 1: Synchronous Confirmation Pattern** from the task document `/Users/olofs_mba/Documents/Repos/huledu-reboot/Documentation/TASKS/fix_idempotency_test_shortcuts.md`.

**Progress**:
- ✅ Created shared test utility: `/Users/olofs_mba/Documents/Repos/huledu-reboot/libs/huleedu_service_libs/tests/idempotency_test_utils.py`
- ✅ Fixed `services/batch_conductor_service/tests/unit/test_bcs_idempotency_basic.py`:
  - Added `test_async_confirmation_pattern`
  - Added `test_crash_before_confirmation`
- ⏳ **NEXT**: Continue with remaining services for Issue 1

### Critical Test Quality Issues Discovered

<ULTRATHINK>
The idempotency tests have several critical shortcuts:

1. **Synchronous Confirmation Pattern**: Tests call `await confirm_idempotency()` immediately after processing, not simulating real async transaction commits
2. **Unrealistic MockRedisClient**: No TTL expiration, no concurrency protection, no network latency
3. **TTL Testing Gaps**: Tests only verify initial 300s processing TTL, never the configured TTL after confirmation
4. **Fail-Open Tests**: Only check Redis wasn't called, don't verify actual message processing
5. **Missing Scenarios**: No concurrent worker tests, no stale lock recovery, no transaction rollback tests
</ULTRATHINK>

## Your Immediate Task

**YOU MUST CONTINUE WITH ISSUE 1** from the task document. The next service to fix is `services/batch_orchestrator_service/tests/unit/test_idempotency_basic.py`.

### Workflow Requirements

<ULTRATHINK>
MANDATORY PROCESS - DO NOT SKIP:
1. Read the task document section for Issue 1
2. Use the AsyncConfirmationTestHelper from `idempotency_test_utils.py`
3. Add similar tests as done for batch_conductor_service:
   - test_async_confirmation_pattern
   - test_crash_before_confirmation
4. Run ONLY the modified test file to verify
5. Do NOT move to next file until current file passes
6. Update task document to mark completion
</ULTRATHINK>

### Required Subagent Usage

When implementing test fixes, use these agents:
- **test-engineer**: For creating and running tests
- **lead-architect-planner**: If you need to understand architectural patterns
- **documentation-maintainer**: After completing each service, update the task document

### Key Files and Patterns

**Test Pattern to Follow** (from batch_conductor_service):
```python
helper = AsyncConfirmationTestHelper()

@idempotent_consumer(redis_client=mock_redis_client, config=config)
async def handle_message_with_controlled_confirmation(
    msg: ConsumerRecord, *, confirm_idempotency
) -> bool:
    return await helper.process_with_controlled_confirmation(
        bcs_kafka_consumer._handle_spellcheck_completed,
        msg,
        confirm_idempotency
    )

# Start processing in background
process_task = asyncio.create_task(handle_message_with_controlled_confirmation(record))

# Wait for processing to complete but before confirmation
await helper.wait_for_processing_complete()

# Verify "processing" state
assert stored_data["status"] == "processing"
assert mock_redis_client.set_calls[0][2] == 300  # Processing TTL

# Allow confirmation
helper.allow_confirmation()
```

### Current Service Status

**Services Remaining for Issue 1**:
1. `batch_orchestrator_service` - NEXT
2. `cj_assessment_service`
3. `essay_lifecycle_service`
4. `spellchecker_service`
5. `result_aggregator_service`

### Critical Rules to Follow

- **ONE file at a time** - Never edit multiple files then test
- **Run tests after EACH change** - Verify nothing breaks
- **Use existing patterns** - Don't create new test patterns
- **Update documentation** - Mark progress in task document

## Important Context

All idempotency tests currently pass (53/53) but contain dangerous shortcuts. We're systematically fixing these to ensure tests actually verify real-world behavior, not just mock interactions.

The AsyncConfirmationTestHelper allows us to control timing between processing and confirmation, simulating real async database transactions.

## Begin Work

Start by reading the Issue 1 section in `/Users/olofs_mba/Documents/Repos/huledu-reboot/Documentation/TASKS/fix_idempotency_test_shortcuts.md` and then fix the batch_orchestrator_service tests.