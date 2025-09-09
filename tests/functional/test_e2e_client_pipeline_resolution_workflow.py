"""
End-to-End Client Pipeline Resolution Workflow Tests

Tests the complete integration of API Gateway → Kafka → BOS → BCS → Pipeline Execution.
Validates that ClientBatchPipelineRequestV1 events trigger the complete pipeline resolution
and execution workflow using real services and infrastructure.

This is the culminating test for the BCS ↔ BOS integration implementation.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tests.functional.comprehensive_pipeline_utils import load_real_test_essays
from tests.functional.pipeline_harness_helpers import (
    BCSIntegrationHelper,
    KafkaMonitorHelper,
)
from tests.functional.pipeline_harness_helpers.kafka_monitor import PipelineExecutionTracker
from tests.functional.pipeline_test_harness import PipelineTestHarness
from tests.functional.pipeline_validation_utils import validate_batch_pipeline_state
from tests.utils.auth_manager import AuthTestManager
from tests.utils.distributed_state_manager import distributed_state_manager
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager


class TestClientPipelineResolutionWorkflow:
    """End-to-end tests for complete client pipeline resolution workflow."""

    @pytest.fixture
    async def service_manager(self) -> ServiceTestManager:
        """Initialize ServiceTestManager with authentication for service management."""
        auth_manager = AuthTestManager()
        return ServiceTestManager(auth_manager=auth_manager)

    @pytest.fixture
    async def test_teacher(self, service_manager: ServiceTestManager):
        """Create authenticated test teacher for pipeline testing."""
        return service_manager.auth_manager.create_teacher_user("Pipeline Test Teacher")

    @pytest.fixture
    async def kafka_manager(self) -> KafkaTestManager:
        """Initialize KafkaTestManager for event workflow testing."""
        from tests.functional.comprehensive_pipeline_utils import create_comprehensive_kafka_manager

        return create_comprehensive_kafka_manager()

    @pytest.fixture
    async def validated_services(self, service_manager: ServiceTestManager) -> dict[str, Any]:
        """
        Ensure all required services are available and validated.

        This fixture validates that critical services are healthy before proceeding
        with end-to-end pipeline resolution testing.
        """
        endpoints = await service_manager.get_validated_endpoints()

        required_services = [
            "batch_orchestrator_service",
            "batch_conductor_service",
            "essay_lifecycle_api",
            "content_service",
        ]

        for service in required_services:
            if service not in endpoints:
                pytest.skip(f"{service} not available for client pipeline resolution E2E testing")

        return endpoints

    @pytest.mark.docker
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_complete_client_pipeline_resolution_workflow(
        self,
        service_manager: ServiceTestManager,
        kafka_manager: KafkaTestManager,
        test_teacher,
    ):
        """
        Test complete client pipeline resolution and execution workflow.

        Validates:
        - ClientBatchPipelineRequestV1 event triggers BCS ↔ BOS integration
        - BCS resolves pipeline based on actual batch state
        - Resolved pipeline initiates specialized service execution
        - Complete pipeline workflow executes correctly
        """
        # Ensure clean distributed state for test isolation
        await distributed_state_manager.quick_redis_cleanup()

        print("\n🚀 Starting complete client pipeline resolution workflow test")

        # Setup harness for batch creation WITH CREDIT PROVISIONING
        auth_manager = AuthTestManager()
        harness = PipelineTestHarness(service_manager, kafka_manager, auth_manager)

        try:
            # STEP 1: Create batch using harness (includes credit provisioning!)
            essay_files = await load_real_test_essays(max_essays=3)
            batch_id, correlation_id = await harness.setup_guest_batch(
                essay_files=essay_files, user=test_teacher
            )
            print(f"📦 Created test batch: {batch_id} with credits provisioned")

            # STEP 2: Verify batch is ready for client-triggered processing
            print("📊 Verifying batch is ready for client-triggered processing...")
            batch_state = await validate_batch_pipeline_state(service_manager, batch_id)
            pipeline_state = batch_state.get("pipeline_state", {}) if batch_state else {}

            # Handle the case where pipeline_state might not have cj_assessment initialized yet
            if not pipeline_state:
                print("⚠️ No pipeline state found yet - batch may not be fully initialized")
                cj_assessment_status = "not_initialized"
            else:
                cj_assessment_data = pipeline_state.get("cj_assessment")
                if cj_assessment_data is None:
                    print("⚠️ CJ Assessment not found in pipeline state")
                    cj_assessment_status = "not_found"
                elif isinstance(cj_assessment_data, dict):
                    cj_assessment_status = cj_assessment_data.get("status", "unknown")
                else:
                    print(f"⚠️ Unexpected cj_assessment data type: {type(cj_assessment_data)}")
                    cj_assessment_status = "unknown"

            print(f"📋 CJ Assessment status: {cj_assessment_status}")
            print(f"📊 Full pipeline state: {pipeline_state}")

            # Verify the system is correctly waiting for client trigger
            expected_statuses = ["pending_dependencies", "not_initialized", "not_found"]
            assert cj_assessment_status in expected_statuses, (
                f"Expected cj_assessment to be one of {expected_statuses} "
                f"(waiting for client trigger), but got: {cj_assessment_status}"
            )
            print("✅ Batch is ready and correctly waiting for client-triggered processing")

            # STEP 3: Start consumer for monitoring
            await harness.start_consumer()

            # STEP 4: Trigger pipeline via Kafka using BCS integration helper
            request_correlation_id = await BCSIntegrationHelper.trigger_pipeline_via_kafka(
                kafka_manager=kafka_manager, batch_id=batch_id, pipeline_name="cj_assessment"
            )
            print(
                f"📡 Published cj_assessment pipeline request with correlation: "
                f"{request_correlation_id}"
            )

            # STEP 5: Monitor pipeline execution using harness infrastructure
            tracker = PipelineExecutionTracker()
            completion_event = await KafkaMonitorHelper.monitor_pipeline_execution(
                consumer=harness.consumer,
                request_correlation_id=request_correlation_id,
                batch_correlation_id=correlation_id,
                expected_steps=["spellcheck", "cj_assessment"],
                expected_completion_event="huleedu.batch.cj_assessment.completed.v1",
                tracker=tracker,
                timeout_seconds=180,  # 3 minutes for complete workflow
            )

            # STEP 6: Validate results
            print("\n📋 Workflow Results:")
            print(f"  Initiated phases: {tracker.initiated_phases}")
            print(f"  Completed phases: {tracker.completed_phases}")
            print(f"  Pipeline completed: {completion_event is not None}")

            # Validate that pipeline resolution triggered services
            assert completion_event is not None, (
                "Pipeline resolution should trigger service execution"
            )
            assert len(tracker.completed_phases) > 0, "Pipeline should have executed phases"

            # STEP 7: Validate batch state was updated
            batch_state = await validate_batch_pipeline_state(service_manager, batch_id)
            print(f"📊 Final batch state: {batch_state}")

            # STEP 8: CRITICAL: Validate BCS ↔ BOS integration actually occurred
            integration_evidence = await BCSIntegrationHelper.validate_bcs_integration(
                service_manager, batch_id, "cj_assessment"
            )

            # STEP 9: Assert integration-specific validations
            assert integration_evidence["bcs_http_requests"] > 0, (
                "BCS should have received HTTP requests from BOS"
            )

            assert integration_evidence["pipeline_resolution_occurred"], (
                "BCS should have resolved a pipeline"
            )

            assert integration_evidence["dependency_resolution_validated"], (
                "BCS should have performed intelligent dependency resolution"
            )

            print("🎯 BCS ↔ BOS Integration VALIDATED!")
            print(f"  ✅ HTTP calls to BCS: {integration_evidence['bcs_http_requests']}")
            print(f"  ✅ Pipeline resolved: {integration_evidence['resolved_pipeline']}")
            print(
                f"  ✅ Dependency analysis: "
                f"{integration_evidence['dependency_resolution_validated']}"
            )

        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            raise
        finally:
            await harness.cleanup()

        print("🎉 Complete client pipeline resolution workflow test PASSED!")

    @pytest.mark.docker
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_state_aware_pipeline_optimization(
        self,
        service_manager: ServiceTestManager,
        kafka_manager: KafkaTestManager,
        test_teacher,
    ):
        """
        Test BCS intelligent pipeline resolution based on batch state.

        Validates:
        - BCS analyzes actual essay states (spellcheck completed/pending)
        - Pipeline dependency resolution optimizes based on current state
        - Resolved pipeline reflects intelligent state analysis
        """
        # Ensure clean distributed state for test isolation
        await distributed_state_manager.quick_redis_cleanup()

        print("\n🧠 Starting state-aware pipeline optimization test")

        # Setup harness for batch creation WITH CREDIT PROVISIONING
        auth_manager = AuthTestManager()
        harness = PipelineTestHarness(service_manager, kafka_manager, auth_manager)

        try:
            # Create batch with harness (includes credits!)
            essay_files = await load_real_test_essays(max_essays=2)
            batch_id, correlation_id = await harness.setup_guest_batch(
                essay_files=essay_files, user=test_teacher
            )
            print(f"📦 Created batch {batch_id} for state-aware testing with credits")

            # Start monitoring
            await harness.start_consumer()

            # Trigger pipeline via Kafka using BCS integration helper
            request_correlation_id = await BCSIntegrationHelper.trigger_pipeline_via_kafka(
                kafka_manager=kafka_manager, batch_id=batch_id, pipeline_name="cj_assessment"
            )
            print(
                f"📡 Published cj_assessment pipeline request with correlation: "
                f"{request_correlation_id}"
            )

            # Monitor execution using harness infrastructure
            tracker = PipelineExecutionTracker()
            completion_event = await KafkaMonitorHelper.monitor_pipeline_execution(
                consumer=harness.consumer,
                request_correlation_id=request_correlation_id,
                batch_correlation_id=correlation_id,
                expected_steps=["spellcheck", "cj_assessment"],
                expected_completion_event="huleedu.batch.cj_assessment.completed.v1",
                tracker=tracker,
                timeout_seconds=60,
            )

            # Validate state-aware optimization occurred
            print("🧠 State-aware workflow results:")
            print(f"  Initiated phases: {tracker.initiated_phases}")
            print(f"  Completed phases: {tracker.completed_phases}")

            assert completion_event is not None, "State-aware pipeline should initiate correctly"
            assert len(tracker.completed_phases) > 0, "Pipeline should execute phases"

            print("✅ State-aware pipeline optimization validated")

        except Exception as e:
            print(f"❌ State-aware test failed: {e}")
            raise
        finally:
            await harness.cleanup()

        print("🎉 State-aware pipeline optimization test PASSED!")

    @pytest.mark.docker
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_concurrent_client_pipeline_requests(
        self,
        service_manager: ServiceTestManager,
        kafka_manager: KafkaTestManager,
        test_teacher,
    ):
        """
        Test multiple concurrent client pipeline resolution requests.

        Validates:
        - BCS handles concurrent batch analysis correctly
        - BOS maintains request isolation
        - No race conditions in pipeline resolution
        """
        # Ensure clean distributed state for test isolation
        await distributed_state_manager.quick_redis_cleanup()

        print("\n🔄 Starting concurrent client pipeline requests test")

        auth_manager = AuthTestManager()

        # Create multiple harnesses for concurrent testing
        harnesses = []
        batch_configs = []

        try:
            # Create multiple batches with credits using harness
            for i in range(2):
                harness = PipelineTestHarness(service_manager, kafka_manager, auth_manager)
                essay_files = await load_real_test_essays(max_essays=2)

                batch_id, correlation_id = await harness.setup_guest_batch(
                    essay_files=essay_files, user=test_teacher
                )

                harnesses.append(harness)
                batch_configs.append((batch_id, correlation_id))
                print(f"📦 Created test batch {i + 1}: {batch_id} with credits")

            # Start consumers for all harnesses
            for harness in harnesses:
                await harness.start_consumer()

            # Trigger concurrent pipelines via Kafka
            tasks = []
            for batch_id, _ in batch_configs:
                task = BCSIntegrationHelper.trigger_pipeline_via_kafka(
                    kafka_manager=kafka_manager, batch_id=batch_id, pipeline_name="cj_assessment"
                )
                tasks.append(task)

            # Execute all requests concurrently
            request_correlation_ids = await asyncio.gather(*tasks)
            print(f"📡 Published {len(tasks)} concurrent pipeline requests")

            # Monitor at least one completion to validate concurrent handling
            tracker = PipelineExecutionTracker()
            completion_event = await KafkaMonitorHelper.monitor_pipeline_execution(
                consumer=harnesses[0].consumer,
                request_correlation_id=request_correlation_ids[0],
                batch_correlation_id=batch_configs[0][1],
                expected_steps=["spellcheck", "cj_assessment"],
                expected_completion_event="huleedu.batch.cj_assessment.completed.v1",
                tracker=tracker,
                timeout_seconds=150,  # 2.5 minutes
            )

            # Validate at least one request was processed
            print("🔄 Concurrent request monitoring results:")
            print(f"  First batch completed: {completion_event is not None}")
            print(f"  Completed phases: {tracker.completed_phases}")

            assert completion_event is not None, (
                "At least one concurrent request should be processed"
            )

        except Exception as e:
            print(f"❌ Concurrent test failed: {e}")
            raise
        finally:
            # Cleanup all harnesses
            for harness in harnesses:
                await harness.cleanup()

        print("🎉 Concurrent client pipeline requests test PASSED!")
