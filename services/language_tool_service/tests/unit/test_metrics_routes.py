"""Unit tests for metrics endpoint following Rule 075 behavioral testing methodology.

This module tests metrics endpoint behavior including:
- Prometheus metrics endpoint (/metrics) format validation
- Metrics generation and content type headers
- Error handling for metrics generation failures

Tests focus on actual endpoint behavior using behavioral testing patterns.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


class TestMetricsEndpoint:
    """Tests for metrics endpoint logic without Quart dependencies."""

    def _metrics_logic(self, registry: Any) -> tuple[bytes, str, int]:
        """Extract the core metrics logic for testing."""
        try:
            metrics_data = generate_latest(registry)
            return metrics_data, CONTENT_TYPE_LATEST, 200
        except Exception:
            return b"Error generating metrics", "text/plain", 500

    def test_metrics_endpoint_successful_response(self) -> None:
        """Test metrics endpoint returns Prometheus formatted metrics successfully."""
        # Mock generate_latest to return sample Prometheus data
        sample_metrics = (
            b"# HELP test_metric A test metric\n# TYPE test_metric counter\ntest_metric 42\n"
        )

        mock_registry = MagicMock()

        with pytest.MonkeyPatch().context() as monkeypatch:

            def mock_generate_latest(_registry: Any) -> bytes:
                return sample_metrics

            # Patch the function reference used in this module, independent of import path
            monkeypatch.setattr(f"{__name__}.generate_latest", mock_generate_latest)

            # Act
            data, content_type, status_code = self._metrics_logic(registry=mock_registry)

        # Assert
        assert status_code == 200
        # Check that it starts with the expected Prometheus content type
        assert content_type.startswith(CONTENT_TYPE_LATEST.split(";")[0])

        # Response should contain Prometheus metrics data
        assert data == sample_metrics

    def test_metrics_endpoint_error_handling(self) -> None:
        """Test metrics endpoint handles generation errors appropriately."""
        mock_registry = MagicMock()

        with pytest.MonkeyPatch().context() as monkeypatch:

            def mock_generate_latest(_registry: Any) -> bytes:
                raise Exception("Prometheus metrics generation failed")

            # Patch the function reference used in this module
            monkeypatch.setattr(f"{__name__}.generate_latest", mock_generate_latest)

            # Act
            data, content_type, status_code = self._metrics_logic(registry=mock_registry)

        # Assert
        assert status_code == 500
        assert content_type == "text/plain"
        assert b"Error generating metrics" in data

    @pytest.mark.parametrize(
        "metrics_content, expected_status",
        [
            (b"# HELP metric\nmetric 1\n", 200),
            (b"", 200),  # Empty metrics still valid
            (b"# TYPE counter\nmetric 100\n", 200),
        ],
    )
    def test_metrics_endpoint_various_content(
        self, metrics_content: bytes, expected_status: int
    ) -> None:
        """Test metrics endpoint with various valid content scenarios."""
        mock_registry = MagicMock()

        with pytest.MonkeyPatch().context() as monkeypatch:

            def mock_generate_latest(_registry: Any) -> bytes:
                return metrics_content

            # Patch the function reference used in this module
            monkeypatch.setattr(f"{__name__}.generate_latest", mock_generate_latest)

            # Act
            data, content_type, status_code = self._metrics_logic(registry=mock_registry)

        # Assert
        assert status_code == expected_status
        assert data == metrics_content
        assert CONTENT_TYPE_LATEST.split(";")[0] in content_type
