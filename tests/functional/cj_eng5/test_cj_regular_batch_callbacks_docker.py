"""Docker-backed CJ ↔ LPS callback invariants for regular ENG5 batches.

This module focuses on callback-level safety and preferred_bundle_size hint
semantics for a larger ENG5-style batch (24 essays) under the
``cj_generic_batch`` mock profile. It complements
``test_cj_regular_batch_resampling_docker.py``, which concentrates on
resampling and positional fairness semantics.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from common_core.domain_enums import CourseCode
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1
from common_core.status_enums import CJBatchStateEnum

from services.cj_assessment_service.config import Settings as CJSettings
from tests.functional.cj_eng5.test_cj_small_net_continuation_docker import (
    _ensure_sufficient_credits,
    _get_lps_mock_mode,
    _request_cj_pipeline_execution,
    _wait_for_batch_ready_via_kafka,
    _wait_for_cj_batch_final_state,
)
from tests.utils.auth_manager import AuthTestUser
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager


class TestCJRegularBatchCallbacksDocker:
    """Callback-level invariants for regular ENG5 batches."""

    @pytest.fixture
    async def service_manager(self) -> ServiceTestManager:
        """Service validation manager."""
        return ServiceTestManager()

    @pytest.fixture
    async def validated_services(self, service_manager: ServiceTestManager) -> dict:
        """Ensure core services required for CJ continuation are running."""
        endpoints = await service_manager.get_validated_endpoints()

        required = {"api_gateway_service", "cj_assessment_service", "llm_provider_service"}
        missing = required - set(endpoints.keys())
        if missing:
            pytest.skip(
                f"Required services not available for integration testing: {sorted(missing)}"
            )

        return endpoints

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.mock_profile("cj_generic_batch")
    @pytest.mark.asyncio
    async def test_cj_regular_batch_callbacks_and_preferred_bundle_size_invariants(
        self,
        service_manager: ServiceTestManager,
        validated_services: dict[str, Any],
    ) -> None:
        """Validate callback counts and preferred_bundle_size hints for regular ENG5 batch.

        Notes:
        - This test is only meaningful when CJ emits batching metadata hints.
          In environments where `CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS`
          is false (the current default), we skip early instead of running a full
          24-essay ENG5 batch merely to discover that no preferred_bundle_size hints
          are present in callback metadata.
        """
        settings = CJSettings()
        if not settings.ENABLE_LLM_BATCHING_METADATA_HINTS:
            pytest.skip(
                "CJ batching metadata hints are disabled "
                "(CJ_ASSESSMENT_SERVICE_ENABLE_LLM_BATCHING_METADATA_HINTS=false); "
                "enable them before running this docker test."
            )
        test_user: AuthTestUser = service_manager.create_test_user()
        kafka_manager = KafkaTestManager()

        mode_info = await _get_lps_mock_mode(validated_services)

        if not mode_info.get("use_mock_llm", False):
            pytest.skip(
                "LPS reports USE_MOCK_LLM = false; enable mock mode before running this test"
            )

        if mode_info.get("mock_mode") != "cj_generic_batch":
            pytest.skip(
                "LPS mock_mode is not 'cj_generic_batch'; restart "
                "llm_provider_service with this profile before running regular-batch "
                "CJ callback and bundling tests."
            )

        expected_essay_count = 24
        assert expected_essay_count > settings.MIN_RESAMPLING_NET_SIZE

        bos_batch_id, correlation_id = await service_manager.create_batch_via_agw(
            expected_essay_count=expected_essay_count,
            course_code=CourseCode.ENG5,
            user=test_user,
        )

        files = [
            {
                "name": f"eng5-regular-batch-bundling-essay-{i + 1}.txt",
                "content": (
                    f"ENG5 regular-batch essay content for bundling test, student {i + 1}. "
                    "Text kept simple for docker tests."
                ),
            }
            for i in range(expected_essay_count)
        ]
        await service_manager.upload_files(
            batch_id=bos_batch_id,
            files=files,
            user=test_user,
            correlation_id=correlation_id,
        )

        await _wait_for_batch_ready_via_kafka(
            kafka_manager,
            bos_batch_id=bos_batch_id,
            correlation_id=correlation_id,
        )

        await _ensure_sufficient_credits(
            service_manager,
            user=test_user,
            required_credits=300,
        )

        try:
            await _request_cj_pipeline_execution(
                service_manager,
                bos_batch_id=bos_batch_id,
                correlation_id=correlation_id,
                user=test_user,
            )
        except RuntimeError as exc:
            msg = str(exc)
            if "402" in msg and "insufficient_credits" in msg:
                pytest.skip(
                    "CJ pipeline request denied due to insufficient credits; "
                    "adjust entitlements or credit config before running this test"
                )
            raise

        batch_state = await _wait_for_cj_batch_final_state(
            bos_batch_id=bos_batch_id,
            expected_essay_count=expected_essay_count,
            timeout_seconds=600.0,
        )

        assert batch_state.state == CJBatchStateEnum.COMPLETED
        assert batch_state.batch_upload is not None
        assert batch_state.batch_upload.expected_essay_count == expected_essay_count

        completed = batch_state.completed_comparisons
        failed = batch_state.failed_comparisons
        submitted = batch_state.submitted_comparisons
        callbacks_recorded = completed + failed

        assert callbacks_recorded > 0
        assert failed == 0
        assert submitted == completed == batch_state.total_comparisons

        denominator = batch_state.completion_denominator()
        assert callbacks_recorded <= denominator

        callbacks_expected = callbacks_recorded

        callback_topic = CJSettings().LLM_PROVIDER_CALLBACK_TOPIC

        callbacks: list[LLMComparisonResultV1] = []
        callback_event_timestamps: list[Any] = []
        extra_callbacks_for_batch = False

        async with kafka_manager.consumer(
            "cj_regular_batch_callbacks_and_hints",
            topics=[callback_topic],
            auto_offset_reset="earliest",
        ) as consumer:
            try:
                async with asyncio.timeout(120.0):
                    while True:
                        msg_batch = await consumer.getmany(timeout_ms=1000, max_records=50)
                        if not msg_batch:
                            if len(callbacks) >= callbacks_expected:
                                break
                            continue

                        for _topic_partition, messages in msg_batch.items():
                            for message in messages:
                                envelope = EventEnvelope[Any].model_validate_json(message.value)
                                result = LLMComparisonResultV1.model_validate(envelope.data)
                                metadata = result.request_metadata or {}

                                if metadata.get("bos_batch_id") != bos_batch_id:
                                    continue

                                cj_batch_id = metadata.get("cj_batch_id")
                                if cj_batch_id is not None and str(cj_batch_id) != str(
                                    batch_state.batch_id
                                ):
                                    continue

                                if len(callbacks) >= callbacks_expected:
                                    extra_callbacks_for_batch = True
                                    break

                                callbacks.append(result)
                                callback_event_timestamps.append(envelope.event_timestamp)

                            if extra_callbacks_for_batch:
                                break

                        if extra_callbacks_for_batch:
                            break

            except TimeoutError:
                pytest.fail(
                    "Timeout while collecting LPS callbacks for regular ENG5 batch: "
                    f"expected {callbacks_expected}, collected {len(callbacks)}. "
                    "Ensure dev stack, Kafka, and mock provider are running."
                )

        assert extra_callbacks_for_batch is False, (
            "Observed more LPS callbacks for this batch than CJ recorded via "
            "completed_comparisons + failed_comparisons; check continuation guard semantics."
        )
        assert len(callbacks) == callbacks_expected, (
            f"Expected {callbacks_expected} callbacks for bos_batch_id={bos_batch_id}, "
            f"collected {len(callbacks)}"
        )

        hinted_values: list[int] = []
        for cb in callbacks:
            meta = cb.request_metadata or {}
            if "preferred_bundle_size" in meta:
                hinted_values.append(meta["preferred_bundle_size"])

        if not hinted_values:
            pytest.skip(
                "No preferred_bundle_size hints present in regular-batch callbacks; "
                "enable CJ batching metadata hints before running this docker test."
            )

        for value in hinted_values:
            assert isinstance(value, int)
            assert 1 <= value <= 64

        completed_at = batch_state.batch_upload.completed_at
        assert completed_at is not None

        if callback_event_timestamps:
            max(callback_event_timestamps)
