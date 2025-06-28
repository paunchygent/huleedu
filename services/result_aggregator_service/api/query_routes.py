"""Internal API routes for querying aggregated results."""
from typing import Optional
from uuid import uuid4

from dishka.integrations.quart import FromDishka, inject
from quart import Blueprint, Response, g, jsonify, request

from huleedu_service_libs.logging_utils import create_service_logger

from ..metrics import ResultAggregatorMetrics
from ..models_api import BatchStatusResponse, ErrorResponse
from ..protocols import (
    BatchQueryServiceProtocol,
    SecurityServiceProtocol
)


logger = create_service_logger("result_aggregator.api.query")

query_bp = Blueprint("query", __name__, url_prefix="/internal/v1")


@query_bp.before_request
@inject
async def authenticate_request(
    security: FromDishka[SecurityServiceProtocol]
) -> Optional[Response]:
    """Authenticate internal service requests."""
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
    metrics: FromDishka[ResultAggregatorMetrics]
) -> Response:
    """Get comprehensive batch status including all essay results."""
    with metrics.api_request_duration.labels(
        endpoint="get_batch_status",
        method="GET"
    ).time():
        try:
            logger.info(
                "Batch status query",
                batch_id=batch_id,
                service_id=g.service_id,
                correlation_id=g.correlation_id
            )
            
            # Query the aggregated results
            result = await query_service.get_batch_status(batch_id)
            
            if not result:
                metrics.api_requests_total.labels(
                    endpoint="get_batch_status",
                    method="GET",
                    status_code=404
                ).inc()
                return jsonify({"error": "Batch not found"}), 404
                
            # Convert to API response model
            response = BatchStatusResponse.from_domain(result)
            
            metrics.api_requests_total.labels(
                endpoint="get_batch_status",
                method="GET", 
                status_code=200
            ).inc()
            
            return jsonify(response.model_dump(mode="json")), 200
            
        except ValueError as e:
            logger.error("Invalid batch ID", batch_id=batch_id, error=str(e))
            metrics.api_errors_total.labels(
                endpoint="get_batch_status",
                error_type="validation"
            ).inc()
            return jsonify({"error": "Invalid batch ID"}), 400
            
        except Exception as e:
            logger.error(
                "Error retrieving batch status",
                batch_id=batch_id,
                error=str(e),
                exc_info=True
            )
            metrics.api_errors_total.labels(
                endpoint="get_batch_status",
                error_type="internal"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500


@query_bp.route("/batches/user/<user_id>", methods=["GET"])
@inject
async def get_user_batches(
    user_id: str,
    query_service: FromDishka[BatchQueryServiceProtocol],
    metrics: FromDishka[ResultAggregatorMetrics]
) -> Response:
    """Get all batches for a specific user."""
    with metrics.api_request_duration.labels(
        endpoint="get_user_batches",
        method="GET"
    ).time():
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
                service_id=g.service_id
            )
            
            # Query batches
            batches = await query_service.get_user_batches(
                user_id=user_id,
                status=status,
                limit=limit,
                offset=offset
            )
            
            metrics.api_requests_total.labels(
                endpoint="get_user_batches",
                method="GET",
                status_code=200
            ).inc()
            
            return jsonify({
                "batches": [b.model_dump(mode="json") for b in batches],
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "total": len(batches)  # Would include total count in production
                }
            }), 200
            
        except Exception as e:
            logger.error(
                "Error retrieving user batches",
                user_id=user_id,
                error=str(e),
                exc_info=True
            )
            metrics.api_errors_total.labels(
                endpoint="get_user_batches",
                error_type="internal"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500
