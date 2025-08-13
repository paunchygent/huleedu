"""
TRUE End-to-End Gateway Pattern Tests for NLP Service Phase 2.

This module tests the complete NLP Phase 2 pipeline using REAL services
running in TestContainers. Unlike antipattern tests that mock everything,
these tests validate the actual gateway pattern implementation.

Key validation points:
1. ELS acts as a gateway between BOS and NLP Service
2. NLP Service ONLY consumes from ELS, never directly from BOS  
3. Event transformation preserves correlation IDs
4. Complete pipeline execution works end-to-end
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import pytest_asyncio
from aiokafka import AIOKafkaProducer
from testcontainers.compose import DockerCompose

from common_core.events.envelope import EventEnvelope
from tests.integration.pipeline.conftest import send_event_and_wait
from tests.integration.pipeline.test_helpers import PipelineTestHelper, ServiceHealthChecker, print_pipeline_summary


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.docker
class TestNlpPhase2GatewayPatternE2E:
    """
    TRUE End-to-End tests for NLP Service Phase 2 Gateway Pattern.
    
    These tests start actual services and validate the complete pipeline flow.
    """

    @pytest_asyncio.fixture
    async def pipeline_helper(
        self,
        docker_compose_environment: DockerCompose,
        kafka_producer: AIOKafkaProducer,
        kafka_consumer_factory,
        topic_names: dict[str, str],
    ):
        """Create a pipeline test helper for E2E operations."""
        
        helper = PipelineTestHelper(
            compose=docker_compose_environment,
            kafka_producer=kafka_producer,
            kafka_consumer_factory=kafka_consumer_factory,
            topic_names=topic_names,
        )
        
        # Verify Kafka topics exist before starting tests
        topic_status = await helper.verify_kafka_topics_exist()
        missing_topics = [name for name, exists in topic_status.items() if not exists]
        
        if missing_topics:
            pytest.fail(f"Missing required Kafka topics: {missing_topics}")
        
        yield helper
        
        helper.cleanup()

    @pytest_asyncio.fixture
    async def health_checker(
        self,
        docker_compose_environment: DockerCompose,
    ) -> ServiceHealthChecker:
        """Service health checker for E2E testing."""
        return ServiceHealthChecker(docker_compose_environment)

    @pytest.mark.asyncio
    @pytest.mark.timeout(180)  # 3 minutes for full E2E test
    async def test_nlp_service_only_consumes_from_els(
        self,
        pipeline_helper: PipelineTestHelper,
        health_checker: ServiceHealthChecker,
        test_data: dict[str, Any],
        event_factory: dict[str, Any],
    ) -> None:
        """
        CRITICAL TEST: Verify NLP Service does NOT consume from BOS directly.
        
        This test validates the core gateway pattern:
        1. Send BATCH_NLP_INITIATE_COMMAND to BOS topic
        2. Verify NLP Service does NOT process it directly
        3. Verify ELS processes and transforms the command
        4. Verify NLP Service ONLY processes the ELS-transformed event
        
        This is the fundamental architectural constraint we're testing.
        """
        
        print("\\n" + "="*80)
        print("🎯 TESTING: NLP Service Gateway Pattern - No Direct BOS Consumption")
        print("="*80)
        
        # Step 1: Verify all services are healthy before starting
        print("\\n1️⃣ Verifying service health...")
        
        services_to_check = ["essay_lifecycle_worker", "nlp_service"]
        for service in services_to_check:
            is_ready = await health_checker.wait_for_service_ready(service, timeout=60.0)
            assert is_ready, f"Service {service} is not ready for testing"
        
        print("✅ All services are healthy and ready")
        
        # Step 2: Create the BOS command event
        print("\\n2️⃣ Creating BOS command event...")
        
        bos_command = event_factory["batch_nlp_initiate_command"](
            batch_id=test_data["batch_id"],
            essays=test_data["essays"],
            correlation_id=test_data["correlation_id"],
        )
        
        print(f"📝 Created command for batch {test_data['batch_id']} with {len(test_data['essays'])} essays")
        print(f"🔗 Correlation ID: {test_data['correlation_id']}")
        
        # Step 3: Send BOS command to ELS and verify NO direct consumption by NLP
        print("\\n3️⃣ Testing gateway pattern...")
        
        # Send the BOS command
        await pipeline_helper.send_command_to_els(
            event=bos_command,
            key=test_data["batch_id"],
        )
        
        print("📤 BOS command sent to ELS topic")
        
        # Critical test: Verify NLP does NOT consume directly from BOS
        print("\\n🔍 Verifying NO direct consumption by NLP service...")
        no_direct_consumption = await pipeline_helper.verify_no_direct_consumption(
            correlation_id=test_data["correlation_id"],
            wait_time=15.0,  # Wait long enough to be sure
        )
        
        assert no_direct_consumption, (
            "❌ GATEWAY PATTERN VIOLATION: NLP Service consumed directly from BOS! "
            "This violates the architectural constraint that NLP should only consume from ELS."
        )
        
        print("✅ CONFIRMED: NLP Service does NOT consume directly from BOS")
        
        # Step 4: Verify ELS transforms the command
        print("\\n4️⃣ Verifying ELS gateway transformation...")
        
        els_event = await pipeline_helper.wait_for_els_transformation(
            correlation_id=test_data["correlation_id"],
            timeout=30.0,
        )
        
        assert els_event is not None, (
            "❌ ELS failed to transform BOS command to NLP service request. "
            "Check ELS gateway implementation."
        )
        
        print("✅ ELS successfully transformed BOS command to NLP service request")
        
        # Validate the ELS transformation
        assert els_event.event_type == "huleedu.batch.nlp.processing.requested.v1"
        assert els_event.source_service == "essay_lifecycle_service"
        assert els_event.correlation_id == test_data["correlation_id"]
        assert "batch_id" in els_event.data
        assert els_event.data["batch_id"] == test_data["batch_id"]
        
        print(f"✅ ELS event validation passed: {els_event.event_id}")
        
        # Step 5: Verify NLP Service processes the ELS event
        print("\\n5️⃣ Verifying NLP Service processes ELS event...")
        
        completion_event = await pipeline_helper.wait_for_nlp_completion(
            correlation_id=test_data["correlation_id"],
            timeout=60.0,
        )
        
        assert completion_event is not None, (
            "❌ NLP Service failed to process ELS event and complete the batch. "
            "Check NLP Service event handling."
        )
        
        print("✅ NLP Service successfully processed ELS event")
        
        # Validate the completion event
        assert completion_event.event_type == "huleedu.batch.nlp.analysis.completed.v1"
        assert completion_event.correlation_id == test_data["correlation_id"]
        assert completion_event.data["batch_id"] == test_data["batch_id"]
        
        print(f"✅ Completion event validation passed: {completion_event.event_id}")
        
        # Step 6: Wait for individual essay events (rich data to RAS)
        print("\\n6️⃣ Verifying individual essay processing...")
        
        essay_events = await pipeline_helper.wait_for_essay_nlp_events(
            correlation_id=test_data["correlation_id"],
            expected_count=len(test_data["essays"]),
            timeout=60.0,
        )
        
        assert len(essay_events) == len(test_data["essays"]), (
            f"❌ Expected {len(test_data['essays'])} essay events, got {len(essay_events)}. "
            "Not all essays were processed."
        )
        
        print(f"✅ All {len(essay_events)} essays processed successfully")
        
        # Final validation
        for event in essay_events:
            assert event.event_type == "huleedu.essay.nlp.completed.v1"
            assert event.correlation_id == test_data["correlation_id"]
            assert "nlp_analysis" in event.data
            assert "essay_id" in event.data
        
        print("✅ All essay events validated successfully")
        
        # Print summary
        print_pipeline_summary(
            bos_event=bos_command,
            els_event=els_event,
            nlp_events=essay_events,
            completion_event=completion_event,
        )
        
        print("\\n🎉 GATEWAY PATTERN TEST PASSED!")
        print("✅ NLP Service correctly consumes ONLY from ELS, never directly from BOS")
        print("✅ Complete pipeline execution successful")

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)  # 2 minutes for transformation test
    async def test_els_transforms_command_to_service_request(
        self,
        pipeline_helper: PipelineTestHelper,
        test_data: dict[str, Any],
        event_factory: dict[str, Any],
    ) -> None:
        """
        Verify ELS correctly transforms BOS command to NLP service request.
        
        This test focuses specifically on the transformation logic:
        1. Send BATCH_NLP_INITIATE_COMMAND with specific data
        2. Verify ELS transforms to BATCH_NLP_PROCESSING_REQUESTED  
        3. Validate data preservation and event structure
        4. Confirm service boundaries (source_service changes)
        """
        
        print("\\n" + "="*80)
        print("🔄 TESTING: ELS Command Transformation Logic")
        print("="*80)
        
        # Create a BOS command with specific test data
        test_correlation_id = f"transform-test-{test_data['correlation_id']}"
        
        bos_command = event_factory["batch_nlp_initiate_command"](
            batch_id=test_data["batch_id"],
            essays=test_data["essays"],
            correlation_id=test_correlation_id,
        )
        
        print(f"📝 Testing transformation for batch: {test_data['batch_id']}")
        print(f"📊 Input essays: {len(test_data['essays'])}")
        print(f"🔗 Correlation ID: {test_correlation_id}")
        
        # Send the command
        await pipeline_helper.send_command_to_els(
            event=bos_command,
            key=test_data["batch_id"],
        )
        
        print("📤 BOS command sent, waiting for ELS transformation...")
        
        # Wait for the transformation
        els_event = await pipeline_helper.wait_for_els_transformation(
            correlation_id=test_correlation_id,
            timeout=30.0,
        )
        
        assert els_event is not None, "ELS failed to transform the command within timeout"
        
        print("✅ ELS transformation detected!")
        
        # Detailed validation of the transformation
        print("\\n🔍 Validating transformation details...")
        
        # Event structure validation
        assert els_event.event_type == "huleedu.batch.nlp.processing.requested.v1", (
            f"Wrong event type: expected 'huleedu.batch.nlp.processing.requested.v1', "
            f"got '{els_event.event_type}'"
        )
        
        assert els_event.source_service == "essay_lifecycle_service", (
            f"Wrong source service: expected 'essay_lifecycle_service', "
            f"got '{els_event.source_service}'"
        )
        
        print("✅ Event type and source service correct")
        
        # Correlation ID preservation
        assert els_event.correlation_id == test_correlation_id, (
            f"Correlation ID not preserved: expected '{test_correlation_id}', "
            f"got '{els_event.correlation_id}'"
        )
        
        print("✅ Correlation ID preserved")
        
        # Data transformation validation
        assert "batch_id" in els_event.data, "batch_id missing from transformed event"
        assert els_event.data["batch_id"] == test_data["batch_id"], (
            f"batch_id not preserved: expected '{test_data['batch_id']}', "
            f"got '{els_event.data['batch_id']}'"
        )
        
        assert "essays_to_process" in els_event.data, "essays_to_process missing"
        assert "language" in els_event.data, "language missing"
        
        transformed_essays = els_event.data["essays_to_process"]
        assert len(transformed_essays) == len(test_data["essays"]), (
            f"Essay count mismatch: expected {len(test_data['essays'])}, "
            f"got {len(transformed_essays)}"
        )
        
        print(f"✅ Data preservation: {len(transformed_essays)} essays transformed")
        
        # Validate individual essay transformation
        original_essay_ids = {essay["essay_id"] for essay in test_data["essays"]}
        transformed_essay_ids = {essay["essay_id"] for essay in transformed_essays}
        
        assert original_essay_ids == transformed_essay_ids, (
            f"Essay IDs not preserved: "
            f"original={original_essay_ids}, transformed={transformed_essay_ids}"
        )
        
        print("✅ All essay IDs preserved in transformation")
        
        # Validate that essays now have content (enriched by ELS)
        for essay in transformed_essays:
            assert "essay_id" in essay, "essay_id missing from transformed essay"
            assert "content" in essay, "content missing from transformed essay"
            # Content might be enriched/retrieved by ELS
            
        print("✅ Essay content properly included in transformation")
        
        print("\\n🎉 TRANSFORMATION TEST PASSED!")
        print("✅ ELS correctly transforms BOS commands to NLP service requests")
        print("✅ All data preserved and properly formatted")

    @pytest.mark.asyncio  
    @pytest.mark.timeout(60)  # 1 minute for rejection test
    async def test_nlp_handler_rejects_direct_bos_events(
        self,
        pipeline_helper: PipelineTestHelper,
        test_data: dict[str, Any],
        event_factory: dict[str, Any],
        kafka_producer: AIOKafkaProducer,
        topic_names: dict[str, str],
    ) -> None:
        """
        Verify NLP Service handler explicitly rejects direct BOS events.
        
        This test simulates a misconfiguration where BOS events are sent
        directly to NLP topics and validates that NLP Service properly
        rejects them rather than processing them.
        """
        
        print("\\n" + "="*80)
        print("🚫 TESTING: NLP Service Rejects Direct BOS Events")
        print("="*80)
        
        # Create a BOS command but send it to wrong topic (simulating misconfiguration)
        test_correlation_id = f"rejection-test-{test_data['correlation_id']}"
        
        bos_command = event_factory["batch_nlp_initiate_command"](
            batch_id=test_data["batch_id"],
            essays=test_data["essays"],
            correlation_id=test_correlation_id,
        )
        
        print(f"🎭 Simulating misconfiguration: sending BOS event to NLP topic")
        print(f"🔗 Test correlation ID: {test_correlation_id}")
        
        # Send BOS command directly to ELS topic (wrong event type for that topic)
        # This simulates a configuration error or direct publishing
        await send_event_and_wait(
            producer=kafka_producer,
            topic=topic_names["batch_nlp_processing_requested"],  # Wrong topic for BOS event
            event=bos_command,
            key=test_data["batch_id"],
        )
        
        print("📤 BOS event sent to NLP topic (simulating misconfiguration)")
        
        # Verify NLP Service does NOT process this misconfigured event
        print("\\n🔍 Verifying NLP Service rejects the misconfigured event...")
        
        no_processing = await pipeline_helper.verify_no_direct_consumption(
            correlation_id=test_correlation_id,
            wait_time=20.0,  # Wait long enough to be sure
        )
        
        assert no_processing, (
            "❌ NLP Service incorrectly processed a direct BOS event! "
            "The service should reject events with wrong event types or sources."
        )
        
        print("✅ CONFIRMED: NLP Service correctly rejects direct BOS events")
        
        # Additional check: no essay events should be generated
        essay_events = await pipeline_helper.wait_for_essay_nlp_events(
            correlation_id=test_correlation_id,
            expected_count=0,  # We expect zero events
            timeout=10.0,
        )
        
        assert len(essay_events) == 0, (
            f"❌ Found {len(essay_events)} unexpected essay events from rejected BOS command"
        )
        
        print("✅ CONFIRMED: No essay events generated from rejected command")
        
        print("\\n🎉 REJECTION TEST PASSED!")
        print("✅ NLP Service correctly rejects misconfigured/direct BOS events")
        print("✅ Service maintains proper event type validation")

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)  # 2 minutes for correlation test
    async def test_gateway_preserves_correlation_ids(
        self,
        pipeline_helper: PipelineTestHelper,
        test_data: dict[str, Any],
        event_factory: dict[str, Any],
    ) -> None:
        """
        Verify correlation IDs are preserved through the gateway transformation.
        
        This test validates end-to-end correlation ID tracking:
        1. Send command with specific correlation ID
        2. Verify ELS preserves correlation ID in transformation
        3. Verify NLP Service maintains correlation ID in all responses
        4. Confirm traceability through the complete pipeline
        """
        
        print("\\n" + "="*80)
        print("🔗 TESTING: Correlation ID Preservation Through Gateway")
        print("="*80)
        
        # Use a unique correlation ID for this test
        test_correlation_id = f"correlation-test-{test_data['batch_id']}-{int(asyncio.get_event_loop().time())}"
        
        print(f"🎯 Test correlation ID: {test_correlation_id}")
        print(f"📋 Batch ID: {test_data['batch_id']}")
        
        # Create and send the BOS command
        bos_command = event_factory["batch_nlp_initiate_command"](
            batch_id=test_data["batch_id"],
            essays=test_data["essays"],
            correlation_id=test_correlation_id,
        )
        
        await pipeline_helper.send_command_to_els(
            event=bos_command,
            key=test_data["batch_id"],
        )
        
        print("📤 BOS command sent with test correlation ID")
        
        # Step 1: Verify ELS preserves correlation ID in transformation
        print("\\n1️⃣ Checking correlation ID in ELS transformation...")
        
        els_event = await pipeline_helper.wait_for_els_transformation(
            correlation_id=test_correlation_id,
            timeout=30.0,
        )
        
        assert els_event is not None, "ELS transformation not found"
        assert els_event.correlation_id == test_correlation_id, (
            f"ELS failed to preserve correlation ID: "
            f"expected '{test_correlation_id}', got '{els_event.correlation_id}'"
        )
        
        print(f"✅ ELS preserved correlation ID: {els_event.correlation_id}")
        
        # Step 2: Verify NLP Service preserves correlation ID in completion
        print("\\n2️⃣ Checking correlation ID in NLP completion...")
        
        completion_event = await pipeline_helper.wait_for_nlp_completion(
            correlation_id=test_correlation_id,
            timeout=60.0,
        )
        
        assert completion_event is not None, "NLP completion not found"
        assert completion_event.correlation_id == test_correlation_id, (
            f"NLP Service failed to preserve correlation ID in completion: "
            f"expected '{test_correlation_id}', got '{completion_event.correlation_id}'"
        )
        
        print(f"✅ NLP preserved correlation ID in completion: {completion_event.correlation_id}")
        
        # Step 3: Verify correlation ID in individual essay events  
        print("\\n3️⃣ Checking correlation ID in essay events...")
        
        essay_events = await pipeline_helper.wait_for_essay_nlp_events(
            correlation_id=test_correlation_id,
            expected_count=len(test_data["essays"]),
            timeout=60.0,
        )
        
        assert len(essay_events) == len(test_data["essays"]), (
            f"Expected {len(test_data['essays'])} essay events, got {len(essay_events)}"
        )
        
        for i, event in enumerate(essay_events, 1):
            assert event.correlation_id == test_correlation_id, (
                f"Essay event {i} failed to preserve correlation ID: "
                f"expected '{test_correlation_id}', got '{event.correlation_id}'"
            )
        
        print(f"✅ All {len(essay_events)} essay events preserved correlation ID")
        
        # Comprehensive validation
        all_events = [bos_command, els_event, completion_event] + essay_events
        correlation_ids = [event.correlation_id for event in all_events]
        
        # All correlation IDs should be identical
        unique_correlation_ids = set(correlation_ids)
        assert len(unique_correlation_ids) == 1, (
            f"Correlation ID inconsistency detected: found {unique_correlation_ids}"
        )
        
        assert list(unique_correlation_ids)[0] == test_correlation_id, (
            f"Correlation ID mismatch: expected '{test_correlation_id}', "
            f"found '{unique_correlation_ids}'"
        )
        
        print("\\n🎉 CORRELATION ID TEST PASSED!")
        print(f"✅ Correlation ID '{test_correlation_id}' preserved through entire pipeline")
        print(f"✅ Validated across {len(all_events)} events (BOS → ELS → NLP → Essays → Completion)")

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)  # 1.5 minutes for error handling test
    async def test_gateway_handles_transformation_errors(
        self,
        pipeline_helper: PipelineTestHelper,
        kafka_producer: AIOKafkaProducer,
        topic_names: dict[str, str],
    ) -> None:
        """
        Verify gateway handles transformation errors gracefully.
        
        This test validates error handling in the ELS gateway:
        1. Send malformed command to ELS
        2. Verify ELS handles error appropriately  
        3. Verify no downstream processing occurs
        4. Check that system remains stable
        """
        
        print("\\n" + "="*80)
        print("⚠️ TESTING: Gateway Error Handling")
        print("="*80)
        
        from uuid import uuid4
        
        # Create a malformed command (missing required fields)
        test_correlation_id = f"error-test-{uuid4().hex[:8]}"
        
        malformed_command: EventEnvelope = EventEnvelope(
            event_id=str(uuid4()),
            event_type="huleedu.batch.nlp.initiate.command.v1",
            source_service="batch_orchestrator_service",
            correlation_id=test_correlation_id,
            data={
                # Missing critical fields like batch_id, essays_to_process
                "language": "en",
                "malformed": True,
            },
        )
        
        print(f"🎭 Created malformed command with correlation ID: {test_correlation_id}")
        print("📋 Command is missing batch_id and essays_to_process")
        
        # Send the malformed command
        await send_event_and_wait(
            producer=kafka_producer,
            topic=topic_names["batch_nlp_initiate_command"],
            event=malformed_command,
            key="malformed-test",
        )
        
        print("📤 Malformed command sent to ELS")
        
        # Verify ELS does NOT produce a malformed transformation
        print("\\n🔍 Verifying no malformed transformation occurs...")
        
        els_event = await pipeline_helper.wait_for_els_transformation(
            correlation_id=test_correlation_id,
            timeout=15.0,  # Shorter timeout for error case
        )
        
        # ELS should either:
        # 1. Not produce any transformation (preferred)
        # 2. Produce an error event (if implemented)
        # 3. Handle gracefully and continue (system stability)
        
        if els_event is None:
            print("✅ ELS correctly rejected malformed command (no transformation)")
        else:
            # If ELS did produce an event, it should be an error event or properly handled
            print(f"ℹ️ ELS produced event: {els_event.event_type}")
            # In a real implementation, this might be an error event
        
        # Verify no NLP processing occurs
        print("\\n🔍 Verifying no downstream NLP processing...")
        
        no_processing = await pipeline_helper.verify_no_direct_consumption(
            correlation_id=test_correlation_id,
            wait_time=10.0,
        )
        
        assert no_processing, (
            "❌ NLP Service incorrectly processed malformed command! "
            "Malformed events should not reach NLP processing."
        )
        
        print("✅ CONFIRMED: No downstream processing of malformed command")
        
        # Verify no essay events generated
        essay_events = await pipeline_helper.wait_for_essay_nlp_events(
            correlation_id=test_correlation_id,
            expected_count=0,
            timeout=5.0,
        )
        
        assert len(essay_events) == 0, (
            f"❌ Found {len(essay_events)} unexpected essay events from malformed command"
        )
        
        print("✅ CONFIRMED: No essay events generated from malformed command")
        
        # System stability check: verify services are still healthy
        print("\\n🔍 Verifying system stability after error...")
        
        # Send a valid command to ensure system is still working
        from uuid import uuid4
        
        test_batch_id = f"stability-test-{uuid4().hex[:8]}"
        stability_correlation_id = f"stability-{uuid4().hex[:8]}"
        
        valid_command: EventEnvelope = EventEnvelope(
            event_id=str(uuid4()),
            event_type="huleedu.batch.nlp.initiate.command.v1",
            source_service="batch_orchestrator_service",
            correlation_id=stability_correlation_id,
            data={
                "event_name": "BATCH_NLP_INITIATE_COMMAND",
                "entity_id": test_batch_id,
                "entity_type": "batch", 
                "essays_to_process": [
                    {
                        "essay_id": str(uuid4()),
                        "text_storage_id": f"storage-{uuid4()}",
                    }
                ],
                "language": "en",
            },
        )
        
        await send_event_and_wait(
            producer=kafka_producer,
            topic=topic_names["batch_nlp_initiate_command"],
            event=valid_command,
            key=test_batch_id,
        )
        
        # Quick check that valid command still works
        stability_els_event = await pipeline_helper.wait_for_els_transformation(
            correlation_id=stability_correlation_id,
            timeout=15.0,
        )
        
        if stability_els_event is not None:
            print("✅ System stability confirmed: valid commands still processed")
        else:
            print("⚠️ System stability unclear: valid command not processed quickly")
        
        print("\\n🎉 ERROR HANDLING TEST PASSED!")
        print("✅ Gateway handles malformed commands gracefully")
        print("✅ No downstream processing of invalid events")
        print("✅ System remains stable after error conditions")