"""Small-net diagnostics implementation for ENG5 LOWER5 mock mode."""

from __future__ import annotations

import asyncio
import json
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping
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


class TestEng5MockParityLower5Diagnostics:
    """Small-net diagnostics test suite for ENG5 LOWER5 mock profile."""

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
    async def test_eng5_mock_lower5_small_net_diagnostics_across_batches(
        self,
        validated_services: dict,
        kafka_manager: KafkaTestManager,
    ) -> None:
        """
        Drive multiple LOWER5-shaped small-net batches through LPS using the
        ENG5 LOWER5 mock profile and assert small-net diagnostics:

        - Each unique LOWER5 anchor pair appears exactly once per batch.
        - Across all batches, each pair appears exactly ``num_batches`` times.
        - Winners for a given pair are stable across batches.
        - Per-batch and aggregate winner proportions and token/latency metrics
          remain within the same bands as the recorded LOWER5 trace.
        """
        base_url = validated_services["llm_provider_service"]["base_url"]
        mode_info = await get_lps_mock_mode(base_url)

        if not mode_info.get("use_mock_llm", False):
            pytest.skip(
                "LPS reports USE_MOCK_LLM = false; enable mock mode before running this test"
            )

        if mode_info.get("mock_mode") != "eng5_lower5_gpt51_low":
            pytest.skip(
                "LPS mock_mode is not 'eng5_lower5_gpt51_low'; restart "
                "llm_provider_service with this profile before running "
                "ENG5 LOWER5 diagnostics tests."
            )

        scenario_id = "eng5_lower5_gpt51_low_20251202"

        summary_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "llm_traces"
            / scenario_id
            / "summary.json"
        )
        with summary_path.open("r", encoding="utf-8") as f:
            recorded_summary: dict[str, Any] = json.load(f)

        callback_topic = "test.llm.mock_parity.eng5_lower5.small_net_diagnostics.v1"
        await kafka_manager.ensure_topics([callback_topic])

        # LOWER5-shaped small-net: all unique pairs between five anchors.
        anchor_ids = [f"eng5-lower5-anchor-{i:02d}" for i in range(1, 6)]
        anchor_pairs = list(combinations(anchor_ids, 2))
        requests_per_batch = len(anchor_pairs)
        assert requests_per_batch == 10

        num_batches = 3
        total_requests = num_batches * requests_per_batch

        lps_url = f"{base_url}/api/v1/comparison"

        request_ids_by_batch: dict[str, list[str]] = {}
        callbacks_by_batch: dict[str, list[LLMComparisonResultV1]] = {}

        async with aiohttp.ClientSession() as session:
            for batch_index in range(num_batches):
                bos_batch_id = f"bos-eng5-lower5-small-net-{batch_index + 1:03d}"
                batch_request_ids: list[str] = []

                for anchor_a, anchor_b in anchor_pairs:
                    correlation_id = uuid4()

                    task = ComparisonTask(
                        essay_a=EssayForComparison(
                            id=anchor_a,
                            text_content=f"ENG5 LOWER5 anchor essay content for {anchor_a}",
                        ),
                        essay_b=EssayForComparison(
                            id=anchor_b,
                            text_content=f"ENG5 LOWER5 anchor essay content for {anchor_b}",
                        ),
                        prompt="ENG5 LOWER5 anchor alignment comparison prompt",
                    )

                    metadata_adapter = CJLLMComparisonMetadata.from_comparison_task(
                        task,
                        bos_batch_id=bos_batch_id,
                    ).with_additional_context(cj_llm_batching_mode="serial_bundle")

                    request_metadata = metadata_adapter.to_request_metadata()

                    user_prompt = (
                        "ENG5 LOWER5 anchor alignment comparison between "
                        f"{anchor_a} and {anchor_b}. "
                        "Judge which essay better matches the ENG5 LOWER5 rubric."
                    )

                    request = LLMComparisonRequest(
                        user_prompt=user_prompt,
                        callback_topic=callback_topic,
                        correlation_id=correlation_id,
                        metadata=request_metadata,
                        llm_config_overrides=ProviderOverrides(
                            provider_override=LLMProviderType.MOCK,
                        ),
                    )

                    async with session.post(
                        lps_url,
                        json=request.model_dump(mode="json"),
                        timeout=aiohttp.ClientTimeout(total=15.0),
                        headers={"Content-Type": "application/json"},
                    ) as response:
                        assert response.status == 202, (
                            f"Expected 202 (queued), got {response.status}"
                        )

                        data = await response.json()
                        queued = LLMQueuedResponse.model_validate(data)
                        batch_request_ids.append(str(queued.queue_id))

                request_ids_by_batch[bos_batch_id] = batch_request_ids

        callbacks: list[LLMComparisonResultV1] = []

        async with kafka_manager.consumer(
            "eng5_mock_parity_lower5_small_net_diagnostics",
            topics=[callback_topic],
            auto_offset_reset="earliest",
        ) as consumer:
            try:
                async with asyncio.timeout(90.0):
                    while len(callbacks) < total_requests:
                        msg_batch = await consumer.getmany(timeout_ms=1000, max_records=50)
                        if not msg_batch:
                            continue

                        for _tp, messages in msg_batch.items():
                            for message in messages:
                                envelope = EventEnvelope[Any].model_validate_json(message.value)

                                try:
                                    result = LLMComparisonResultV1.model_validate(envelope.data)
                                except Exception as exc:  # pragma: no cover - defensive guard
                                    pytest.fail(f"Malformed LLMComparisonResultV1 payload: {exc}")

                                for bos_batch_id, expected_ids in request_ids_by_batch.items():
                                    if result.request_id in expected_ids:
                                        callbacks.append(result)
                                        callbacks_by_batch.setdefault(
                                            bos_batch_id,
                                            [],
                                        ).append(result)
                                        break
                                if len(callbacks) >= total_requests:
                                    break
                            if len(callbacks) >= total_requests:
                                break
            except TimeoutError:
                pytest.fail(
                    "Timeout waiting for LPS callbacks (90s) in LOWER5 small-net diagnostics test. "
                    "Ensure dev stack is running and LPS mock mode is configured "
                    "for eng5_lower5_gpt51_low."
                )

        assert len(callbacks) == total_requests, (
            f"Expected {total_requests} callbacks across batches, collected {len(callbacks)}"
        )

        assert set(callbacks_by_batch.keys()) == set(request_ids_by_batch.keys())

        # Per-callback contract checks and basic metadata validation.
        for bos_batch_id, expected_ids in request_ids_by_batch.items():
            batch_callbacks = callbacks_by_batch.get(bos_batch_id, [])
            assert len(batch_callbacks) == len(expected_ids), (
                f"Batch {bos_batch_id} expected {len(expected_ids)} callbacks, "
                f"collected {len(batch_callbacks)}"
            )

            seen_pairs_in_batch: set[tuple[str, str]] = set()

            for cb in batch_callbacks:
                assert cb.is_success, (
                    f"Expected success result in diagnostics test, got error: {cb.error_detail}"
                )
                assert cb.winner is not None
                assert cb.justification
                assert cb.confidence is not None
                assert 1.0 <= cb.confidence <= 5.0

                meta = cb.request_metadata
                assert meta.get("bos_batch_id") == bos_batch_id
                essay_a_id = str(meta.get("essay_a_id"))
                essay_b_id = str(meta.get("essay_b_id"))
                assert essay_a_id
                assert essay_b_id

                if essay_a_id <= essay_b_id:
                    pair_key: tuple[str, str] = (essay_a_id, essay_b_id)
                else:
                    pair_key = (essay_b_id, essay_a_id)
                seen_pairs_in_batch.add(pair_key)

            expected_pairs = {(min(a, b), max(a, b)) for a, b in anchor_pairs}
            assert seen_pairs_in_batch == expected_pairs

        # Cross-batch pair coverage and winner stability diagnostics.
        pair_counts: dict[tuple[str, str], int] = {}
        pair_winners: dict[tuple[str, str], str] = {}

        for cb in callbacks:
            meta = cb.request_metadata
            essay_a_id = str(meta.get("essay_a_id"))
            essay_b_id = str(meta.get("essay_b_id"))
            if essay_a_id <= essay_b_id:
                pair_key = (essay_a_id, essay_b_id)
            else:
                pair_key = (essay_b_id, essay_a_id)

            pair_counts[pair_key] = pair_counts.get(pair_key, 0) + 1

            winner_label = cb.winner.value if cb.winner is not None else ""
            if pair_key in pair_winners:
                assert pair_winners[pair_key] == winner_label, (
                    f"Winner changed across batches for pair {pair_key}"
                )
            else:
                pair_winners[pair_key] = winner_label

        expected_pairs_global = {(min(a, b), max(a, b)) for a, b in anchor_pairs}
        assert set(pair_counts.keys()) == expected_pairs_global

        for pair_key, count in pair_counts.items():
            assert count == num_batches, (
                f"Pair {pair_key} expected {num_batches} callbacks across batches, observed {count}"
            )

        # Winner proportion and token/latency parity vs recorded LOWER5 trace.
        def _winner_proportions(summary: Mapping[str, Any]) -> dict[str, float]:
            total = summary["total_events"]
            if total == 0:
                return {"Essay A": 0.0, "Essay B": 0.0}
            counts = summary["winner_counts"]
            return {
                "Essay A": counts.get("Essay A", 0) / total,
                "Essay B": counts.get("Essay B", 0) / total,
            }

        def _mean_tokens(summary: Mapping[str, Any], field: str) -> float:
            return float(summary["token_usage"][field]["mean"])

        def _assert_summary_within_parity(summary: Mapping[str, Any]) -> None:
            live_props = _winner_proportions(summary)
            recorded_props = _winner_proportions(recorded_summary)

            # Winner shape guardrail: LOWER5 trace has Essay B as majority
            # winner; preserve that qualitative shape while allowing some
            # stochastic drift in proportions.
            assert recorded_props["Essay B"] >= recorded_props["Essay A"]
            assert live_props["Essay B"] >= live_props["Essay A"], (
                "Expected Essay B to remain the majority winner in LOWER5 "
                f"small-net diagnostics; live proportions={live_props}"
            )

            max_drift = 0.20
            for label in ("Essay A", "Essay B"):
                diff = abs(live_props[label] - recorded_props[label])
                # Allow up to ±20 percentage points drift per label to keep
                # this as a canary rather than a brittle parity pin on a
                # 10-comparison small net.
                assert diff <= max_drift, (
                    f"Winner proportion for {label} outside LOWER5 small-net "
                    f"tolerance: live={live_props[label]:.3f}, "
                    f"recorded={recorded_props[label]:.3f}, "
                    f"tolerance={max_drift:.2f}"
                )

            assert summary["error_count"] == 0

            for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
                recorded_mean = _mean_tokens(recorded_summary, field)
                live_mean = _mean_tokens(summary, field)

                tolerance = max(5.0, recorded_mean * 0.5)
                assert abs(live_mean - recorded_mean) <= tolerance, (
                    f"{field} mean outside tolerance for LOWER5 small-net batch: "
                    f"live={live_mean}, recorded={recorded_mean}, tolerance={tolerance}"
                )

            recorded_rt = recorded_summary["response_time_ms"]
            live_rt = summary["response_time_ms"]

            assert live_rt["mean_ms"] >= 0.0
            assert live_rt["p95_ms"] >= 0.0

            assert live_rt["mean_ms"] <= recorded_rt["mean_ms"] + 100.0
            assert live_rt["p95_ms"] <= recorded_rt["p95_ms"] + 200.0

        per_batch_summaries: dict[str, Mapping[str, Any]] = {}

        for bos_batch_id, batch_callbacks in callbacks_by_batch.items():
            batch_summary = compute_llm_trace_summary(
                batch_callbacks,
                scenario_id=f"eng5_lower5_small_net_{bos_batch_id}",
            )
            per_batch_summaries[bos_batch_id] = batch_summary
            _assert_summary_within_parity(batch_summary)

        aggregate_summary = compute_llm_trace_summary(
            callbacks,
            scenario_id="eng5_lower5_small_net_aggregate",
        )
        _assert_summary_within_parity(aggregate_summary)

        print(
            "ENG5 LOWER5 small-net diagnostics:",
            {
                "num_batches": num_batches,
                "requests_per_batch": requests_per_batch,
                "total_callbacks": len(callbacks),
                "aggregate_response_time_ms": aggregate_summary["response_time_ms"],
            },
        )

        # LPS serial-bundle and queue metrics guardrails for ENG5 LOWER5 profile.
        await assert_lps_serial_bundle_metrics_for_mock_profile(validated_services)
