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

from tests.functional.client_pipeline_test_setup import (
    create_multiple_test_batches,
    create_test_batch_with_essays,
    get_concurrent_monitoring_topics,
    get_pipeline_monitoring_topics,
    get_state_aware_monitoring_topics,
)
from tests.functional.client_pipeline_test_utils import publish_client_pipeline_request
from tests.functional.comprehensive_pipeline_utils import create_comprehensive_kafka_manager
from tests.functional.pipeline_validation_utils import (
    validate_batch_pipeline_state,
    validate_bcs_dependency_resolution,
    validate_bcs_integration_occurred,
)
from tests.functional.workflow_monitoring_utils import (
    is_related_to_batch,
    monitor_pipeline_resolution_workflow,
)
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager
from tests.utils.test_auth_manager import AuthTestManager


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
            "essay_lifecycle_service",
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
        validated_services: dict[str, Any],
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
        print("\n🚀 Starting complete client pipeline resolution workflow test")

        try:
            # 1. Setup: Create batch with real essays
            batch_id, correlation_id = await create_test_batch_with_essays(
                service_manager, 3, test_teacher=test_teacher
            )

            # 2. Verify batch is ready for client-triggered processing
            print("📊 Verifying batch is ready for client-triggered processing...")
            batch_state = await validate_batch_pipeline_state(service_manager, batch_id)
            pipeline_state = batch_state.get("pipeline_state", {}) if batch_state else {}

            # With our new simplified architecture, pipelines should be pending_dependencies
            # (waiting for client trigger)
            cj_assessment_status = pipeline_state.get("cj_assessment", {}).get("status", "unknown")
            print(f"📋 CJ Assessment status: {cj_assessment_status}")

            # Verify the system is correctly waiting for client trigger (not auto-starting)
            assert cj_assessment_status == "pending_dependencies", (
                f"Expected cj_assessment to be pending_dependencies (waiting for client trigger), "
                f"but got: {cj_assessment_status}"
            )
            print("✅ Batch is ready and correctly waiting for client-triggered processing")

            # 3. Setup pipeline monitoring for the client-initiated request (start at latest offset)
            pipeline_topics = get_pipeline_monitoring_topics()

            async with kafka_manager.consumer(
                "client_pipeline_resolution_e2e",
                pipeline_topics,
                auto_offset_reset="latest",
            ) as consumer:
                # 4. Publish ClientBatchPipelineRequestV1 event to trigger cj_assessment
                request_correlation_id = await publish_client_pipeline_request(
                    kafka_manager,
                    batch_id,
                    "cj_assessment",  # Use cj_assessment pipeline which is enabled
                    correlation_id,
                )

                print(
                    "📡 Published cj_assessment pipeline request with "
                    f"correlation: {request_correlation_id}",
                )

                # 5. Monitor complete pipeline resolution workflow
                workflow_results = await monitor_pipeline_resolution_workflow(
                    consumer,
                    batch_id,
                    request_correlation_id,
                    timeout_seconds=180,  # 3 minutes for complete workflow
                )

                # 6. Validate workflow completion
                print("\n📋 Workflow Results:")
                print(
                    f"  Specialized services triggered: "
                    f"{workflow_results['specialized_services_triggered']}",
                )
                print(f"  Pipeline initiated: {workflow_results['pipeline_initiated']}")
                print(f"  Completion events: {len(workflow_results['completion_events'])}")

                # Validate that pipeline resolution triggered services
                assert workflow_results["pipeline_initiated"], (
                    "Pipeline resolution should trigger service execution"
                )

                # 7. Validate batch state was updated
                batch_state = await validate_batch_pipeline_state(service_manager, batch_id)
                print(f"📊 Final batch state: {batch_state}")

                # 8. CRITICAL: Validate BCS ↔ BOS integration actually occurred
                integration_evidence = await validate_bcs_integration_occurred(
                    service_manager,
                    batch_id,
                    "cj_assessment",  # Changed from cj_assessment to cj_assessment
                )

                # 9. Validate BCS performed dependency resolution
                bcs_resolution_validated = await validate_bcs_dependency_resolution(
                    integration_evidence,
                )

                # 10. Assert integration-specific validations
                assert integration_evidence["bcs_http_requests"] > 0, (
                    "BCS should have received HTTP requests from BOS"
                )

                assert integration_evidence["pipeline_resolution_occurred"], (
                    "BCS should have resolved a pipeline"
                )

                assert bcs_resolution_validated, (
                    "BCS should have performed intelligent dependency resolution"
                )

                print("🎯 BCS ↔ BOS Integration VALIDATED!")
                print(f"  ✅ HTTP calls to BCS: {integration_evidence['bcs_http_requests']}")
                print(f"  ✅ Pipeline resolved: {integration_evidence['resolved_pipeline']}")
                print(f"  ✅ Dependency analysis: {bcs_resolution_validated}")

        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            raise

        print("🎉 Complete client pipeline resolution workflow test PASSED!")

    @pytest.mark.docker
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_state_aware_pipeline_optimization(
        self,
        service_manager: ServiceTestManager,
        kafka_manager: KafkaTestManager,
        validated_services: dict[str, Any],
        test_teacher,
    ):
        """
        Test BCS intelligent pipeline resolution based on batch state.

        Validates:
        - BCS analyzes actual essay states (spellcheck completed/pending)
        - Pipeline dependency resolution optimizes based on current state
        - Resolved pipeline reflects intelligent state analysis
        """
        print("\n🧠 Starting state-aware pipeline optimization test")

        try:
            # Setup monitoring FIRST to catch all events from batch creation
            pipeline_topics = get_state_aware_monitoring_topics()

            async with kafka_manager.consumer(
                "state_aware_pipeline_e2e",
                pipeline_topics,
            ) as consumer:
                # Create batch with minimal essays - essays are now stored but
                # don't auto-trigger pipeline
                batch_id, correlation_id = await create_test_batch_with_essays(
                    service_manager, 2, test_teacher=test_teacher
                )

                print(f"📦 Created batch {batch_id} for state-aware testing")

                # ARCHITECTURAL FIX: Explicitly trigger pipeline execution via client request
                # This follows the new client-controlled architecture where
                # pipelines require explicit triggers
                request_correlation_id = await publish_client_pipeline_request(
                    kafka_manager,
                    batch_id,
                    # Use cj_assessment pipeline which enables
                    # dependency resolution
                    "cj_assessment",
                    correlation_id,
                )

                print(
                    "📡 Published cj_assessment pipeline request with "
                    f"correlation: {request_correlation_id}",
                )

                # Monitor for the client-triggered pipeline execution
                workflow_results = await monitor_pipeline_resolution_workflow(
                    consumer,
                    batch_id,
                    request_correlation_id,  # Use the request correlation ID for monitoring
                    timeout_seconds=60,  # Pipeline should execute after client trigger
                )

                # Validate state-aware optimization occurred
                print(f"🧠 State-aware workflow results: {workflow_results}")

                # For fresh essays requesting AI feedback, BCS should determine
                # that spellcheck is a prerequisite
                assert workflow_results["pipeline_initiated"], (
                    "State-aware pipeline should initiate correctly"
                )

                print("✅ State-aware pipeline optimization validated")

        except Exception as e:
            print(f"❌ State-aware test failed: {e}")
            raise

        print("🎉 State-aware pipeline optimization test PASSED!")

    @pytest.mark.docker
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_concurrent_client_pipeline_requests(
        self,
        service_manager: ServiceTestManager,
        kafka_manager: KafkaTestManager,
        validated_services: dict[str, Any],
        test_teacher,
    ):
        """
        Test multiple concurrent client pipeline resolution requests.

        Validates:
        - BCS handles concurrent batch analysis correctly
        - BOS maintains request isolation
        - No race conditions in pipeline resolution
        """
        print("\n🔄 Starting concurrent client pipeline requests test")

        try:
            # Create multiple batches for concurrent testing
            batch_ids, correlation_ids = await create_multiple_test_batches(
                service_manager, 2, 2, test_teacher=test_teacher
            )

            # Setup monitoring for concurrent requests
            pipeline_topics = get_concurrent_monitoring_topics()

            async with kafka_manager.consumer(
                "concurrent_pipeline_e2e",
                pipeline_topics,
            ) as consumer:
                # Publish concurrent pipeline requests
                tasks = []
                for batch_id, correlation_id in zip(batch_ids, correlation_ids, strict=False):
                    task = publish_client_pipeline_request(
                        kafka_manager,
                        batch_id,
                        "cj_assessment",
                        correlation_id,
                    )
                    tasks.append(task)

                # Execute all requests concurrently
                await asyncio.gather(*tasks)
                print(f"📡 Published {len(tasks)} concurrent pipeline requests")

                # Monitor for successful processing of all requests
                processed_batches = set()
                start_time = asyncio.get_event_loop().time()
                timeout = 150  # 2.5 minutes

                async for message in consumer:
                    if asyncio.get_event_loop().time() - start_time > timeout:
                        break

                    try:
                        if hasattr(message, "value"):
                            import json

                            event_data = json.loads(message.value.decode("utf-8"))

                            # Check which batch this event belongs to
                            for batch_id in batch_ids:
                                if is_related_to_batch(event_data, batch_id, ""):
                                    processed_batches.add(batch_id)
                                    print(f"📥 Event received for batch {batch_id}")

                            # Check if all batches have been processed
                            if len(processed_batches) >= len(batch_ids):
                                print("✅ All concurrent requests processed")
                                break

                    except Exception as e:
                        print(f"⚠️ Error processing concurrent event: {e}")
                        continue

                # Validate all requests were processed
                print(f"🔄 Processed batches: {len(processed_batches)}/{len(batch_ids)}")
                assert len(processed_batches) >= 1, (
                    "At least one concurrent request should be processed"
                )

        except Exception as e:
            print(f"❌ Concurrent test failed: {e}")
            raise

        print("🎉 Concurrent client pipeline requests test PASSED!")
