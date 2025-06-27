from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Request
from httpx import AsyncClient
from starlette.responses import StreamingResponse

from ..config import settings

router = APIRouter(route_class=DishkaRoute)


@router.api_route("/classes/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_class_requests(
    path: str,
    request: Request,
    http_client: FromDishka[AsyncClient],
):
    """Proxies all /classes requests to the Class Management Service."""
    url = f"{settings.CMS_API_URL}/v1/classes/{path}"

    # Prepare the request to be forwarded
    headers = dict(request.headers)
    headers.pop("host", None)  # Let httpx set the host

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

    return StreamingResponse(
        r.aiter_raw(),
        status_code=r.status_code,
        headers=r.headers,
    )
