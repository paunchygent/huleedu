"""
Concurrent request performance tests.

Tests concurrent request handling capabilities and validates
P95 response time targets under load. All tests use mock providers to avoid API costs.
"""

import asyncio
import statistics
import time
from typing import Tuple
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest
from dishka import make_async_container

from common_core import LLMProviderType
from common_core.domain_enums import EssayComparisonWinner
from services.llm_provider_service.config import Settings
from services.llm_provider_service.di import LLMProviderServiceProvider


class TestConcurrentPerformance:
    """Tests for concurrent request handling performance."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_performance(self, mock_only_settings: Settings) -> None:
        """Test concurrent request performance with 50 parallel requests."""
        from services.llm_provider_service.internal_models import LLMProviderResponse

        concurrent_requests = 50

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
                        container = make_async_container(LLMProviderServiceProvider())

                        async with container() as request_container:
                            from services.llm_provider_service.protocols import (
                                LLMOrchestratorProtocol,
                            )

                            orchestrator = await request_container.get(LLMOrchestratorProtocol)

                            async def make_request(request_id: int) -> Tuple[float, bool]:
                                """Make a single request and return response time and success."""
                                start_time = time.perf_counter()

                                try:
                                    _, error = await orchestrator.perform_comparison(
                                        provider=LLMProviderType.ANTHROPIC,  # Mock implementation
                                        user_prompt="Compare these essays",
                                        essay_a=f"Sample essay A content {request_id}",
                                        essay_b=f"Sample essay B content {request_id}",
                                        correlation_id=UUID(
                                            f"00000000-0000-0000-0000-{request_id:012d}"
                                        ),
                                        model="mock-model",
                                    )

                                    response_time = time.perf_counter() - start_time
                                    return response_time, error is None
                                except Exception:
                                    response_time = time.perf_counter() - start_time
                                    return response_time, False

                            # Run concurrent requests
                            start_time = time.perf_counter()

                            tasks = [make_request(i) for i in range(concurrent_requests)]
                            results = await asyncio.gather(*tasks)

                            total_time = time.perf_counter() - start_time

                            # Analyze results
                            response_times = [r[0] for r in results]
                            successes = [r[1] for r in results]

                            p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
                            success_rate = sum(successes) / len(successes) * 100

                            print("Concurrent requests performance:")
                            print(f"  Total requests: {concurrent_requests}")
                            print(f"  Total time: {total_time:.4f}s")
                            print(f"  Requests per second: {concurrent_requests / total_time:.2f}")
                            print(f"  Success rate: {success_rate:.1f}%")
                            print(f"  P95 response time: {p95_time:.4f}s")
                            print(f"  Mean response time: {statistics.mean(response_times):.4f}s")

                            # Assertions
                            assert success_rate >= 95  # At least 95% success rate
                            assert p95_time < 0.5  # P95 should be under 500ms
                            assert (
                                statistics.mean(response_times) < 0.2
                            )  # Mean should be under 200ms

    @pytest.mark.asyncio
    async def test_high_concurrency_stress(self, mock_only_settings: Settings) -> None:
        """Test higher concurrency stress with 100 parallel requests."""
        from services.llm_provider_service.internal_models import LLMProviderResponse

        concurrent_requests = 100

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

                            async def make_request(request_id: int) -> Tuple[float, bool]:
                                start_time = time.perf_counter()
                                try:
                                    _, error = await orchestrator.perform_comparison(
                                        provider=LLMProviderType.ANTHROPIC,
                                        user_prompt="Stress test comparison",
                                        essay_a=f"Stress essay A {request_id}",
                                        essay_b=f"Stress essay B {request_id}",
                                        correlation_id=UUID(
                                            f"11111111-1111-1111-1111-{request_id:012d}"
                                        ),
                                        model="mock-model",
                                    )
                                    response_time = time.perf_counter() - start_time
                                    return response_time, error is None
                                except Exception:
                                    response_time = time.perf_counter() - start_time
                                    return response_time, False

                            # Run stress test
                            start_time = time.perf_counter()
                            tasks = [make_request(i) for i in range(concurrent_requests)]
                            results = await asyncio.gather(*tasks)
                            total_time = time.perf_counter() - start_time

                            response_times = [r[0] for r in results]
                            successes = [r[1] for r in results]

                            p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
                            p99_time = sorted(response_times)[int(len(response_times) * 0.99)]
                            success_rate = sum(successes) / len(successes) * 100

                            print("High concurrency stress test:")
                            print(f"  Concurrent requests: {concurrent_requests}")
                            print(f"  Total time: {total_time:.4f}s")
                            print(f"  Throughput: {concurrent_requests / total_time:.2f} req/s")
                            print(f"  Success rate: {success_rate:.1f}%")
                            print(f"  P95: {p95_time:.4f}s, P99: {p99_time:.4f}s")
                            print(f"  Mean: {statistics.mean(response_times):.4f}s")

                            # Stress test assertions (slightly relaxed)
                            assert success_rate >= 90  # At least 90% success under stress
                            assert p95_time < 1.0  # P95 under 1 second under stress
                            assert statistics.mean(response_times) < 0.5  # Mean under 500ms

    @pytest.mark.asyncio
    async def test_concurrent_burst_pattern(self, mock_only_settings: Settings) -> None:
        """Test burst pattern: multiple waves of concurrent requests."""
        from services.llm_provider_service.internal_models import LLMProviderResponse

        burst_size = 25
        burst_count = 3
        burst_interval = 0.5  # 500ms between bursts

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

                            all_response_times = []
                            all_successes = []

                            async def make_burst_request(
                                burst_id: int, request_id: int
                            ) -> Tuple[float, bool]:
                                start_time = time.perf_counter()
                                try:
                                    _, error = await orchestrator.perform_comparison(
                                        provider=LLMProviderType.ANTHROPIC,
                                        user_prompt="Burst test comparison",
                                        essay_a=f"Burst {burst_id} essay A {request_id}",
                                        essay_b=f"Burst {burst_id} essay B {request_id}",
                                        correlation_id=UUID(
                                            f"22222222-2222-{burst_id:04d}-2222-{request_id:012d}"
                                        ),
                                        model="mock-model",
                                    )
                                    response_time = time.perf_counter() - start_time
                                    return response_time, error is None
                                except Exception:
                                    response_time = time.perf_counter() - start_time
                                    return response_time, False

                            # Execute burst pattern
                            total_start_time = time.perf_counter()

                            for burst_id in range(burst_count):
                                print(f"  Executing burst {burst_id + 1}/{burst_count}...")

                                # Create tasks for this burst
                                burst_tasks = [
                                    make_burst_request(burst_id, i) for i in range(burst_size)
                                ]

                                # Execute burst concurrently
                                burst_results = await asyncio.gather(*burst_tasks)

                                # Collect results
                                burst_times = [r[0] for r in burst_results]
                                burst_successes = [r[1] for r in burst_results]

                                all_response_times.extend(burst_times)
                                all_successes.extend(burst_successes)

                                print(
                                    f"    Burst {burst_id + 1} P95: "
                                    f"{sorted(burst_times)[int(len(burst_times) * 0.95)]:.4f}s"
                                )

                                # Wait before next burst (except for last burst)
                                if burst_id < burst_count - 1:
                                    await asyncio.sleep(burst_interval)

                            total_time = time.perf_counter() - total_start_time

                            # Analyze overall results
                            p95_time = sorted(all_response_times)[
                                int(len(all_response_times) * 0.95)
                            ]
                            success_rate = sum(all_successes) / len(all_successes) * 100
                            total_requests = burst_size * burst_count

                            print("Burst pattern results:")
                            print(
                                f"  Total requests: {total_requests} "
                                f"({burst_count} bursts of {burst_size})"
                            )
                            print(f"  Total time: {total_time:.4f}s")
                            print(f"  Overall success rate: {success_rate:.1f}%")
                            print(f"  Overall P95: {p95_time:.4f}s")
                            print(f"  Overall mean: {statistics.mean(all_response_times):.4f}s")

                            # Assertions
                            assert success_rate >= 95  # Should handle bursts well
                            assert p95_time < 0.6  # P95 should remain reasonable during bursts
                            assert statistics.mean(all_response_times) < 0.3  # Mean should stay low

    @pytest.mark.asyncio
    async def test_concurrent_mixed_providers(self, mock_only_settings: Settings) -> None:
        """Test concurrent requests using different mock providers."""
        from services.llm_provider_service.internal_models import LLMProviderResponse

        requests_per_provider = 10
        providers = [
            LLMProviderType.ANTHROPIC,
            LLMProviderType.OPENAI,
            LLMProviderType.GOOGLE,
        ]

        with patch(
            "services.llm_provider_service.implementations.mock_provider_impl.MockProviderImpl"
        ) as MockProviderClass:
            mock_provider_instance = AsyncMock()
            mock_response = LLMProviderResponse(
                winner=EssayComparisonWinner.ESSAY_A,
                justification="Essay A is better structured",
                confidence=0.85,
                provider=LLMProviderType.ANTHROPIC,  # Will be overridden by orchestrator
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

                            async def make_provider_request(
                                provider: LLMProviderType, request_id: int
                            ) -> Tuple[float, bool, str]:
                                start_time = time.perf_counter()
                                try:
                                    _, error = await orchestrator.perform_comparison(
                                        provider=provider,
                                        user_prompt="Mixed provider test",
                                        essay_a=f"Essay A for {provider.value} {request_id}",
                                        essay_b=f"Essay B for {provider.value} {request_id}",
                                        correlation_id=UUID(
                                            f"33333333-3333-3333-3333-{request_id:012d}"
                                        ),
                                        model="mock-model",
                                    )
                                    response_time = time.perf_counter() - start_time
                                    return response_time, error is None, provider.value
                                except Exception:
                                    response_time = time.perf_counter() - start_time
                                    return response_time, False, provider.value

                            # Create mixed provider tasks
                            all_tasks = []
                            for provider in providers:
                                for i in range(requests_per_provider):
                                    all_tasks.append(make_provider_request(provider, i))

                            # Execute all requests concurrently
                            start_time = time.perf_counter()
                            results = await asyncio.gather(*all_tasks)
                            total_time = time.perf_counter() - start_time

                            # Analyze results by provider
                            provider_results: dict[str, list[tuple[float, bool]]] = {
                                provider.value: [] for provider in providers
                            }
                            for response_time, success, provider_name in results:
                                provider_results[provider_name].append((response_time, success))

                            total_requests = len(results)
                            all_response_times = [r[0] for r in results]
                            all_successes = [r[1] for r in results]

                            print("Mixed provider concurrent test:")
                            print(f"  Total requests: {total_requests}")
                            print(f"  Total time: {total_time:.4f}s")
                            print(
                                f"  Overall success rate: "
                                f"{sum(all_successes) / len(all_successes) * 100:.1f}%"
                            )
                            p95_index = int(len(all_response_times) * 0.95)
                            p95_time = sorted(all_response_times)[p95_index]
                            print(f"  Overall P95: {p95_time:.4f}s")

                            for provider_name, provider_data in provider_results.items():
                                provider_times = [r[0] for r in provider_data]
                                provider_successes = [r[1] for r in provider_data]
                                success_rate = (
                                    sum(provider_successes) / len(provider_successes) * 100
                                )
                                mean_time = statistics.mean(provider_times)
                                print(
                                    f"  {provider_name}: {success_rate:.1f}% success, "
                                    f"{mean_time:.4f}s mean"
                                )

                            # Assertions
                            overall_success_rate = sum(all_successes) / len(all_successes) * 100
                            assert overall_success_rate >= 95
                            assert statistics.mean(all_response_times) < 0.3
