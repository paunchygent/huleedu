"""
Connection pool performance and efficiency tests.

Tests connection pool management, reuse efficiency, and session optimization
for different LLM providers.
"""

import pytest

from common_core import LLMProviderType
from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.connection_pool_manager_impl import (
    ConnectionPoolManagerImpl,
)


class TestConnectionPoolPerformance:
    """Tests for connection pool efficiency and performance."""

    @pytest.mark.asyncio
    async def test_connection_pool_efficiency(self, mock_only_settings: Settings) -> None:
        """Test connection pool efficiency and reuse."""
        pool_manager = ConnectionPoolManagerImpl(mock_only_settings)

        try:
            # Test connection pool creation
            session1 = await pool_manager.get_session(LLMProviderType.MOCK.value)
            session2 = await pool_manager.get_session(LLMProviderType.MOCK.value)

            # Should reuse the same session
            assert session1 is session2

            # Test different providers get different sessions
            openai_session = await pool_manager.get_session("openai")
            assert openai_session is not session1

            # Test connection statistics
            stats = await pool_manager.get_connection_stats(LLMProviderType.MOCK.value)
            assert "pool_size" in stats
            assert "total_connections" in stats

            # Test health check
            health_status = await pool_manager.health_check_connections()
            assert LLMProviderType.MOCK.value in health_status

            print(f"Connection pool stats: {stats}")
            print(f"Health status: {health_status}")

        finally:
            await pool_manager.cleanup()

    @pytest.mark.asyncio
    async def test_multiple_provider_pool_isolation(self, mock_only_settings: Settings) -> None:
        """Test that different providers have isolated connection pools."""
        pool_manager = ConnectionPoolManagerImpl(mock_only_settings)

        try:
            # Get sessions for different providers
            providers = ["anthropic", "openai", "google", "openrouter"]
            sessions = {}

            for provider in providers:
                session = await pool_manager.get_session(provider)
                sessions[provider] = session

                # Verify each provider gets a unique session
                for other_provider, other_session in sessions.items():
                    if other_provider != provider:
                        assert session is not other_session, (
                            f"{provider} and {other_provider} should have different sessions"
                        )

            # Test session reuse within same provider
            for provider in providers:
                session_reuse = await pool_manager.get_session(provider)
                assert sessions[provider] is session_reuse, f"{provider} should reuse its session"

            # Verify all providers have health status
            health_status = await pool_manager.health_check_connections()
            for provider in providers:
                assert provider in health_status, f"{provider} should be in health status"

            print("Provider isolation test results:")
            for provider in providers:
                stats = await pool_manager.get_connection_stats(provider)
                print(f"  {provider}: {stats}")

        finally:
            await pool_manager.cleanup()

    @pytest.mark.asyncio
    async def test_connection_pool_stress(self, mock_only_settings: Settings) -> None:
        """Test connection pool under stress with rapid session requests."""
        pool_manager = ConnectionPoolManagerImpl(mock_only_settings)

        try:
            import asyncio
            import time

            provider = "anthropic"
            concurrent_requests = 50

            async def get_session_repeatedly(request_id: int) -> float:
                """Get session multiple times and measure time."""
                start_time = time.perf_counter()

                # Make multiple session requests
                for _ in range(5):
                    session = await pool_manager.get_session(provider)
                    assert session is not None

                return time.perf_counter() - start_time

            # Test concurrent session requests
            start_time = time.perf_counter()

            tasks = [get_session_repeatedly(i) for i in range(concurrent_requests)]
            response_times = await asyncio.gather(*tasks)

            total_time = time.perf_counter() - start_time

            # Analyze stress test results
            avg_time = sum(response_times) / len(response_times)
            max_time = max(response_times)
            min_time = min(response_times)

            print("Connection pool stress test:")
            print(f"  Concurrent requests: {concurrent_requests}")
            print(f"  Total time: {total_time:.4f}s")
            print(f"  Average time per request: {avg_time:.4f}s")
            print(f"  Min/Max time: {min_time:.4f}s / {max_time:.4f}s")

            # Verify pool statistics after stress
            stats = await pool_manager.get_connection_stats(provider)
            print(f"  Pool stats after stress: {stats}")

            # Assertions
            assert avg_time < 0.01  # Should be very fast (connection reuse)
            assert max_time < 0.05  # Even worst case should be fast
            assert stats["pool_size"] > 0  # Pool should be active

        finally:
            await pool_manager.cleanup()

    @pytest.mark.asyncio
    async def test_connection_pool_cleanup_efficiency(self, mock_only_settings: Settings) -> None:
        """Test connection pool cleanup and resource management."""
        import time

        pool_manager = ConnectionPoolManagerImpl(mock_only_settings)

        # Create sessions for multiple providers
        providers = ["anthropic", "openai", "google"]

        for provider in providers:
            session = await pool_manager.get_session(provider)
            assert session is not None

        # Verify all sessions are active
        for provider in providers:
            health_status = await pool_manager.health_check_connections()
            assert provider in health_status

        # Test cleanup performance
        cleanup_start = time.perf_counter()
        await pool_manager.cleanup()
        cleanup_time = time.perf_counter() - cleanup_start

        print("Connection pool cleanup:")
        print(f"  Cleanup time: {cleanup_time:.4f}s")
        print(f"  Providers cleaned up: {len(providers)}")

        # Verify cleanup was efficient
        assert cleanup_time < 2.0  # Cleanup should be reasonably fast

        # Verify sessions are properly cleaned up (new pool manager needed to test)
        new_pool_manager = ConnectionPoolManagerImpl(mock_only_settings)
        try:
            # Should create fresh sessions
            for provider in providers:
                session = await new_pool_manager.get_session(provider)
                assert session is not None

        finally:
            await new_pool_manager.cleanup()

    @pytest.mark.asyncio
    async def test_connection_pool_memory_efficiency(self, mock_only_settings: Settings) -> None:
        """Test memory efficiency of connection pools."""
        import gc
        import os

        import psutil

        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        pool_managers = []

        try:
            # Create multiple pool managers (simulating memory pressure)
            for i in range(10):
                pool_manager = ConnectionPoolManagerImpl(mock_only_settings)

                # Create sessions for each manager
                for provider in ["anthropic", "openai", "google"]:
                    await pool_manager.get_session(provider)

                pool_managers.append(pool_manager)

            # Measure memory after creating pools
            mid_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = mid_memory - initial_memory

            print("Memory efficiency test:")
            print(f"  Initial memory: {initial_memory:.2f} MB")
            print(f"  Memory after 10 pools: {mid_memory:.2f} MB")
            print(f"  Memory increase: {memory_increase:.2f} MB")
            print(f"  Memory per pool: {memory_increase / 10:.2f} MB")

            # Cleanup all pools
            for pool_manager in pool_managers:
                await pool_manager.cleanup()

            # Force garbage collection
            gc.collect()

            # Measure memory after cleanup
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_recovered = mid_memory - final_memory

            print(f"  Memory after cleanup: {final_memory:.2f} MB")
            print(f"  Memory recovered: {memory_recovered:.2f} MB")
            print(f"  Recovery rate: {(memory_recovered / memory_increase) * 100:.1f}%")

            # Assertions for memory efficiency
            assert memory_increase < 50  # Should not use excessive memory
            assert memory_recovered > (memory_increase * 0.5)  # Should recover most memory

        finally:
            # Ensure cleanup even if test fails
            for pool_manager in pool_managers:
                try:
                    await pool_manager.cleanup()
                except Exception:
                    pass

    @pytest.mark.asyncio
    async def test_connection_pool_concurrent_cleanup(self, mock_only_settings: Settings) -> None:
        """Test concurrent access during cleanup scenarios."""
        import asyncio
        import time

        pool_manager = ConnectionPoolManagerImpl(mock_only_settings)

        async def concurrent_session_access(delay: float) -> bool:
            """Try to access sessions with delay."""
            try:
                await asyncio.sleep(delay)
                session = await pool_manager.get_session("anthropic")
                return session is not None
            except Exception:
                return False

        async def delayed_cleanup(delay: float) -> float:
            """Cleanup after delay and measure time."""
            await asyncio.sleep(delay)
            start_time = time.perf_counter()
            await pool_manager.cleanup()
            return time.perf_counter() - start_time

        try:
            # Create initial session
            initial_session = await pool_manager.get_session("anthropic")
            assert initial_session is not None

            # Start concurrent access tasks with various delays
            access_tasks = [
                concurrent_session_access(0.1),
                concurrent_session_access(0.2),
                concurrent_session_access(0.3),
            ]

            # Start cleanup task
            cleanup_task = delayed_cleanup(0.15)

            # Run all tasks concurrently
            access_results = await asyncio.gather(*access_tasks, return_exceptions=True)
            cleanup_time = await cleanup_task

            # Analyze results
            successful_accesses = sum(1 for result in access_results if result is True)
            failed_accesses = len(access_results) - successful_accesses

            print("Concurrent cleanup test:")
            print(f"  Successful accesses: {successful_accesses}")
            print(f"  Failed accesses: {failed_accesses}")
            print(f"  Cleanup time: {cleanup_time:.4f}s")

            # Should handle concurrent access gracefully
            assert cleanup_time < 1.0  # Cleanup should be fast even with concurrent access

        except Exception:
            # Ensure cleanup if test fails
            try:
                await pool_manager.cleanup()
            except Exception:
                pass
