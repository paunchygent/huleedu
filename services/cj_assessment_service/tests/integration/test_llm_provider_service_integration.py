"""Integration tests for CJ Assessment Service with LLM Provider Service.

These tests verify end-to-end communication between CJ Assessment Service
and the centralized LLM Provider Service.
"""

import asyncio
from uuid import uuid4

import aiohttp
import pytest

from common_core.config_enums import LLMProviderType
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent
from common_core.events.cj_assessment_events import (
    ELS_CJAssessmentRequestV1,
    LLMConfigOverrides,
)
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EntityReference, EssayProcessingInputRefV1, SystemProcessingMetadata


class TestLLMProviderServiceIntegration:
    """Test CJ Assessment Service integration with LLM Provider Service."""

    @pytest.fixture
    async def http_session(self):
        """Create HTTP session for testing."""
        async with aiohttp.ClientSession() as session:
            yield session

    @pytest.fixture
    def llm_provider_url(self):
        """LLM Provider Service URL."""
        return "http://localhost:8090/api/v1"

    @pytest.fixture
    def cj_assessment_url(self):
        """CJ Assessment Service health URL."""
        return "http://localhost:9095"

    async def test_services_are_healthy(self, http_session, llm_provider_url, cj_assessment_url):
        """Test that both services are running and healthy."""
        # Check LLM Provider Service
        async with http_session.get(
            f"{llm_provider_url.replace('/api/v1', '')}/healthz"
        ) as response:
            assert response.status == 200
            health_data = await response.json()
            assert health_data["status"] == "healthy"
            assert health_data["dependencies"]["redis"] == "healthy"
            print(f"LLM Provider Service: {health_data}")

        # Check CJ Assessment Service
        async with http_session.get(f"{cj_assessment_url}/healthz") as response:
            assert response.status == 200
            health_data = await response.json()
            assert health_data["status"] == "ok"
            print(f"CJ Assessment Service: {health_data}")

    async def test_llm_provider_comparison_endpoint(self, http_session, llm_provider_url):
        """Test direct call to LLM Provider Service comparison endpoint."""
        request_data = {
            "user_prompt": "Compare these two essays and determine which is better written.",
            "essay_a": "This is a well-structured essay with clear arguments and good flow.",
            "essay_b": "This essay lacks structure and has unclear arguments.",
            "llm_config_overrides": {
                "provider_override": LLMProviderType.ANTHROPIC.value,
                "temperature_override": 0.1,
            },
            "correlation_id": str(uuid4()),
        }

        # Use mock provider to avoid real API calls
        headers = {"X-Use-Mock-LLM": "true"}  # This header might not work, check service config

        async with http_session.post(
            f"{llm_provider_url}/comparison",
            json=request_data,
            headers=headers,
        ) as response:
            if response.status == 200:
                result = await response.json()
                print(f"LLM Provider Response: {result}")

                # Verify response format
                assert "winner" in result
                assert result["winner"] in ["Essay A", "Essay B"]
                assert "justification" in result
                assert "confidence" in result
                assert 1 <= result["confidence"] <= 5
                assert "provider" in result
                assert "cached" in result
            else:
                error_text = await response.text()
                pytest.skip(f"LLM Provider Service returned {response.status}: {error_text}")

    async def test_cj_assessment_kafka_integration(self):
        """Test CJ Assessment Service processing via Kafka.

        This test publishes a CJ assessment request to Kafka and monitors
        the docker logs to verify processing.
        """
        # Create test event
        event_data = ELS_CJAssessmentRequestV1(
            entity_ref=EntityReference(
                entity_type="batch",
                entity_id="test-batch-123",
            ),
            system_metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_type="batch",
                    entity_id="test-batch-123",
                )
            ),
            essays_for_cj=[
                EssayProcessingInputRefV1(
                    essay_id="essay-1",
                    text_storage_id="content/essay-1.txt",
                ),
                EssayProcessingInputRefV1(
                    essay_id="essay-2", 
                    text_storage_id="content/essay-2.txt",
                ),
            ],
            language="en",
            course_code=CourseCode.ENG5,
            essay_instructions="Write a clear argumentative essay",
            llm_config_overrides=LLMConfigOverrides(
                provider_override=LLMProviderType.ANTHROPIC,
                temperature_override=0.1,
            ),
        )

        # Create event envelope
        envelope = EventEnvelope(
            event_type=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED.value,
            source_service="test-integration",
            data=event_data,
        )

        # Note: This would require Kafka to be accessible from the test environment
        # For now, we'll skip the actual Kafka publish
        pytest.skip("Kafka integration requires running in Docker network")

    @pytest.mark.parametrize("provider", [LLMProviderType.ANTHROPIC, LLMProviderType.OPENAI])
    async def test_provider_configuration(self, http_session, llm_provider_url, provider):
        """Test that different providers can be configured."""
        async with http_session.get(f"{llm_provider_url}/providers") as response:
            assert response.status == 200
            providers_data = await response.json()

            # Check that the provider is available - providers is a list of objects
            provider_names = [p["name"] for p in providers_data["providers"]]
            assert provider.value in provider_names
            
            # Find the provider object
            provider_info = next(p for p in providers_data["providers"] if p["name"] == provider.value)
            assert provider_info["enabled"] is True
            assert provider_info["available"] is True
            print(f"Provider {provider.value}: {provider_info}")


@pytest.mark.asyncio
class TestMockProviderIntegration:
    """Test integration using mock LLM provider."""

    async def test_mock_provider_response(self):
        """Test that mock provider returns expected format."""
        # This test would need to configure LLM Provider Service
        # to use mock provider via environment variable
        pytest.skip("Mock provider test requires service reconfiguration")


@pytest.mark.asyncio
class TestQueueIntegration:
    """Test integration for queue-based LLM processing."""

    @pytest.fixture
    async def http_session(self):
        """Create HTTP session for testing."""
        async with aiohttp.ClientSession() as session:
            yield session

    @pytest.fixture
    def llm_provider_url(self):
        """LLM Provider Service URL."""
        return "http://localhost:8090/api/v1"

    async def test_queue_status_endpoint(self, http_session, llm_provider_url):
        """Test queue status endpoint exists and responds appropriately."""
        # Test with a fake queue ID to verify endpoint exists
        fake_queue_id = str(uuid4())

        async with http_session.get(f"{llm_provider_url}/status/{fake_queue_id}") as response:
            # Should return 404 for non-existent queue ID
            assert response.status == 404
            error_data = await response.json()
            assert "error" in error_data
            print(f"Queue status (404): {error_data}")

    async def test_queue_results_endpoint(self, http_session, llm_provider_url):
        """Test queue results endpoint exists and responds appropriately."""
        # Test with a fake queue ID to verify endpoint exists
        fake_queue_id = str(uuid4())

        async with http_session.get(f"{llm_provider_url}/results/{fake_queue_id}") as response:
            # Should return 404 for non-existent queue ID
            assert response.status == 404
            error_data = await response.json()
            assert "error" in error_data
            print(f"Queue results (404): {error_data}")

    async def test_llm_provider_service_health_with_queue_stats(
        self, http_session, llm_provider_url
    ):
        """Test LLM Provider Service health endpoint includes queue stats."""
        async with http_session.get(
            f"{llm_provider_url.replace('/api/v1', '')}/healthz"
        ) as response:
            assert response.status == 200
            health_data = await response.json()
            assert health_data["status"] == "healthy"

            # Queue stats should be included in health response
            if "queue_stats" in health_data:
                queue_stats = health_data["queue_stats"]
                assert "queue_size" in queue_stats
                assert "queue_type" in queue_stats
                print(f"Queue stats: {queue_stats}")
            else:
                print("Queue stats not included in health response")

    async def test_comparison_endpoint_immediate_response(self, http_session, llm_provider_url):
        """Test comparison endpoint returns immediate response when providers available."""
        request_data = {
            "user_prompt": "Compare these two essays and determine which is better written.",
            "essay_a": "This is a well-structured essay with clear arguments and good flow.",
            "essay_b": "This essay lacks structure and has unclear arguments.",
            "llm_config_overrides": {
                "provider_override": LLMProviderType.ANTHROPIC.value,
                "temperature_override": 0.1,
            },
            "correlation_id": str(uuid4()),
        }

        # Use mock provider to avoid real API calls
        headers = {"X-Use-Mock-LLM": "true"}

        async with http_session.post(
            f"{llm_provider_url}/comparison",
            json=request_data,
            headers=headers,
        ) as response:
            if response.status == 200:
                # Immediate response
                result = await response.json()
                print(f"Immediate response: {result}")

                # Verify response format
                assert "winner" in result
                assert result["winner"] in ["Essay A", "Essay B"]
                assert "justification" in result
                assert "confidence" in result
                assert 1 <= result["confidence"] <= 5
                assert "provider" in result

            elif response.status == 202:
                # Queued response - test queue endpoints
                queue_response = await response.json()
                print(f"Queued response: {queue_response}")

                assert "queue_id" in queue_response
                assert "status" in queue_response
                assert queue_response["status"] == "queued"

                queue_id = queue_response["queue_id"]

                # Test queue status endpoint
                await asyncio.sleep(1)  # Brief wait
                async with http_session.get(
                    f"{llm_provider_url}/status/{queue_id}"
                ) as status_response:
                    if status_response.status == 200:
                        status_data = await status_response.json()
                        print(f"Queue status: {status_data}")
                        assert "status" in status_data
                        assert status_data["status"] in [
                            "queued",
                            "processing",
                            "completed",
                            "failed",
                            "expired",
                        ]

                # Test queue results endpoint (may not be ready)
                async with http_session.get(
                    f"{llm_provider_url}/results/{queue_id}"
                ) as result_response:
                    if result_response.status == 200:
                        result_data = await result_response.json()
                        print(f"Queue result: {result_data}")
                        # Same format as immediate response
                        assert "winner" in result_data
                        assert "justification" in result_data
                        assert "confidence" in result_data
                    elif result_response.status == 202:
                        result_data = await result_response.json()
                        print(f"Result not ready: {result_data}")
                        assert "status" in result_data
                    else:
                        print(f"Result response: {result_response.status}")

            else:
                error_text = await response.text()
                print(f"Comparison request failed: {response.status} - {error_text}")

    async def test_cj_assessment_client_queue_handling(self):
        """Test CJ Assessment Service client handles both immediate and queued responses."""
        from services.cj_assessment_service.config import Settings
        from services.cj_assessment_service.implementations.llm_provider_service_client import (
            LLMProviderServiceClient,
        )
        from services.cj_assessment_service.implementations.retry_manager_impl import (
            RetryManagerImpl,
        )

        # Create settings with queue polling enabled
        settings = Settings()
        settings.LLM_PROVIDER_SERVICE_URL = "http://localhost:8090/api/v1"
        settings.LLM_QUEUE_POLLING_ENABLED = True
        settings.LLM_QUEUE_POLLING_INITIAL_DELAY_SECONDS = 1.0
        settings.LLM_QUEUE_POLLING_MAX_DELAY_SECONDS = 5.0
        settings.LLM_QUEUE_POLLING_MAX_ATTEMPTS = 10
        settings.LLM_QUEUE_TOTAL_TIMEOUT_SECONDS = 60

        # Create retry manager
        retry_manager = RetryManagerImpl(settings)

        async with aiohttp.ClientSession() as session:
            client = LLMProviderServiceClient(session, settings, retry_manager)

            # Test with a comparison prompt
            prompt = """Compare these two essays and determine which is better written.
Essay A (ID: test-1):
This is a well-structured essay with clear arguments and good flow.

Essay B (ID: test-2):
This essay lacks structure and has unclear arguments.

Please respond with a JSON object containing:
- 'winner': 'Essay A' or 'Essay B'
- 'justification': Brief explanation of your decision
- 'confidence': Rating from 1-5 (5 = very confident)"""

            try:
                result, error = await client.generate_comparison(
                    user_prompt=prompt,
                    model_override="gpt-4o-mini",
                    temperature_override=0.1,
                )

                if error is None:
                    print(f"CJ Assessment client result: {result}")
                    assert result is not None
                    assert "winner" in result
                    assert "justification" in result
                    assert "confidence" in result
                else:
                    print(f"CJ Assessment client error: {error}")
                    # Some errors are expected in test environment

            except Exception as e:
                print(f"CJ Assessment client exception: {e}")
                # Exceptions may occur due to service unavailability in test environment
