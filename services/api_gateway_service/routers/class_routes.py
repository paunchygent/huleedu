from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Request
from httpx import AsyncClient
from starlette.responses import StreamingResponse

from huleedu_service_libs.logging_utils import create_service_logger

from ..app.metrics import GatewayMetrics
from ..config import settings

router = APIRouter(route_class=DishkaRoute)
logger = create_service_logger("api_gateway.class_routes")


@router.api_route("/classes/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_class_requests(
    path: str,
    request: Request,
    http_client: FromDishka[AsyncClient],
    metrics: FromDishka[GatewayMetrics],
):
    """Proxies all /classes requests to the Class Management Service."""
    url = f"{settings.CMS_API_URL}/v1/classes/{path}"
    endpoint = f"/classes/{path}"

    logger.info(f"Proxying {request.method} request to class management service: {endpoint}")

    with metrics.http_request_duration_seconds.labels(
        method=request.method, endpoint=endpoint
    ).time():
        try:
            # Prepare the request to be forwarded
            headers = dict(request.headers)
            headers.pop("host", None)  # Let httpx set the host

            # Time the downstream service call
            with metrics.downstream_service_call_duration_seconds.labels(
                service="class_management", method=request.method, endpoint=f"/v1/classes/{path}"
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
                service="class_management",
                method=request.method,
                endpoint=f"/v1/classes/{path}",
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
                method=request.method, endpoint=endpoint, http_status="500"
            ).inc()
            metrics.api_errors_total.labels(endpoint=endpoint, error_type="proxy_error").inc()
            raise
