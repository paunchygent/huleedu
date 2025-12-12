"""Docker-backed batch_api metrics assertions for the CJ generic mock profile.

This suite is intentionally lighter than the serial_bundle parity tests:
it exercises the LPS `QueueProcessingMode.BATCH_API` path under the existing
`cj_generic_batch` mock profile and pins queue + job-level metrics.
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

from services.cj_assessment_service.models_api import (
    CJLLMComparisonMetadata,
    ComparisonTask,
    EssayForComparison,
)
from services.llm_provider_service.config import (
    QueueProcessingMode,
)
from services.llm_provider_service.config import (
    Settings as LLMProviderSettings,
)
from tests.eng5_profiles._lps_helpers import get_lps_mock_mode
from tests.eng5_profiles.eng5_lps_metrics_assertions import (
    assert_lps_batch_api_metrics_for_mock_profile,
)
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager


class TestCJMockBatchApiMetricsGeneric:
    """Integration test: LPS batch_api metrics under cj_generic_batch mock profile."""

    @pytest.fixture
    async def service_manager(self) -> ServiceTestManager:
        """Service validation manager."""
        return ServiceTestManager()

    @pytest.fixture
    async def kafka_manager(self) -> KafkaTestManager:
        """Kafka test utilities manager."""
        return KafkaTestManager()

    @pytest.fixture
    async def validated_services(self, service_manager: ServiceTestManager) -> dict[str, Any]:
        """Ensure LLM Provider Service is running and healthy."""
        endpoints = await service_manager.get_validated_endpoints()

        if "llm_provider_service" not in endpoints:
            pytest.skip("llm_provider_service not available for integration testing")

        return endpoints

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cj_generic_batch_api_metrics_and_callbacks(
        self,
        validated_services: dict[str, Any],
        kafka_manager: KafkaTestManager,
    ) -> None:
        if LLMProviderSettings().QUEUE_PROCESSING_MODE is not QueueProcessingMode.BATCH_API:
            pytest.skip(
                "This test requires LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=batch_api "
                "(configure .env and restart llm_provider_service)."
            )

        base_url = validated_services["llm_provider_service"]["base_url"]
        mode_info = await get_lps_mock_mode(base_url)

        if not mode_info.get("use_mock_llm", False):
            pytest.skip(
                "LPS reports USE_MOCK_LLM = false; enable mock mode before running this test"
            )

        if mode_info.get("mock_mode") != "cj_generic_batch":
            pytest.skip(
                "LPS mock_mode is not 'cj_generic_batch'; restart llm_provider_service with "
                "this profile before running batch_api metrics tests."
            )

        callback_topic = "test.llm.mock_parity.generic.batch_api.v1"
        await kafka_manager.ensure_topics([callback_topic])

        num_requests = 16
        bos_batch_id = f"bos-cj-generic-mock-batch-api-{uuid4().hex[:8]}"

        task = ComparisonTask(
            essay_a=EssayForComparison(id="essay-a-generic", text_content="Essay A content"),
            essay_b=EssayForComparison(id="essay-b-generic", text_content="Essay B content"),
            prompt="Compare these two essays for quality",
        )
        metadata_adapter = CJLLMComparisonMetadata.from_comparison_task(
            task,
            bos_batch_id=bos_batch_id,
        )

        lps_url = f"{base_url}/api/v1/comparison"
        request_ids: list[str] = []

        async with aiohttp.ClientSession() as session:
            for _ in range(num_requests):
                correlation_id = str(uuid4())
                request = LLMComparisonRequest(
                    user_prompt=task.prompt,
                    callback_topic=callback_topic,
                    correlation_id=correlation_id,
                    metadata=metadata_adapter.to_request_metadata(),
                    llm_config_overrides=ProviderOverrides(
                        provider_override=LLMProviderType.MOCK,
                        model_override="gpt-5.1",
                        system_prompt_override="CJ generic mock batch_api metrics test",
                    ),
                )

                async with session.post(
                    lps_url,
                    json=request.model_dump(mode="json"),
                    timeout=aiohttp.ClientTimeout(total=10.0),
                    headers={"Content-Type": "application/json"},
                ) as response:
                    assert response.status == 202, f"Expected 202 (queued), got {response.status}"
                    data = await response.json()
                    queued = LLMQueuedResponse.model_validate(data)
                    request_ids.append(str(queued.queue_id))

        callbacks: list[LLMComparisonResultV1] = []

        async with kafka_manager.consumer(
            "cj_mock_batch_api_generic",
            topics=[callback_topic],
            auto_offset_reset="earliest",
        ) as consumer:
            try:
                async with asyncio.timeout(30.0):
                    while len(callbacks) < num_requests:
                        msg_batch = await consumer.getmany(timeout_ms=1000, max_records=20)
                        if not msg_batch:
                            continue

                        for _tp, messages in msg_batch.items():
                            for message in messages:
                                envelope = EventEnvelope[Any].model_validate_json(message.value)
                                result = LLMComparisonResultV1.model_validate(envelope.data)

                                if result.request_id not in request_ids:
                                    continue

                                callbacks.append(result)
                                if len(callbacks) >= num_requests:
                                    break
                            if len(callbacks) >= num_requests:
                                break
            except TimeoutError:
                pytest.fail(
                    "Timeout waiting for LPS callbacks (30s). "
                    "Ensure dev stack is running and batch_api queue mode is configured."
                )

        assert len(callbacks) == num_requests

        for cb in callbacks:
            assert cb.is_success, f"Expected success result, got error: {cb.error_detail}"
            assert cb.winner is not None
            assert cb.justification
            assert cb.confidence is not None
            assert 1.0 <= cb.confidence <= 5.0

            meta = cb.request_metadata
            assert meta.get("essay_a_id") == "essay-a-generic"
            assert meta.get("essay_b_id") == "essay-b-generic"
            assert meta.get("bos_batch_id") == bos_batch_id

        await assert_lps_batch_api_metrics_for_mock_profile(validated_services)
