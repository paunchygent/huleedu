"""
Tests for health check endpoints in WebSocket Service.

Tests the health endpoints for basic service health, Redis connectivity,
WebSocket manager status, and Prometheus metrics.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealthRoutes:
    """Test suite for health check endpoints."""

    def test_basic_health_check(self, create_test_app):
        """Test basic health check endpoint returns healthy status."""
        app = create_test_app()

        with TestClient(app) as client:
            response = client.get("/healthz")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "websocket_service"
        assert "timestamp" in data
        assert "uptime_seconds" in data

    def test_redis_health_check_success(self, create_test_app, mock_redis_client):
        """Test Redis health check when Redis is healthy."""
        app = create_test_app()

        # Redis mock is configured to succeed by default
        with TestClient(app) as client:
            response = client.get("/healthz/redis")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "redis"
        assert "url" in data
        # Verify credentials are masked
        assert "***:***" in data["url"]

    def test_redis_health_check_failure(self, create_test_app, mock_redis_client):
        """Test Redis health check when Redis is unhealthy."""
        app = create_test_app()

        # Configure Redis to fail
        mock_redis_client.ping.side_effect = Exception("Connection refused")

        with TestClient(app) as client:
            response = client.get("/healthz/redis")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["service"] == "redis"
        assert "error" in data

    def test_websocket_manager_health(self, create_test_app, mock_websocket_manager):
        """Test WebSocket manager health endpoint."""
        app = create_test_app()

        # Add some test connections
        mock_websocket_manager.connections = {
            "user1": ["conn1", "conn2"],
            "user2": ["conn3"],
        }

        with TestClient(app) as client:
            response = client.get("/healthz/websocket")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "websocket_manager"
        assert data["total_connections"] == 3
        assert data["max_connections_per_user"] == 5

    def test_metrics_endpoint(self, create_test_app):
        """Test Prometheus metrics endpoint."""
        app = create_test_app()

        with TestClient(app) as client:
            response = client.get("/metrics")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

        # Verify some expected metrics are present
        metrics_text = response.text
        assert "websocket_connections_total" in metrics_text
        assert "websocket_active_connections" in metrics_text
        assert "http_request_duration_seconds" in metrics_text
