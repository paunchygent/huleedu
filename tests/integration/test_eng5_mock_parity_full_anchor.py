"""Docker-backed parity test for ENG5 anchor mock mode.

This test validates that the LLM Provider Service mock provider in
``eng5_anchor_gpt51_low`` mode produces callbacks whose aggregate behaviour
matches the recorded ENG5 GPT-5.1 low full-anchor run
(``eng5_anchor_align_gpt51_low_20251201``) within sensible tolerances.

Assumptions:
- LPS is running in mock-only mode with:
  - ``LLM_PROVIDER_SERVICE_USE_MOCK_LLM=true``
  - ``LLM_PROVIDER_SERVICE_MOCK_MODE=eng5_anchor_gpt51_low``
- CJ publishes LLM comparison requests to LPS using the standard callback
  topic contract; this test drives LPS directly via HTTP with
  ``LLMProviderType.MOCK`` overrides.
"""

from __future__ import annotations

import asyncio
import json
import os
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
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager


class TestEng5MockParityFullAnchor:
    """Integration test: ENG5 full-anchor mock mode parity vs recorded summary."""

    @staticmethod
    def _load_env_mock_mode() -> str | None:
        """Load LLM_PROVIDER_SERVICE_MOCK_MODE from the repo-root .env if present."""

        env_path = Path(__file__).resolve().parents[2] / ".env"
        if not env_path.exists():
            return None

        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("LLM_PROVIDER_SERVICE_MOCK_MODE"):
                _, _, value = stripped.partition("=")
                return value.strip() or None
        return None

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
    async def test_eng5_mock_parity_anchor_mode_matches_recorded_summary(
        self,
        validated_services: dict,  # noqa: ARG002 - ensures services are running
        kafka_manager: KafkaTestManager,
    ) -> None:
        """
        Send a full 12-anchor (66 comparison) batch of ENG5-shaped requests
        through LPS using the mock provider in ``eng5_anchor_gpt51_low`` mode
        and compare live callbacks against the recorded summary for
        ``eng5_anchor_align_gpt51_low_20251201``.

        Behavioural parity expectations:
        - All callbacks succeed (no errors).
        - Winner distribution approximates the recorded GPT-5.1 low run.
        - Token usage means remain in the same order of magnitude.
        - Latency stays within a reasonable band of the recorded trace.
        """
        # This test is only valid when the LPS container is configured
        # to use the ENG5 anchor mock mode and mock-only provider.
        use_mock_env = os.getenv("LLM_PROVIDER_SERVICE_USE_MOCK_LLM", "").lower()
        mock_mode_env = os.getenv("LLM_PROVIDER_SERVICE_MOCK_MODE")
        file_mock_mode = self._load_env_mock_mode()
        if use_mock_env != "true" or mock_mode_env != "eng5_anchor_gpt51_low":
            pytest.skip(
                "LLM_PROVIDER_SERVICE_USE_MOCK_LLM must be 'true' and "
                "LLM_PROVIDER_SERVICE_MOCK_MODE must be set to "
                "'eng5_anchor_gpt51_low' for this test; adjust .env and restart "
                "the dev stack before running."
            )
        if file_mock_mode is not None and file_mock_mode != mock_mode_env:
            pytest.skip(
                "Process env LLM_PROVIDER_SERVICE_MOCK_MODE does not match .env; "
                "ensure .env and the running LPS container are using 'eng5_anchor_gpt51_low'."
            )

        scenario_id = "eng5_anchor_align_gpt51_low_20251201"

        # 1. Load recorded summary for baseline metrics
        summary_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "llm_traces"
            / scenario_id
            / "summary.json"
        )
        with summary_path.open("r", encoding="utf-8") as f:
            recorded_summary: dict[str, Any] = json.load(f)

        # Sanity-check fixture expectations (guards against accidental edits)
        assert recorded_summary["total_events"] == 66
        assert recorded_summary["success_count"] == 66
        assert recorded_summary["error_count"] == 0

        # 2. Configure test parameters
        callback_topic = "test.llm.mock_parity.eng5_anchor.v1"
        await kafka_manager.ensure_topics([callback_topic])

        # 12 anchors → C(12, 2) = 66 comparisons
        anchor_ids = [f"eng5-anchor-{i:02d}" for i in range(1, 13)]
        anchor_pairs = list(combinations(anchor_ids, 2))
        num_requests = len(anchor_pairs)
        assert num_requests == 66

        bos_batch_id = "bos-eng5-anchor-mock-parity-001"
        lps_url = "http://localhost:8090/api/v1/comparison"

        # 3. Send ENG5-shaped LLM comparison requests to LPS
        request_ids: list[str] = []

        async with aiohttp.ClientSession() as session:
            for anchor_a, anchor_b in anchor_pairs:
                correlation_id = uuid4()

                task = ComparisonTask(
                    essay_a=EssayForComparison(
                        id=anchor_a,
                        text_content=f"ENG5 anchor essay content for {anchor_a}",
                    ),
                    essay_b=EssayForComparison(
                        id=anchor_b,
                        text_content=f"ENG5 anchor essay content for {anchor_b}",
                    ),
                    prompt="ENG5 anchor alignment comparison prompt",
                )

                metadata_adapter = CJLLMComparisonMetadata.from_comparison_task(
                    task,
                    bos_batch_id=bos_batch_id,
                ).with_additional_context(cj_llm_batching_mode="per_request")

                request_metadata = metadata_adapter.to_request_metadata()

                user_prompt = (
                    f"ENG5 anchor alignment comparison between {anchor_a} and {anchor_b}. "
                    "Judge which essay better matches the ENG5 rubric."
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
                    assert response.status == 202, f"Expected 202 (queued), got {response.status}"

                    data = await response.json()
                    queued = LLMQueuedResponse.model_validate(data)
                    request_ids.append(str(queued.queue_id))

        # 4. Consume callbacks from Kafka and collect LLMComparisonResultV1 payloads
        callbacks: list[LLMComparisonResultV1] = []

        async with kafka_manager.consumer(
            "eng5_mock_parity_full_anchor",
            topics=[callback_topic],
            auto_offset_reset="earliest",
        ) as consumer:
            try:
                # ENG5 anchor batches are relatively large (66 queued comparisons)
                # with realistic mock latency, so allow up to 120s for all callbacks.
                async with asyncio.timeout(120.0):
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
                    "Timeout waiting for LPS callbacks (60s). "
                    "Ensure dev stack is running and LPS mock mode is configured "
                    "for eng5_anchor_gpt51_low."
                )

        assert len(callbacks) == num_requests, (
            f"Expected {num_requests} callbacks, collected {len(callbacks)}"
        )

        # 5. Basic contract and metadata checks
        for cb in callbacks:
            assert cb.is_success, f"Expected success result, got error: {cb.error_detail}"
            assert cb.winner is not None
            assert cb.justification
            assert cb.confidence is not None
            assert 1.0 <= cb.confidence <= 5.0

            meta = cb.request_metadata
            assert meta.get("bos_batch_id") == bos_batch_id
            assert "essay_a_id" in meta
            assert "essay_b_id" in meta

        # 6. Compute live summary using the same helper as trace capture
        live_summary = compute_llm_trace_summary(
            callbacks,
            scenario_id="eng5_anchor_mock_parity",
        )

        assert live_summary["total_events"] == num_requests
        assert live_summary["error_count"] == 0

        # 7. Winner distribution parity
        def _winner_proportions(summary: Mapping[str, Any]) -> dict[str, float]:
            total = summary["total_events"]
            if total == 0:
                return {"Essay A": 0.0, "Essay B": 0.0}
            counts = summary["winner_counts"]
            return {
                "Essay A": counts.get("Essay A", 0) / total,
                "Essay B": counts.get("Essay B", 0) / total,
            }

        recorded_props = _winner_proportions(recorded_summary)
        live_props = _winner_proportions(live_summary)

        for label in ("Essay A", "Essay B"):
            diff = abs(live_props[label] - recorded_props[label])
            # Allow up to ±20 percentage points per label; ENG5 anchor mode
            # is hash-biased towards the recorded distribution but not a
            # strict replay of the original run.
            assert diff <= 0.20, (
                f"Winner proportion for {label} outside tolerance: "
                f"live={live_props[label]:.3f}, "
                f"recorded={recorded_props[label]:.3f}"
            )

        # 8. Token usage parity (means within a reasonable band)
        def _mean_tokens(summary: Mapping[str, Any], field: str) -> float:
            return float(summary["token_usage"][field]["mean"])

        # Prompt and total tokens: use generic tolerance (max 5 tokens, 50% of recorded mean)
        for field in ("prompt_tokens", "total_tokens"):
            recorded_mean = _mean_tokens(recorded_summary, field)
            live_mean = _mean_tokens(live_summary, field)

            tolerance = max(5.0, recorded_mean * 0.5)
            assert abs(live_mean - recorded_mean) <= tolerance, (
                f"{field} mean outside tolerance: "
                f"live={live_mean}, recorded={recorded_mean}, tolerance={tolerance}"
            )

        # Completion tokens: ENG5 anchor prompts are long with relatively
        # modest completions, so use a slightly more forgiving band.
        recorded_completion_mean = _mean_tokens(recorded_summary, "completion_tokens")
        live_completion_mean = _mean_tokens(live_summary, "completion_tokens")
        completion_tolerance = max(10.0, recorded_completion_mean)

        assert abs(live_completion_mean - recorded_completion_mean) <= completion_tolerance, (
            "completion_tokens mean outside tolerance: "
            f"live={live_completion_mean}, "
            f"recorded={recorded_completion_mean}, "
            f"tolerance={completion_tolerance}"
        )

        # 9. Latency parity (same order-of-magnitude, bounded)
        recorded_rt = recorded_summary["response_time_ms"]
        live_rt = live_summary["response_time_ms"]

        assert live_rt["mean_ms"] >= 0.0
        assert live_rt["p95_ms"] >= 0.0

        # Keep mean and p95 within a modest additive band of the fixture.
        assert live_rt["mean_ms"] <= recorded_rt["mean_ms"] + 100.0
        assert live_rt["p95_ms"] <= recorded_rt["p95_ms"] + 200.0
