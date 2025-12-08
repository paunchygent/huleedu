"""BFF Teacher Service proxy routes.

Forwards all /bff/v1/teacher/* requests to the BFF Teacher Service.
Follows the same proxy pattern as class_routes.py.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Request
from httpx import AsyncClient
from starlette.responses import StreamingResponse

from huleedu_service_libs.error_handling import raise_external_service_error
from huleedu_service_libs.logging_utils import create_service_logger
from services.api_gateway_service.config import settings

from ..protocols import MetricsProtocol

router = APIRouter(route_class=DishkaRoute)
logger = create_service_logger("api_gateway.bff_teacher_routes")


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
    summary="BFF Teacher Service Proxy",
    description="Proxy all teacher BFF requests to the BFF Teacher Service",
    response_description="Response from BFF Teacher Service",
    responses={
        200: {
            "description": "Successful operation (varies by endpoint)",
            "content": {
                "application/json": {
                    "examples": {
                        "dashboard": {
                            "summary": "GET /dashboard - Teacher dashboard",
                            "value": {"batches": [], "total_count": 0},
                        }
                    }
                }
            },
        },
        401: {
            "description": "Authentication required",
            "content": {
                "application/json": {
                    "example": {
                        "error_type": "AuthenticationError",
                        "message": "Valid JWT token required",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                    }
                }
            },
        },
        503: {
            "description": "Service temporarily unavailable",
            "content": {
                "application/json": {
                    "example": {
                        "error_type": "ExternalServiceError",
                        "message": "BFF Teacher Service temporarily unavailable",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                        "external_service": "bff_teacher",
                        "retry_recommended": True,
                    }
                }
            },
        },
    },
)
async def proxy_bff_teacher_requests(
    path: str,
    request: Request,
    http_client: FromDishka[AsyncClient],
    metrics: FromDishka[MetricsProtocol],
    user_id: FromDishka[str],
    org_id: FromDishka[str | None],
    correlation_id: FromDishka[UUID],
):
    """Proxy all BFF Teacher requests to the BFF Teacher Service.

    This endpoint acts as a transparent proxy for all teacher BFF operations,
    forwarding requests to the BFF Teacher Service while providing authentication,
    rate limiting, and comprehensive error handling.

    **Authentication**: Requires valid JWT token in Authorization header (Bearer format)

    **Proxy Behavior**:
    - All request headers are preserved (except 'host')
    - Request body is streamed to avoid memory issues with large payloads
    - Response is streamed back with original status codes and headers
    - Identity headers (X-User-ID, X-Correlation-ID, X-Org-ID) are injected
    """
    url = f"{settings.BFF_TEACHER_URL}/bff/v1/teacher/{path}"
    endpoint = f"/bff/v1/teacher/{path}"

    logger.info(f"Proxying {request.method} request to BFF Teacher Service: {endpoint}")

    with metrics.http_request_duration_seconds.labels(
        method=request.method, endpoint=endpoint
    ).time():
        try:
            # Prepare the request to be forwarded with identity headers
            headers = {
                **request.headers,
                "X-User-ID": user_id,
                "X-Correlation-ID": str(correlation_id),
            }
            if org_id:
                headers["X-Org-ID"] = org_id
            headers.pop("host", None)  # Let httpx set the host

            # Time the downstream service call
            with metrics.downstream_service_call_duration_seconds.labels(
                service="bff_teacher", method=request.method, endpoint=f"/bff/v1/teacher/{path}"
            ).time():
                # Stream the request body
                req = http_client.build_request(
                    method=request.method,
                    url=url,
                    headers=headers,
                    params=request.query_params,
                    content=request.stream(),
                )

                # Send the request and stream the response back
                r = await http_client.send(req, stream=True)

            # Record downstream service call
            metrics.downstream_service_calls_total.labels(
                service="bff_teacher",
                method=request.method,
                endpoint=f"/bff/v1/teacher/{path}",
                status_code=str(r.status_code),
            ).inc()

            # Record HTTP response
            metrics.http_requests_total.labels(
                method=request.method, endpoint=endpoint, http_status=str(r.status_code)
            ).inc()

            logger.info(
                f"Proxied {request.method} request completed: {endpoint}, status: {r.status_code}"
            )

            return StreamingResponse(
                r.aiter_raw(),
                status_code=r.status_code,
                headers=r.headers,
            )

        except Exception as e:
            logger.error(
                f"Error proxying {request.method} request to {endpoint}: {e}", exc_info=True
            )
            metrics.http_requests_total.labels(
                method=request.method, endpoint=endpoint, http_status="503"
            ).inc()
            metrics.api_errors_total.labels(endpoint=endpoint, error_type="proxy_error").inc()

            correlation_id_str = request.headers.get("x-correlation-id", str(uuid4()))
            try:
                corr_id = UUID(correlation_id_str)
            except ValueError:
                corr_id = uuid4()
            raise_external_service_error(
                service="api_gateway_service",
                operation=f"proxy_{request.method.lower()}_bff_teacher_request",
                external_service="bff_teacher",
                message=f"Error proxying request to BFF Teacher Service: {str(e)}",
                correlation_id=corr_id,
                path=path,
                method=request.method,
            )
