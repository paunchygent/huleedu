"""
End-to-end performance tests.

Tests complete pipeline performance under realistic load patterns
including burst scenarios and mixed workloads. All tests use mock providers to avoid API costs.
"""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest
from dishka import make_async_container

from common_core import LLMProviderType
from common_core.domain_enums import EssayComparisonWinner
from services.llm_provider_service.config import Settings
from services.llm_provider_service.di import LLMProviderServiceProvider

from .conftest import PerformanceMetrics


class TestEndToEndPerformance:
    """Tests for complete end-to-end pipeline performance."""

    @pytest.mark.asyncio
    async def test_end_to_end_load_scenario(self, mock_only_settings: Settings) -> None:
        """Test complete end-to-end load scenario with realistic patterns."""
        from services.llm_provider_service.internal_models import LLMProviderResponse

        metrics = PerformanceMetrics()

        # Simulate realistic load pattern
        request_batches = [
            (10, 0.1),  # 10 requests with 0.1s intervals
            (20, 0.05),  # 20 requests with 0.05s intervals (higher load)
            (5, 0.2),  # 5 requests with 0.2s intervals (cooldown)
        ]

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

                            # Run load test batches
                            total_requests = 0

                            for batch_size, interval in request_batches:
                                batch_tasks = []

                                for i in range(batch_size):

                                    async def make_request(request_id: int) -> None:
                                        start_time = time.perf_counter()

                                        try:
                                            _, error = await orchestrator.perform_comparison(
                                                provider=LLMProviderType.ANTHROPIC,  # Mock
                                                user_prompt="Compare these essays",
                                                essay_a=f"Load test essay A {request_id}",
                                                essay_b=f"Load test essay B {request_id}",
                                                correlation_id=UUID(
                                                    f"00000000-0000-0000-0000-{request_id:012d}"
                                                ),
                                                model="mock-model",
                                            )

                                            response_time = time.perf_counter() - start_time
                                            status_code = 200 if error is None else 500

                                            metrics.add_measurement(response_time, status_code)

                                        except Exception as e:
                                            response_time = time.perf_counter() - start_time
                                            metrics.add_measurement(response_time, 500, str(e))

                                    batch_tasks.append(make_request(total_requests + i))

                                    # Add interval between requests
                                    if i < batch_size - 1:
                                        await asyncio.sleep(interval)

                                # Wait for batch to complete
                                await asyncio.gather(*batch_tasks)
                                total_requests += batch_size

                                # Brief pause between batches
                                await asyncio.sleep(0.5)

                            # Analyze results
                            stats = metrics.get_statistics()

                            print("End-to-end load test results:")
                            print(f"  Total requests: {stats['total_requests']}")
                            success_rate = (
                                stats["successful_requests"] / stats["total_requests"] * 100
                            )
                            print(f"  Success rate: {success_rate:.1f}%")
                            print(f"  Error rate: {stats['error_rate']:.1f}%")
                            print("  Response times:")
                            print(f"    Mean: {stats['response_times']['mean']:.4f}s")
                            print(f"    Median: {stats['response_times']['median']:.4f}s")
                            print(f"    P95: {stats['response_times']['p95']:.4f}s")
                            print(f"    P99: {stats['response_times']['p99']:.4f}s")
                            print(f"  Status codes: {stats['status_codes']}")

                            # Validate performance targets
                            assert stats["response_times"]["p95"] < 0.5  # P95 under 500ms
                            assert (
                                stats["successful_requests"] / stats["total_requests"] >= 0.95
                            )  # 95% success rate
                            assert stats["error_rate"] < 5  # Less than 5% error rate

    @pytest.mark.asyncio
    async def test_mixed_workload_performance(self, mock_only_settings: Settings) -> None:
        """Test performance under mixed workload with different request types."""
        from services.llm_provider_service.internal_models import LLMProviderResponse

        metrics = PerformanceMetrics()

        # Define different workload types
        workloads = [
            ("quick", 15, 0.05, "Quick comparison"),
            ("detailed", 10, 0.1, "Detailed analysis comparison"),
            ("batch", 8, 0.15, "Batch processing comparison"),
        ]

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

                            async def execute_workload(
                                workload_name: str, count: int, delay: float, prompt: str
                            ) -> dict:
                                """Execute a specific workload type."""
                                workload_metrics = PerformanceMetrics()
                                tasks = []

                                async def workload_request(request_id: int) -> None:
                                    start_time = time.perf_counter()
                                    try:
                                        _, error = await orchestrator.perform_comparison(
                                            provider=LLMProviderType.ANTHROPIC,
                                            user_prompt=prompt,
                                            essay_a=f"{workload_name} essay A {request_id}",
                                            essay_b=f"{workload_name} essay B {request_id}",
                                            correlation_id=UUID(
                                                f"44444444-4444-4444-4444-{request_id:012d}"
                                            ),
                                            model="mock-model",
                                        )
                                        response_time = time.perf_counter() - start_time
                                        status_code = 200 if error is None else 500
                                        workload_metrics.add_measurement(response_time, status_code)
                                        metrics.add_measurement(response_time, status_code)
                                    except Exception as e:
                                        response_time = time.perf_counter() - start_time
                                        workload_metrics.add_measurement(response_time, 500, str(e))
                                        metrics.add_measurement(response_time, 500, str(e))

                                # Create tasks with delays
                                for i in range(count):
                                    tasks.append(workload_request(i))
                                    if i < count - 1:
                                        await asyncio.sleep(delay)

                                await asyncio.gather(*tasks)
                                return workload_metrics.get_statistics()

                            # Execute all workloads concurrently
                            workload_results = {}
                            workload_tasks = []

                            for workload_name, count, delay, prompt in workloads:
                                task = execute_workload(workload_name, count, delay, prompt)
                                workload_tasks.append((workload_name, task))

                            # Run all workloads
                            for workload_name, task in workload_tasks:
                                workload_results[workload_name] = await task

                            # Analyze overall mixed workload results
                            overall_stats = metrics.get_statistics()

                            print("Mixed workload performance results:")
                            print(f"  Total requests: {overall_stats['total_requests']}")
                            overall_success_rate = (
                                overall_stats["successful_requests"]
                                / overall_stats["total_requests"]
                                * 100
                            )
                            print(f"  Overall success rate: {overall_success_rate:.1f}%")
                            print(f"  Overall P95: {overall_stats['response_times']['p95']:.4f}s")

                            # Per-workload analysis
                            for workload_name, stats in workload_results.items():
                                if stats:  # Check if stats is not empty
                                    print(f"  {workload_name.capitalize()} workload:")
                                    print(f"    Requests: {stats['total_requests']}")
                                    workload_success_rate = (
                                        stats["successful_requests"] / stats["total_requests"] * 100
                                    )
                                    print(f"    Success rate: {workload_success_rate:.1f}%")
                                    print(f"    Mean time: {stats['response_times']['mean']:.4f}s")

                            # Validate mixed workload performance
                            assert (
                                overall_stats["response_times"]["p95"] < 0.6
                            )  # P95 under 600ms for mixed load
                            assert (
                                overall_stats["successful_requests"]
                                / overall_stats["total_requests"]
                                >= 0.90
                            )  # 90% success rate

    @pytest.mark.asyncio
    async def test_sustained_load_performance(self, mock_only_settings: Settings) -> None:
        """Test performance under sustained load over time."""
        from services.llm_provider_service.internal_models import LLMProviderResponse

        duration_seconds = 30
        requests_per_second = 5
        # total_expected_requests = duration_seconds * requests_per_second  # Unused

        metrics = PerformanceMetrics()

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

                            async def sustained_request_generator() -> None:
                                """Generate requests at sustained rate."""
                                request_id = 0
                                start_time = time.perf_counter()

                                while time.perf_counter() - start_time < duration_seconds:

                                    async def make_sustained_request(req_id: int) -> None:
                                        req_start = time.perf_counter()
                                        try:
                                            _, error = await orchestrator.perform_comparison(
                                                provider=LLMProviderType.ANTHROPIC,
                                                user_prompt="Sustained load test",
                                                essay_a=f"Sustained essay A {req_id}",
                                                essay_b=f"Sustained essay B {req_id}",
                                                correlation_id=UUID(
                                                    f"55555555-5555-5555-5555-{req_id:012d}"
                                                ),
                                                model="mock-model",
                                            )
                                            response_time = time.perf_counter() - req_start
                                            status_code = 200 if error is None else 500
                                            metrics.add_measurement(response_time, status_code)
                                        except Exception as e:
                                            response_time = time.perf_counter() - req_start
                                            metrics.add_measurement(response_time, 500, str(e))

                                    # Start request without waiting for completion
                                    asyncio.create_task(make_sustained_request(request_id))
                                    request_id += 1

                                    # Wait for next request interval
                                    await asyncio.sleep(1.0 / requests_per_second)

                            # Run sustained load test
                            print(
                                f"Starting sustained load test: {requests_per_second} req/s "
                                f"for {duration_seconds}s"
                            )
                            await sustained_request_generator()

                            # Wait a bit for remaining requests to complete
                            await asyncio.sleep(2.0)

                            # Analyze sustained load results
                            stats = metrics.get_statistics()

                            print("Sustained load test results:")
                            print(f"  Duration: {duration_seconds}s")
                            print(f"  Target rate: {requests_per_second} req/s")
                            print(f"  Actual requests: {stats['total_requests']}")
                            actual_rate = stats["total_requests"] / duration_seconds
                            print(f"  Actual rate: {actual_rate:.2f} req/s")
                            sustained_success_rate = (
                                stats["successful_requests"] / stats["total_requests"] * 100
                            )
                            print(f"  Success rate: {sustained_success_rate:.1f}%")
                            print("  Response times:")
                            print(f"    Mean: {stats['response_times']['mean']:.4f}s")
                            print(f"    P95: {stats['response_times']['p95']:.4f}s")
                            print(f"    P99: {stats['response_times']['p99']:.4f}s")

                            # Validate sustained performance
                            actual_rate = stats["total_requests"] / duration_seconds
                            assert (
                                actual_rate >= requests_per_second * 0.8
                            )  # At least 80% of target rate
                            assert stats["response_times"]["p95"] < 1.0  # P95 under 1 second
                            assert (
                                stats["successful_requests"] / stats["total_requests"] >= 0.85
                            )  # 85% success rate
