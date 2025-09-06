"""Unit tests for RateLimiterImpl Redis-based sliding window rate limiting implementation.

Tests focus on behavioral validation of rate limiting enforcement, sliding window calculations,
threshold management, concurrent request handling, and Swedish character support in identifiers.
Following Rule 075 methodology with AsyncMock(spec=Protocol) patterns.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.entitlements_service.implementations.rate_limiter_impl import RateLimiterImpl
from services.entitlements_service.protocols import PolicyLoaderProtocol, RateLimitCheck


class TestRateLimiterImpl:
    """Tests for Redis-based sliding window rate limiter implementation."""

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create mock Redis client following AtomicRedisClientProtocol."""
        mock_client = AsyncMock(spec=AtomicRedisClientProtocol)
        # Pipeline has mixed sync/async interface - only execute() is async
        mock_pipeline = MagicMock()  # Base mock for sync methods
        mock_pipeline.zremrangebyscore = MagicMock()  # Sync method
        mock_pipeline.zcard = MagicMock()  # Sync method
        mock_pipeline.zadd = MagicMock()  # Sync method
        mock_pipeline.execute = AsyncMock(return_value=[None, 0])  # Only this is async
        mock_client.create_transaction_pipeline.return_value = mock_pipeline
        return mock_client

    @pytest.fixture
    def mock_policy_loader(self) -> AsyncMock:
        """Create mock policy loader with default rate limit configurations."""
        mock_loader = AsyncMock(spec=PolicyLoaderProtocol)
        # Default return for most tests: 10 operations per 60 seconds
        mock_loader.get_rate_limit.return_value = (10, 60)
        return mock_loader

    @pytest.fixture
    def rate_limiter_enabled(
        self,
        mock_redis_client: AsyncMock,
        mock_policy_loader: AsyncMock,
    ) -> RateLimiterImpl:
        """Create enabled rate limiter with all dependencies mocked."""
        return RateLimiterImpl(
            redis_client=mock_redis_client,
            policy_loader=mock_policy_loader,
            enabled=True,
        )

    @pytest.fixture
    def rate_limiter_disabled(
        self,
        mock_redis_client: AsyncMock,
        mock_policy_loader: AsyncMock,
    ) -> RateLimiterImpl:
        """Create disabled rate limiter for testing disabled behavior."""
        return RateLimiterImpl(
            redis_client=mock_redis_client,
            policy_loader=mock_policy_loader,
            enabled=False,
        )

    class TestRateLimitEnforcement:
        """Tests for rate limit enforcement behaviors."""

        @pytest.mark.asyncio
        @pytest.mark.parametrize(
            "current_count, limit, amount, expected_allowed, description",
            [
                # Within limits scenarios
                (0, 10, 1, True, "First request should be allowed"),
                (5, 10, 1, True, "Under limit should be allowed"),
                (9, 10, 1, True, "At threshold should be allowed"),
                (8, 10, 2, True, "Multiple operations under limit allowed"),
                # At limits scenarios
                (10, 10, 1, False, "At limit should be denied"),
                (9, 10, 2, False, "Would exceed limit should be denied"),
                (15, 10, 1, False, "Over limit should be denied"),
                # Edge cases
                (0, 1, 1, True, "Single operation limit allows first request"),
                (1, 1, 1, False, "Single operation limit denies second request"),
                (999, 1000, 1, True, "High limits work correctly"),
                (1000, 1000, 1, False, "High limit enforcement works"),
            ],
        )
        async def test_rate_limit_enforcement_decisions(
            self,
            rate_limiter_enabled: RateLimiterImpl,
            mock_redis_client: AsyncMock,
            mock_policy_loader: AsyncMock,
            current_count: int,
            limit: int,
            amount: int,
            expected_allowed: bool,
            description: str,
        ) -> None:
            """Test rate limit enforcement decisions for various scenarios."""
            # Arrange
            subject_id = "test-user-123"
            metric = "ai_feedback"
            window_seconds = 60

            # Configure policy loader for this specific test case
            mock_policy_loader.get_rate_limit.return_value = (limit, window_seconds)

            # Configure Redis pipeline to return current count
            mock_pipeline = mock_redis_client.create_transaction_pipeline.return_value
            mock_pipeline.execute.return_value = [None, current_count]

            # Act
            result = await rate_limiter_enabled.check_rate_limit(subject_id, metric, amount)

            # Assert
            assert isinstance(result, RateLimitCheck)
            assert result.allowed == expected_allowed, description
            assert result.limit == limit
            assert result.window_seconds == window_seconds
            assert result.current_count == current_count

            # Verify Redis operations
            mock_redis_client.create_transaction_pipeline.assert_called_once()
            mock_pipeline.zremrangebyscore.assert_called_once()
            mock_pipeline.zcard.assert_called_once()
            mock_pipeline.execute.assert_called_once()

        @pytest.mark.asyncio
        @pytest.mark.parametrize(
            "subject_id, expected_key",
            [
                ("user-123", "rate_limit:user-123:ai_feedback"),
                ("användare-åäö", "rate_limit:användare-åäö:ai_feedback"),
                ("organisation-ÅÄÖ", "rate_limit:organisation-ÅÄÖ:ai_feedback"),
                ("user:with:colons", "rate_limit:user:with:colons:ai_feedback"),
                ("complex-åäö-ÅÄÖ-123", "rate_limit:complex-åäö-ÅÄÖ-123:ai_feedback"),
            ],
        )
        async def test_rate_limit_key_generation_with_swedish_characters(
            self,
            rate_limiter_enabled: RateLimiterImpl,
            mock_redis_client: AsyncMock,
            subject_id: str,
            expected_key: str,
        ) -> None:
            """Test Redis key generation preserves Swedish characters correctly."""
            # Arrange
            metric = "ai_feedback"
            mock_pipeline = mock_redis_client.create_transaction_pipeline.return_value
            mock_pipeline.execute.return_value = [None, 0]

            # Act
            await rate_limiter_enabled.check_rate_limit(subject_id, metric, 1)

            # Assert - Verify the key used in Redis operations
            mock_pipeline.zremrangebyscore.assert_called_once()
            call_args = mock_pipeline.zremrangebyscore.call_args
            redis_key = call_args[0][0]  # First positional argument
            assert redis_key == expected_key

        @pytest.mark.asyncio
        async def test_disabled_rate_limiter_allows_all_requests(
            self,
            rate_limiter_disabled: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Test disabled rate limiter allows all requests without Redis operations."""
            # Arrange
            subject_id = "test-user"
            metric = "ai_feedback"
            amount = 1000  # Intentionally high amount

            # Act
            result = await rate_limiter_disabled.check_rate_limit(subject_id, metric, amount)

            # Assert
            assert result.allowed is True
            assert result.limit == 0
            assert result.window_seconds == 0
            assert result.current_count == 0

            # Verify no Redis operations performed
            mock_redis_client.create_transaction_pipeline.assert_not_called()

    class TestSlidingWindowBehavior:
        """Tests for sliding window time-based calculations."""

        @pytest.mark.asyncio
        @pytest.mark.parametrize(
            "metric, expected_limit, expected_window",
            [
                ("ai_feedback", 10, 60),
                ("essay_scoring", 5, 300),
                ("svenska_bedömning", 20, 120),  # Swedish metric
            ],
        )
        async def test_different_window_configurations(
            self,
            rate_limiter_enabled: RateLimiterImpl,
            mock_redis_client: AsyncMock,
            mock_policy_loader: AsyncMock,
            metric: str,
            expected_limit: int,
            expected_window: int,
        ) -> None:
            """Test rate limiter handles different window configurations correctly."""
            # Arrange
            subject_id = "multi-metric-user"
            mock_policy_loader.get_rate_limit.return_value = (expected_limit, expected_window)
            mock_pipeline = mock_redis_client.create_transaction_pipeline.return_value
            mock_pipeline.execute.return_value = [None, 1]

            # Act
            result = await rate_limiter_enabled.check_rate_limit(subject_id, metric, 1)

            # Assert
            assert result.limit == expected_limit
            assert result.window_seconds == expected_window
            assert result.allowed is True  # Under limit

        @pytest.mark.asyncio
        async def test_no_limit_configured_behavior(
            self,
            rate_limiter_enabled: RateLimiterImpl,
            mock_policy_loader: AsyncMock,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Test behavior when no rate limit is configured for a metric."""
            # Arrange - Configure no limit (0, 0)
            subject_id = "unlimited-user"
            metric = "unlimited_metric"
            mock_policy_loader.get_rate_limit.return_value = (0, 0)

            # Act
            result = await rate_limiter_enabled.check_rate_limit(subject_id, metric, 100)

            # Assert
            assert result.allowed is True
            assert result.limit == 0
            assert result.window_seconds == 0
            assert result.current_count == 0

            # Verify no Redis operations for unlimited metrics
            mock_redis_client.create_transaction_pipeline.assert_not_called()

    class TestUsageRecording:
        """Tests for usage recording functionality."""

        @pytest.mark.asyncio
        async def test_record_usage_adds_timestamped_entries(
            self,
            rate_limiter_enabled: RateLimiterImpl,
            mock_redis_client: AsyncMock,
            mock_policy_loader: AsyncMock,
        ) -> None:
            """Test usage recording adds timestamped entries to Redis sorted set."""
            # Arrange
            subject_id = "recording-user"
            metric = "ai_feedback"
            amount = 3
            window_seconds = 60
            mock_policy_loader.get_rate_limit.return_value = (10, window_seconds)

            # Act
            await rate_limiter_enabled.record_usage(subject_id, metric, amount)

            # Assert
            expected_key = f"rate_limit:{subject_id}:{metric}"
            mock_redis_client.zadd.assert_called_once()
            call_args = mock_redis_client.zadd.call_args
            key, entries = call_args[0]

            assert key == expected_key
            assert len(entries) == amount  # Should have 3 entries

            # Verify entries have timestamp-based structure
            for member, score in entries.items():
                assert isinstance(member, str)
                assert isinstance(score, float)
                assert ":" in member  # Format: "timestamp:index"

            # Verify TTL set with buffer
            expected_ttl = window_seconds + 3600
            mock_redis_client.expire.assert_called_once_with(expected_key, expected_ttl)

        @pytest.mark.asyncio
        @pytest.mark.parametrize(
            "subject_id, metric, amount",
            [
                ("användare-åäö", "svenska_bedömning", 1),
                ("organisation-ÅÄÖ", "ai_feedback", 3),
                ("mixed-åäö-ÅÄÖ-123", "essay_scoring", 2),
            ],
        )
        async def test_record_usage_swedish_character_support(
            self,
            rate_limiter_enabled: RateLimiterImpl,
            mock_redis_client: AsyncMock,
            subject_id: str,
            metric: str,
            amount: int,
        ) -> None:
            """Test usage recording preserves Swedish characters in Redis keys."""
            # Act
            await rate_limiter_enabled.record_usage(subject_id, metric, amount)

            # Assert
            expected_key = f"rate_limit:{subject_id}:{metric}"
            mock_redis_client.zadd.assert_called_once()
            call_args = mock_redis_client.zadd.call_args
            key, entries = call_args[0]
            assert key == expected_key
            assert len(entries) == amount

        @pytest.mark.asyncio
        async def test_record_usage_disabled_limiter(
            self,
            rate_limiter_disabled: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Test disabled rate limiter skips usage recording."""
            # Act
            await rate_limiter_disabled.record_usage("test-user", "ai_feedback", 5)

            # Assert
            mock_redis_client.zadd.assert_not_called()
            mock_redis_client.expire.assert_not_called()

        @pytest.mark.asyncio
        async def test_record_usage_no_limit_configured(
            self,
            rate_limiter_enabled: RateLimiterImpl,
            mock_policy_loader: AsyncMock,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Test usage recording skipped when no limit configured."""
            # Arrange - No limit configured
            mock_policy_loader.get_rate_limit.return_value = (0, 0)

            # Act
            await rate_limiter_enabled.record_usage("test-user", "unlimited_metric", 3)

            # Assert
            mock_redis_client.zadd.assert_not_called()

    class TestConcurrentRequests:
        """Tests for concurrent request handling and atomic operations."""

        @pytest.mark.asyncio
        async def test_pipeline_execution_failure_handling(
            self,
            rate_limiter_enabled: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Test graceful handling of Redis pipeline execution failures."""
            # Arrange
            subject_id = "error-user"
            metric = "ai_feedback"
            mock_pipeline = mock_redis_client.create_transaction_pipeline.return_value
            mock_pipeline.execute.side_effect = ConnectionError("Redis connection lost")

            # Act
            result = await rate_limiter_enabled.check_rate_limit(subject_id, metric, 1)

            # Assert - Should fail open (allow request) on Redis errors
            assert result.allowed is True
            assert result.limit == 0
            assert result.window_seconds == 0
            assert result.current_count == 0

    class TestAdminOperations:
        """Tests for administrative operations like reset and get usage."""

        @pytest.mark.asyncio
        async def test_reset_rate_limit_removes_key(
            self,
            rate_limiter_enabled: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Test rate limit reset removes Redis key completely."""
            # Arrange
            subject_id = "reset-user"
            metric = "ai_feedback"

            # Act
            await rate_limiter_enabled.reset_rate_limit(subject_id, metric)

            # Assert
            expected_key = f"rate_limit:{subject_id}:{metric}"
            mock_redis_client.delete.assert_called_once_with(expected_key)

        @pytest.mark.asyncio
        async def test_reset_rate_limit_swedish_characters(
            self,
            rate_limiter_enabled: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Test rate limit reset with Swedish characters in identifiers."""
            # Arrange
            subject_id = "användare-åäö"
            metric = "svenska_bedömning"

            # Act
            await rate_limiter_enabled.reset_rate_limit(subject_id, metric)

            # Assert
            expected_key = f"rate_limit:{subject_id}:{metric}"
            mock_redis_client.delete.assert_called_once_with(expected_key)

        @pytest.mark.asyncio
        async def test_get_usage_no_limit_configured(
            self,
            rate_limiter_enabled: RateLimiterImpl,
            mock_policy_loader: AsyncMock,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Test usage statistics when no limit configured."""
            # Arrange - No limit configured
            mock_policy_loader.get_rate_limit.return_value = (0, 0)

            # Act
            stats = await rate_limiter_enabled.get_current_usage("user", "unlimited_metric")

            # Assert
            expected_stats = {
                "current_count": 0,
                "limit": 0,
                "window_seconds": 0,
                "remaining": 0,
            }
            assert stats == expected_stats
            mock_redis_client.create_transaction_pipeline.assert_not_called()

    class TestErrorRecovery:
        """Tests for error handling and recovery scenarios."""

        @pytest.mark.asyncio
        async def test_redis_connection_failure_fails_open(
            self,
            rate_limiter_enabled: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Test Redis connection failure results in fail-open behavior."""
            # Arrange
            mock_redis_client.create_transaction_pipeline.side_effect = ConnectionError(
                "Redis server unavailable"
            )

            # Act
            result = await rate_limiter_enabled.check_rate_limit("user", "ai_feedback", 1)

            # Assert - Should allow request on Redis failure
            assert result.allowed is True
            assert result.limit == 0
            assert result.window_seconds == 0
            assert result.current_count == 0

        @pytest.mark.asyncio
        async def test_policy_loader_failure_fails_open(
            self,
            rate_limiter_enabled: RateLimiterImpl,
            mock_policy_loader: AsyncMock,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Test policy loader failure results in fail-open behavior."""
            # Arrange
            mock_policy_loader.get_rate_limit.side_effect = Exception("Policy file corrupted")

            # Act
            result = await rate_limiter_enabled.check_rate_limit("user", "ai_feedback", 1)

            # Assert - Should allow request on policy failure
            assert result.allowed is True
            assert result.limit == 0
            assert result.window_seconds == 0
            assert result.current_count == 0

        @pytest.mark.asyncio
        async def test_usage_recording_failure_silent(
            self,
            rate_limiter_enabled: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Test usage recording failures are handled silently."""
            # Arrange
            mock_redis_client.zadd.side_effect = Exception("Redis write failed")

            # Act - Should not raise exception
            await rate_limiter_enabled.record_usage("user", "ai_feedback", 1)

            # Assert - No exception raised, operation completes
            mock_redis_client.zadd.assert_called_once()
