"""
Unit tests for RateLimiterImpl Redis-based rate limiting implementation.

Tests focus on rate limiting algorithms, time window behaviors, Redis integration,
and error resilience patterns. Includes security-focused rate limiting scenarios
and Swedish character support in rate limit keys.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.identity_service.implementations.rate_limiter_impl import (
    RateLimiterImpl,
    create_rate_limit_key,
)


class TestRateLimiterImpl:
    """Tests for Redis-based rate limiter implementation."""

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create mock Redis client following protocol."""
        return AsyncMock(spec=AtomicRedisClientProtocol)

    @pytest.fixture
    def rate_limiter(self, mock_redis_client: AsyncMock) -> RateLimiterImpl:
        """Create rate limiter with mocked Redis client."""
        return RateLimiterImpl(redis_client=mock_redis_client)

    class TestCheckRateLimit:
        """Tests for check_rate_limit method behavior."""

        @pytest.mark.parametrize(
            "current_count, limit, expected_allowed, expected_remaining",
            [
                (None, 5, True, 4),  # First attempt, key doesn't exist
                (0, 5, True, 4),  # Zero count (edge case)
                (1, 5, True, 3),  # Under limit
                (2, 5, True, 2),  # Under limit
                (4, 5, True, 0),  # At threshold, last allowed attempt
                (5, 5, False, 0),  # At limit, should deny
                (10, 5, False, 0),  # Over limit, should deny
                (100, 5, False, 0),  # Way over limit
            ],
        )
        async def test_check_rate_limit_various_scenarios(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
            current_count: int | None,
            limit: int,
            expected_allowed: bool,
            expected_remaining: int,
        ) -> None:
            """Should correctly determine rate limit status for various scenarios."""
            # Arrange
            key = "login:ip:192.168.1.1"
            window_seconds = 300
            mock_redis_client.get.return_value = (
                str(current_count) if current_count is not None else None
            )

            # Act
            allowed, remaining = await rate_limiter.check_rate_limit(key, limit, window_seconds)

            # Assert
            assert allowed == expected_allowed
            assert remaining == expected_remaining
            mock_redis_client.get.assert_called_once_with(key)

        async def test_check_rate_limit_first_attempt_key_not_exists(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should allow first attempt when key doesn't exist in Redis."""
            # Arrange
            key = "login:email:user@example.com"
            limit = 3
            window_seconds = 60
            mock_redis_client.get.return_value = None

            # Act
            allowed, remaining = await rate_limiter.check_rate_limit(key, limit, window_seconds)

            # Assert
            assert allowed is True
            assert remaining == 2  # limit - 1
            mock_redis_client.get.assert_called_once_with(key)

        @pytest.mark.parametrize(
            "invalid_value",
            [
                "not_a_number",
                "123.45",
                "",
                "null",
                "undefined",
                "abc123",
                "1.5e10",  # Scientific notation
            ],
        )
        async def test_check_rate_limit_handles_invalid_redis_values(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
            invalid_value: str,
        ) -> None:
            """Should handle invalid values in Redis by resetting key and allowing request."""
            # Arrange
            key = "register:ip:10.0.0.1"
            limit = 5
            window_seconds = 600
            mock_redis_client.get.return_value = invalid_value

            # Act
            allowed, remaining = await rate_limiter.check_rate_limit(key, limit, window_seconds)

            # Assert
            assert allowed is True
            assert remaining == 4  # limit - 1 (first attempt after reset)
            mock_redis_client.get.assert_called_once_with(key)
            mock_redis_client.delete_key.assert_called_once_with(key)

        async def test_check_rate_limit_negative_count_treated_as_corrupted_data(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should treat negative count values as corrupted data and reset the key."""
            # Arrange - Negative counts are now treated as data corruption
            key = "edge_case:negative:count"
            limit = 5
            window_seconds = 300
            mock_redis_client.get.return_value = "-3"

            # Act
            allowed, remaining = await rate_limiter.check_rate_limit(key, limit, window_seconds)

            # Assert - Negative count triggers data reset
            assert allowed is True
            assert remaining == 4  # limit - 1 (reset behavior)
            mock_redis_client.get.assert_called_once_with(key)
            mock_redis_client.delete_key.assert_called_once_with(key)

        async def test_check_rate_limit_redis_connection_failure(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should allow request on Redis connection failure (graceful degradation)."""
            # Arrange
            key = "password_reset:email:user@domain.se"
            limit = 3
            window_seconds = 3600
            mock_redis_client.get.side_effect = ConnectionError("Redis connection failed")

            # Act
            allowed, remaining = await rate_limiter.check_rate_limit(key, limit, window_seconds)

            # Assert
            assert allowed is True
            assert remaining == 2  # limit - 1 (default fallback)
            mock_redis_client.get.assert_called_once_with(key)

        async def test_check_rate_limit_with_swedish_characters_in_key(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should handle rate limit keys with Swedish characters properly."""
            # Arrange
            key = "login:email:användare@skola.se"  # Swedish characters
            limit = 10
            window_seconds = 900
            mock_redis_client.get.return_value = "3"

            # Act
            allowed, remaining = await rate_limiter.check_rate_limit(key, limit, window_seconds)

            # Assert
            assert allowed is True
            assert remaining == 6  # limit - current_count - 1 = 10 - 3 - 1
            mock_redis_client.get.assert_called_once_with(key)

        async def test_check_rate_limit_various_limits(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should handle various rate limit configurations correctly."""
            # Test cases: (limit, expected_remaining)
            test_cases = [(1, 0), (10, 9), (100, 99), (1000, 999)]

            for limit, expected_remaining in test_cases:
                mock_redis_client.reset_mock()
                mock_redis_client.get.return_value = None
                key = f"api_call:user:limit_{limit}"

                allowed, remaining = await rate_limiter.check_rate_limit(key, limit, 1800)

                assert allowed is True
                assert remaining == expected_remaining
                mock_redis_client.get.assert_called_once_with(key)

    class TestIncrement:
        """Tests for increment method behavior."""

        async def test_increment_first_attempt_sets_key_with_ttl(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should set key with TTL on first increment attempt."""
            # Arrange
            key = "login:ip:203.0.113.1"
            window_seconds = 300
            mock_redis_client.get.return_value = None
            mock_redis_client.set_if_not_exists.return_value = True

            # Act
            count = await rate_limiter.increment(key, window_seconds)

            # Assert
            assert count == 1
            mock_redis_client.get.assert_called_once_with(key)
            mock_redis_client.set_if_not_exists.assert_called_once_with(
                key, "1", ttl_seconds=window_seconds
            )

        async def test_increment_race_condition_handling(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should handle race condition when another process sets key first."""
            # Arrange
            key = "register:email:test@example.com"
            window_seconds = 600
            mock_redis_client.get.side_effect = [None, "2"]  # First None, then someone else set it
            mock_redis_client.set_if_not_exists.return_value = False  # Race condition occurred

            # Act
            count = await rate_limiter.increment(key, window_seconds)

            # Assert
            assert count == 2  # Got the value set by the other process
            assert mock_redis_client.get.call_count == 2
            mock_redis_client.set_if_not_exists.assert_called_once_with(
                key, "1", ttl_seconds=window_seconds
            )

        async def test_increment_race_condition_with_invalid_value(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should handle race condition with invalid value in Redis."""
            # Arrange
            key = "password_change:user:12345"
            window_seconds = 1800
            mock_redis_client.get.side_effect = [None, "invalid_number"]
            mock_redis_client.set_if_not_exists.return_value = False

            # Act
            count = await rate_limiter.increment(key, window_seconds)

            # Assert
            assert count == 1  # Conservative fallback
            assert mock_redis_client.get.call_count == 2
            mock_redis_client.set_if_not_exists.assert_called_once()

        async def test_increment_existing_valid_values(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should correctly increment existing valid values."""
            test_cases = [("1", 2), ("5", 6), ("10", 11), ("99", 100), ("0", 1)]

            for current_value, expected_new_count in test_cases:
                mock_redis_client.reset_mock()
                mock_redis_client.get.return_value = current_value
                key = f"api_call:token:{current_value}"

                count = await rate_limiter.increment(key, 3600)

                assert count == expected_new_count
                mock_redis_client.get.assert_called_once_with(key)
                mock_redis_client.setex.assert_called_once_with(key, 3600, str(expected_new_count))

        async def test_increment_invalid_existing_values_resets_to_one(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should reset invalid values to 1 and update with TTL."""
            invalid_values = ["not_a_number", "", "null", "1.5", "1e10", "abc"]

            for invalid_value in invalid_values:
                mock_redis_client.reset_mock()
                mock_redis_client.get.return_value = invalid_value
                key = f"verification:email:{invalid_value}"

                count = await rate_limiter.increment(key, 900)

                assert count == 1
                mock_redis_client.get.assert_called_once_with(key)
                mock_redis_client.setex.assert_called_once_with(key, 900, "1")

        async def test_increment_negative_value_treated_as_corrupted_data(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should treat negative values as corrupted data and reset to 1."""
            # Negative counts are now treated as data corruption
            mock_redis_client.get.return_value = "-5"

            count = await rate_limiter.increment("edge_case:negative", 600)

            # Corrupted data is reset to 1
            assert count == 1
            mock_redis_client.setex.assert_called_once_with("edge_case:negative", 600, "1")

        async def test_increment_redis_operation_failure(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should return conservative value 1 on Redis operation failure."""
            # Arrange
            key = "login:session:session_123"
            window_seconds = 7200
            mock_redis_client.get.side_effect = ConnectionError("Redis unavailable")

            # Act
            count = await rate_limiter.increment(key, window_seconds)

            # Assert
            assert count == 1  # Conservative approach on error
            mock_redis_client.get.assert_called_once_with(key)

        async def test_increment_various_window_sizes(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should handle various TTL window sizes correctly."""
            test_cases = [60, 3600, 86400, 604800]  # 1 min, 1 hour, 24 hours, 1 week

            for window_seconds in test_cases:
                key = f"test:window:{window_seconds}"
                mock_redis_client.reset_mock()
                mock_redis_client.get.return_value = None
                mock_redis_client.set_if_not_exists.return_value = True

                count = await rate_limiter.increment(key, window_seconds)

                assert count == 1
                mock_redis_client.set_if_not_exists.assert_called_once_with(
                    key, "1", ttl_seconds=window_seconds
                )

    class TestReset:
        """Tests for reset method behavior."""

        async def test_reset_existing_key_success(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should successfully reset existing rate limit key."""
            # Arrange
            key = "login:ip:192.168.1.100"
            mock_redis_client.delete_key.return_value = 1  # Key was deleted

            # Act
            result = await rate_limiter.reset(key)

            # Assert
            assert result is True
            mock_redis_client.delete_key.assert_called_once_with(key)

        async def test_reset_non_existent_key(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should handle reset of non-existent key gracefully."""
            # Arrange
            key = "nonexistent:key:12345"
            mock_redis_client.delete_key.return_value = 0  # No key was deleted

            # Act
            result = await rate_limiter.reset(key)

            # Assert
            assert result is False
            mock_redis_client.delete_key.assert_called_once_with(key)

        async def test_reset_redis_operation_failure(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should return False on Redis operation failure."""
            # Arrange
            key = "reset_test:failure:case"
            mock_redis_client.delete_key.side_effect = ConnectionError("Redis connection lost")

            # Act
            result = await rate_limiter.reset(key)

            # Assert
            assert result is False
            mock_redis_client.delete_key.assert_called_once_with(key)

        async def test_reset_various_key_formats(
            self,
            rate_limiter: RateLimiterImpl,
            mock_redis_client: AsyncMock,
        ) -> None:
            """Should handle reset for various key formats including Swedish characters."""
            key_patterns = [
                "login:ip:203.0.113.42",
                "register:email:test@domain.se",
                "password_reset:user:åsa_andersson",
                "api:token:very-long-token-123456789",
                "verification:session:session_åäö_123",
            ]

            for key_pattern in key_patterns:
                mock_redis_client.reset_mock()
                mock_redis_client.delete_key.return_value = 1

                result = await rate_limiter.reset(key_pattern)

                assert result is True
                mock_redis_client.delete_key.assert_called_once_with(key_pattern)


class TestCreateRateLimitKey:
    """Tests for create_rate_limit_key utility function."""

    @pytest.mark.parametrize(
        "action, identifier, namespace, expected_key",
        [
            ("login", "192.168.1.1", "identity", "identity:rate_limit:login:192.168.1.1"),
            (
                "register",
                "user@example.com",
                "auth",
                "auth:rate_limit:register:user_at_example.com",
            ),
            (
                "password_reset",
                "test@domain.se",
                "security",
                "security:rate_limit:password_reset:test_at_domain.se",
            ),
            ("api_call", "token:123:456", "api", "api:rate_limit:api_call:token_123_456"),
        ],
    )
    def test_create_rate_limit_key_standard_cases(
        self,
        action: str,
        identifier: str,
        namespace: str,
        expected_key: str,
    ) -> None:
        """Should create properly formatted rate limit keys for standard cases."""
        # Act
        result = create_rate_limit_key(action, identifier, namespace)

        # Assert
        assert result == expected_key

    def test_create_rate_limit_key_default_namespace(self) -> None:
        """Should use default 'identity' namespace when not specified."""
        # Act
        result = create_rate_limit_key("login", "user@test.com")

        # Assert
        assert result == "identity:rate_limit:login:user_at_test.com"

    def test_create_rate_limit_key_special_character_handling(self) -> None:
        """Should properly escape special characters in identifiers."""
        test_cases = [
            ("user:password:123", "user_password_123"),
            ("email@domain.com", "email_at_domain.com"),
            ("user@domain.se:session:456", "user_at_domain.se_session_456"),
            ("complex::case@@test", "complex__case_at__at_test"),
            ("åsa@skolan.se", "åsa_at_skolan.se"),  # Swedish chars preserved
        ]

        for identifier, expected_safe in test_cases:
            result = create_rate_limit_key("test_action", identifier)
            expected = f"identity:rate_limit:test_action:{expected_safe}"
            assert result == expected

    def test_create_rate_limit_key_edge_cases(self) -> None:
        """Should handle Swedish characters and empty values gracefully."""
        # Swedish characters preserved
        result1 = create_rate_limit_key(
            "email_verification", "åsa.andersson@skolan.se", "education"
        )
        assert result1 == "education:rate_limit:email_verification:åsa.andersson_at_skolan.se"
        assert "åsa" in result1 and "_at_" in result1

        # Empty values handling
        assert create_rate_limit_key("", "identifier") == "identity:rate_limit::identifier"
        assert create_rate_limit_key("action", "") == "identity:rate_limit:action:"
        assert create_rate_limit_key("action", "identifier", "") == ":rate_limit:action:identifier"
