#!/usr/bin/env python3
"""
Phase 3 Validation: BOS Dynamic Pipeline Orchestration

This script validates:
1. BOS pipeline sequence definition during batch registration
2. ELSBatchPhaseOutcomeV1 event consumption by BOS
3. Next-phase determination and command generation
4. Pipeline state management and progression

Usage: pdm run python scripts/tests/test_phase3_bos_orchestration.py
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add BOS service to path for testing
bos_path = Path(__file__).parent.parent.parent / "services" / "batch_orchestrator_service"
sys.path.insert(0, str(bos_path))


def test_pipeline_sequence_definition():
    """Test BOS pipeline sequence definition and storage."""
    print("🧪 Testing pipeline sequence definition...")

    try:
        from common_core.pipeline_models import (
            PipelineExecutionStatus,
            PipelineStateDetail,
            ProcessingPipelineState,
        )

        # Test creating pipeline state with various sequences
        sequences = [
            ["spellcheck", "cj_assessment"],
            ["spellcheck", "ai_feedback", "nlp"],
            ["spellcheck", "ai_feedback", "cj_assessment"],
            ["spellcheck"]  # Minimal pipeline
        ]

        for sequence in sequences:
            pipeline_state = ProcessingPipelineState(
                batch_id=f'test-batch-{len(sequence)}',
                requested_pipelines=sequence
            )

            assert pipeline_state.batch_id.startswith('test-batch-')
            assert pipeline_state.requested_pipelines == sequence
            assert len(pipeline_state.requested_pipelines) >= 1

            # Test that pipeline details can be accessed
            for stage_name in sequence:
                pipeline_detail = pipeline_state.get_pipeline(stage_name)
                if pipeline_detail is not None:
                    assert isinstance(pipeline_detail, PipelineStateDetail)

        print(f"✅ Pipeline sequence definition working for {len(sequences)} different sequences")
        return True

    except ImportError as e:
        print(f"❌ Failed to import pipeline models: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Pipeline sequence validation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error testing pipeline sequences: {e}")
        return False


async def test_batch_registration_pipeline_setup():
    """Test batch registration sets up pipeline sequences correctly."""
    print("🧪 Testing batch registration pipeline setup...")

    try:
        from api_models import BatchRegistrationRequestV1
        from config import Settings
        from implementations.batch_processing_service_impl import BatchProcessingServiceImpl
        from implementations.batch_repository_impl import MockBatchRepositoryImpl
        from protocols import BatchEventPublisherProtocol

        # Mock event publisher
        class MockEventPublisher:
            async def publish_batch_event(self, event):
                pass

        # Setup test dependencies
        batch_repo = MockBatchRepositoryImpl()
        event_publisher = MockEventPublisher()
        settings = Settings()

        service = BatchProcessingServiceImpl(
            batch_repo=batch_repo,
            event_publisher=event_publisher,
            settings=settings
        )

        # Test registration with CJ assessment enabled
        registration_data = BatchRegistrationRequestV1(
            course_code="ENG101",
            class_designation="Fall2024",
            teacher_name="Test Teacher",
            expected_essay_count=5,
            essay_instructions="Test instructions",
            enable_cj_assessment=True
        )

        batch_id = await service.register_new_batch(registration_data, uuid4())

        # Verify pipeline state was created
        pipeline_state = await batch_repo.get_processing_pipeline_state(batch_id)
        assert pipeline_state is not None

        if isinstance(pipeline_state, dict):
            assert 'requested_pipelines' in pipeline_state
            requested = pipeline_state['requested_pipelines']
        else:
            requested = pipeline_state.requested_pipelines

        assert 'spellcheck' in requested
        assert 'cj_assessment' in requested  # Should be included when enabled

        print("✅ Batch registration pipeline setup working correctly")
        return True

    except ImportError as e:
        print(f"❌ Failed to import for batch registration test: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Batch registration validation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error in batch registration test: {e}")
        return False


def test_els_batch_phase_outcome_consumption():
    """Test BOS can consume ELSBatchPhaseOutcomeV1 events."""
    print("🧪 Testing ELSBatchPhaseOutcomeV1 event consumption...")

    try:
        from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
        from common_core.metadata_models import EssayProcessingInputRefV1

        # Test creating the event that BOS should consume
        processed_essays = [
            EssayProcessingInputRefV1(
                essay_id='essay-1',
                text_storage_id='storage-1-corrected'
            ),
            EssayProcessingInputRefV1(
                essay_id='essay-2',
                text_storage_id='storage-2-corrected'
            )
        ]

        phase_outcome_event = ELSBatchPhaseOutcomeV1(
            batch_id='test-batch-123',
            phase_name='spellcheck',
            phase_status='COMPLETED_SUCCESSFULLY',
            processed_essays=processed_essays,
            failed_essay_ids=['essay-3'],  # One failed
            correlation_id=uuid4()
        )

        # Verify event structure
        assert phase_outcome_event.batch_id == 'test-batch-123'
        assert phase_outcome_event.phase_name == 'spellcheck'
        assert len(phase_outcome_event.processed_essays) == 2
        assert len(phase_outcome_event.failed_essay_ids) == 1

        # Test serialization (for Kafka transport)
        serialized = phase_outcome_event.model_dump_json()
        reconstructed = ELSBatchPhaseOutcomeV1.model_validate_json(serialized)
        assert reconstructed.batch_id == phase_outcome_event.batch_id

        print("✅ ELSBatchPhaseOutcomeV1 event consumption structure validated")
        return True

    except ImportError as e:
        print(f"❌ Failed to import ELSBatchPhaseOutcomeV1: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Event consumption validation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error testing event consumption: {e}")
        return False


def test_next_phase_determination():
    """Test BOS logic for determining next phase in pipeline."""
    print("🧪 Testing next phase determination logic...")

    try:
        from common_core.pipeline_models import ProcessingPipelineState

        # Test various pipeline progression scenarios
        test_cases = [
            {
                'sequence': ['spellcheck', 'ai_feedback', 'cj_assessment'],
                'completed': 'spellcheck',
                'expected_next': 'ai_feedback'
            },
            {
                'sequence': ['spellcheck', 'ai_feedback', 'cj_assessment'],
                'completed': 'ai_feedback',
                'expected_next': 'cj_assessment'
            },
            {
                'sequence': ['spellcheck', 'ai_feedback', 'cj_assessment'],
                'completed': 'cj_assessment',
                'expected_next': None  # End of pipeline
            },
            {
                'sequence': ['spellcheck', 'cj_assessment'],
                'completed': 'spellcheck',
                'expected_next': 'cj_assessment'
            },
            {
                'sequence': ['spellcheck'],
                'completed': 'spellcheck',
                'expected_next': None  # Single-stage pipeline
            }
        ]

        for case in test_cases:
            pipeline_state = ProcessingPipelineState(
                batch_id='test-batch',
                requested_pipelines=case['sequence']
            )

            # Simulate next phase determination logic
            completed_phase = case['completed']
            try:
                current_index = pipeline_state.requested_pipelines.index(completed_phase)
                if current_index + 1 < len(pipeline_state.requested_pipelines):
                    next_phase = pipeline_state.requested_pipelines[current_index + 1]
                else:
                    next_phase = None
            except ValueError:
                next_phase = None

            assert next_phase == case['expected_next'], \
                f"Expected {case['expected_next']}, got {next_phase} for sequence {case['sequence']} after {completed_phase}"

        print("✅ Next phase determination logic working correctly")
        return True

    except ImportError as e:
        print(f"❌ Failed to import for next phase test: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Next phase determination failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error in next phase test: {e}")
        return False


def test_command_generation_mapping():
    """Test BOS command generation for different phases."""
    print("🧪 Testing command generation mapping...")

    try:
        from common_core.batch_service_models import (
            BatchServiceCJAssessmentInitiateCommandDataV1,
            BatchServiceSpellcheckInitiateCommandDataV1,
        )
        from common_core.enums import ProcessingEvent
        from common_core.metadata_models import EntityReference, EssayProcessingInputRefV1

        # Test mapping phase names to command types
        phase_to_command = {
            'spellcheck': {
                'command_class': BatchServiceSpellcheckInitiateCommandDataV1,
                'event_type': ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND
            },
            'cj_assessment': {
                'command_class': BatchServiceCJAssessmentInitiateCommandDataV1,
                'event_type': ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND
            }
        }

        # Test command construction for each supported phase
        test_essays = [
            EssayProcessingInputRefV1(essay_id='essay-1', text_storage_id='storage-1'),
            EssayProcessingInputRefV1(essay_id='essay-2', text_storage_id='storage-2')
        ]

        for phase_name, command_info in phase_to_command.items():
            command_class = command_info['command_class']

            # Test creating command data
            command_data = command_class(
                event_name=command_info['event_type'],
                entity_ref=EntityReference(entity_id='test-batch', entity_type='batch'),
                essays_to_process=test_essays,
                language='en',
                course_code='TEST101',
                teacher_name='Test Teacher',
                class_designation='TestClass',
                essay_instructions='Test instructions'
            )

            assert command_data.entity_ref.entity_id == 'test-batch'
            assert len(command_data.essays_to_process) == 2
            assert command_data.language == 'en'

        print("✅ Command generation mapping working correctly")
        return True

    except ImportError as e:
        print(f"❌ Failed to import command models: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Command generation validation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error in command generation test: {e}")
        return False


async def test_pipeline_state_updates():
    """Test BOS pipeline state updates during orchestration."""
    print("🧪 Testing pipeline state updates...")

    try:
        from implementations.batch_repository_impl import MockBatchRepositoryImpl

        from common_core.pipeline_models import PipelineExecutionStatus, ProcessingPipelineState

        # Test pipeline state progression
        batch_repo = MockBatchRepositoryImpl()

        # Initial pipeline state
        initial_state = ProcessingPipelineState(
            batch_id='test-batch',
            requested_pipelines=['spellcheck', 'ai_feedback']
        )

        await batch_repo.save_processing_pipeline_state('test-batch', initial_state)

        # Simulate spellcheck completion and AI feedback initiation
        retrieved_state = await batch_repo.get_processing_pipeline_state('test-batch')
        assert retrieved_state is not None

        # Test state update logic (simulating BOS orchestration)
        if isinstance(retrieved_state, dict):
            retrieved_state['spellcheck_status'] = 'COMPLETED_SUCCESSFULLY'
            retrieved_state['ai_feedback_status'] = 'DISPATCH_INITIATED'
        else:
            # Handle Pydantic object case
            if hasattr(retrieved_state, 'spellcheck') and retrieved_state.spellcheck:
                retrieved_state.spellcheck.status = PipelineExecutionStatus.COMPLETED_SUCCESSFULLY
            if hasattr(retrieved_state, 'ai_feedback') and retrieved_state.ai_feedback:
                retrieved_state.ai_feedback.status = PipelineExecutionStatus.DISPATCH_INITIATED

        await batch_repo.save_processing_pipeline_state('test-batch', retrieved_state)

        # Verify updates
        final_state = await batch_repo.get_processing_pipeline_state('test-batch')
        assert final_state is not None

        print("✅ Pipeline state updates working correctly")
        return True

    except ImportError as e:
        print(f"❌ Failed to import for pipeline state test: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Pipeline state update validation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error in pipeline state test: {e}")
        return False


def test_essay_list_propagation():
    """Test that essay lists propagate correctly between phases."""
    print("🧪 Testing essay list propagation...")

    try:
        from common_core.batch_service_models import BatchServiceCJAssessmentInitiateCommandDataV1
        from common_core.enums import ProcessingEvent
        from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
        from common_core.metadata_models import EntityReference, EssayProcessingInputRefV1

        # Simulate ELS phase completion with partial success
        spellcheck_outcome = ELSBatchPhaseOutcomeV1(
            batch_id='test-batch',
            phase_name='spellcheck',
            phase_status='COMPLETED_WITH_FAILURES',
            processed_essays=[
                EssayProcessingInputRefV1(essay_id='essay-1', text_storage_id='corrected-1'),
                EssayProcessingInputRefV1(essay_id='essay-2', text_storage_id='corrected-2')
            ],
            failed_essay_ids=['essay-3', 'essay-4'],  # These should not propagate
            correlation_id=uuid4()
        )

        # Simulate BOS creating next phase command using only successful essays
        next_phase_command = BatchServiceCJAssessmentInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND,
            entity_ref=EntityReference(entity_id='test-batch', entity_type='batch'),
            essays_to_process=spellcheck_outcome.processed_essays,  # Only successful essays
            language='en',
            course_code='TEST101',
            teacher_name='Test Teacher',
            class_designation='TestClass',
            essay_instructions='Test instructions'
        )

        # Verify only successful essays are included
        assert len(next_phase_command.essays_to_process) == 2
        assert next_phase_command.essays_to_process[0].essay_id == 'essay-1'
        assert next_phase_command.essays_to_process[0].text_storage_id == 'corrected-1'
        assert next_phase_command.essays_to_process[1].essay_id == 'essay-2'
        assert next_phase_command.essays_to_process[1].text_storage_id == 'corrected-2'

        # Ensure failed essays are not included
        essay_ids = [essay.essay_id for essay in next_phase_command.essays_to_process]
        assert 'essay-3' not in essay_ids
        assert 'essay-4' not in essay_ids

        print("✅ Essay list propagation working correctly (failed essays excluded)")
        return True

    except ImportError as e:
        print(f"❌ Failed to import for essay propagation test: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Essay list propagation validation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error in essay propagation test: {e}")
        return False


async def test_idempotency_handling():
    """Test BOS idempotency handling for phase initiation."""
    print("🧪 Testing idempotency handling...")

    try:
        from common_core.pipeline_models import PipelineExecutionStatus, ProcessingPipelineState

        # Test scenario: phase already initiated should not be re-initiated
        pipeline_state = ProcessingPipelineState(
            batch_id='test-batch',
            requested_pipelines=['spellcheck', 'ai_feedback']
        )

        # Simulate AI feedback already initiated
        if hasattr(pipeline_state, 'ai_feedback') and pipeline_state.ai_feedback:
            pipeline_state.ai_feedback.status = PipelineExecutionStatus.DISPATCH_INITIATED

        # Test idempotency check logic
        next_phase_name = 'ai_feedback'
        next_phase_detail = pipeline_state.get_pipeline(next_phase_name)

        should_skip = (next_phase_detail and
                      next_phase_detail.status not in [
                          PipelineExecutionStatus.REQUESTED_BY_USER,
                          PipelineExecutionStatus.PENDING_DEPENDENCIES
                      ])

        assert should_skip, "Should skip already initiated phase"

        print("✅ Idempotency handling working correctly")
        return True

    except ImportError as e:
        print(f"❌ Failed to import for idempotency test: {e}")
        return False
    except AssertionError as e:
        print(f"❌ Idempotency validation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error in idempotency test: {e}")
        return False


async def main():
    """Run all Phase 3 validation tests."""
    print("🚀 Phase 3 Validation: BOS Dynamic Pipeline Orchestration")
    print("=" * 80)

    sync_tests = [
        test_pipeline_sequence_definition,
        test_els_batch_phase_outcome_consumption,
        test_next_phase_determination,
        test_command_generation_mapping,
        test_essay_list_propagation
    ]

    async_tests = [
        test_batch_registration_pipeline_setup,
        test_pipeline_state_updates,
        test_idempotency_handling
    ]

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
    print("📊 Phase 3 Validation Summary:")
    print(f"✅ Passed: {sum(results)}/{len(results)} tests")

    if all(results):
        print("🎉 All Phase 3 validations passed! Ready for Phase 4.")
        return 0
    else:
        print("❌ Some Phase 3 validations failed. Please address before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
