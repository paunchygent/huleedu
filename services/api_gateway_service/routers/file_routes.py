"""
File upload routes for API Gateway Service.

Implements secure file upload proxy to the File Service with proper authentication.
"""

from __future__ import annotations

import httpx
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from huleedu_service_libs.logging_utils import create_service_logger
from services.api_gateway_service.config import settings

from ..app.metrics import GatewayMetrics
from ..app.rate_limiter import limiter
from ..auth import get_current_user_id

router = APIRouter(route_class=DishkaRoute)
logger = create_service_logger("api_gateway.file_routes")


@router.post("/files/batch", status_code=201)
@limiter.limit("5/minute")  # Lower limit for file uploads
async def upload_batch_files(
    request: Request,  # Required for rate limiting
    http_client: FromDishka[httpx.AsyncClient],
    metrics: FromDishka[GatewayMetrics],
    batch_id: str = Form(...),  # noqa: B008
    files: list[UploadFile] = File(...),  # noqa: B008
    user_id: str = Depends(get_current_user_id),  # noqa: B008
):
    """
    Proxy file uploads to the File Service with authentication and rate limiting.

    Streams multipart/form-data directly to the File Service while adding
    authentication headers and comprehensive error handling.
    """
    correlation_id = request.headers.get("x-correlation-id", "gateway-file-upload")
    endpoint = "/files/batch"

    logger.info(
        f"File upload request: batch_id='{batch_id}', "
        f"files_count={len(files)}, user_id='{user_id}', correlation_id='{correlation_id}'"
    )

    with metrics.http_request_duration_seconds.labels(method="POST", endpoint=endpoint).time():
        try:
            # Prepare multipart data for proxying to file service
            files_data = []
            for file in files:
                # Read file content - this could be memory intensive for large files
                # In production, consider streaming implementation
                content = await file.read()
                files_data.append(("files", (file.filename, content, file.content_type)))

            # Prepare form data
            form_data = {
                "batch_id": batch_id,
            }

            # Add authentication header for file service
            headers = {
                "X-User-ID": user_id,
                "X-Correlation-ID": correlation_id,
            }

            # Forward request to file service
            file_service_url = f"{settings.FILE_SERVICE_URL}/v1/files/batch"

            # Time the downstream service call
            with metrics.downstream_service_call_duration_seconds.labels(
                service="file_service", method="POST", endpoint="/v1/files/batch"
            ).time():
                response = await http_client.post(
                    file_service_url,
                    files=files_data,
                    data=form_data,
                    headers=headers,
                    timeout=60.0,  # Longer timeout for file uploads
                )

            # Record downstream service call
            metrics.downstream_service_calls_total.labels(
                service="file_service",
                method="POST",
                endpoint="/v1/files/batch",
                status_code=str(response.status_code),
            ).inc()

            # Handle different response status codes
            if response.status_code == 201:
                response_data = response.json()
                logger.info(
                    f"File upload successful: batch_id='{batch_id}', "
                    f"user_id='{user_id}', correlation_id='{correlation_id}'"
                )
                metrics.http_requests_total.labels(
                    method="POST", endpoint=endpoint, http_status="201"
                ).inc()
                return JSONResponse(status_code=201, content=response_data)
            elif response.status_code == 400:
                error_data = response.json()
                logger.warning(
                    f"File upload validation error: batch_id='{batch_id}', "
                    f"user_id='{user_id}', error='{error_data}'"
                )
                metrics.http_requests_total.labels(
                    method="POST", endpoint=endpoint, http_status="400"
                ).inc()
                metrics.api_errors_total.labels(
                    endpoint=endpoint, error_type="validation_error"
                ).inc()
                raise HTTPException(
                    status_code=400, detail=error_data.get("detail", "File validation failed")
                )
            elif response.status_code == 403:
                logger.warning(
                    f"File upload access denied: batch_id='{batch_id}', user_id='{user_id}'"
                )
                metrics.http_requests_total.labels(
                    method="POST", endpoint=endpoint, http_status="403"
                ).inc()
                metrics.api_errors_total.labels(endpoint=endpoint, error_type="access_denied").inc()
                raise HTTPException(
                    status_code=403,
                    detail="Access denied: You don't have permission to upload files to this batch",
                )
            elif response.status_code == 404:
                logger.warning(
                    f"File upload batch not found: batch_id='{batch_id}', user_id='{user_id}'"
                )
                metrics.http_requests_total.labels(
                    method="POST", endpoint=endpoint, http_status="404"
                ).inc()
                metrics.api_errors_total.labels(endpoint=endpoint, error_type="not_found").inc()
                raise HTTPException(status_code=404, detail="Batch not found")
            else:
                logger.error(
                    f"File service error: status={response.status_code}, "
                    f"batch_id='{batch_id}', user_id='{user_id}'"
                )
                metrics.http_requests_total.labels(
                    method="POST", endpoint=endpoint, http_status="503"
                ).inc()
                metrics.api_errors_total.labels(
                    endpoint=endpoint, error_type="downstream_service_error"
                ).inc()
                raise HTTPException(status_code=503, detail="File service temporarily unavailable")

        except httpx.TimeoutException:
            logger.error(
                f"File upload timeout: batch_id='{batch_id}', "
                f"user_id='{user_id}', correlation_id='{correlation_id}'"
            )
            metrics.http_requests_total.labels(
                method="POST", endpoint=endpoint, http_status="504"
            ).inc()
            metrics.api_errors_total.labels(endpoint=endpoint, error_type="timeout").inc()
            raise HTTPException(
                status_code=504, detail="File upload timeout - please try again with smaller files"
            ) from None
        except httpx.RequestError as e:
            logger.error(
                f"File service connection error: batch_id='{batch_id}', "
                f"user_id='{user_id}', error='{e}'"
            )
            metrics.http_requests_total.labels(
                method="POST", endpoint=endpoint, http_status="503"
            ).inc()
            metrics.api_errors_total.labels(endpoint=endpoint, error_type="connection_error").inc()
            raise HTTPException(status_code=503, detail="File service connection failed") from e
        except HTTPException:
            # Re-raise HTTPException without wrapping it
            raise
        except Exception as e:
            logger.error(
                f"Unexpected file upload error: batch_id='{batch_id}', "
                f"user_id='{user_id}', error='{e}'",
                exc_info=True,
            )
            metrics.http_requests_total.labels(
                method="POST", endpoint=endpoint, http_status="500"
            ).inc()
            metrics.api_errors_total.labels(endpoint=endpoint, error_type="internal_error").inc()
            raise HTTPException(
                status_code=500, detail="Internal server error during file upload"
            ) from e
