#!/usr/bin/env python3
"""
Phase 1 Validation: common_core Updates for Enhanced Pipeline Communication

This script validates:
1. ALL_PROCESSING_COMPLETED added to EssayStatus enum
2. ELSBatchPhaseOutcomeV1 event model creation and validation
3. ProcessingEvent enum updates
4. Topic mapping functionality

Usage: pdm run python scripts/tests/test_phase1_common_core_events.py
"""

import json
import sys
from uuid import uuid4


def test_essay_status_completeness():
    """Test that all required EssayStatus enum values exist."""
    print("🧪 Testing EssayStatus enum completeness...")

    try:
        from common_core.enums import EssayStatus

        # Test that ALL_PROCESSING_COMPLETED exists
        assert hasattr(EssayStatus, 'ALL_PROCESSING_COMPLETED'), "ALL_PROCESSING_COMPLETED missing from EssayStatus"

        # Test all required CJ assessment states exist
        required_cj_states = [
            'AWAITING_CJ_ASSESSMENT',
            'CJ_ASSESSMENT_IN_PROGRESS',
            'CJ_ASSESSMENT_SUCCESS',
            'CJ_ASSESSMENT_FAILED'
        ]

        for state in required_cj_states:
            assert hasattr(EssayStatus, state), f"Missing CJ assessment state: {state}"

        # Test all required AI feedback states exist
        required_ai_states = [
            'AWAITING_AI_FEEDBACK',
            'AI_FEEDBACK_IN_PROGRESS',
            'AI_FEEDBACK_SUCCESS',
            'AI_FEEDBACK_FAILED'
        ]

        for state in required_ai_states:
            assert hasattr(EssayStatus, state), f"Missing AI feedback state: {state}"

        # Test all required NLP states exist
        required_nlp_states = [
            'AWAITING_NLP',
            'NLP_IN_PROGRESS',
            'NLP_SUCCESS',
            'NLP_FAILED'
        ]

        for state in required_nlp_states:
            assert hasattr(EssayStatus, state), f"Missing NLP state: {state}"

        print("✅ All required EssayStatus enum values exist")
        return True

    except ImportError as e:
        print(f"❌ Failed to import EssayStatus: {e}")
        return False
    except AssertionError as e:
        print(f"❌ EssayStatus validation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error testing EssayStatus: {e}")
        return False


def test_els_batch_phase_outcome_event():
    """Test ELSBatchPhaseOutcomeV1 event model creation and validation."""
    print("🧪 Testing ELSBatchPhaseOutcomeV1 event model...")

    try:
        from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
        from common_core.metadata_models import EssayProcessingInputRefV1

        # Test basic event creation
        test_event = ELSBatchPhaseOutcomeV1(
            batch_id='test-batch-123',
            phase_name='spellcheck',
            phase_status='COMPLETED_SUCCESSFULLY',
            processed_essays=[],
            failed_essay_ids=[],
            correlation_id=uuid4()
        )

        assert test_event.batch_id == 'test-batch-123'
        assert test_event.phase_name == 'spellcheck'
        assert test_event.phase_status == 'COMPLETED_SUCCESSFULLY'
        assert isinstance(test_event.processed_essays, list)
        assert isinstance(test_event.failed_essay_ids, list)

        # Test with essay processing references
        test_essay_ref = EssayProcessingInputRefV1(
            essay_id='essay-123',
            text_storage_id='storage-456'
        )

        test_event_with_essays = ELSBatchPhaseOutcomeV1(
            batch_id='test-batch-456',
            phase_name='ai_feedback',
            phase_status='COMPLETED_WITH_FAILURES',
            processed_essays=[test_essay_ref],
            failed_essay_ids=['essay-789'],
            correlation_id=uuid4()
        )

        assert len(test_event_with_essays.processed_essays) == 1
        assert test_event_with_essays.processed_essays[0].essay_id == 'essay-123'
        assert len(test_event_with_essays.failed_essay_ids) == 1

        print("✅ ELSBatchPhaseOutcomeV1 event model validation passed")
        return True

    except ImportError as e:
        print(f"❌ Failed to import ELSBatchPhaseOutcomeV1: {e}")
        print("💡 Hint: This model needs to be created in common_core/events/els_bos_events.py")
        return False
    except AssertionError as e:
        print(f"❌ ELSBatchPhaseOutcomeV1 validation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error testing ELSBatchPhaseOutcomeV1: {e}")
        return False


def test_processing_event_updates():
    """Test ProcessingEvent enum updates for new event types."""
    print("🧪 Testing ProcessingEvent enum updates...")

    try:
        from common_core.enums import ProcessingEvent

        # Test that ELS_BATCH_PHASE_OUTCOME event exists
        assert hasattr(ProcessingEvent, 'ELS_BATCH_PHASE_OUTCOME'), "ELS_BATCH_PHASE_OUTCOME missing from ProcessingEvent"

        # Test additional command events for AI feedback and NLP if they should exist
        potential_new_events = [
            'BATCH_AIFEEDBACK_INITIATE_COMMAND',
            'BATCH_NLP_INITIATE_COMMAND'
        ]

        for event in potential_new_events:
            if hasattr(ProcessingEvent, event):
                print(f"✅ Found optional event: {event}")

        print("✅ ProcessingEvent enum updates validated")
        return True

    except ImportError as e:
        print(f"❌ Failed to import ProcessingEvent: {e}")
        return False
    except AssertionError as e:
        print(f"❌ ProcessingEvent validation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error testing ProcessingEvent: {e}")
        return False


def test_topic_name_mapping():
    """Test topic_name function mapping for new events."""
    print("🧪 Testing topic_name mapping for new events...")

    try:
        from common_core.enums import ProcessingEvent, topic_name

        # Test existing mappings still work
        spellcheck_topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
        assert spellcheck_topic == "huleedu.essay.spellcheck.requested.v1"

        # Test new ELS batch phase outcome mapping
        if hasattr(ProcessingEvent, 'ELS_BATCH_PHASE_OUTCOME'):
            phase_outcome_topic = topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME)
            assert phase_outcome_topic is not None, "ELS_BATCH_PHASE_OUTCOME should have topic mapping"
            print(f"✅ ELS_BATCH_PHASE_OUTCOME maps to: {phase_outcome_topic}")

        print("✅ Topic name mapping validation passed")
        return True

    except ImportError as e:
        print(f"❌ Failed to import topic_name: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Topic mapping validation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error testing topic mapping: {e}")
        return False


def test_event_serialization():
    """Test contract serialization and deserialization."""
    print("🧪 Testing event contract serialization...")

    try:
        from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
        from common_core.metadata_models import EssayProcessingInputRefV1

        # Create test event with complete data
        test_essay_ref = EssayProcessingInputRefV1(
            essay_id='essay-123',
            text_storage_id='storage-456'
        )

        original_event = ELSBatchPhaseOutcomeV1(
            batch_id='test-batch-789',
            phase_name='cj_assessment',
            phase_status='COMPLETED_SUCCESSFULLY',
            processed_essays=[test_essay_ref],
            failed_essay_ids=['failed-essay-1', 'failed-essay-2'],
            correlation_id=uuid4()
        )

        # Test JSON serialization
        json_str = original_event.model_dump_json()
        json_data = json.loads(json_str)

        assert json_data['batch_id'] == 'test-batch-789'
        assert json_data['phase_name'] == 'cj_assessment'
        assert len(json_data['processed_essays']) == 1
        assert len(json_data['failed_essay_ids']) == 2

        # Test deserialization
        reconstructed_event = ELSBatchPhaseOutcomeV1.model_validate_json(json_str)

        assert reconstructed_event.batch_id == original_event.batch_id
        assert reconstructed_event.phase_name == original_event.phase_name
        assert reconstructed_event.phase_status == original_event.phase_status
        assert len(reconstructed_event.processed_essays) == len(original_event.processed_essays)
        assert reconstructed_event.processed_essays[0].essay_id == test_essay_ref.essay_id

        print("✅ Event contract serialization test passed")
        return True

    except ImportError as e:
        print(f"❌ Failed to import for serialization test: {e}")
        return False
    except Exception as e:
        print(f"❌ Serialization test failed: {e}")
        return False


def main():
    """Run all Phase 1 validation tests."""
    print("🚀 Phase 1 Validation: common_core Updates for Enhanced Pipeline Communication")
    print("=" * 80)

    tests = [
        test_essay_status_completeness,
        test_els_batch_phase_outcome_event,
        test_processing_event_updates,
        test_topic_name_mapping,
        test_event_serialization
    ]

    results = []
    for test in tests:
        print()
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 80)
    print("📊 Phase 1 Validation Summary:")
    print(f"✅ Passed: {sum(results)}/{len(results)} tests")

    if all(results):
        print("🎉 All Phase 1 validations passed! Ready for Phase 2.")
        return 0
    else:
        print("❌ Some Phase 1 validations failed. Please address before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
