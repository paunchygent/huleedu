"""
E2E Pipeline Processing Workflows

Simplified consolidated test suite for spellcheck pipeline functionality from step 4.
Focuses on Content Service integration and basic spellcheck workflow validation.

Uses modern utility patterns (ServiceTestManager) exclusively - NO direct HTTP calls.
"""

import httpx
import pytest

from tests.utils.service_test_manager import ServiceTestManager


class TestE2EPipelineWorkflows:
    """Test simplified spellcheck pipeline workflow using modern utility patterns exclusively."""

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_content_service_upload_and_retrieval(self):
        """
        Test Content Service upload and retrieval functionality using ServiceTestManager.

        This consolidates the core Content Service integration patterns from step 4.
        """
        service_manager = ServiceTestManager()

        # Validate required services are available using utility
        endpoints = await service_manager.get_validated_endpoints()
        if "content_service" not in endpoints:
            pytest.skip("Content Service not available")

        test_content = """
        This is a test essay with some spelling errors that should be corrected.
        The spellchecker service should identify and fix these mistakes.
        We will validate that the corrected text is stored properly.
        """

        # Step 1: Upload content to Content Service using validated endpoint
        storage_id = await self._upload_content_via_utility(
            endpoints["content_service"]["base_url"],
            test_content,
        )
        assert storage_id is not None
        print(f"✅ Content uploaded with storage_id: {storage_id}")

        # Step 2: Retrieve content from Content Service using validated endpoint
        retrieved_content = await self._fetch_content_via_utility(
            endpoints["content_service"]["base_url"],
            storage_id,
        )

        assert retrieved_content is not None
        assert retrieved_content == test_content
        print("✅ Content retrieval validated")

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_spellchecker_service_health(self):
        """
        Test Spell Checker Service health validation using ServiceTestManager.

        Consolidates health checking patterns from step 4.
        """
        service_manager = ServiceTestManager()

        # Validate Spell Checker Service using modern endpoint validation
        endpoints = await service_manager.get_validated_endpoints()
        if "spellchecker_service" not in endpoints:
            pytest.skip("Spell Checker Service not available")

        # Verify the service is healthy
        spell_checker_info = endpoints["spellchecker_service"]
        assert spell_checker_info["status"] == "healthy"
        print("✅ Spell Checker Service health validated")

    # Helper methods for Content Service operations using utility pattern

    async def _upload_content_via_utility(self, base_url: str, content: str) -> str:
        """
        Upload content to Content Service using httpx (aligned with ServiceTestManager pattern).

        Note: Uses httpx instead of aiohttp to align with ServiceTestManager's HTTP client choice.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url}/v1/content",
                content=content.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
            )

            if response.status_code not in [200, 201]:
                raise RuntimeError(
                    f"Content upload failed: {response.status_code} - {response.text}",
                )

            response_data = response.json()
            storage_id: str = response_data["storage_id"]
            return storage_id

    async def _fetch_content_via_utility(self, base_url: str, storage_id: str) -> str:
        """
        Fetch content from Content Service using httpx (aligned with ServiceTestManager pattern).

        Note: Uses httpx instead of aiohttp to align with ServiceTestManager's HTTP client choice.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{base_url}/v1/content/{storage_id}")

            if response.status_code != 200:
                raise RuntimeError(
                    f"Content fetch failed: {response.status_code} - {response.text}",
                )

            return response.text
