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
logger = create_service_logger("api_gateway.class_routes")


@router.api_route(
    "/classes/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
    summary="Class Management Proxy",
    description="Proxy all class management operations to the Class Management Service",
    response_description="Response from Class Management Service",
    responses={
        200: {
            "description": "Successful operation (varies by endpoint)",
            "content": {
                "application/json": {
                    "examples": {
                        "get_classes": {
                            "summary": "GET /classes - List user's classes",
                            "value": {
                                "classes": [
                                    {
                                        "class_id": "class_123",
                                        "name": "Advanced Writing",
                                        "description": "Advanced essay writing course",
                                        "created_at": "2024-01-15T10:30:00Z",
                                        "student_count": 25,
                                    }
                                ],
                                "total_count": 1,
                            },
                        },
                        "get_class_detail": {
                            "summary": "GET /classes/{class_id} - Get class details",
                            "value": {
                                "class_id": "class_123",
                                "name": "Advanced Writing",
                                "description": "Advanced essay writing course",
                                "created_at": "2024-01-15T10:30:00Z",
                                "updated_at": "2024-01-15T11:00:00Z",
                                "student_count": 25,
                                "students": [
                                    {
                                        "student_id": "student_456",
                                        "name": "John Doe",
                                        "email": "john@example.com",
                                        "enrolled_at": "2024-01-10T09:00:00Z",
                                    }
                                ],
                            },
                        },
                    }
                }
            },
        },
        201: {
            "description": "Resource created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "class_id": "class_789",
                        "name": "Creative Writing",
                        "description": "Creative writing workshop",
                        "created_at": "2024-01-15T12:00:00Z",
                        "message": "Class created successfully",
                    }
                }
            },
        },
        400: {
            "description": "Invalid request parameters",
            "content": {
                "application/json": {
                    "examples": {
                        "validation_error": {
                            "summary": "Missing required fields",
                            "value": {
                                "error_type": "ValidationError",
                                "message": "Class name is required",
                                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                                "field": "name",
                            },
                        },
                        "invalid_class_id": {
                            "summary": "Invalid class identifier",
                            "value": {
                                "error_type": "ValidationError",
                                "message": "Invalid class ID format",
                                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                                "field": "class_id",
                            },
                        },
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
        403: {
            "description": "Access forbidden - insufficient permissions",
            "content": {
                "application/json": {
                    "example": {
                        "error_type": "AuthorizationError",
                        "message": "User does not have permission to access this class",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                        "class_id": "class_123",
                        "user_id": "user_456",
                    }
                }
            },
        },
        404: {
            "description": "Class not found",
            "content": {
                "application/json": {
                    "example": {
                        "error_type": "ResourceNotFoundError",
                        "message": "Class not found",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                        "resource_type": "class",
                        "resource_id": "class_123",
                    }
                }
            },
        },
        409: {
            "description": "Conflict - resource already exists or operation not allowed",
            "content": {
                "application/json": {
                    "example": {
                        "error_type": "ConflictError",
                        "message": "Class with this name already exists",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                        "conflicting_field": "name",
                        "existing_class_id": "class_456",
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
                        "message": "Class Management Service temporarily unavailable",
                        "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                        "external_service": "class_management",
                        "retry_recommended": True,
                    }
                }
            },
        },
    },
)
async def proxy_class_requests(
    path: str,
    request: Request,
    http_client: FromDishka[AsyncClient],
    metrics: FromDishka[MetricsProtocol],
    user_id: FromDishka[str],
    org_id: FromDishka[str | None],
    correlation_id: FromDishka[UUID],
):
    """
    Proxy all class management operations to the Class Management Service.

    This endpoint acts as a transparent proxy for all class-related operations, forwarding
    requests to the Class Management Service while providing authentication, rate limiting,
    and comprehensive error handling. All HTTP methods (GET, POST, PUT, DELETE) are supported.

    **Authentication**: Requires valid JWT token in Authorization header (Bearer format)

    **Supported Operations**:
    - `GET /classes` - List user's classes
    - `GET /classes/{class_id}` - Get specific class details
    - `POST /classes` - Create a new class
    - `PUT /classes/{class_id}` - Update existing class
    - `DELETE /classes/{class_id}` - Delete a class
    - `GET /classes/{class_id}/students` - List class students
    - `POST /classes/{class_id}/students` - Add student to class
    - `DELETE /classes/{class_id}/students/{student_id}` - Remove student from class

    **Request/Response Flow**:
    1. Validate authentication and extract user context
    2. Forward request to Class Management Service with preserved headers and body
    3. Stream response back to client with original status codes and headers
    4. Record metrics for monitoring and observability

    **Class Management Features**:
    - Create and manage writing classes
    - Enroll and manage students
    - Set class-specific writing assignments
    - Track student progress and submissions
    - Generate class-level analytics and reports

    **Error Handling**:
    - Authentication failures return 401
    - Authorization failures (class ownership) return 403
    - Missing classes return 404
    - Validation errors return 400 with detailed field information
    - Conflicts (duplicate names) return 409
    - Service unavailability returns 503 with retry recommendation

    **Client Implementation Examples**:

    **List Classes**:
    ```javascript
    const response = await fetch('/api/classes', {
        headers: {
            'Authorization': 'Bearer ' + token
        }
    });
    const { classes } = await response.json();
    ```

    **Create Class**:
    ```javascript
    const response = await fetch('/api/classes', {
        method: 'POST',
        headers: {
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            name: 'Advanced Writing',
            description: 'Advanced essay writing course',
            max_students: 30
        })
    });
    ```

    **Update Class**:
    ```javascript
    const response = await fetch(`/api/classes/${classId}`, {
        method: 'PUT',
        headers: {
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            name: 'Updated Class Name',
            description: 'Updated description'
        })
    });
    ```

    **Proxy Behavior**:
    - All request headers are preserved (except 'host')
    - Request body is streamed to avoid memory issues with large payloads
    - Response is streamed back with original status codes and headers
    - Comprehensive metrics are recorded for monitoring
    - Correlation IDs are preserved for request tracing
    """
    url = f"{settings.CMS_API_URL}/v1/classes/{path}"
    endpoint = f"/classes/{path}"

    logger.info(f"Proxying {request.method} request to class management service: {endpoint}")

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
                method=request.method, endpoint=endpoint, http_status="503"
            ).inc()
            metrics.api_errors_total.labels(endpoint=endpoint, error_type="proxy_error").inc()

            correlation_id_str = request.headers.get("x-correlation-id", str(uuid4()))
            try:
                correlation_id = UUID(correlation_id_str)
            except ValueError:
                correlation_id = uuid4()
            raise_external_service_error(
                service="api_gateway_service",
                operation=f"proxy_{request.method.lower()}_class_request",
                external_service="class_management",
                message=f"Error proxying request to class management service: {str(e)}",
                correlation_id=correlation_id,
                path=path,
                method=request.method,
            )
