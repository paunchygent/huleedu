"""CJ/ENG5 mock profile suite harness.

This docker-backed suite provides a thin orchestration layer over the existing
CJ generic + ENG5 anchor + ENG5 LOWER5 mock parity tests. It treats the
LLM Provider Service `/admin/mock-mode` endpoint as the single source of truth
for the active mock profile and delegates deeper behavioural checks to the
per-profile test modules.
"""

from __future__ import annotations

import pytest

from tests.eng5_profiles._lps_helpers import get_lps_mock_mode
from tests.eng5_profiles.test_cj_mock_parity_generic import TestCJMockParityGeneric
from tests.eng5_profiles.test_eng5_mock_parity_full_anchor import (
    TestEng5MockParityFullAnchor,
)
from tests.eng5_profiles.test_eng5_mock_parity_lower5 import TestEng5MockParityLower5
from tests.utils.kafka_test_manager import KafkaTestManager
from tests.utils.service_test_manager import ServiceTestManager


class TestEng5ProfileSuite:
    """High-level CJ/ENG5 mock profile suite orchestrated via /admin/mock-mode."""

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
    async def test_profile_suite_cj_generic(
        self,
        validated_services: dict,
        kafka_manager: KafkaTestManager,
    ) -> None:
        """
        CJ generic mock profile suite smoke test.

        Validates that when LPS is running with the CJ generic mock profile:
        - `/admin/mock-mode` reports `use_mock_llm=true` and `mock_mode=cj_generic_batch`.
        - The existing CJ generic parity and coverage tests pass under this profile.
        """
        base_url = validated_services["llm_provider_service"]["base_url"]
        mode_info = await get_lps_mock_mode(base_url)

        if not mode_info.get("use_mock_llm", False):
            pytest.skip(
                "LPS reports USE_MOCK_LLM = false; enable mock mode before running "
                "CJ generic profile suite tests"
            )

        if mode_info.get("mock_mode") != "cj_generic_batch":
            pytest.skip(
                "LPS mock_mode is not 'cj_generic_batch'; restart llm_provider_service "
                "with this profile before running CJ generic profile suite tests."
            )

        impl = TestCJMockParityGeneric()
        await impl.test_cj_mock_parity_generic_mode_matches_recorded_summary(
            validated_services=validated_services,
            kafka_manager=kafka_manager,
        )
        await impl.test_cj_mock_parity_generic_mode_stable_across_multiple_batches(
            validated_services=validated_services,
            kafka_manager=kafka_manager,
        )

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_profile_suite_eng5_anchor(
        self,
        validated_services: dict,
        kafka_manager: KafkaTestManager,
    ) -> None:
        """
        ENG5 anchor mock profile suite smoke test.

        Validates that when LPS is running with the ENG5 anchor mock profile:
        - `/admin/mock-mode` reports `use_mock_llm=true` and
          `mock_mode=eng5_anchor_gpt51_low`.
        - The existing ENG5 anchor parity test passes under this profile.
        """
        base_url = validated_services["llm_provider_service"]["base_url"]
        mode_info = await get_lps_mock_mode(base_url)

        if not mode_info.get("use_mock_llm", False):
            pytest.skip(
                "LPS reports USE_MOCK_LLM = false; enable mock mode before running "
                "ENG5 anchor profile suite tests"
            )

        if mode_info.get("mock_mode") != "eng5_anchor_gpt51_low":
            pytest.skip(
                "LPS mock_mode is not 'eng5_anchor_gpt51_low'; restart llm_provider_service "
                "with this profile before running ENG5 anchor profile suite tests."
            )

        impl = TestEng5MockParityFullAnchor()
        await impl.test_eng5_mock_parity_anchor_mode_matches_recorded_summary(
            validated_services=validated_services,
            kafka_manager=kafka_manager,
        )

    @pytest.mark.docker
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_profile_suite_eng5_lower5(
        self,
        validated_services: dict,
        kafka_manager: KafkaTestManager,
    ) -> None:
        """
        ENG5 LOWER5 mock profile suite smoke test.

        Validates that when LPS is running with the ENG5 LOWER5 mock profile:
        - `/admin/mock-mode` reports `use_mock_llm=true` and
          `mock_mode=eng5_lower5_gpt51_low`.
        - The existing ENG5 LOWER5 parity and small-net diagnostics tests pass
          under this profile.
        """
        base_url = validated_services["llm_provider_service"]["base_url"]
        mode_info = await get_lps_mock_mode(base_url)

        if not mode_info.get("use_mock_llm", False):
            pytest.skip(
                "LPS reports USE_MOCK_LLM = false; enable mock mode before running "
                "ENG5 LOWER5 profile suite tests"
            )

        if mode_info.get("mock_mode") != "eng5_lower5_gpt51_low":
            pytest.skip(
                "LPS mock_mode is not 'eng5_lower5_gpt51_low'; restart llm_provider_service "
                "with this profile before running ENG5 LOWER5 profile suite tests."
            )

        impl = TestEng5MockParityLower5()
        await impl.test_eng5_mock_parity_lower5_mode_matches_recorded_summary(
            validated_services=validated_services,
            kafka_manager=kafka_manager,
        )
        await impl.test_eng5_mock_lower5_small_net_diagnostics_across_batches(
            validated_services=validated_services,
            kafka_manager=kafka_manager,
        )
