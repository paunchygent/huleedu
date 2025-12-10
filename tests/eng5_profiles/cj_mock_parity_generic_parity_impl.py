"""Single-batch CJ generic mock parity test implementation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from statistics import mean
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

from scripts.llm_traces.eng5_cj_trace_capture import compute_llm_trace_summary
from services.cj_assessment_service.models_api import (
    CJLLMComparisonMetadata,
    ComparisonTask,
    EssayForComparison,
)
from tests.eng5_profiles._lps_helpers import get_lps_mock_mode
from tests.eng5_profiles.eng5_lps_metrics_assertions import (
    assert_lps_serial_bundle_metrics_for_mock_profile,
)
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager


class TestCJMockParityGenericParity:
    """Single-batch parity test for CJ generic mock profile."""

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
    async def test_cj_mock_parity_generic_mode_matches_recorded_summary(
        self,
        validated_services: dict,
        kafka_manager: KafkaTestManager,
    ) -> None:
        """
        Send a small batch of CJ-shaped requests through LPS using the mock
        provider and compare live callbacks against the recorded summary for
        ``cj_lps_roundtrip_mock_20251205``.

        Behavioural parity expectations:
        - All callbacks succeed (no errors).
        - Winner distribution heavily favours Essay A.
        - Token usage means remain close to the recorded fixture.
        - Latency stays within a reasonable band of the recorded trace.
        """
        base_url = validated_services["llm_provider_service"]["base_url"]
        mode_info = await get_lps_mock_mode(base_url)

        if not mode_info.get("use_mock_llm", False):
            pytest.skip(
                "LPS reports USE_MOCK_LLM = false; enable mock mode before running this test"
            )

        if mode_info.get("mock_mode") != "cj_generic_batch":
            pytest.skip(
                "LPS mock_mode is not 'cj_generic_batch'; restart "
                "llm_provider_service with this profile before running "
                "CJ generic parity tests."
            )

        scenario_id = "cj_lps_roundtrip_mock_20251205"

        summary_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "llm_traces"
            / scenario_id
            / "summary.json"
        )
        with summary_path.open("r", encoding="utf-8") as f:
            recorded_summary: dict[str, Any] = json.load(f)

        assert recorded_summary["total_events"] == recorded_summary["success_count"]
        assert recorded_summary["error_count"] == 0
        assert (
            recorded_summary["winner_counts"].get("Essay A", 0) == recorded_summary["total_events"]
        )

        callback_topic = "test.llm.mock_parity.generic.v1"
        await kafka_manager.ensure_topics([callback_topic])

        num_requests = recorded_summary["total_events"]
        bos_batch_id = "bos-cj-generic-mock-parity-001"

        task = ComparisonTask(
            essay_a=EssayForComparison(id="essay-a-generic", text_content="Essay A content"),
            essay_b=EssayForComparison(id="essay-b-generic", text_content="Essay B content"),
            prompt="Compare these two essays for quality",
        )

        metadata_adapter = CJLLMComparisonMetadata.from_comparison_task(
            task,
            bos_batch_id=bos_batch_id,
        ).with_additional_context(cj_llm_batching_mode="per_request")

        request_ids: list[str] = []

        base_url = validated_services["llm_provider_service"]["base_url"]
        lps_url = f"{base_url}/api/v1/comparison"

        async with aiohttp.ClientSession() as session:
            for _ in range(num_requests):
                correlation_id = uuid4()
                request_metadata = metadata_adapter.to_request_metadata()

                request = LLMComparisonRequest(
                    user_prompt=task.prompt,
                    callback_topic=callback_topic,
                    correlation_id=correlation_id,
                    metadata=request_metadata,
                    llm_config_overrides=ProviderOverrides(
                        provider_override=LLMProviderType.MOCK,
                        system_prompt_override="CJ generic mock parity test system prompt",
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
            "cj_mock_parity_generic",
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

                                try:
                                    result = LLMComparisonResultV1.model_validate(envelope.data)
                                except Exception as exc:  # pragma: no cover - defensive guard
                                    pytest.fail(f"Malformed LLMComparisonResultV1 payload: {exc}")

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
                    "Ensure dev stack is running and mock provider mode is configured."
                )

        assert len(callbacks) == num_requests, (
            f"Expected {num_requests} callbacks, collected {len(callbacks)}"
        )

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

        live_summary = compute_llm_trace_summary(callbacks, scenario_id="cj_generic_batch_test")

        live_winner_counts = live_summary["winner_counts"]
        live_total = live_summary["total_events"]
        live_essay_a = live_winner_counts.get("Essay A", 0)

        assert live_total == num_requests
        assert live_essay_a / live_total >= 0.9
        assert live_summary["error_count"] == 0

        def _mean_tokens(summary: Any, field: str) -> float:
            return float(summary["token_usage"][field]["mean"])

        for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            recorded_mean = _mean_tokens(recorded_summary, field)
            live_mean = _mean_tokens(live_summary, field)

            tolerance = max(5.0, recorded_mean * 0.5)
            assert abs(live_mean - recorded_mean) <= tolerance, (
                f"{field} mean outside tolerance: "
                f"live={live_mean}, recorded={recorded_mean}, tolerance={tolerance}"
            )

        recorded_rt = recorded_summary["response_time_ms"]
        live_rt = live_summary["response_time_ms"]

        assert live_rt["mean_ms"] >= 0.0
        assert live_rt["p95_ms"] >= 0.0
        assert live_rt["mean_ms"] <= recorded_rt["mean_ms"] + 100.0
        assert live_rt["p95_ms"] <= recorded_rt["p95_ms"] + 200.0

        live_response_times = [cb.response_time_ms for cb in callbacks]
        assert mean(live_response_times) >= 0.0

        await assert_lps_serial_bundle_metrics_for_mock_profile(validated_services)
