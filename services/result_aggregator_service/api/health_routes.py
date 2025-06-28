"""Health check and metrics endpoints."""

from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

from ..metrics import ResultAggregatorMetrics

logger = create_service_logger("result_aggregator.api.health")

health_bp = Blueprint("health", __name__)


@health_bp.route("/healthz")
async def health_check() -> Response:
    """Health check endpoint."""
    return jsonify(
        {"status": "healthy", "service": "result_aggregator_service", "version": "1.0.0"}
    )


@health_bp.route("/metrics")
@inject
async def metrics(metrics_instance: FromDishka[ResultAggregatorMetrics]) -> Response:
    """Prometheus metrics endpoint."""
    from prometheus_client import generate_latest

    return Response(generate_latest(), mimetype="text/plain; version=0.0.4")
