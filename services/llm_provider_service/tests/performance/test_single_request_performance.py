"""
Single request performance baseline tests.

Tests individual request performance to establish baseline metrics
for the LLM Provider Service. All tests use mock providers to avoid API costs.
"""

import time
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest
from dishka import make_async_container

from common_core import LLMProviderType
from common_core.domain_enums import EssayComparisonWinner
from services.llm_provider_service.config import Settings
from services.llm_provider_service.di import LLMProviderServiceProvider


class TestSingleRequestPerformance:
    """Tests for single request performance baseline."""

    @pytest.mark.asyncio
    async def test_single_request_performance(self, mock_only_settings: Settings) -> None:
        """Test single request performance baseline."""
        from services.llm_provider_service.internal_models import LLMProviderResponse

        # Mock the MockProviderImpl where it's actually imported
        with patch(
            "services.llm_provider_service.implementations.mock_provider_impl.MockProviderImpl"
        ) as MockProviderClass:
            # Create a mock instance that returns proper response
            mock_provider_instance = AsyncMock()
            mock_response = LLMProviderResponse(
                winner=EssayComparisonWinner.ESSAY_A,
                justification="Essay A is better structured",
                confidence=0.85,
                provider=LLMProviderType.ANTHROPIC,
                model="mock-model",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                raw_response={"mock": "response"},
            )
            mock_provider_instance.generate_comparison = AsyncMock(
                return_value=(mock_response, None)
            )

            # Make the class return our instance
            MockProviderClass.return_value = mock_provider_instance

            # Mock Kafka to prevent connection attempts
            with patch("services.llm_provider_service.di.KafkaBus") as mock_kafka_bus:
                mock_kafka_instance = AsyncMock()
                mock_kafka_instance.start = AsyncMock()
                mock_kafka_instance.stop = AsyncMock()
                mock_kafka_bus.return_value = mock_kafka_instance

                # Mock Redis to prevent connection attempts
                with patch("services.llm_provider_service.di.RedisClient") as mock_redis_client:
                    mock_redis_instance = AsyncMock()
                    mock_redis_instance.start = AsyncMock()
                    mock_redis_instance.stop = AsyncMock()
                    # Fix the pipeline mock - it should return a regular Mock, not AsyncMock
                    mock_client = Mock()  # Regular Mock for the client
                    mock_pipeline = Mock()  # Regular Mock for the pipeline
                    mock_pipeline.execute = AsyncMock(return_value=[])  # Only execute is async
                    mock_client.pipeline.return_value = mock_pipeline
                    mock_redis_instance.client = mock_client
                    mock_redis_client.return_value = mock_redis_instance

                    # Patch the settings module to use our test settings
                    with patch("services.llm_provider_service.di.settings", mock_only_settings):
                        # Create DI container
                        container = make_async_container(LLMProviderServiceProvider())

                        async with container() as request_container:
                            from services.llm_provider_service.protocols import (
                                LLMOrchestratorProtocol,
                            )

                            orchestrator = await request_container.get(LLMOrchestratorProtocol)

                            # Measure single request performance
                            start_time = time.perf_counter()

                            result, error = await orchestrator.perform_comparison(
                                provider=LLMProviderType.ANTHROPIC,
                                user_prompt="Compare these essays",
                                essay_a="Sample essay A content",
                                essay_b="Sample essay B content",
                                correlation_id=UUID("00000000-0000-0000-0000-000000000001"),
                                model="mock-model",
                            )

                            response_time = time.perf_counter() - start_time

                            # Assertions
                            assert error is None
                            assert result is not None
                            assert response_time < 0.1  # Should be under 100ms for mock

                            print(f"Single request performance: {response_time:.4f}s")

    @pytest.mark.asyncio
    async def test_multiple_sequential_requests(self, mock_only_settings: Settings) -> None:
        """Test performance consistency across multiple sequential requests."""
        from services.llm_provider_service.internal_models import LLMProviderResponse

        request_count = 10
        response_times = []

        with patch(
            "services.llm_provider_service.implementations.mock_provider_impl.MockProviderImpl"
        ) as MockProviderClass:
            mock_provider_instance = AsyncMock()
            mock_response = LLMProviderResponse(
                winner=EssayComparisonWinner.ESSAY_A,
                justification="Essay A is better structured",
                confidence=0.85,
                provider=LLMProviderType.ANTHROPIC,
                model="mock-model",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                raw_response={"mock": "response"},
            )
            mock_provider_instance.generate_comparison = AsyncMock(
                return_value=(mock_response, None)
            )
            MockProviderClass.return_value = mock_provider_instance

            with patch("services.llm_provider_service.di.KafkaBus") as mock_kafka_bus:
                mock_kafka_instance = AsyncMock()
                mock_kafka_instance.start = AsyncMock()
                mock_kafka_instance.stop = AsyncMock()
                mock_kafka_bus.return_value = mock_kafka_instance

                with patch("services.llm_provider_service.di.RedisClient") as mock_redis_client:
                    mock_redis_instance = AsyncMock()
                    mock_redis_instance.start = AsyncMock()
                    mock_redis_instance.stop = AsyncMock()
                    mock_client = Mock()
                    mock_pipeline = Mock()
                    mock_pipeline.execute = AsyncMock(return_value=[])
                    mock_client.pipeline.return_value = mock_pipeline
                    mock_redis_instance.client = mock_client
                    mock_redis_client.return_value = mock_redis_instance

                    with patch("services.llm_provider_service.di.settings", mock_only_settings):
                        container = make_async_container(LLMProviderServiceProvider())

                        async with container() as request_container:
                            from services.llm_provider_service.protocols import (
                                LLMOrchestratorProtocol,
                            )

                            orchestrator = await request_container.get(LLMOrchestratorProtocol)

                            # Make sequential requests
                            for i in range(request_count):
                                start_time = time.perf_counter()

                                result, error = await orchestrator.perform_comparison(
                                    provider=LLMProviderType.ANTHROPIC,
                                    user_prompt="Compare these essays",
                                    essay_a=f"Sample essay A content {i}",
                                    essay_b=f"Sample essay B content {i}",
                                    correlation_id=UUID(f"00000000-0000-0000-0000-{i:012d}"),
                                    model="mock-model",
                                )

                                response_time = time.perf_counter() - start_time
                                response_times.append(response_time)

                                # Verify each request succeeds
                                assert error is None
                                assert result is not None

                            # Analyze performance consistency
                            avg_time = sum(response_times) / len(response_times)
                            max_time = max(response_times)
                            min_time = min(response_times)

                            print("Sequential requests performance:")
                            print(f"  Requests: {request_count}")
                            print(f"  Average: {avg_time:.4f}s")
                            print(f"  Min: {min_time:.4f}s")
                            print(f"  Max: {max_time:.4f}s")
                            print(f"  Variance: {max_time - min_time:.4f}s")

                            # Assertions for consistency
                            assert avg_time < 0.1  # Average should be under 100ms
                            assert max_time < 0.2  # No request should take more than 200ms
                            assert (max_time - min_time) < 0.1  # Variance should be low

    @pytest.mark.asyncio
    async def test_request_overhead_analysis(self, mock_only_settings: Settings) -> None:
        """Analyze request overhead by testing minimal mock provider calls."""
        from services.llm_provider_service.internal_models import LLMProviderResponse

        # Test with extremely fast mock to measure overhead
        with patch(
            "services.llm_provider_service.implementations.mock_provider_impl.MockProviderImpl"
        ) as MockProviderClass:
            mock_provider_instance = AsyncMock()
            # Simulate instant response
            mock_response = LLMProviderResponse(
                winner=EssayComparisonWinner.ESSAY_A,
                justification="Instant response",
                confidence=0.9,
                provider=LLMProviderType.ANTHROPIC,
                model="mock-model",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                raw_response={"instant": True},
            )
            mock_provider_instance.generate_comparison = AsyncMock(
                return_value=(mock_response, None)
            )
            MockProviderClass.return_value = mock_provider_instance

            with patch("services.llm_provider_service.di.KafkaBus") as mock_kafka_bus:
                mock_kafka_instance = AsyncMock()
                mock_kafka_instance.start = AsyncMock()
                mock_kafka_instance.stop = AsyncMock()
                mock_kafka_bus.return_value = mock_kafka_instance

                with patch("services.llm_provider_service.di.RedisClient") as mock_redis_client:
                    mock_redis_instance = AsyncMock()
                    mock_redis_instance.start = AsyncMock()
                    mock_redis_instance.stop = AsyncMock()
                    mock_client = Mock()
                    mock_pipeline = Mock()
                    mock_pipeline.execute = AsyncMock(return_value=[])
                    mock_client.pipeline.return_value = mock_pipeline
                    mock_redis_instance.client = mock_client
                    mock_redis_client.return_value = mock_redis_instance

                    with patch("services.llm_provider_service.di.settings", mock_only_settings):
                        container = make_async_container(LLMProviderServiceProvider())

                        async with container() as request_container:
                            from services.llm_provider_service.protocols import (
                                LLMOrchestratorProtocol,
                            )

                            orchestrator = await request_container.get(LLMOrchestratorProtocol)

                            # Warm up (eliminate cold start effects)
                            await orchestrator.perform_comparison(
                                provider=LLMProviderType.ANTHROPIC,
                                user_prompt="Warmup",
                                essay_a="Warmup A",
                                essay_b="Warmup B",
                                correlation_id=UUID("00000000-0000-0000-0000-000000000000"),
                                model="mock-model",
                            )

                            # Measure minimal overhead
                            overhead_measurements = []
                            for i in range(5):
                                start_time = time.perf_counter()

                                result, error = await orchestrator.perform_comparison(
                                    provider=LLMProviderType.ANTHROPIC,
                                    user_prompt="Test",
                                    essay_a="A",
                                    essay_b="B",
                                    correlation_id=UUID(f"00000000-0000-0000-0000-{i:012d}"),
                                    model="mock-model",
                                )

                                overhead_time = time.perf_counter() - start_time
                                overhead_measurements.append(overhead_time)

                                assert error is None
                                assert result is not None

                            avg_overhead = sum(overhead_measurements) / len(overhead_measurements)
                            min_overhead = min(overhead_measurements)

                            print("Request overhead analysis:")
                            print(f"  Average overhead: {avg_overhead:.6f}s")
                            print(f"  Minimum overhead: {min_overhead:.6f}s")
                            print(
                                f"  Overhead measurements: "
                                f"{[f'{t:.6f}' for t in overhead_measurements]}"
                            )

                            # Assert reasonable overhead (infrastructure should add minimal latency)
                            assert avg_overhead < 0.05  # Average overhead should be under 50ms
                            assert min_overhead < 0.02  # Minimum should be under 20ms
