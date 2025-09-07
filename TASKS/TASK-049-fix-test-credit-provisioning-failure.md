# TASK-049: Fix Test Credit Provisioning Failure

**Status**: ✅ Completed  
**Priority**: High  
**Category**: Testing Infrastructure  
**Created**: 2025-01-07  
**Completed**: 2025-01-07  

## Problem Statement

The functional test `test_e2e_cj_after_nlp_with_pruning.py` is failing due to insufficient credits during the CJ Assessment pipeline phase. After Entitlements Service integration, BOS now performs preflight credit checks before initiating pipelines, but test infrastructure doesn't provision credits for test users.

### Root Cause Analysis

**Event Flow Breakdown:**
1. ✅ NLP pipeline completes successfully (spellcheck + nlp phases)
2. ✅ CJ Assessment pipeline request sent to BOS
3. ✅ BOS → BCS: Pipeline resolution successful (returns ['cj_assessment'])
4. ❌ BOS → Entitlements: Preflight check FAILS (0 credits available, 45 required)
5. ❌ BOS publishes `PipelineDeniedV1` event instead of initiating pipeline
6. ❌ Test times out waiting for CJ Assessment completion

**BOS Log Evidence:**
```
Pipeline denied due to insufficient credits
required_credits: 45, available_credits: 0
```

## Solution Design

### Requirements (Simplified)
1. **Simple provisioning**: Provision credits to both org and user  
2. **Configurable amount**: Default 10,000 credits
3. **Optional disabling**: Allow testing credit denial scenarios
4. **Clear logging**: Log what was provisioned

### Actual Implementation

#### Added Simple Credit Provisioning Method

**File**: `tests/functional/pipeline_test_harness.py`

Added a single `provision_credits()` method that:
- Provisions to org if user has organization_id
- Always provisions to user as fallback
- Can be disabled for denial testing
- Logs results clearly

#### Integration Points

Updated existing methods to call credit provisioning:
- `setup_regular_batch_with_student_matching()` - After batch ready, before returning
- `setup_guest_batch()` - After batch ready, before returning

## Implementation Details

### Credit Provisioning Method (Actual)
```python
async def provision_credits(
    self,
    amount: int = 10000,
    provision_credits: bool = True,
) -> None:
    """
    Provision credits for test user to ensure pipelines can execute.

    BOS checks org credits first, then user credits. We provision to both
    to ensure tests pass regardless of user type.

    Args:
        amount: Credit amount to provision (default 10000 is sufficient for most tests)
        provision_credits: Set to False to test credit denial scenarios
    """
    if not provision_credits:
        logger.info("Credit provisioning disabled for this test")
        return

    # Provision to org if user has one
    if hasattr(self.teacher_user, "organization_id") and self.teacher_user.organization_id:
        try:
            await self.service_manager.make_request(
                method="POST",
                service="entitlements_service",
                path="/v1/admin/credits/set",
                json={
                    "subject_type": "org",
                    "subject_id": self.teacher_user.organization_id,
                    "balance": amount,
                },
                user=self.teacher_user,
                correlation_id=self.correlation_id,
            )
            logger.info(f"💳 Provisioned {amount} credits to org {self.teacher_user.organization_id}")
        except Exception as e:
            logger.warning(f"Could not provision org credits: {e}")

    # Always provision to user as fallback
    try:
        await self.service_manager.make_request(
            method="POST",
            service="entitlements_service",
            path="/v1/admin/credits/set",
            json={
                "subject_type": "user",
                "subject_id": self.teacher_user.user_id,
                "balance": amount,
            },
            user=self.teacher_user,
            correlation_id=self.correlation_id,
        )
        logger.info(f"💳 Provisioned {amount} credits to user {self.teacher_user.user_id}")
    except Exception as e:
        logger.warning(f"Could not provision user credits: {e}")
        logger.warning("⚠️ Tests may fail with 402 insufficient credits errors")
```

### Admin Endpoint Usage
```python
POST /v1/admin/credits/set
{
    "subject_type": "org|user",
    "subject_id": "<id>",
    "balance": <amount>
}
```

## Testing Strategy

### Test Scenarios
1. **Default provisioning** - Verify auto strategy works
2. **Org-specific** - Test org_only strategy
3. **User-specific** - Test user_only strategy
4. **Denial testing** - Test with enabled=False
5. **Fallback** - Test fallback on primary failure
6. **Both strategy** - Verify both subjects get credits

### Verification Points
- Check BOS preflight logs show sufficient credits
- Verify pipeline initiates after provisioning
- Confirm Entitlements Service records consumption
- Test 402 response when provisioning disabled

## Rollback Plan

If issues arise:
1. Tests can disable provisioning with `enabled=False`
2. Individual tests can override with custom config
3. Existing tests without provisioning calls continue working

## Results

### Test Execution
```
✅ test_e2e_cj_after_nlp_with_pruning.py PASSED in 25.01s
```

### Key Log Messages
```
💳 Provisioned 10000 credits to org test_org_test_user_319de7ba
💳 Provisioned 10000 credits to user test_user_319de7ba
✅ NLP pipeline complete! Executed: ['spellcheck', 'nlp'] in 7.63s
✅ BCS correctly pruned spellcheck! Pruned phases: ['spellcheck']
✅ CJ Assessment pipeline complete with pruning! Executed: ['cj_assessment'], Pruned: ['spellcheck'] in 2.52s
```

## Success Criteria

1. ✅ `test_e2e_cj_after_nlp_with_pruning.py` passes
2. ✅ Credit provisioning logs are clear and traceable
3. ✅ Both org and user credits are provisioned
4. ✅ BOS preflight checks pass with sufficient credits
5. ✅ Test can be disabled for 402 denial scenarios

## Notes

- Kept implementation simple - just provision to both org and user
- Default 10,000 credits is sufficient for all current test scenarios  
- Can be disabled by passing `provision_credits=False` for denial testing
- Explicit logging with 💳 emoji makes credit provisioning visible in logs

## References

- Entitlements Service Admin API: `/services/entitlements_service/api/admin_routes.py`
- BOS Preflight Logic: `/services/batch_orchestrator_service/pipeline/credit_guard.py`
- Test Harness: `/tests/functional/pipeline_test_harness.py`

## Lessons Learned

- **KISS principle works**: Initial design was overcomplicated with strategies
- **Simple solution**: Just provision to both org and user covers all cases
- **Default behavior**: Making credit provisioning automatic prevents test failures
- **Clear logging**: Using emojis (💳) makes credit operations visible in test logs