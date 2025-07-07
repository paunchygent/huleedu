"""Tests for database metrics implementation."""

from unittest.mock import Mock, patch

import pytest
from huleedu_service_libs.database.metrics import (
    NoOpDatabaseMetrics,
    PrometheusDatabaseMetrics,
    setup_database_monitoring,
)


class TestPrometheusDatabaseMetrics:
    """Test Prometheus database metrics implementation."""

    def test_initialization(self):
        """Test metrics initialization."""
        with patch("huleedu_service_libs.database.metrics.REGISTRY"):
            metrics = PrometheusDatabaseMetrics("test_service")
            assert metrics.service_name == "test_service"
            assert isinstance(metrics.metrics, dict)

    def test_record_query_duration_success(self):
        """Test recording successful query duration."""
        with patch("huleedu_service_libs.database.metrics.REGISTRY"):
            metrics = PrometheusDatabaseMetrics("test_service")

            # Mock the histogram metric
            mock_histogram = Mock()
            mock_labels = Mock()
            mock_histogram.labels.return_value = mock_labels
            metrics.metrics["database_query_duration_seconds"] = mock_histogram

            # Record query duration
            metrics.record_query_duration("select", "test_table", 1.5, True)

            # Verify metrics were called correctly
            mock_histogram.labels.assert_called_once_with(
                operation="select", table="test_table", result="success"
            )
            mock_labels.observe.assert_called_once_with(1.5)

    def test_record_query_duration_error(self):
        """Test recording failed query duration."""
        with patch("huleedu_service_libs.database.metrics.REGISTRY"):
            metrics = PrometheusDatabaseMetrics("test_service")

            # Mock the histogram metric
            mock_histogram = Mock()
            mock_labels = Mock()
            mock_histogram.labels.return_value = mock_labels
            metrics.metrics["database_query_duration_seconds"] = mock_histogram

            # Record query duration with error
            metrics.record_query_duration("insert", "test_table", 0.5, False)

            # Verify metrics were called correctly
            mock_histogram.labels.assert_called_once_with(
                operation="insert", table="test_table", result="error"
            )
            mock_labels.observe.assert_called_once_with(0.5)

    def test_set_connection_pool_status(self):
        """Test setting connection pool status."""
        with patch("huleedu_service_libs.database.metrics.REGISTRY"):
            metrics = PrometheusDatabaseMetrics("test_service")

            # Mock gauge metrics
            mock_active = Mock()
            mock_idle = Mock()
            mock_total = Mock()
            mock_overflow = Mock()

            metrics.metrics.update(
                {
                    "database_connections_active": mock_active,
                    "database_connections_idle": mock_idle,
                    "database_connections_total": mock_total,
                    "database_connections_overflow": mock_overflow,
                }
            )

            # Set pool status
            metrics.set_connection_pool_status(
                active=5,
                idle=3,
                total=10,
                overflow=2,
            )

            # Verify all gauges were set
            mock_active.set.assert_called_once_with(5)
            mock_idle.set.assert_called_once_with(3)
            mock_total.set.assert_called_once_with(10)
            mock_overflow.set.assert_called_once_with(2)

    def test_record_database_error(self):
        """Test recording database errors."""
        with patch("huleedu_service_libs.database.metrics.REGISTRY"):
            metrics = PrometheusDatabaseMetrics("test_service")

            # Mock the counter metric
            mock_counter = Mock()
            mock_labels = Mock()
            mock_counter.labels.return_value = mock_labels
            metrics.metrics["database_errors_total"] = mock_counter

            # Record database error
            metrics.record_database_error("ConnectionError", "select")

            # Verify counter was incremented
            mock_counter.labels.assert_called_once_with(
                error_type="ConnectionError", operation="select"
            )
            mock_labels.inc.assert_called_once()


class TestNoOpDatabaseMetrics:
    """Test no-op database metrics implementation."""

    def test_initialization(self):
        """Test no-op metrics initialization."""
        metrics = NoOpDatabaseMetrics("test_service")
        assert metrics.service_name == "test_service"

    def test_all_methods_are_no_op(self):
        """Test that all methods can be called without errors."""
        metrics = NoOpDatabaseMetrics("test_service")

        # All these should not raise any exceptions
        metrics.record_query_duration("select", "table", 1.0, True)
        metrics.record_connection_acquired(10, 5)
        metrics.record_connection_released(10, 5)
        metrics.record_transaction_duration("insert", 0.5, False)
        metrics.record_database_error("Error", "update")
        metrics.set_connection_pool_status(5, 3, 10, 2)

        # Get metrics should return empty dict
        assert metrics.get_metrics() == {}


class TestSetupDatabaseMonitoring:
    """Test database monitoring setup function."""

    @patch("huleedu_service_libs.database.connection_monitoring.setup_connection_monitoring")
    def test_setup_database_monitoring(self, mock_setup_connection):
        """Test complete database monitoring setup."""
        # Mock engine
        mock_engine = Mock()

        with patch("huleedu_service_libs.database.metrics.REGISTRY"):
            # Setup monitoring
            result = setup_database_monitoring(mock_engine, "test_service")

            # Verify result
            assert isinstance(result, PrometheusDatabaseMetrics)
            assert result.service_name == "test_service"

            # Verify connection monitoring was setup
            mock_setup_connection.assert_called_once_with(mock_engine, result)

    @patch("huleedu_service_libs.database.connection_monitoring.setup_connection_monitoring")
    def test_setup_with_existing_metrics(self, mock_setup_connection):
        """Test setup with existing metrics dictionary."""
        # Use the mock parameter to avoid diagnostic warning
        _ = mock_setup_connection

        mock_engine = Mock()
        existing_metrics = {"custom_metric": Mock()}

        with patch("huleedu_service_libs.database.metrics.REGISTRY"):
            result = setup_database_monitoring(mock_engine, "test_service", existing_metrics)

            # Verify the existing metrics are preserved
            assert "custom_metric" in result.get_metrics()


if __name__ == "__main__":
    pytest.main([__file__])
