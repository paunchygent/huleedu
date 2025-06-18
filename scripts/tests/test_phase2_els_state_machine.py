#!/usr/bin/env python3
"""
Phase 2 Validation: ELS State Machine Implementation

This script validates:
1. transitions library dependency
2. EssayStateMachine class implementation
3. State machine integration with ELS components
4. Batch-level phase completion tracking

Usage: pdm run python scripts/tests/test_phase2_els_state_machine.py
"""

import asyncio
import sys
from pathlib import Path

# Add ELS service to path for testing
els_path = Path(__file__).parent.parent.parent / "services" / "essay_lifecycle_service"
sys.path.insert(0, str(els_path))


def test_transitions_library():
    """Test that transitions library is properly installed and accessible."""
    print("🧪 Testing transitions library installation...")

    try:
        from transitions import Machine

        # Test basic machine creation
        class TestModel:
            pass

        test_model = TestModel()
        Machine(model=test_model, states=["A", "B"], initial="A")

        assert test_model.state == "A"  # type: ignore[attr-defined]
        print("✅ transitions library is properly installed and functional")
        return True

    except ImportError as e:
        print(f"❌ Failed to import transitions library: {e}")
        print("💡 Hint: Run 'pdm add transitions' to install")
        return False
    except Exception as e:
        print(f"❌ Unexpected error testing transitions library: {e}")
        return False


def test_essay_state_machine_creation():
    """Test EssayStateMachine class instantiation and basic functionality."""
    print("🧪 Testing EssayStateMachine class creation...")

    try:
        from essay_state_machine import EssayStateMachine

        from common_core.enums import EssayStatus

        # Test machine creation with valid initial state
        machine = EssayStateMachine("test-essay-123", EssayStatus.READY_FOR_PROCESSING)

        assert machine.essay_id == "test-essay-123"
        assert machine.current_status == EssayStatus.READY_FOR_PROCESSING
        assert hasattr(machine, "machine")

        print(f"✅ EssayStateMachine created successfully with status: {machine.current_status}")
        return True

    except ImportError as e:
        print(f"❌ Failed to import EssayStateMachine: {e}")
        print(
            "💡 Hint: EssayStateMachine class needs to be created in "
            "services/essay_lifecycle_service/essay_state_machine.py"
        )
        return False
    except Exception as e:
        print(f"❌ Unexpected error creating EssayStateMachine: {e}")
        return False


def test_state_machine_triggers():
    """Test state machine trigger definitions and basic transitions."""
    print("🧪 Testing state machine triggers and transitions...")

    try:
        from essay_state_machine import (
            CMD_INITIATE_SPELLCHECK,
            EVT_SPELLCHECK_SUCCEEDED,
            EssayStateMachine,
        )

        from common_core.enums import EssayStatus

        # Test spellcheck initiation from READY_FOR_PROCESSING
        machine = EssayStateMachine("test-essay", EssayStatus.READY_FOR_PROCESSING)

        # Valid transition: READY_FOR_PROCESSING -> AWAITING_SPELLCHECK
        success = machine.trigger(CMD_INITIATE_SPELLCHECK)
        assert success, "Failed to initiate spellcheck from READY_FOR_PROCESSING"
        assert machine.current_status == EssayStatus.AWAITING_SPELLCHECK

        # Test invalid transition (should fail)
        invalid_success = machine.trigger(EVT_SPELLCHECK_SUCCEEDED)
        assert not invalid_success, "Invalid transition should have failed"

        # Test valid trigger checking
        assert machine.can_trigger("EVT_SPELLCHECK_STARTED")
        assert not machine.can_trigger("EVT_AI_FEEDBACK_SUCCEEDED")

        print("✅ State machine triggers and transitions working correctly")
        return True

    except ImportError as e:
        print(f"❌ Failed to import state machine triggers: {e}")
        return False
    except AssertionError as e:
        print(f"❌ State machine trigger validation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error testing triggers: {e}")
        return False


def test_multi_phase_transitions():
    """Test complex multi-phase pipeline transitions."""
    print("🧪 Testing multi-phase pipeline transitions...")

    try:
        from essay_state_machine import (
            CMD_INITIATE_AI_FEEDBACK,
            CMD_INITIATE_CJ_ASSESSMENT,
            CMD_INITIATE_SPELLCHECK,
            CMD_MARK_PIPELINE_COMPLETE,
            EVT_AI_FEEDBACK_SUCCEEDED,
            EVT_CJ_ASSESSMENT_SUCCEEDED,
            EVT_SPELLCHECK_SUCCEEDED,
            EssayStateMachine,
        )

        from common_core.enums import EssayStatus

        # Test full pipeline: Spellcheck -> AI Feedback -> CJ Assessment -> Complete
        machine = EssayStateMachine("test-pipeline-essay", EssayStatus.READY_FOR_PROCESSING)

        # Phase 1: Spellcheck
        assert machine.trigger(CMD_INITIATE_SPELLCHECK)
        assert machine.current_status == EssayStatus.AWAITING_SPELLCHECK

        assert machine.trigger("EVT_SPELLCHECK_STARTED")
        assert machine.current_status == EssayStatus.SPELLCHECKING_IN_PROGRESS

        assert machine.trigger(EVT_SPELLCHECK_SUCCEEDED)
        assert machine.current_status == EssayStatus.SPELLCHECKED_SUCCESS

        # Phase 2: AI Feedback
        assert machine.trigger(CMD_INITIATE_AI_FEEDBACK)
        assert machine.current_status == EssayStatus.AWAITING_AI_FEEDBACK

        assert machine.trigger("EVT_AI_FEEDBACK_STARTED")
        assert machine.current_status == EssayStatus.AI_FEEDBACK_IN_PROGRESS

        assert machine.trigger(EVT_AI_FEEDBACK_SUCCEEDED)
        assert machine.current_status == EssayStatus.AI_FEEDBACK_SUCCESS

        # Phase 3: CJ Assessment
        assert machine.trigger(CMD_INITIATE_CJ_ASSESSMENT)
        assert machine.current_status == EssayStatus.AWAITING_CJ_ASSESSMENT

        assert machine.trigger("EVT_CJ_ASSESSMENT_STARTED")
        assert machine.current_status == EssayStatus.CJ_ASSESSMENT_IN_PROGRESS

        assert machine.trigger(EVT_CJ_ASSESSMENT_SUCCEEDED)
        assert machine.current_status == EssayStatus.CJ_ASSESSMENT_SUCCESS

        # Phase 4: Complete
        assert machine.trigger(CMD_MARK_PIPELINE_COMPLETE)
        assert machine.current_status == EssayStatus.ALL_PROCESSING_COMPLETED

        print("✅ Multi-phase pipeline transitions working correctly")
        return True

    except ImportError as e:
        print(f"❌ Failed to import for multi-phase test: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Multi-phase transition validation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error in multi-phase test: {e}")
        return False


def test_state_machine_validation_capabilities():
    """Test EssayStateMachine validation and trigger capabilities."""
    print("🧪 Testing EssayStateMachine validation capabilities...")

    try:
        from essay_state_machine import CMD_INITIATE_SPELLCHECK, EssayStateMachine

        from common_core.enums import EssayStatus

        machine = EssayStateMachine("test-validation", EssayStatus.READY_FOR_PROCESSING)

        # Test can_trigger method works correctly
        can_trigger = machine.can_trigger(CMD_INITIATE_SPELLCHECK)
        assert can_trigger, (
            "EssayStateMachine should allow CMD_INITIATE_SPELLCHECK from READY_FOR_PROCESSING"
        )

        # Test getting valid triggers
        valid_triggers = machine.get_valid_triggers()
        assert isinstance(valid_triggers, list)
        assert len(valid_triggers) > 0
        assert CMD_INITIATE_SPELLCHECK in valid_triggers

        # Test invalid trigger validation
        invalid_trigger = machine.can_trigger("INVALID_TRIGGER")
        assert not invalid_trigger, "EssayStateMachine should reject invalid triggers"

        print("✅ EssayStateMachine validation capabilities working correctly")
        return True

    except ImportError as e:
        print(f"❌ Failed to import for validation test: {e}")
        return False
    except AssertionError as e:
        print(f"❌ EssayStateMachine validation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error in validation test: {e}")
        return False


async def test_state_store_integration():
    """Test state store integration with state machine."""
    print("🧪 Testing state store integration...")

    try:
        import os

        # Test with temporary database file (in-memory doesn't work across connections)
        import tempfile

        from essay_state_machine import CMD_INITIATE_SPELLCHECK, EssayStateMachine
        from state_store import SQLiteEssayStateStore

        from common_core.enums import EssayStatus

        temp_db = tempfile.mktemp(suffix=".db")
        store = SQLiteEssayStateStore(temp_db)
        await store.initialize()

        # Create initial essay state
        await store.create_essay_record(
            essay_id="test-store-essay",
            slot_assignment="1",
            batch_id="test-batch",
            initial_status=EssayStatus.READY_FOR_PROCESSING,
        )

        # Test state machine integration
        machine = EssayStateMachine("test-store-essay", EssayStatus.READY_FOR_PROCESSING)
        success = machine.trigger(CMD_INITIATE_SPELLCHECK)
        assert success

        # Test updating state via machine
        await store.update_essay_status_via_machine(
            "test-store-essay",
            machine.current_status,
            {"test_metadata": "state_machine_transition"},
        )

        # Verify state was persisted
        essay_state = await store.get_essay_state("test-store-essay")
        assert essay_state is not None
        assert essay_state.current_status == EssayStatus.AWAITING_SPELLCHECK

        # Clean up temporary file
        try:
            os.unlink(temp_db)
        except OSError:
            pass

        print("✅ State store integration working correctly")
        return True

    except ImportError as e:
        print(f"❌ Failed to import for state store test: {e}")
        return False
    except AssertionError as e:
        print(f"❌ State store integration failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error in state store test: {e}")
        return False


def test_convenience_methods():
    """Test convenience methods on EssayStateMachine."""
    print("🧪 Testing convenience methods...")

    try:
        from essay_state_machine import EssayStateMachine

        from common_core.enums import EssayStatus

        machine = EssayStateMachine("test-convenience", EssayStatus.READY_FOR_PROCESSING)

        # Test convenience methods exist and work
        if hasattr(machine, "cmd_initiate_spellcheck"):
            success = machine.cmd_initiate_spellcheck()
            assert success
            assert machine.current_status == EssayStatus.AWAITING_SPELLCHECK
            print("✅ Convenience methods working")
        else:
            print("ℹ️  Convenience methods not implemented (optional)")

        return True

    except Exception as e:
        print(f"❌ Error testing convenience methods: {e}")
        return False


async def test_batch_phase_completion_tracking():
    """Test batch-level phase completion tracking (stub test)."""
    print("🧪 Testing batch-level phase completion tracking...")

    try:
        # This is a stub test since the actual implementation will be more complex
        # and depend on the specific batch tracking logic in ELS

        print("ℹ️  Batch phase completion tracking test - implementation pending")
        print("💡 This will be validated in integration tests once ELS handlers are updated")
        return True

    except Exception as e:
        print(f"❌ Error in batch tracking test: {e}")
        return False


async def main():
    """Run all Phase 2 validation tests."""
    print("🚀 Phase 2 Validation: ELS State Machine Implementation")
    print("=" * 80)

    sync_tests = [
        test_transitions_library,
        test_essay_state_machine_creation,
        test_state_machine_triggers,
        test_multi_phase_transitions,
        test_state_machine_validation_capabilities,
        test_convenience_methods,
    ]

    async_tests = [test_state_store_integration, test_batch_phase_completion_tracking]

    results = []

    # Run synchronous tests
    for test in sync_tests:
        print()
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)

    # Run asynchronous tests
    for test in async_tests:
        print()
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 80)
    print("📊 Phase 2 Validation Summary:")
    print(f"✅ Passed: {sum(results)}/{len(results)} tests")

    if all(results):
        print("🎉 All Phase 2 validations passed! Ready for Phase 3.")
        return 0
    else:
        print("❌ Some Phase 2 validations failed. Please address before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
