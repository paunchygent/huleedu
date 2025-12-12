"""Docker-backed CJ regular-batch ENG5 run exercising provider_batch_api.

This test is focused on the ENG5 → CJ per-batch override plumbing:
- ENG5 runner sets `llm_batching_mode_hint="provider_batch_api"` in envelope metadata.
- CJ maps that hint into `BatchConfigOverrides.llm_batching_mode_override`.
- CJ persists `llm_batching_mode="provider_batch_api"` and emits CJ batching metrics.

It intentionally keeps the existing serial_bundle docker semantics tests untouched.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from common_core import LLMBatchingMode
from common_core.domain_enums import CourseCode, Language
from common_core.events.cj_assessment_events import LLMConfigOverrides
from common_core.metadata_models import EssayProcessingInputRefV1
from common_core.status_enums import CJBatchStateEnum

from scripts.cj_experiments_runners.eng5_np.requests import compose_cj_assessment_request
from scripts.cj_experiments_runners.eng5_np.settings import RunnerMode, RunnerSettings
from services.cj_assessment_service.config import Settings as CJSettings
from services.llm_provider_service.config import (
    QueueProcessingMode,
)
from services.llm_provider_service.config import (
    Settings as LLMProviderSettings,
)
from tests.functional.cj_eng5.test_cj_small_net_continuation_docker import (
    _ensure_sufficient_credits,
    _get_lps_mock_mode,
    _wait_for_cj_batch_final_state,
)
from tests.utils.auth_manager import AuthTestUser
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.metrics_helpers import fetch_and_parse_metrics, find_metric_values_in_map
from tests.utils.prompt_reference import make_prompt_ref
from tests.utils.service_test_manager import ServiceTestManager


class TestCJRegularBatchProviderBatchApiDocker:
    """Provider-batch docker semantics for a regular ENG5 batch."""

    @pytest.fixture
    async def service_manager(self) -> ServiceTestManager:
        """Service validation manager."""
        return ServiceTestManager()

    @pytest.fixture
    async def validated_services(self, service_manager: ServiceTestManager) -> dict[str, Any]:
        """Ensure services required for direct runner-driven CJ requests are available."""
        endpoints = await service_manager.get_validated_endpoints()

        required = {"content_service", "cj_assessment_service", "llm_provider_service"}
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
    async def test_cj_regular_batch_provider_batch_api_metrics_and_override_plumbing(
        self,
        service_manager: ServiceTestManager,
        validated_services: dict[str, Any],
    ) -> None:
        """Run a regular ENG5 batch via runner metadata hint and assert CJ metrics."""

        if LLMProviderSettings().QUEUE_PROCESSING_MODE is not QueueProcessingMode.BATCH_API:
            pytest.skip(
                "This docker test requires LPS queue mode batch_api "
                "(LLM_PROVIDER_SERVICE_QUEUE_PROCESSING_MODE=batch_api)."
            )

        if CJSettings().LLM_BATCHING_MODE is LLMBatchingMode.PROVIDER_BATCH_API:
            pytest.skip(
                "This docker test is intended to validate per-batch override plumbing; "
                "run with CJ_ASSESSMENT_SERVICE_LLM_BATCHING_MODE=serial_bundle and rely on "
                "ENG5 llm_batching_mode_hint=provider_batch_api."
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
                "LPS mock_mode is not 'cj_generic_batch'; restart llm_provider_service with "
                "this profile before running provider_batch_api docker semantics."
            )

        expected_essay_count = 24

        prompt_storage_id = await service_manager.upload_content_directly(
            "ENG5 provider-batch test prompt: Compare the essays for quality.\n",
            user=test_user,
        )
        prompt_ref = make_prompt_ref(
            prompt_storage_id,
            path_hint="tests/functional/cj_eng5/provider_batch_api_prompt.txt",
        )

        essay_refs: list[EssayProcessingInputRefV1] = []
        for i in range(expected_essay_count):
            storage_id = await service_manager.upload_content_directly(
                (
                    f"ENG5 provider-batch essay content for student {i + 1}. "
                    "Text kept simple for docker tests.\n"
                ),
                user=test_user,
            )
            essay_refs.append(
                EssayProcessingInputRefV1(
                    essay_id=f"essay-{i + 1:03d}",
                    text_storage_id=storage_id,
                )
            )

        batch_uuid = uuid.uuid4()
        correlation_id = uuid.uuid4()

        runner_settings = RunnerSettings(
            assignment_id=uuid.uuid4(),
            course_id=uuid.uuid4(),
            grade_scale="eng5",
            mode=RunnerMode.EXECUTE,
            use_kafka=True,
            output_dir=Path("/tmp"),
            runner_version="test",
            git_sha="test",
            batch_uuid=batch_uuid,
            batch_id=f"eng5-provider-batch-api-{batch_uuid.hex[:8]}",
            user_id=test_user.user_id,
            org_id=test_user.organization_id,
            course_code=CourseCode.ENG5,
            language=Language.ENGLISH,
            correlation_id=correlation_id,
            kafka_bootstrap="localhost:9093",
            kafka_client_id="test_eng5_provider_batch_api",
            content_service_url=validated_services["content_service"]["base_url"],
            llm_overrides=LLMConfigOverrides(
                judge_rubric_override=(
                    "Judge rubric (test): choose the stronger essay overall. "
                    "Return winner, brief justification, and confidence."
                )
            ),
            max_comparisons=60,
            llm_batching_mode_hint="provider_batch_api",
        )

        envelope = compose_cj_assessment_request(
            settings=runner_settings,
            essay_refs=essay_refs,
            prompt_reference=prompt_ref,
        )

        # Ensure entitlements allow CJ execution for this user/org before we enqueue work.
        await _ensure_sufficient_credits(service_manager, user=test_user, required_credits=500)

        await kafka_manager.ensure_topics([envelope.event_type])
        await kafka_manager.publish_event(
            envelope.event_type,
            envelope.model_dump(mode="json"),
        )

        batch_state = await _wait_for_cj_batch_final_state(
            bos_batch_id=str(batch_uuid),
            expected_essay_count=expected_essay_count,
            timeout_seconds=600.0,
        )

        assert batch_state.batch_upload is not None
        assert batch_state.state == CJBatchStateEnum.COMPLETED
        assert (batch_state.failed_comparisons or 0) == 0

        processing_metadata = batch_state.processing_metadata or {}
        assert processing_metadata.get("llm_batching_mode") == "provider_batch_api"

        upload_metadata = batch_state.batch_upload.processing_metadata or {}
        original_request = upload_metadata.get("original_request") or {}
        batch_config_overrides = original_request.get("batch_config_overrides") or {}
        assert batch_config_overrides.get("llm_batching_mode_override") == "provider_batch_api"

        cj_metrics_url = validated_services["cj_assessment_service"].get("metrics_url")
        lps_metrics_url = validated_services["llm_provider_service"].get("metrics_url")
        assert cj_metrics_url, "CJ Assessment metrics URL missing from validated services"
        assert lps_metrics_url, "LLM Provider Service metrics URL missing from validated services"

        cj_metrics = await fetch_and_parse_metrics(metrics_url=cj_metrics_url)
        lps_metrics = await fetch_and_parse_metrics(metrics_url=lps_metrics_url)

        provider_batch_api_labels = {"batching_mode": "provider_batch_api"}

        cj_requests_values = find_metric_values_in_map(
            cj_metrics,
            "cj_llm_requests_total",
            provider_batch_api_labels,
        )
        cj_batches_values = find_metric_values_in_map(
            cj_metrics,
            "cj_llm_batches_started_total",
            provider_batch_api_labels,
        )

        assert cj_requests_values and max(cj_requests_values) >= 1.0
        assert cj_batches_values and max(cj_batches_values) >= 1.0

        # Sanity-check that the batch_api path produced queue/job-level metrics in LPS.
        expected_provider = str(mode_info.get("default_provider") or "openai")
        expected_model = CJSettings().DEFAULT_LLM_MODEL

        wait_count_values = find_metric_values_in_map(
            lps_metrics,
            "llm_provider_queue_wait_time_seconds_count",
            {"queue_processing_mode": "batch_api"},
        )
        assert wait_count_values and sum(wait_count_values) > 0.0

        job_scheduled_values = find_metric_values_in_map(
            lps_metrics,
            "llm_provider_batch_api_jobs_total",
            {"provider": expected_provider, "model": expected_model, "status": "scheduled"},
        )
        assert job_scheduled_values and max(job_scheduled_values) >= 1.0

        job_completed_values = find_metric_values_in_map(
            lps_metrics,
            "llm_provider_batch_api_jobs_total",
            {"provider": expected_provider, "model": expected_model, "status": "completed"},
        )
        assert job_completed_values and max(job_completed_values) >= 1.0
