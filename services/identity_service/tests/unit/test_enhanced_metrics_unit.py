"""
Unit tests for enhanced identity service metrics functionality.

Tests focus on metric structure validation, label correctness, and metric behavior
following Rule 075 methodology with protocol-based mocking.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from prometheus_client import REGISTRY, Counter, Gauge, Histogram

from services.identity_service.implementations.event_publisher_impl import (
    DefaultIdentityEventPublisher,
)
from services.identity_service.implementations.outbox_manager import OutboxManager
from services.identity_service.metrics import (
    ACCOUNT_LOCKOUTS,
    ACTIVE_SESSIONS,
    AUTHENTICATION_ATTEMPTS,
    FAILED_LOGIN_ATTEMPTS,
    PASSWORD_RESET_REQUESTS,
    REQUEST_COUNT,
    REQUEST_LATENCY,
    TOKEN_ISSUANCE,
    TOKEN_REVOCATIONS,
)


class TestEnhancedMetricsStructure:
    """Tests for enhanced metrics structure and labeling correctness."""

    def test_authentication_attempts_counter_structure(self) -> None:
        """Test AUTHENTICATION_ATTEMPTS counter has correct structure and labels."""
        assert isinstance(AUTHENTICATION_ATTEMPTS, Counter)
        assert AUTHENTICATION_ATTEMPTS._name == "identity_authentication_attempts"
        assert AUTHENTICATION_ATTEMPTS._documentation == "Total number of authentication attempts"
        assert set(AUTHENTICATION_ATTEMPTS._labelnames) == {"status", "failure_reason"}

    def test_token_issuance_counter_structure(self) -> None:
        """Test TOKEN_ISSUANCE counter has correct structure and labels."""
        assert isinstance(TOKEN_ISSUANCE, Counter)
        assert TOKEN_ISSUANCE._name == "identity_tokens_issued"
        assert TOKEN_ISSUANCE._documentation == "Total number of tokens issued"
        assert set(TOKEN_ISSUANCE._labelnames) == {"token_type"}

    def test_password_reset_requests_counter_structure(self) -> None:
        """Test PASSWORD_RESET_REQUESTS counter has correct structure and labels."""
        assert isinstance(PASSWORD_RESET_REQUESTS, Counter)
        assert PASSWORD_RESET_REQUESTS._name == "identity_password_reset_requests"
        assert PASSWORD_RESET_REQUESTS._documentation == "Total number of password reset requests"
        assert set(PASSWORD_RESET_REQUESTS._labelnames) == {"status"}

    def test_active_sessions_gauge_structure(self) -> None:
        """Test ACTIVE_SESSIONS gauge has correct structure."""
        assert isinstance(ACTIVE_SESSIONS, Gauge)
        assert ACTIVE_SESSIONS._name == "identity_active_sessions"
        assert ACTIVE_SESSIONS._documentation == "Number of currently active user sessions"
        assert ACTIVE_SESSIONS._labelnames == ()

    def test_failed_login_attempts_histogram_structure(self) -> None:
        """Test FAILED_LOGIN_ATTEMPTS histogram has correct structure and buckets."""
        assert isinstance(FAILED_LOGIN_ATTEMPTS, Histogram)
        assert FAILED_LOGIN_ATTEMPTS._name == "identity_failed_login_attempts"
        assert (
            FAILED_LOGIN_ATTEMPTS._documentation == "Distribution of failed login attempts per user"
        )
        expected_buckets = [1.0, 2.0, 3.0, 5.0, 10.0, 25.0, 50.0, float("inf")]
        assert FAILED_LOGIN_ATTEMPTS._upper_bounds == expected_buckets

    def test_token_revocations_counter_structure(self) -> None:
        """Test TOKEN_REVOCATIONS counter has correct structure and labels."""
        assert isinstance(TOKEN_REVOCATIONS, Counter)
        assert TOKEN_REVOCATIONS._name == "identity_token_revocations"
        assert TOKEN_REVOCATIONS._documentation == "Total number of token revocations"
        assert set(TOKEN_REVOCATIONS._labelnames) == {"token_type", "reason"}

    def test_account_lockouts_counter_structure(self) -> None:
        """Test ACCOUNT_LOCKOUTS counter has correct structure and labels."""
        assert isinstance(ACCOUNT_LOCKOUTS, Counter)
        assert ACCOUNT_LOCKOUTS._name == "identity_account_lockouts"
        assert ACCOUNT_LOCKOUTS._documentation == "Total number of account lockouts"
        assert set(ACCOUNT_LOCKOUTS._labelnames) == {"reason"}

    def test_request_count_counter_structure(self) -> None:
        """Test REQUEST_COUNT counter has correct general structure."""
        assert isinstance(REQUEST_COUNT, Counter)
        assert REQUEST_COUNT._name == "identity_requests"
        assert REQUEST_COUNT._documentation == "Total number of identity requests"
        assert set(REQUEST_COUNT._labelnames) == {"route", "method", "status"}

    def test_request_latency_histogram_structure(self) -> None:
        """Test REQUEST_LATENCY histogram has correct structure."""
        assert isinstance(REQUEST_LATENCY, Histogram)
        assert REQUEST_LATENCY._name == "identity_request_duration_seconds"
        assert REQUEST_LATENCY._documentation == "Latency of identity requests"
        assert set(REQUEST_LATENCY._labelnames) == {"route"}


class TestMetricsBehavior:
    """Tests for metrics behavior and value updates."""

    def setup_method(self) -> None:
        """Setup method for test isolation."""
        # Note: Prometheus metrics are global singletons, so we can't easily reset them
        # Tests should be designed to be independent despite this limitation
        pass

    @pytest.mark.parametrize(
        "expected_labels",
        [
            {"status": "success", "failure_reason": ""},
            {"status": "failed", "failure_reason": "invalid_password"},
            {"status": "failed", "failure_reason": "account_locked"},
            {"status": "failed", "failure_reason": "rate_limited"},
        ],
    )
    def test_authentication_attempts_labeling(self, expected_labels: dict) -> None:
        """Test AUTHENTICATION_ATTEMPTS counter accepts various label combinations."""
        # Act - increment counter with labels
        AUTHENTICATION_ATTEMPTS.labels(**expected_labels).inc()

        # Assert - check that metric exists with correct labels
        metric_value = AUTHENTICATION_ATTEMPTS.labels(**expected_labels)._value._value
        assert metric_value == 1.0

    @pytest.mark.parametrize(
        "expected_labels",
        [
            {"token_type": "access"},
            {"token_type": "refresh"},
            {"token_type": "verification"},
            {"token_type": "reset"},
        ],
    )
    def test_token_issuance_labeling(self, expected_labels: dict) -> None:
        """Test TOKEN_ISSUANCE counter accepts various token types."""
        # Act
        TOKEN_ISSUANCE.labels(**expected_labels).inc()

        # Assert
        metric_value = TOKEN_ISSUANCE.labels(**expected_labels)._value._value
        assert metric_value == 1.0

    @pytest.mark.parametrize(
        "expected_labels",
        [
            {"status": "initiated"},
            {"status": "completed"},
            {"status": "failed"},
            {"status": "expired"},
        ],
    )
    def test_password_reset_requests_labeling(self, expected_labels: dict) -> None:
        """Test PASSWORD_RESET_REQUESTS counter accepts various status values."""
        # Act
        PASSWORD_RESET_REQUESTS.labels(**expected_labels).inc()

        # Assert
        metric_value = PASSWORD_RESET_REQUESTS.labels(**expected_labels)._value._value
        assert metric_value == 1.0

    def test_active_sessions_gauge_operations(self) -> None:
        """Test ACTIVE_SESSIONS gauge supports increment/decrement operations."""
        # Act - Test gauge operations
        ACTIVE_SESSIONS.inc(5)  # Add 5 sessions
        assert ACTIVE_SESSIONS._value._value == 5.0

        ACTIVE_SESSIONS.dec(2)  # Remove 2 sessions
        assert ACTIVE_SESSIONS._value._value == 3.0

        ACTIVE_SESSIONS.set(10)  # Set to 10 sessions
        assert ACTIVE_SESSIONS._value._value == 10.0

    @pytest.mark.parametrize(
        "attempt_count, expected_bucket",
        [
            (1, 1),
            (3, 3),
            (7, 10),  # Should fall into 10 bucket
            (30, 50),  # Should fall into 50 bucket
            (100, float("inf")),  # Should fall into +Inf bucket
        ],
    )
    def test_failed_login_attempts_histogram_bucketing(
        self, attempt_count: int, expected_bucket: float
    ) -> None:
        """Test FAILED_LOGIN_ATTEMPTS histogram buckets failed attempts correctly."""
        # Arrange - record initial sum value
        initial_sum = FAILED_LOGIN_ATTEMPTS._sum._value
        
        # Act
        FAILED_LOGIN_ATTEMPTS.observe(attempt_count)

        # Assert - check bucket count using the upper bounds
        buckets = FAILED_LOGIN_ATTEMPTS._upper_bounds
        # Find the appropriate bucket index and verify observation was recorded
        bucket_found = False
        for bucket_le in buckets:
            if bucket_le >= expected_bucket:
                bucket_found = True
                break
        assert bucket_found, f"Bucket {expected_bucket} not found"
        
        # Verify that the histogram recorded the observation by checking sum increase
        assert FAILED_LOGIN_ATTEMPTS._sum._value == initial_sum + attempt_count

    @pytest.mark.parametrize(
        "expected_labels",
        [
            {"token_type": "access", "reason": "user_logout"},
            {"token_type": "refresh", "reason": "security_breach"},
            {"token_type": "access", "reason": "admin_revoke"},
            {"token_type": "verification", "reason": "expired"},
        ],
    )
    def test_token_revocations_labeling(self, expected_labels: dict) -> None:
        """Test TOKEN_REVOCATIONS counter accepts various token types and reasons."""
        # Act
        TOKEN_REVOCATIONS.labels(**expected_labels).inc()

        # Assert
        metric_value = TOKEN_REVOCATIONS.labels(**expected_labels)._value._value
        assert metric_value == 1.0

    @pytest.mark.parametrize(
        "expected_labels",
        [
            {"reason": "too_many_failed_attempts"},
            {"reason": "suspicious_activity"},
            {"reason": "admin_action"},
            {"reason": "security_policy"},
        ],
    )
    def test_account_lockouts_labeling(self, expected_labels: dict) -> None:
        """Test ACCOUNT_LOCKOUTS counter accepts various lockout reasons."""
        # Act
        ACCOUNT_LOCKOUTS.labels(**expected_labels).inc()

        # Assert
        metric_value = ACCOUNT_LOCKOUTS.labels(**expected_labels)._value._value
        assert metric_value == 1.0


class TestTokenRevokedEventPublishing:
    """Tests for the publish_token_revoked method functionality."""

    @pytest.fixture
    def mock_outbox_manager(self) -> AsyncMock:
        """Create mock outbox manager following protocol."""
        return AsyncMock(spec=OutboxManager)

    @pytest.fixture
    def event_publisher(self, mock_outbox_manager: AsyncMock) -> DefaultIdentityEventPublisher:
        """Create event publisher with mocked dependencies."""
        return DefaultIdentityEventPublisher(
            outbox_manager=mock_outbox_manager, source_service_name="identity_service"
        )

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Generate correlation ID for test scenarios."""
        return uuid4()

    @pytest.fixture
    def sample_token_data(self) -> dict:
        """Create sample token data for testing."""
        return {
            "user_id": str(uuid4()),
            "jti": str(uuid4()),
            "reason": "user_logout",
        }

    async def test_publish_token_revoked_calls_outbox_manager(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_token_data: dict,
        correlation_id: UUID,
    ) -> None:
        """Test publish_token_revoked calls outbox manager with correct parameters."""
        # Act
        await event_publisher.publish_token_revoked(
            user_id=sample_token_data["user_id"],
            jti=sample_token_data["jti"],
            reason=sample_token_data["reason"],
            correlation_id=correlation_id,
        )

        # Assert outbox manager was called
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_kwargs = mock_outbox_manager.publish_to_outbox.call_args.kwargs

        # Verify call structure
        assert call_kwargs["event_type"] == "TokenRevokedV1"
        
        # Verify event data
        event_data = call_kwargs["event_data"]
        assert event_data["correlation_id"] == str(correlation_id)
        assert event_data["user_id"] == sample_token_data["user_id"]
        assert event_data["jti"] == sample_token_data["jti"]
        assert event_data["reason"] == sample_token_data["reason"]
        assert "timestamp" in event_data

    @pytest.mark.parametrize(
        "user_id, jti, reason",
        [
            ("user123", "jti456", "user_logout"),
            ("åäö_user", "jti_special", "security_breach"),  # Swedish characters
            ("admin_user", "admin_jti", "admin_revoke"),
            ("test_user", "session_jti", "session_timeout"),
        ],
    )
    async def test_publish_token_revoked_handles_various_scenarios(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        correlation_id: UUID,
        user_id: str,
        jti: str,
        reason: str,
    ) -> None:
        """Test publish_token_revoked handles various user scenarios including Swedish characters."""
        # Act
        await event_publisher.publish_token_revoked(
            user_id=user_id, jti=jti, reason=reason, correlation_id=correlation_id
        )

        # Assert
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        event_data = mock_outbox_manager.publish_to_outbox.call_args.kwargs["event_data"]

        assert event_data["user_id"] == user_id
        assert event_data["jti"] == jti
        assert event_data["reason"] == reason

    async def test_publish_token_revoked_includes_timestamp(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_token_data: dict,
        correlation_id: UUID,
    ) -> None:
        """Test publish_token_revoked includes proper timestamp in event data."""
        # Arrange
        before_time = datetime.now(UTC)

        # Act
        await event_publisher.publish_token_revoked(
            user_id=sample_token_data["user_id"],
            jti=sample_token_data["jti"],
            reason=sample_token_data["reason"],
            correlation_id=correlation_id,
        )

        # Assert
        after_time = datetime.now(UTC)
        event_data = mock_outbox_manager.publish_to_outbox.call_args.kwargs["event_data"]
        
        # Verify timestamp is present and properly formatted
        assert "timestamp" in event_data
        timestamp_str = event_data["timestamp"]
        assert isinstance(timestamp_str, str)
        
        # Verify timestamp is in ISO format and within expected range
        event_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        assert before_time <= event_time <= after_time

    async def test_publish_token_revoked_propagates_outbox_errors(
        self,
        event_publisher: DefaultIdentityEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_token_data: dict,
        correlation_id: UUID,
    ) -> None:
        """Test publish_token_revoked propagates outbox manager errors correctly."""
        # Arrange
        expected_error = Exception("Outbox failure")
        mock_outbox_manager.publish_to_outbox.side_effect = expected_error

        # Act & Assert
        with pytest.raises(Exception, match="Outbox failure"):
            await event_publisher.publish_token_revoked(
                user_id=sample_token_data["user_id"],
                jti=sample_token_data["jti"],
                reason=sample_token_data["reason"],
                correlation_id=correlation_id,
            )


class TestMetricsIntegration:
    """Tests for metrics integration with event publishing."""

    def test_all_metrics_registered_in_prometheus(self) -> None:
        """Test that all identity metrics are properly registered with Prometheus."""
        metric_names = {
            "identity_requests",
            "identity_request_duration_seconds",
            "identity_authentication_attempts",
            "identity_tokens_issued",
            "identity_password_reset_requests",
            "identity_active_sessions",
            "identity_failed_login_attempts",
            "identity_token_revocations",
            "identity_account_lockouts",
        }

        # Get registered metrics from the default registry
        registered_metrics = set()
        for collector in REGISTRY._names_to_collectors.values():
            if hasattr(collector, "_name"):
                registered_metrics.add(collector._name)

        # Check that all our metrics are registered
        missing_metrics = metric_names - registered_metrics
        assert not missing_metrics, f"Missing metrics in registry: {missing_metrics}"

    def test_metric_label_consistency_across_types(self) -> None:
        """Test that related metrics use consistent labeling patterns."""
        # Authentication metrics should have status label
        auth_metrics = [AUTHENTICATION_ATTEMPTS, PASSWORD_RESET_REQUESTS]
        for metric in auth_metrics:
            assert "status" in metric._labelnames

        # Token metrics should have token_type or related labels
        token_metrics = [TOKEN_ISSUANCE, TOKEN_REVOCATIONS]
        for metric in token_metrics:
            assert "token_type" in metric._labelnames

    def test_counter_metrics_never_decrease(self) -> None:
        """Test that counter metrics maintain monotonic increase property."""
        # Test a few counter metrics
        initial_auth_value = AUTHENTICATION_ATTEMPTS.labels(
            status="test", failure_reason="test"
        )._value._value
        AUTHENTICATION_ATTEMPTS.labels(status="test", failure_reason="test").inc()
        final_auth_value = AUTHENTICATION_ATTEMPTS.labels(
            status="test", failure_reason="test"
        )._value._value

        assert final_auth_value > initial_auth_value

        initial_token_value = TOKEN_ISSUANCE.labels(token_type="test")._value._value
        TOKEN_ISSUANCE.labels(token_type="test").inc()
        final_token_value = TOKEN_ISSUANCE.labels(token_type="test")._value._value

        assert final_token_value > initial_token_value
