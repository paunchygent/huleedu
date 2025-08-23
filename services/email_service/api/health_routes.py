"""Health check routes for Email Service.

This module provides mandatory health endpoints required by all services.
"""

from __future__ import annotations

from quart import Blueprint, Response, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.get("/healthz")
async def health_check() -> Response:
    """Health check endpoint for Kubernetes/Docker."""
    return jsonify({"status": "healthy", "service": "email_service"})


@health_bp.get("/health")
async def health_check_alt() -> Response:
    """Alternative health check endpoint."""
    return jsonify({"status": "healthy", "service": "email_service"})
