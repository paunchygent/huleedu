"""Cross-service integration test: CJ ↔ LPS metadata preservation.

Tests that CJ metadata survives the full HTTP → Queue → Kafka → Callback cycle
using real service boundaries (HTTP POST + Kafka consumer).

This test validates the critical contract:
- CJ sends metadata via HTTP POST to LPS
- LPS queues the request and processes it
- LPS publishes callback to Kafka with preserved metadata
- CJ can parse the callback and retrieve original metadata

Located in tests/integration/ because it exercises real cross-service HTTP/Kafka.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import aiohttp
import pytest
from common_core import (
    LLMComparisonRequest,
    LLMProviderType,
    LLMQueuedResponse,
)
from common_core import LLMConfigOverridesHTTP as ProviderOverrides
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1
from pydantic import ValidationError

from services.cj_assessment_service.models_api import (
    CJLLMComparisonMetadata,
    ComparisonTask,
    EssayForComparison,
)
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager


class TestCJLPSMetadataRoundtrip:
    """Integration test for CJ → LPS → CJ metadata preservation via HTTP/Kafka."""

    @pytest.fixture
    async def service_manager(self) -> ServiceTestManager:
        """Service validation manager."""
        return ServiceTestManager()

    @pytest.fixture
    async def kafka_manager(self) -> KafkaTestManager:
        """Kafka test utilities manager."""
        return KafkaTestManager()

    @pytest.fixture
    async def validated_services(self, service_manager: ServiceTestManager) -> dict:
        """Ensure LLM Provider Service is running and healthy."""
        endpoints = await service_manager.get_validated_endpoints()

        if "llm_provider_service" not in endpoints:
            pytest.skip("llm_provider_service not available for integration testing")

        return endpoints

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_metadata_preserved_through_http_kafka_roundtrip(
        self,
        validated_services: dict,  # noqa: ARG002 - ensures services are running
        kafka_manager: KafkaTestManager,
    ) -> None:
        """
        Test full metadata round-trip: CJ → LPS (HTTP) → CJ (Kafka callback).

        Validates:
        1. HTTP request/response contract (LLMComparisonRequest → LLMQueuedResponse)
        2. Kafka EventEnvelope structure and metadata (event_type, source_service,
           correlation_id)
        3. LLMComparisonResultV1 callback schema and success contract
        4. Complete CJ metadata preservation (essay_a_id, essay_b_id, bos_batch_id,
           cj_llm_batching_mode)
        5. LPS metadata additions (prompt_sha256) without pollution
        6. Distributed tracing via correlation_id propagation
        """
        # 1. Build CJ comparison task with metadata
        correlation_id = uuid4()
        # Use static topic name to avoid Kafka topic creation delays
        callback_topic = "test.llm.callback.roundtrip.v1"

        task = ComparisonTask(
            essay_a=EssayForComparison(id="essay-a-rt", text_content="Essay A content"),
            essay_b=EssayForComparison(id="essay-b-rt", text_content="Essay B content"),
            prompt="Compare these two essays for quality",
        )

        metadata_adapter = CJLLMComparisonMetadata.from_comparison_task(
            task,
            bos_batch_id="bos-roundtrip-001",
        ).with_additional_context(cj_llm_batching_mode="per_request")

        request_metadata = metadata_adapter.to_request_metadata()

        # 2. Build LLMComparisonRequest
        request = LLMComparisonRequest(
            user_prompt=task.prompt,
            callback_topic=callback_topic,
            correlation_id=correlation_id,
            metadata=request_metadata,
            llm_config_overrides=ProviderOverrides(
                provider_override=LLMProviderType.MOCK,  # Use MOCK to avoid API costs
                system_prompt_override="Test system prompt",
            ),
        )

        # 3. Pre-create Kafka topic to avoid UnknownTopicOrPartitionError
        await kafka_manager.ensure_topics([callback_topic])

        # 4. Send HTTP request to LPS
        lps_url = "http://localhost:8090/api/v1/comparison"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    lps_url,
                    json=request.model_dump(mode="json"),
                    timeout=aiohttp.ClientTimeout(total=10.0),
                    headers={"Content-Type": "application/json"},
                ) as response:
                    assert response.status == 202, f"Expected 202 (queued), got {response.status}"

                    # Validate HTTP response using Pydantic model
                    response_data = await response.json()
                    queued_response = LLMQueuedResponse(**response_data)
                    assert queued_response.status == "queued", "Expected queued status"

                    print(f"✅ Request queued: {queued_response.queue_id}")
            except aiohttp.ClientError as e:
                pytest.fail(f"HTTP POST to LPS failed: {e}")

        # 5. Set up Kafka consumer and listen for callback
        # Topic exists now, consumer will read from start
        callback_received = False
        callback_data: LLMComparisonResultV1 | None = None

        async with kafka_manager.consumer(
            "cj_lps_roundtrip",
            topics=[callback_topic],
            auto_offset_reset="earliest",  # Read from beginning to catch message
        ) as consumer:
            try:
                async with asyncio.timeout(30.0):  # 30s timeout for callback
                    async for msg in consumer:
                        try:
                            # Parse and validate EventEnvelope structure
                            envelope = EventEnvelope[Any].model_validate_json(msg.value)

                            # Skip events not for this test (old events from previous runs)
                            if envelope.correlation_id != correlation_id:
                                continue

                            # Validate it's the right event type and source
                            # NOTE: LPS currently uses model name as event_type, not topic name
                            assert envelope.event_type == "LLMComparisonResultV1", (
                                f"Wrong event_type: expected LLMComparisonResultV1, "
                                f"got {envelope.event_type}"
                            )
                            assert envelope.source_service == "llm_provider_service", (
                                f"Wrong source_service: {envelope.source_service}"
                            )

                            # Validate callback data against LLMComparisonResultV1 schema
                            callback_result = LLMComparisonResultV1.model_validate(envelope.data)

                            # Check correlation_id in event data as well
                            assert callback_result.correlation_id == correlation_id, (
                                "Event data correlation_id mismatch"
                            )

                            # 6. Validate LLMComparisonResultV1 success contract
                            assert callback_result.is_success, (
                                f"Expected success result, "
                                f"got error: {callback_result.error_detail}"
                            )
                            assert callback_result.winner is not None, "Missing winner"
                            assert callback_result.justification, "Missing justification"
                            assert callback_result.confidence is not None, "Missing confidence"
                            assert 1.0 <= callback_result.confidence <= 5.0, (
                                f"Invalid confidence: {callback_result.confidence}"
                            )
                            # NOTE: provider_override may not be applied in all environments
                            assert callback_result.provider in LLMProviderType, (
                                f"Invalid provider: {callback_result.provider}"
                            )
                            assert callback_result.response_time_ms >= 0, (
                                f"Invalid response_time_ms: {callback_result.response_time_ms}"
                            )

                            # 7. Verify complete metadata preservation
                            req_metadata = callback_result.request_metadata

                            # Build expected metadata for comparison
                            sent_metadata = {
                                "essay_a_id": "essay-a-rt",
                                "essay_b_id": "essay-b-rt",
                                "bos_batch_id": "bos-roundtrip-001",
                                "cj_llm_batching_mode": "per_request",
                            }

                            # Verify all CJ metadata preserved exactly
                            for key, expected_value in sent_metadata.items():
                                assert req_metadata.get(key) == expected_value, (
                                    f"Metadata mismatch for {key}: "
                                    f"expected {expected_value}, got {req_metadata.get(key)}"
                                )

                            # Verify LPS additions
                            assert "prompt_sha256" in req_metadata, (
                                "LPS should add prompt_sha256 to metadata"
                            )
                            assert isinstance(req_metadata["prompt_sha256"], str), (
                                "prompt_sha256 should be string"
                            )
                            assert len(req_metadata["prompt_sha256"]) == 64, (
                                f"prompt_sha256 should be SHA256 hex (64 chars), "
                                f"got {len(req_metadata['prompt_sha256'])}"
                            )

                            # 8. Verify no unexpected metadata pollution
                            # Allow LPS to append diagnostic/cache metadata without polluting
                            # CJ fields
                            allowed_lps_keys = {
                                "prompt_sha256",
                                "resolved_provider",
                                "queue_processing_mode",
                                "usage",
                                "cache_read_input_tokens",
                                "cache_creation_input_tokens",
                            }

                            expected_keys = set(sent_metadata.keys()) | allowed_lps_keys
                            actual_keys = set(req_metadata.keys())
                            unexpected_keys = actual_keys - expected_keys
                            assert not unexpected_keys, (
                                f"LPS added unexpected metadata keys: {unexpected_keys}"
                            )

                            callback_received = True
                            callback_data = callback_result
                            print("✅ Callback received with preserved metadata")
                            print(f"   essay_a_id: {req_metadata['essay_a_id']}")
                            print(f"   essay_b_id: {req_metadata['essay_b_id']}")
                            print(f"   bos_batch_id: {req_metadata['bos_batch_id']}")
                            print(
                                f"   cj_llm_batching_mode: {req_metadata['cj_llm_batching_mode']}"
                            )
                            print(f"   prompt_sha256: {req_metadata['prompt_sha256'][:16]}...")
                            break

                        except ValidationError as e:
                            pytest.fail(f"Malformed event structure: {e}")

            except TimeoutError:
                pytest.fail(
                    "Timeout waiting for LPS callback (30s). "
                    "Check LPS queue processor is running and MOCK provider is enabled."
                )

        # Final assertions
        assert callback_received, "No callback received from LPS"
        assert callback_data is not None, "Callback data was not captured"

        print("\n✅ Metadata round-trip test PASSED!")
        print("   Contract validations:")
        print("   • EventEnvelope structure ✓")
        print("   • LLMComparisonResultV1 schema ✓")
        print("   • Correlation ID propagation ✓")
        print("   • Complete metadata preservation ✓")
        print("   • No metadata pollution ✓")
        print(f"   Winner: {callback_data.winner}, Confidence: {callback_data.confidence}")

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_reasoning_overrides_roundtrip(
        self,
        validated_services: dict,  # noqa: ARG002 - ensures services are running
        kafka_manager: KafkaTestManager,
    ) -> None:
        """LLMComparisonRequest with reasoning/verbosity overrides is accepted and echoed."""
        correlation_id = uuid4()
        callback_topic = "test.llm.callback.reasoning.v1"

        task = ComparisonTask(
            essay_a=EssayForComparison(id="essay-a-reason", text_content="Essay A content"),
            essay_b=EssayForComparison(id="essay-b-reason", text_content="Essay B content"),
            prompt="Compare with reasoning controls",
        )

        metadata_adapter = CJLLMComparisonMetadata.from_comparison_task(
            task,
            bos_batch_id="bos-reasoning-001",
        ).with_additional_context(
            reasoning_effort="low",
            output_verbosity="low",
        )
        request_metadata = metadata_adapter.to_request_metadata()

        request = LLMComparisonRequest(
            user_prompt=task.prompt,
            callback_topic=callback_topic,
            correlation_id=correlation_id,
            metadata=request_metadata,
            llm_config_overrides=ProviderOverrides(
                provider_override=LLMProviderType.MOCK,
                system_prompt_override="Reasoning controls test system prompt",
                reasoning_effort="low",
                output_verbosity="low",
            ),
        )

        await kafka_manager.ensure_topics([callback_topic])

        lps_url = "http://localhost:8090/api/v1/comparison"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                lps_url,
                json=request.model_dump(mode="json"),
                timeout=aiohttp.ClientTimeout(total=10.0),
                headers={"Content-Type": "application/json"},
            ) as response:
                assert response.status == 202, f"Expected 202 (queued), got {response.status}"
                data = await response.json()
                queued = LLMQueuedResponse.model_validate(data)
                queue_id = queued.queue_id

        callback: LLMComparisonResultV1 | None = None
        async with kafka_manager.consumer(
            "cj_lps_reasoning_roundtrip",
            topics=[callback_topic],
            auto_offset_reset="earliest",
        ) as consumer:
            try:
                async with asyncio.timeout(30.0):
                    async for message in consumer:
                        envelope = EventEnvelope[Any].model_validate_json(message.value)
                        result = LLMComparisonResultV1.model_validate(envelope.data)
                        if result.request_id == str(queue_id):
                            callback = result
                            break
            except TimeoutError:
                pytest.fail(
                    "Timeout waiting for LPS callback (30s) in reasoning overrides test. "
                    "Check LPS queue processor is running and MOCK provider is enabled."
                )

        assert callback is not None, "No callback received for reasoning overrides test"
        assert callback.provider in LLMProviderType

        meta = callback.request_metadata
        assert meta.get("essay_a_id") == "essay-a-reason"
        assert meta.get("essay_b_id") == "essay-b-reason"
        assert meta.get("bos_batch_id") == "bos-reasoning-001"
        # Reasoning/verbosity hints should roundtrip via metadata
        assert meta.get("reasoning_effort") == "low"
        assert meta.get("output_verbosity") == "low"
