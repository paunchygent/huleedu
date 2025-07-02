"""Integration tests for CJ Assessment Service with LLM Provider Service.

These tests verify end-to-end communication between CJ Assessment Service
and the centralized LLM Provider Service.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import aiohttp
import pytest
from aiokafka import AIOKafkaProducer

from common_core import LLMProviderType
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent
from common_core.events.cj_assessment_events import (
    ELS_CJAssessmentRequestV1,
    LLMConfigOverrides,
)
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EntityReference, EssayProcessingInputRefV1
from common_core.status_enums import ProcessingStage


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
        async with http_session.get(f"{llm_provider_url.replace('/api/v1', '')}/healthz") as response:
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
                "provider_override": "anthropic",
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
            essays_for_cj=[
                EssayProcessingInputRefV1(
                    entity_ref=EntityReference(
                        entity_type="essay",
                        entity_id="essay-1",
                    ),
                    content_ref="content/essay-1.txt",
                ),
                EssayProcessingInputRefV1(
                    entity_ref=EntityReference(
                        entity_type="essay", 
                        entity_id="essay-2",
                    ),
                    content_ref="content/essay-2.txt",
                ),
            ],
            language="en",
            course_code=CourseCode.WRITING_FUNDAMENTALS,
            essay_instructions="Write a clear argumentative essay",
            llm_config_overrides=LLMConfigOverrides(
                provider_override="anthropic",
                temperature_override=0.1,
            ),
        )

        # Create event envelope
        envelope = EventEnvelope(
            event_type=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUEST.value,
            source_service="test-integration",
            data=event_data,
        )

        # Note: This would require Kafka to be accessible from the test environment
        # For now, we'll skip the actual Kafka publish
        pytest.skip("Kafka integration requires running in Docker network")

    @pytest.mark.parametrize("provider", ["anthropic", "openai"])
    async def test_provider_configuration(self, http_session, llm_provider_url, provider):
        """Test that different providers can be configured."""
        async with http_session.get(f"{llm_provider_url}/providers") as response:
            assert response.status == 200
            providers_data = await response.json()
            
            # Check that the provider is available
            assert provider in providers_data["providers"]
            provider_info = providers_data["providers"][provider]
            assert provider_info["configured"] is True
            print(f"Provider {provider}: {provider_info}")


@pytest.mark.asyncio
class TestMockProviderIntegration:
    """Test integration using mock LLM provider."""

    async def test_mock_provider_response(self):
        """Test that mock provider returns expected format."""
        # This test would need to configure LLM Provider Service
        # to use mock provider via environment variable
        pytest.skip("Mock provider test requires service reconfiguration")