"""
File upload routes for API Gateway Service.

Implements secure file upload proxy to the File Service with proper authentication.
"""

from __future__ import annotations

from uuid import UUID

import httpx
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile

from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_authentication_error,
    raise_connection_error,
    raise_external_service_error,
    raise_resource_not_found,
    raise_timeout_error,
    raise_unknown_error,
    raise_validation_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from services.api_gateway_service.config import settings
from services.api_gateway_service.protocols import HttpClientProtocol, MetricsProtocol

from ..app.rate_limiter import limiter

router = APIRouter()
logger = create_service_logger("api_gateway.file_routes")


@router.post("/files/batch", status_code=201)
@limiter.limit("5/minute")  # Lower limit for file uploads
@inject
async def upload_batch_files(
    request: Request,  # Required for rate limiting and form parsing
    http_client: FromDishka[HttpClientProtocol],
    metrics: FromDishka[MetricsProtocol],
    user_id: FromDishka[str],  # Provided by AuthProvider.provide_user_id
    correlation_id: FromDishka[UUID],  # Provided by AuthProvider.provide_correlation_id
):
    """
    Proxy file uploads to the File Service with authentication and rate limiting.

    Streams multipart/form-data directly to the File Service while adding
    authentication headers and comprehensive error handling.
    """
    # Parse form data using FastAPI's native capabilities (not Dishka DI)
    try:
        form = await request.form()

        # Extract and validate batch_id
        batch_id = form.get("batch_id")
        if not batch_id:
            raise_validation_error(
                service="api_gateway_service",
                operation="upload_batch_files",
                field="batch_id",
                message="batch_id is required in form data",
                correlation_id=correlation_id,
            )

        # Extract and validate files from form
        files: list[UploadFile] = []

        # Get all files from the form - FastAPI can handle multiple files under same field name
        form_files = form.getlist("files")
        for file_item in form_files:
            if isinstance(file_item, UploadFile):
                files.append(file_item)

        if not files:
            raise_validation_error(
                service="api_gateway_service",
                operation="upload_batch_files",
                field="files",
                message="At least one file is required",
                correlation_id=correlation_id,
            )

    except HuleEduError:
        # Re-raise our structured errors
        raise
    except Exception as e:
        # Wrap unexpected form parsing errors
        logger.error(f"Form parsing failed: {e}", exc_info=True)
        raise_validation_error(
            service="api_gateway_service",
            operation="upload_batch_files",
            field="form",
            message=f"Failed to parse form data: {str(e)}",
            correlation_id=correlation_id,
            error_type=type(e).__name__,
        )

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
                files_data.append(
                    (
                        "files",
                        (
                            file.filename or "unnamed",
                            content,
                            file.content_type or "application/octet-stream",
                        ),
                    )
                )

            # Prepare form data
            form_data = {
                "batch_id": str(batch_id),
            }

            # Add authentication header for file service
            headers = {
                "X-User-ID": user_id,
                "X-Correlation-ID": str(correlation_id),
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
                raise_validation_error(
                    service="api_gateway_service",
                    operation="upload_batch_files",
                    field="files",
                    message=error_data.get("detail", "File validation failed"),
                    correlation_id=correlation_id,
                )
            elif response.status_code == 403:
                logger.warning(
                    f"File upload access denied: batch_id='{batch_id}', user_id='{user_id}'"
                )
                metrics.http_requests_total.labels(
                    method="POST", endpoint=endpoint, http_status="403"
                ).inc()
                metrics.api_errors_total.labels(endpoint=endpoint, error_type="access_denied").inc()
                raise_authentication_error(
                    service="api_gateway_service",
                    operation="upload_batch_files",
                    message="Access denied: You don't have permission to upload files to this batch",
                    correlation_id=correlation_id,
                    reason="permission_denied",
                    batch_id=batch_id,
                    user_id=user_id,
                )
            elif response.status_code == 404:
                logger.warning(
                    f"File upload batch not found: batch_id='{batch_id}', user_id='{user_id}'"
                )
                metrics.http_requests_total.labels(
                    method="POST", endpoint=endpoint, http_status="404"
                ).inc()
                metrics.api_errors_total.labels(endpoint=endpoint, error_type="not_found").inc()
                raise_resource_not_found(
                    service="api_gateway_service",
                    operation="upload_batch_files",
                    resource_type="batch",
                    resource_id=str(batch_id),
                    correlation_id=correlation_id,
                )
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
                raise_external_service_error(
                    service="api_gateway_service",
                    operation="upload_batch_files",
                    external_service="file_service",
                    message="File service temporarily unavailable",
                    correlation_id=correlation_id,
                    status_code=response.status_code,
                )

        except httpx.TimeoutException:
            logger.error(
                f"File upload timeout: batch_id='{batch_id}', "
                f"user_id='{user_id}', correlation_id='{correlation_id}'"
            )
            metrics.http_requests_total.labels(
                method="POST", endpoint=endpoint, http_status="504"
            ).inc()
            metrics.api_errors_total.labels(endpoint=endpoint, error_type="timeout").inc()
            raise_timeout_error(
                service="api_gateway_service",
                operation="upload_batch_files",
                timeout_seconds=60.0,
                message="File upload timeout - please try again with smaller files",
                correlation_id=correlation_id,
            )
        except httpx.RequestError as e:
            logger.error(
                f"File service connection error: batch_id='{batch_id}', "
                f"user_id='{user_id}', error='{e}'"
            )
            metrics.http_requests_total.labels(
                method="POST", endpoint=endpoint, http_status="503"
            ).inc()
            metrics.api_errors_total.labels(endpoint=endpoint, error_type="connection_error").inc()
            raise_connection_error(
                service="api_gateway_service",
                operation="upload_batch_files",
                target="file_service",
                message=f"File service connection failed: {str(e)}",
                correlation_id=correlation_id,
            )
        except HuleEduError:
            # Re-raise HuleEduError without wrapping it
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
            raise_unknown_error(
                service="api_gateway_service",
                operation="upload_batch_files",
                message="Internal server error during file upload",
                correlation_id=correlation_id,
                error_type=type(e).__name__,
                error_details=str(e),
            )
