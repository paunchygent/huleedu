"""Internal API routes for querying aggregated results."""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, current_app, g, jsonify, request
from quart_dishka import inject

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.metrics import ResultAggregatorMetrics
from services.result_aggregator_service.models_api import BatchStatusResponse
from services.result_aggregator_service.protocols import (
    BatchQueryServiceProtocol,
    CacheManagerProtocol,
    SecurityServiceProtocol,
)

logger = create_service_logger("result_aggregator.api.query")

query_bp = Blueprint("query", __name__, url_prefix="/internal/v1")


@query_bp.before_request
async def authenticate_request() -> Optional[tuple[Response, int]]:
    """Authenticate internal service requests."""
    # Access Dishka container from extensions
    dishka = current_app.extensions["QUART_DISHKA"].container
    security = await dishka.get(SecurityServiceProtocol)
    # Extract service credentials
    api_key = request.headers.get("X-Internal-API-Key")
    service_id = request.headers.get("X-Service-ID")

    if not api_key or not service_id:
        logger.warning("Missing authentication headers")
        return jsonify({"error": "Missing authentication"}), 401

    # Validate credentials
    if not await security.validate_service_credentials(api_key, service_id):
        logger.warning("Invalid service credentials", service_id=service_id)
        return jsonify({"error": "Invalid credentials"}), 401

    # Set request context
    g.service_id = service_id
    g.correlation_id = request.headers.get("X-Correlation-ID", str(uuid4()))

    return None


@query_bp.route("/batches/<batch_id>/status", methods=["GET"])
@inject
async def get_batch_status(
    batch_id: str,
    query_service: FromDishka[BatchQueryServiceProtocol],
    cache_manager: FromDishka[CacheManagerProtocol],
    metrics: FromDishka[ResultAggregatorMetrics],
    settings: FromDishka[Settings],
) -> Response | tuple[Response, int]:
    """Get comprehensive batch status including all essay results."""
    with metrics.api_request_duration.labels(endpoint="get_batch_status", method="GET").time():
        try:
            logger.info(
                "Batch status query",
                batch_id=batch_id,
                service_id=g.service_id,
                correlation_id=g.correlation_id,
            )

            # Check cache first if enabled
            if settings.CACHE_ENABLED:
                cached_response = await cache_manager.get_batch_status_json(batch_id)

                if cached_response:
                    metrics.cache_hits_total.labels(cache_type="batch_status").inc()
                    logger.debug("Cache hit for batch status", batch_id=batch_id)
                    metrics.api_requests_total.labels(
                        endpoint="get_batch_status", method="GET", status_code=200
                    ).inc()
                    # Return cached JSON response directly
                    return Response(cached_response, mimetype="application/json"), 200

                # Cache miss
                metrics.cache_misses_total.labels(cache_type="batch_status").inc()

            # Query the aggregated results
            result = await query_service.get_batch_status(batch_id)

            if not result:
                metrics.api_requests_total.labels(
                    endpoint="get_batch_status", method="GET", status_code=404
                ).inc()
                return jsonify({"error": "Batch not found"}), 404

            # Convert to API response model
            response = BatchStatusResponse.from_domain(result)
            response_json = response.model_dump_json()

            # Cache the response if caching is enabled
            if settings.CACHE_ENABLED:
                await cache_manager.set_batch_status_json(
                    batch_id, response_json, settings.REDIS_CACHE_TTL_SECONDS
                )

            metrics.api_requests_total.labels(
                endpoint="get_batch_status", method="GET", status_code=200
            ).inc()

            return Response(response_json, mimetype="application/json"), 200

        except ValueError as e:
            logger.error("Invalid batch ID", batch_id=batch_id, error=str(e))
            metrics.api_errors_total.labels(
                endpoint="get_batch_status", error_type="validation"
            ).inc()
            return jsonify({"error": "Invalid batch ID"}), 400

        except Exception as e:
            logger.error(
                "Error retrieving batch status", batch_id=batch_id, error=str(e), exc_info=True
            )
            metrics.api_errors_total.labels(
                endpoint="get_batch_status", error_type="internal"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500


@query_bp.route("/batches/user/<user_id>", methods=["GET"])
@inject
async def get_user_batches(
    user_id: str,
    query_service: FromDishka[BatchQueryServiceProtocol],
    cache_manager: FromDishka[CacheManagerProtocol],
    metrics: FromDishka[ResultAggregatorMetrics],
    settings: FromDishka[Settings],
) -> Response | tuple[Response, int]:
    """Get all batches for a specific user."""
    with metrics.api_request_duration.labels(endpoint="get_user_batches", method="GET").time():
        try:
            # Parse query parameters
            limit = request.args.get("limit", 20, type=int)
            offset = request.args.get("offset", 0, type=int)
            status = request.args.get("status", type=str)

            logger.info(
                "User batches query",
                user_id=user_id,
                limit=limit,
                offset=offset,
                status=status,
                service_id=g.service_id,
            )

            # Check cache first if enabled
            if settings.CACHE_ENABLED:
                cached_response = await cache_manager.get_user_batches_json(
                    user_id, limit, offset, status
                )

                if cached_response:
                    metrics.cache_hits_total.labels(cache_type="user_batches").inc()
                    logger.debug("Cache hit for user batches", user_id=user_id)
                    metrics.api_requests_total.labels(
                        endpoint="get_user_batches", method="GET", status_code=200
                    ).inc()
                    return Response(cached_response, mimetype="application/json"), 200

                # Cache miss
                metrics.cache_misses_total.labels(cache_type="user_batches").inc()

            # Query batches
            batches = await query_service.get_user_batches(
                user_id=user_id, status=status, limit=limit, offset=offset
            )

            # Create response
            response_data = {
                "batches": [
                    BatchStatusResponse.from_domain(b).model_dump(mode="json") for b in batches
                ],
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "total": len(batches),  # Would include total count in production
                },
            }

            import json

            response_json = json.dumps(response_data)

            # Cache the response if caching is enabled
            if settings.CACHE_ENABLED:
                await cache_manager.set_user_batches_json(
                    user_id, limit, offset, status, response_json, settings.REDIS_CACHE_TTL_SECONDS
                )

            metrics.api_requests_total.labels(
                endpoint="get_user_batches", method="GET", status_code=200
            ).inc()

            return Response(response_json, mimetype="application/json"), 200

        except Exception as e:
            logger.error(
                "Error retrieving user batches", user_id=user_id, error=str(e), exc_info=True
            )
            metrics.api_errors_total.labels(
                endpoint="get_user_batches", error_type="internal"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500
