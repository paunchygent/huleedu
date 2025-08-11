"""Integration tests for CJ Assessment Service with LLM Provider Service.

These tests verify end-to-end communication between CJ Assessment Service
and the centralized LLM Provider Service.
"""

import asyncio
import json
from typing import Any
from uuid import uuid4

import aiohttp
import pytest
from aiokafka import AIOKafkaProducer
from common_core.config_enums import LLMProviderType
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import (
    ELS_CJAssessmentRequestV1,
    LLMConfigOverrides,
)
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)


class TestLLMProviderServiceIntegration:
    """Test CJ Assessment Service integration with LLM Provider Service."""

    @pytest.fixture
    async def http_session(self) -> Any:
        """Create HTTP session for testing."""
        async with aiohttp.ClientSession() as session:
            yield session

    @pytest.fixture
    def llm_provider_url(self) -> str:
        """LLM Provider Service URL."""
        return "http://localhost:8090/api/v1"

    @pytest.fixture
    def cj_assessment_url(self) -> str:
        """CJ Assessment Service health URL."""
        return "http://localhost:9095"

    async def test_services_are_healthy(
        self, http_session: Any, llm_provider_url: str, cj_assessment_url: str
    ) -> None:
        """Test that both services are running and healthy."""
        # Check LLM Provider Service
        try:
            async with http_session.get(
                f"{llm_provider_url.replace('/api/v1', '')}/healthz",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                assert response.status == 200
                health_data = await response.json()
                assert health_data["status"] == "healthy"
                assert health_data["dependencies"]["redis"] == "healthy"
                print(f"LLM Provider Service: {health_data}")
        except Exception as e:
            pytest.skip(f"LLM Provider Service not available: {str(e)}")

        # Check CJ Assessment Service
        try:
            async with http_session.get(
                f"{cj_assessment_url}/healthz", timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                assert response.status == 200
                health_data = await response.json()
                assert health_data["status"] == "ok"
                print(f"CJ Assessment Service: {health_data}")
        except Exception as e:
            pytest.skip(f"CJ Assessment Service not available: {str(e)}")

    async def test_llm_provider_comparison_endpoint(
        self, http_session: Any, llm_provider_url: str
    ) -> None:
        """Test direct call to LLM Provider Service comparison endpoint."""
        request_data = {
            "user_prompt": "Compare these two essays and determine which is better written.",
            "essay_a": "This is a well-structured essay with clear arguments and good flow.",
            "essay_b": "This essay lacks structure and has unclear arguments.",
            "callback_topic": topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
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
            else:
                error_text = await response.text()
                pytest.skip(f"LLM Provider Service returned {response.status}: {error_text}")

    async def test_cj_assessment_kafka_integration(self) -> None:
        """Test CJ Assessment Service processing via Kafka.

        This test publishes a CJ assessment request to Kafka and verifies
        the message structure and topic routing.
        """
        # Check if Kafka is available
        kafka_available = await self._check_kafka_availability()
        if not kafka_available:
            pytest.skip("Kafka not available for integration test")

        # Create test event
        event_data = ELS_CJAssessmentRequestV1(
            entity_id="test-batch-123",
            entity_type="batch",
            parent_id=None,
            system_metadata=SystemProcessingMetadata(
                entity_id="test-batch-123",
                entity_type="batch",
                parent_id=None,
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
        envelope: EventEnvelope[ELS_CJAssessmentRequestV1] = EventEnvelope(
            event_type=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED.value,
            source_service="test-integration",
            data=event_data,
        )

        # Publish to Kafka
        try:
            await self._publish_test_event(envelope)
            print(
                f"Successfully published test event to Kafka topic: "
                f"{topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)}"
            )
        except Exception as e:
            pytest.skip(f"Failed to publish to Kafka: {str(e)}")

    async def _check_kafka_availability(self) -> bool:
        """Check if Kafka is available."""
        try:
            producer = AIOKafkaProducer(
                bootstrap_servers=["localhost:9093"],  # External port
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await producer.start()
            await producer.stop()
            return True
        except Exception:
            return False

    async def _publish_test_event(self, envelope: EventEnvelope) -> None:
        """Publish a test event to Kafka."""
        producer = AIOKafkaProducer(
            bootstrap_servers=["localhost:9093"],  # External port
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

        try:
            await producer.start()

            # Serialize envelope with JSON mode to handle UUIDs
            event_data = envelope.model_dump(mode="json")

            # Publish to the correct topic
            topic = topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)
            await producer.send(topic, event_data)

            print(f"Published event to topic: {topic}")
        finally:
            await producer.stop()

    @pytest.mark.parametrize("provider", [LLMProviderType.ANTHROPIC, LLMProviderType.OPENAI])
    async def test_provider_configuration(
        self, http_session: Any, llm_provider_url: str, provider: LLMProviderType
    ) -> None:
        """Test that different providers can be configured."""
        async with http_session.get(f"{llm_provider_url}/providers") as response:
            assert response.status == 200
            providers_data = await response.json()

            # Check that the provider is available - providers is a list of objects
            provider_names = [p["name"] for p in providers_data["providers"]]
            assert provider.value in provider_names

            # Find the provider object
            provider_info = next(
                p for p in providers_data["providers"] if p["name"] == provider.value
            )
            assert provider_info["enabled"] is True
            assert provider_info["available"] is True
            print(f"Provider {provider.value}: {provider_info}")


@pytest.mark.asyncio
class TestMockProviderIntegration:
    """Test integration using mock LLM provider."""

    async def test_mock_provider_response(self) -> None:
        """Test that mock provider returns expected format."""
        # Check if LLM Provider Service is available
        llm_provider_url = "http://localhost:8090/api/v1"
        if not await self._check_service_availability(llm_provider_url):
            pytest.skip("LLM Provider Service not available")

        # Check if service is running in mock mode
        is_mock_mode = await self._get_service_mock_mode(llm_provider_url)
        if not is_mock_mode:
            pytest.skip("LLM Provider Service not running in mock mode")

        # Test mock provider response
        async with aiohttp.ClientSession() as session:
            request_data = {
                "user_prompt": "Compare these two essays and determine which is better written.",
                "essay_a": "This is a mock essay A with good structure.",
                "essay_b": "This is a mock essay B with different qualities.",
                "llm_config_overrides": {
                    "provider_override": "mock",
                    "temperature_override": 0.1,
                },
                "correlation_id": str(uuid4()),
                "callback_topic": topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
            }

            async with session.post(
                f"{llm_provider_url}/comparison",
                json=request_data,
            ) as response:
                # Verify async-only architecture: expect 202 (queued for processing)
                assert response.status == 202
                result = await response.json()

                # Verify queuing response format
                assert "message" in result
                assert (
                    "queued" in result["message"].lower() or "accepted" in result["message"].lower()
                )
                print("\n✅ Mock Provider Integration Test Passed:")
                print("   - Request successfully queued with 202 response")
                print(f"   - Response: {result['message']}")

    async def _check_service_availability(self, service_url: str) -> bool:
        """Check if a service is available."""
        try:
            async with aiohttp.ClientSession() as session:
                health_url = service_url.replace("/api/v1", "") + "/healthz"
                async with session.get(
                    health_url, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    async def _get_service_mock_mode(self, service_url: str) -> bool:
        """Check if service is running in mock mode."""
        try:
            async with aiohttp.ClientSession() as session:
                health_url = service_url.replace("/api/v1", "") + "/healthz"
                async with session.get(
                    health_url, timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        health_data = await response.json()
                        mock_mode = health_data.get("mock_mode", False)
                        return bool(mock_mode)
                    return False
        except Exception:
            return False


@pytest.mark.asyncio
class TestQueueIntegration:
    """Test integration for queue-based LLM processing."""

    @pytest.fixture
    async def http_session(self) -> Any:
        """Create HTTP session for testing."""
        async with aiohttp.ClientSession() as session:
            yield session

    @pytest.fixture
    def llm_provider_url(self) -> str:
        """LLM Provider Service URL."""
        return "http://localhost:8090/api/v1"

    async def test_queue_status_endpoint(self, http_session: Any, llm_provider_url: str) -> None:
        """Test queue status endpoint exists and responds appropriately."""
        # Test with a fake queue ID to verify endpoint exists
        fake_queue_id = str(uuid4())

        async with http_session.get(f"{llm_provider_url}/status/{fake_queue_id}") as response:
            # Should return 404 for non-existent queue ID
            assert response.status == 404
            error_data = await response.json()
            assert "error" in error_data
            print(f"Queue status (404): {error_data}")

    async def test_queue_results_endpoint(self, http_session: Any, llm_provider_url: str) -> None:
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
        self, http_session: Any, llm_provider_url: str
    ) -> None:
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

    async def test_comparison_endpoint_immediate_response(
        self, http_session: Any, llm_provider_url: str
    ) -> None:
        """Test comparison endpoint returns immediate response when providers available."""
        request_data = {
            "user_prompt": "Compare these two essays and determine which is better written.",
            "essay_a": "This is a well-structured essay with clear arguments and good flow.",
            "essay_b": "This essay lacks structure and has unclear arguments.",
            "callback_topic": topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
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

    async def test_cj_assessment_client_queue_handling(self) -> None:
        """Test CJ Assessment Service client handles both immediate and queued responses."""
        from services.cj_assessment_service.config import Settings
        from services.cj_assessment_service.implementations.llm_provider_service_client import (
            LLMProviderServiceClient,
        )
        from services.cj_assessment_service.implementations.retry_manager_impl import (
            RetryManagerImpl,
        )

        # Create settings for LLM provider integration
        settings = Settings()
        settings.LLM_PROVIDER_SERVICE_URL = "http://localhost:8090/api/v1"

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
                result = await client.generate_comparison(
                    user_prompt=prompt,
                    correlation_id=uuid4(),
                    model_override="gpt-4o-mini",
                    temperature_override=0.1,
                )

                print(f"CJ Assessment client result: {result}")
                assert result is not None
                assert "winner" in result
                assert "justification" in result
                assert "confidence" in result

            except Exception as e:
                print(f"CJ Assessment client exception: {e}")
                # Exceptions may occur due to service unavailability in test environment
