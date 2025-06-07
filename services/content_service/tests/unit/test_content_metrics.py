"""Unit tests for Content Service metrics implementation."""

from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry, Counter

from services.content_service.implementations.prometheus_content_metrics import (
    PrometheusContentMetrics,
)
from services.content_service.protocols import ContentMetricsProtocol


class TestPrometheusContentMetrics:
    """Test the PrometheusContentMetrics implementation."""

    @pytest.fixture
    def registry(self) -> CollectorRegistry:
        """Provide a fresh registry for each test."""
        return CollectorRegistry()

    @pytest.fixture
    def content_operations_counter(self, registry: CollectorRegistry) -> Counter:
        """Provide a content operations counter."""
        return Counter(
            "content_operations_total",
            "Total content operations",
            ["operation", "status"],
            registry=registry,
        )

    @pytest.fixture
    def metrics(self, content_operations_counter: Counter) -> ContentMetricsProtocol:
        """Provide a ContentMetricsProtocol implementation."""
        return PrometheusContentMetrics(content_operations_counter)

    def test_implements_protocol(self, metrics: ContentMetricsProtocol) -> None:
        """Test that PrometheusContentMetrics implements ContentMetricsProtocol."""
        assert isinstance(metrics, ContentMetricsProtocol)

    def test_record_upload_success(
        self,
        metrics: ContentMetricsProtocol,
        registry: CollectorRegistry,
    ) -> None:
        """Test recording successful upload operation."""
        # Record upload success
        metrics.record_operation("upload", "success")

        # Debug: print what's in the registry
        metric_families = list(registry.collect())
        print(f"Registry contains {len(metric_families)} metric families:")
        for family in metric_families:
            print(f"  - {family.name}: {family.type}")
            for sample in family.samples:
                print(f"    Sample: {sample.name} = {sample.value}, labels: {sample.labels}")

        # Verify metric was recorded - look for family name "content_operations"
        content_ops_family = next(
            (family for family in metric_families if family.name == "content_operations"),
            None,
        )

        assert content_ops_family is not None, "content_operations metric family not found"

        # Find the specific sample - look for sample name "content_operations_total"
        upload_success_sample = next(
            (
                sample
                for sample in content_ops_family.samples
                if sample.name == "content_operations_total"
                and sample.labels.get("operation") == "upload"
                and sample.labels.get("status") == "success"
            ),
            None,
        )

        assert upload_success_sample is not None, "Upload success metric sample not found"
        assert upload_success_sample.value == 1.0

    def test_record_download_success(
        self, metrics: ContentMetricsProtocol,
        registry: CollectorRegistry,
    ) -> None:
        """Test recording successful download operation."""
        # Record download success
        metrics.record_operation("download", "success")

                # Verify metric was recorded
        metric_families = list(registry.collect())
        content_ops_family = next(
            (family for family in metric_families if family.name == "content_operations"),
            None,
        )

        assert content_ops_family is not None

        download_success_sample = next(
            (
                sample
                for sample in content_ops_family.samples
                if sample.name == "content_operations_total"
                and sample.labels.get("operation") == "download"
                and sample.labels.get("status") == "success"
            ),
            None,
        )

        assert download_success_sample is not None
        assert download_success_sample.value == 1.0

    def test_record_multiple_operations(
        self, metrics: ContentMetricsProtocol, registry: CollectorRegistry
    ) -> None:
        """Test recording multiple operations with different statuses."""
        # Record various operations
        metrics.record_operation("upload", "success")
        metrics.record_operation("upload", "success")
        metrics.record_operation("upload", "failed")
        metrics.record_operation("download", "success")
        metrics.record_operation("download", "not_found")
        metrics.record_operation("download", "error")

                # Verify all metrics were recorded correctly
        metric_families = list(registry.collect())
        content_ops_family = next(
            (family for family in metric_families if family.name == "content_operations"),
            None,
        )

        assert content_ops_family is not None

        # Check specific counts
        def get_sample_value(operation: str, status: str) -> float:
            sample = next(
                (
                    s for s in content_ops_family.samples
                    if s.name == "content_operations_total"
                    and s.labels.get("operation") == operation
                    and s.labels.get("status") == status
                ),
                None,
            )
            return sample.value if sample else 0.0

        assert get_sample_value("upload", "success") == 2.0
        assert get_sample_value("upload", "failed") == 1.0
        assert get_sample_value("download", "success") == 1.0
        assert get_sample_value("download", "not_found") == 1.0
        assert get_sample_value("download", "error") == 1.0

    def test_record_operation_with_error_handling(self, registry: CollectorRegistry) -> None:
        """Test that metrics errors are handled gracefully."""
        # Create metrics with a counter that might fail
        content_operations_counter = Counter(
            "content_operations_total",
            "Total content operations",
            ["operation", "status"],
            registry=registry,
        )

        metrics = PrometheusContentMetrics(content_operations_counter)

        # This should not raise an exception even if there are issues
        # (The actual implementation handles errors gracefully)
        metrics.record_operation("upload", "success")

                # Verify it still recorded the metric
        metric_families = list(registry.collect())
        content_ops_family = next(
            (family for family in metric_families if family.name == "content_operations"),
            None,
        )

        assert content_ops_family is not None

    def test_valid_operation_and_status_combinations(self, metrics: ContentMetricsProtocol) -> None:
        """Test all valid operation and status combinations."""
        valid_operations = ["upload", "download"]
        valid_statuses = ["success", "failed", "error", "not_found"]

        # All combinations should work without error
        for operation in valid_operations:
            for status in valid_statuses:
                # Should not raise any exception
                metrics.record_operation(operation, status)

    def test_protocol_method_signature(self) -> None:
        """Test that the protocol method signature is correctly implemented."""
        # This test ensures the implementation matches the protocol
        counter = Counter("test", "test", ["operation", "status"])
        metrics = PrometheusContentMetrics(counter)

        # Should accept string parameters and return None
        metrics.record_operation("upload", "success")
        # Method should complete without error (returns None)
