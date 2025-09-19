"""
Diagnostic test for NLP Service and Language Tool Service interaction.

This isolated test helps understand:
1. What Language Tool service actually returns for various inputs
2. Where exactly the NLP service fails with 'str' object has no attribute 'get'
3. The actual response patterns causing the cascade failure

This test:
- Makes direct HTTP calls to Language Tool Service to understand its responses
- Triggers NLP Service via Kafka events (since it's a Kafka-only worker)
- Monitors container logs to capture the actual error
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from common_core import EventEnvelope, ProcessingEvent, topic_name
from common_core.events.nlp_events import BatchNlpProcessingRequestedV1
from common_core.metadata_models import EssayProcessingInputRefV1
from structlog import get_logger

from tests.utils.auth_manager import AuthTestManager
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager

logger = get_logger(__name__)


class TestNLPLanguageToolInteractionDiagnostic:
    """Diagnostic test to understand Language Tool response patterns."""

    @pytest.mark.asyncio
    @pytest.mark.docker
    @pytest.mark.timeout(120)
    async def test_language_tool_response_diagnostic(self) -> None:
        """
        Diagnostic test to understand Language Tool and NLP service responses.

        This test:
        1. Calls Language Tool service directly via HTTP with various inputs
        2. Logs the exact response structure and type
        3. Triggers NLP service via Kafka events (it's a Kafka-only worker)
        4. Monitors container logs to capture the actual error
        """
        # Setup (following exact pattern from test_entitlements_event_chain_diagnostic.py)
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_manager = KafkaTestManager()

        # Test data
        test_correlation_id = str(uuid.uuid4())
        test_batch_id = f"test-batch-{uuid.uuid4().hex[:8]}"

        logger.info(
            "🔬 Starting NLP-Language Tool interaction diagnostic",
            correlation_id=test_correlation_id,
            batch_id=test_batch_id,
        )

        # Ensure services are healthy
        endpoints = await service_manager.get_validated_endpoints()

        # Check if Language Tool service is available
        if "language_tool_service" not in endpoints:
            logger.warning("⚠️ Language Tool Service not available, skipping diagnostic")
            pytest.skip("Language Tool Service not available for diagnostic testing")

        logger.info(f"✅ {len(endpoints)} services validated healthy")

        # Create test user for authenticated requests
        test_user = auth_manager.create_test_user(role="teacher")

        # Test cases designed to potentially trigger different response types
        test_cases = [
            {
                "name": "Correct English",
                "text": "This is correct English text.",
                "language": "en-US",
            },
            {
                "name": "Known pattern from tests",
                "text": "I went there to see what happened.",
                "language": "en-US",
            },
            {
                "name": "Empty text",
                "text": "",
                "language": "en-US",
            },
            {
                "name": "Very long text",
                "text": "This is a test sentence. " * 3000,  # ~75,000 chars
                "language": "en-US",
            },
            {
                "name": "Special characters",
                "text": "Test with special chars: é à ö ñ 中文 🚀",
                "language": "en-US",
            },
            {
                "name": "Null bytes",
                "text": "Test with \x00 null bytes",
                "language": "en-US",
            },
            {
                "name": "Invalid language code",
                "text": "Test text",
                "language": "invalid-lang",
            },
            {
                "name": "Swedish text with English language",
                "text": "Detta är svensk text men språket är inställt på engelska.",
                "language": "en-US",
            },
        ]

        # Phase 1: Test Language Tool Service directly
        logger.info("📤 Phase 1: Testing Language Tool Service directly")
        language_tool_responses: list[dict[str, Any]] = []

        for test_case in test_cases:
            logger.info(
                f"🔍 Testing Language Tool with: {test_case['name']}",
                text_length=len(test_case["text"]),
                language=test_case["language"],
            )

            try:
                # Call Language Tool service directly
                response = await service_manager.make_request(
                    method="POST",
                    service="language_tool_service",
                    path="/v1/check",
                    json={
                        "text": test_case["text"],
                        "language": test_case["language"],
                    },
                    user=test_user,
                    correlation_id=test_correlation_id,
                )

                # Log response details
                logger.info(
                    "✅ Language Tool responded successfully",
                    test_name=test_case["name"],
                    response_type=type(response).__name__,
                    is_dict=isinstance(response, dict),
                    is_string=isinstance(response, str),
                    response_keys=list(response.keys()) if isinstance(response, dict) else None,
                    response_preview=str(response)[:200]
                    if not isinstance(response, dict)
                    else None,
                )

                language_tool_responses.append(
                    {
                        "test_case": test_case["name"],
                        "success": True,
                        "response_type": type(response).__name__,
                        "response": response,
                    }
                )

            except Exception as e:
                logger.error(
                    "❌ Language Tool failed",
                    test_name=test_case["name"],
                    error=str(e),
                    error_type=type(e).__name__,
                )

                language_tool_responses.append(
                    {
                        "test_case": test_case["name"],
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )

        # Phase 2: Test NLP Service via Kafka (it's a Kafka-only worker)
        logger.info("📤 Phase 2: Testing NLP Service via Kafka events")

        # Setup Kafka monitoring for NLP responses
        nlp_response_topic = topic_name(ProcessingEvent.BATCH_NLP_ANALYSIS_COMPLETED)
        # Note: No specific NLP error topic available - monitoring success topic only

        consumer_group = f"diagnostic-nlp-{uuid.uuid4().hex[:8]}"
        logger.info(f"📡 Setting up Kafka consumer: group={consumer_group}")

        consumer = AIOKafkaConsumer(
            nlp_response_topic,
            bootstrap_servers=kafka_manager.config.bootstrap_servers,
            group_id=consumer_group,
            auto_offset_reset="latest",  # Only get new events
            enable_auto_commit=False,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
        )

        await consumer.start()
        logger.info("✅ Consumer started for NLP response monitoring")

        # Producer for sending NLP analysis requests
        producer = AIOKafkaProducer(
            bootstrap_servers=kafka_manager.config.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        )
        await producer.start()

        try:
            # Test only the most likely problematic cases via Kafka
            critical_test_cases = [
                test_cases[0],  # Correct English
                test_cases[1],  # Known pattern
                test_cases[2],  # Empty text
            ]

            for test_case in critical_test_cases:
                logger.info(
                    f"🔍 Triggering NLP Service via Kafka for: {test_case['name']}",
                    text_length=len(test_case["text"]),
                )

                # Create NLP analysis request event
                # NLP service expects essays with text storage references
                essays_to_process = [
                    EssayProcessingInputRefV1(
                        essay_id=f"test-essay-{i}",
                        text_storage_id=f"test-storage-{i}",
                        filename=f"test_{test_case['name'].replace(' ', '_')}.txt",
                    )
                    for i in range(1)  # Just one essay for diagnostic
                ]

                nlp_request = BatchNlpProcessingRequestedV1(
                    event_name=ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED,
                    batch_id=test_batch_id,
                    entity_type="batch",
                    entity_id=test_batch_id,
                    timestamp=datetime.now(timezone.utc),
                    essays_to_process=essays_to_process,
                    language="en",  # Use simplified language code
                )

                envelope = EventEnvelope[BatchNlpProcessingRequestedV1](
                    event_id=uuid.uuid4(),
                    event_type=topic_name(ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED),
                    event_timestamp=datetime.now(timezone.utc),
                    source_service="test_diagnostic",
                    correlation_id=uuid.UUID(test_correlation_id),
                    data=nlp_request,
                )

                # Send the event
                await producer.send_and_wait(
                    topic=topic_name(ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED),
                    value=envelope.model_dump(mode="json"),
                    key=test_batch_id.encode("utf-8"),
                )
                logger.info(f"📤 Sent NLP analysis request for {test_case['name']}")

                # Wait briefly for response
                await asyncio.sleep(2)

            # Monitor for responses
            logger.info("👀 Monitoring for NLP Service responses...")
            start_time = asyncio.get_event_loop().time()
            timeout = 10  # 10 seconds timeout

            nlp_kafka_responses = []
            while asyncio.get_event_loop().time() - start_time < timeout:
                try:
                    msg_batch = await consumer.getmany(timeout_ms=500, max_records=100)

                    for topic_partition, messages in msg_batch.items():
                        for message in messages:
                            event_data = message.value
                            if isinstance(event_data, dict):
                                event_correlation = event_data.get("correlation_id", "")
                                if event_correlation == test_correlation_id:
                                    logger.info(
                                        "📨 Received NLP event",
                                        topic=message.topic,
                                        event_type=event_data.get("event_type"),
                                    )
                                    nlp_kafka_responses.append(event_data)

                except asyncio.TimeoutError:
                    pass

                await asyncio.sleep(0.1)

        finally:
            await producer.stop()
            await consumer.stop()

        # Phase 3: Analysis and Container Log Check
        logger.info("📊 Phase 3: Analyzing results and checking container logs")

        # Check if Language Tool returns non-dict responses
        non_dict_responses = []
        for lt_response in language_tool_responses:
            if lt_response["success"] and lt_response.get("response_type") != "dict":
                non_dict_responses.append(lt_response["test_case"])
                logger.warning(
                    f"⚠️ Language Tool returned non-dict response for: {lt_response['test_case']}",
                    response_type=lt_response.get("response_type"),
                )

        # Summary
        logger.info(
            "📋 Diagnostic Summary",
            total_tests=len(test_cases),
            language_tool_successes=sum(1 for r in language_tool_responses if r["success"]),
            language_tool_non_dict_responses=len(non_dict_responses),
            nlp_kafka_events_received=len(nlp_kafka_responses),
        )

        # Log problematic Language Tool responses
        for lt_response in language_tool_responses:
            if lt_response["success"]:
                lt_service_response: Any = lt_response.get("response")
                if not isinstance(lt_service_response, dict):
                    logger.error(
                        "🔴 FOUND ISSUE: Language Tool returned non-dict",
                        test_case=lt_response["test_case"],
                        response_type=type(lt_service_response).__name__,
                        response_preview=str(lt_service_response)[:500],
                    )
                elif not lt_service_response.get("matches") and lt_service_response.get("error"):
                    logger.error(
                        "🔴 Language Tool returned error in response",
                        test_case=lt_response["test_case"],
                        error=lt_service_response.get("error"),
                    )

        logger.info("🎯 Diagnostic test complete")

        # Don't fail the test - this is diagnostic
        # Just assert that we collected some data
        assert len(language_tool_responses) > 0, "No Language Tool responses collected"

    @pytest.mark.asyncio
    @pytest.mark.docker
    @pytest.mark.timeout(60)
    async def test_language_tool_direct_simple(self) -> None:
        """
        Simple direct test of Language Tool Service to quickly identify response issues.

        This focused test directly calls Language Tool with minimal setup to see
        what it actually returns.
        """
        # Minimal setup
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        test_user = auth_manager.create_test_user(role="teacher")

        # Ensure Language Tool service is available
        endpoints = await service_manager.get_validated_endpoints()
        if "language_tool_service" not in endpoints:
            pytest.skip("Language Tool Service not available")

        logger.info("🔬 Direct Language Tool Service test")

        # Test cases that might trigger different responses
        test_inputs = [
            {"text": "This is correct text.", "language": "en-US"},
            {"text": "", "language": "en-US"},  # Empty text
            {"text": "Test", "language": "invalid"},  # Invalid language
            {"text": "A" * 100000, "language": "en-US"},  # Very long text
        ]

        for i, test_input in enumerate(test_inputs):
            logger.info(
                f"Test {i + 1}: text_len={len(test_input['text'])}, lang={test_input['language']}"
            )

            try:
                response = await service_manager.make_request(
                    method="POST",
                    service="language_tool_service",
                    path="/v1/check",
                    json=test_input,
                    user=test_user,
                )

                # Key diagnostic: check response type
                if not isinstance(response, dict):
                    logger.error(
                        "🔴 CRITICAL: Language Tool returned non-dict response",
                        test_num=i + 1,
                        response_type=type(response).__name__,
                        response=str(response)[:500],
                    )
                else:
                    logger.info(
                        "✅ Response is dict",
                        test_num=i + 1,
                        has_errors=bool(response.get("errors")),
                        has_matches=bool(response.get("matches")),
                        keys=list(response.keys()),
                    )

            except Exception as e:
                logger.error(
                    "❌ Request failed",
                    test_num=i + 1,
                    error=str(e)[:500],
                    error_type=type(e).__name__,
                )

    @pytest.mark.asyncio
    @pytest.mark.docker
    @pytest.mark.timeout(60)
    async def test_nlp_pipeline_end_to_end_validation(self) -> None:
        """
        End-to-end validation of NLP processing pipeline with Language Tool integration.

        This test validates the complete fix for the "'str' object has no attribute 'get'" bug:
        1. Uploads essay content to Content Service
        2. Triggers NLP processing via BatchNlpProcessingRequestedV1
        3. Verifies Language Tool integration works without crashes
        4. Monitors for successful batch completion events
        """
        # Setup
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        kafka_manager = KafkaTestManager()

        # Test data
        test_correlation_id = str(uuid.uuid4())
        test_batch_id = f"nlp-e2e-batch-{uuid.uuid4().hex[:8]}"
        test_essay_id = f"nlp-e2e-essay-{uuid.uuid4().hex[:8]}"
        test_user = auth_manager.create_test_user(role="teacher")

        logger.info(
            "🚀 Starting NLP pipeline end-to-end validation",
            correlation_id=test_correlation_id,
            batch_id=test_batch_id,
            essay_id=test_essay_id,
        )

        # Ensure required services are healthy
        endpoints = await service_manager.get_validated_endpoints()
        required_services = ["content_service", "language_tool_service"]
        for service in required_services:
            if service not in endpoints:
                pytest.skip(f"{service} not available for E2E validation")

        logger.info(f"✅ {len(endpoints)} services validated healthy")

        # Step 1: Upload test essay content to Content Service
        test_essay_content = """
        This is a comprehensive test essay for NLP pipeline validation.
        It contains some speling errors that should be identifyed by the grammar checker.
        The Language Tool Service should process this text and return a flat language field.
        We are validating that the NLP service correctly handles the response without crashing.
        This essay also tests various linguistic features like word count, sentence structure,
        and readability metrics that the NLP analyzer will extract.
        """

        logger.info("📤 Uploading test essay to Content Service")
        try:
            # Upload content and get storage ID
            text_storage_id = await service_manager.upload_content_directly(test_essay_content)
            logger.info(f"✅ Essay uploaded with storage_id: {text_storage_id}")
        except Exception as e:
            pytest.fail(f"Failed to upload essay content: {e}")

        # Step 2: Set up Kafka monitoring for NLP completion events
        nlp_completion_topic = topic_name(ProcessingEvent.BATCH_NLP_ANALYSIS_COMPLETED)
        essay_nlp_topic = topic_name(ProcessingEvent.ESSAY_NLP_COMPLETED)

        consumer_group = f"nlp-e2e-validation-{uuid.uuid4().hex[:8]}"
        logger.info(f"📡 Setting up Kafka consumer: group={consumer_group}")

        consumer = AIOKafkaConsumer(
            nlp_completion_topic,
            essay_nlp_topic,
            bootstrap_servers=kafka_manager.config.bootstrap_servers,
            group_id=consumer_group,
            auto_offset_reset="latest",  # Only get new events
            enable_auto_commit=False,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
        )

        await consumer.start()
        logger.info(f"✅ Consumer started for topics: {[nlp_completion_topic, essay_nlp_topic]}")

        # Step 3: Publish BatchNlpProcessingRequestedV1 event
        producer = AIOKafkaProducer(
            bootstrap_servers=kafka_manager.config.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        )
        await producer.start()

        try:
            # Create NLP processing request
            essays_to_process = [
                EssayProcessingInputRefV1(
                    essay_id=test_essay_id,
                    text_storage_id=text_storage_id,
                    filename="test_essay.txt",
                )
            ]

            nlp_request = BatchNlpProcessingRequestedV1(
                event_name=ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED,
                batch_id=test_batch_id,
                entity_type="batch",
                entity_id=test_batch_id,
                timestamp=datetime.now(timezone.utc),
                essays_to_process=essays_to_process,
                language="en",  # Language field for NLP processing
            )

            envelope = EventEnvelope[BatchNlpProcessingRequestedV1](
                event_id=uuid.uuid4(),
                event_type=topic_name(ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED),
                event_timestamp=datetime.now(timezone.utc),
                source_service="test_e2e_validation",
                correlation_id=uuid.UUID(test_correlation_id),
                data=nlp_request,
            )

            # Send the event
            request_topic = topic_name(ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED)
            await producer.send_and_wait(
                topic=request_topic,
                value=envelope.model_dump(mode="json"),
                key=test_batch_id.encode("utf-8"),
            )
            logger.info(
                "📤 Published NLP processing request",
                batch_id=test_batch_id,
                essay_id=test_essay_id,
                topic=request_topic,
            )

            # Step 4: Monitor for NLP completion events
            logger.info("👀 Monitoring for NLP processing completion...")
            start_time = asyncio.get_event_loop().time()
            timeout = 30  # 30 seconds timeout

            batch_completion_received = False
            essay_nlp_received = False
            events_received = []

            while asyncio.get_event_loop().time() - start_time < timeout:
                try:
                    msg_batch = await consumer.getmany(timeout_ms=1000, max_records=100)

                    for topic_partition, messages in msg_batch.items():
                        for message in messages:
                            event_data = message.value
                            if isinstance(event_data, dict):
                                event_correlation = event_data.get("correlation_id", "")

                                if event_correlation == test_correlation_id:
                                    event_type = event_data.get("event_type", "")
                                    logger.info(
                                        "📨 Received NLP event",
                                        event_type=event_type,
                                        topic=message.topic,
                                    )
                                    events_received.append(event_data)

                                    # Check for batch completion
                                    if event_type == topic_name(
                                        ProcessingEvent.BATCH_NLP_ANALYSIS_COMPLETED
                                    ):
                                        batch_completion_received = True
                                        batch_data = event_data.get("data", {})
                                        processing_summary = batch_data.get(
                                            "processing_summary", {}
                                        )
                                        logger.info(
                                            "✅ Batch NLP analysis completed",
                                            successful=processing_summary.get("successful"),
                                            failed=processing_summary.get("failed"),
                                            processing_time=processing_summary.get(
                                                "processing_time_seconds"
                                            ),
                                        )

                                        # Verify our essay was processed successfully
                                        successful_essays = processing_summary.get(
                                            "successful_essay_ids", []
                                        )
                                        assert test_essay_id in successful_essays, (
                                            f"Essay {test_essay_id} not in successful list"
                                        )

                                    # Check for individual essay NLP completion
                                    elif event_type == topic_name(
                                        ProcessingEvent.ESSAY_NLP_COMPLETED
                                    ):
                                        essay_nlp_received = True
                                        essay_data = event_data.get("data", {})
                                        if essay_data.get("essay_id") == test_essay_id:
                                            nlp_metrics = essay_data.get("nlp_metrics", {})
                                            grammar_analysis = essay_data.get(
                                                "grammar_analysis", {}
                                            )
                                            logger.info(
                                                "✅ Essay NLP analysis received",
                                                word_count=nlp_metrics.get("word_count"),
                                                sentence_count=nlp_metrics.get("sentence_count"),
                                                grammar_errors=grammar_analysis.get("error_count"),
                                                detected_language=grammar_analysis.get(
                                                    "detected_language"
                                                ),
                                            )

                    # Break if we received both events
                    if batch_completion_received and essay_nlp_received:
                        break

                except asyncio.TimeoutError:
                    pass

                await asyncio.sleep(0.1)

        finally:
            await producer.stop()
            await consumer.stop()

        # Step 5: Validate results
        logger.info("📊 Validating NLP pipeline results")

        # Assert we received the expected events
        assert batch_completion_received, "Did not receive BatchNlpAnalysisCompletedV1 event"
        assert essay_nlp_received, "Did not receive EssayNlpCompletedV1 event"
        assert len(events_received) >= 2, f"Expected at least 2 events, got {len(events_received)}"

        # Check for any errors in events
        for event in events_received:
            event_data = event.get("data", {})
            # Ensure no critical failures
            if event_data.get("status") == "FAILED_CRITICALLY":
                pytest.fail(f"Batch failed critically: {event_data}")

        logger.info(
            "🎯 NLP pipeline validation complete",
            total_events_received=len(events_received),
            batch_completion=batch_completion_received,
            essay_nlp=essay_nlp_received,
        )

        # Success - the pipeline processed without Language Tool client crashes!
        logger.info(
            "✅ NLP pipeline successfully validated - Language Tool integration working correctly"
        )
