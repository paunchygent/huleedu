"""API routes for Class Management Service."""

from __future__ import annotations

import uuid

from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from services.class_management_service.api_models import (
    CreateClassRequest,
    UpdateClassRequest,
)
from services.class_management_service.metrics import CmsMetrics
from services.class_management_service.models_db import Student, UserClass
from services.class_management_service.protocols import ClassManagementServiceProtocol
from services.class_management_service.exceptions import (
    CourseNotFoundError,
    MultipleCourseError,
    ClassManagementServiceError,
)

logger = create_service_logger("class_management_service.api.class")
class_bp = Blueprint("class_routes", __name__)


@class_bp.route("/", methods=["POST"])
@inject
async def create_class(
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
    metrics: FromDishka[CmsMetrics],
) -> Response | tuple[Response, int]:
    """Create a new class."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    with metrics.http_request_duration_seconds.labels(
        method="POST", endpoint="/v1/classes/"
    ).time():
        try:
            data = await request.get_json()
            create_request = CreateClassRequest(**data)
            correlation_id = uuid.uuid4()  # Generate correlation ID

            new_class = await service.register_new_class(user_id, create_request, correlation_id)
            metrics.http_requests_total.labels(
                method="POST", endpoint="/v1/classes/", http_status=201
            ).inc()
            metrics.class_creations_total.inc()
            return jsonify({"id": str(new_class.id), "name": new_class.name}), 201
        except CourseNotFoundError as e:
            logger.warning(f"Course not found during class creation: {e.message}")
            metrics.http_requests_total.labels(
                method="POST", endpoint="/v1/classes/", http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint="/v1/classes/", error_type="course_not_found"
            ).inc()
            return jsonify({"error": e.message, "error_code": e.error_code}), 400
        except MultipleCourseError as e:
            logger.warning(f"Multiple courses provided during class creation: {e.message}")
            metrics.http_requests_total.labels(
                method="POST", endpoint="/v1/classes/", http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint="/v1/classes/", error_type="multiple_course_error"
            ).inc()
            return jsonify({"error": e.message, "error_code": e.error_code}), 400
        except ClassManagementServiceError as e:
            logger.warning(f"Class management service error during creation: {e.message}")
            metrics.http_requests_total.labels(
                method="POST", endpoint="/v1/classes/", http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint="/v1/classes/", error_type="service_error"
            ).inc()
            return jsonify({"error": e.message, "error_code": e.error_code}), 400
        except Exception as e:
            logger.error(f"Error creating class: {e}", exc_info=True)
            metrics.http_requests_total.labels(
                method="POST", endpoint="/v1/classes/", http_status=500
            ).inc()
            metrics.api_errors_total.labels(
                endpoint="/v1/classes/", error_type="server_error"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500


@class_bp.route("/<class_id>", methods=["GET"])
@inject
async def get_class(
    class_id: str,
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
    metrics: FromDishka[CmsMetrics],
) -> Response | tuple[Response, int]:
    """Retrieve a class by ID."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    with metrics.http_request_duration_seconds.labels(
        method="GET", endpoint=f"/v1/classes/{class_id}"
    ).time():
        try:
            class_uuid = uuid.UUID(class_id)
            class_obj = await service.get_class_by_id(class_uuid)

            if not class_obj:
                metrics.http_requests_total.labels(
                    method="GET", endpoint=f"/v1/classes/{class_id}", http_status=404
                ).inc()
                metrics.api_errors_total.labels(
                    endpoint=f"/v1/classes/{class_id}", error_type="not_found"
                ).inc()
                return jsonify({"error": "Class not found"}), 404

            metrics.http_requests_total.labels(
                method="GET", endpoint=f"/v1/classes/{class_id}", http_status=200
            ).inc()
            return jsonify(
                {
                    "id": str(class_obj.id),
                    "name": class_obj.name,
                    "course_code": class_obj.course.course_code if class_obj.course else None,
                }
            ), 200
        except ValueError:
            metrics.http_requests_total.labels(
                method="GET", endpoint=f"/v1/classes/{class_id}", http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/{class_id}", error_type="bad_request"
            ).inc()
            return jsonify({"error": "Invalid class ID format"}), 400
        except Exception as e:
            logger.error(f"Error retrieving class: {e}", exc_info=True)
            metrics.http_requests_total.labels(
                method="GET", endpoint=f"/v1/classes/{class_id}", http_status=500
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/{class_id}", error_type="server_error"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500


@class_bp.route("/<class_id>", methods=["PUT"])
@inject
async def update_class(
    class_id: str,
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
    metrics: FromDishka[CmsMetrics],
) -> Response | tuple[Response, int]:
    """Update a class."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    with metrics.http_request_duration_seconds.labels(
        method="PUT", endpoint=f"/v1/classes/{class_id}"
    ).time():
        try:
            class_uuid = uuid.UUID(class_id)
            data = await request.get_json()
            update_request = UpdateClassRequest(**data)
            correlation_id = uuid.uuid4()

            updated_class = await service.update_class(
                user_id, class_uuid, update_request, correlation_id
            )

            if not updated_class:
                metrics.http_requests_total.labels(
                    method="PUT", endpoint=f"/v1/classes/{class_id}", http_status=404
                ).inc()
                metrics.api_errors_total.labels(
                    endpoint=f"/v1/classes/{class_id}", error_type="not_found"
                ).inc()
                return jsonify({"error": "Class not found"}), 404

            metrics.http_requests_total.labels(
                method="PUT", endpoint=f"/v1/classes/{class_id}", http_status=200
            ).inc()
            return jsonify(
                {
                    "id": str(updated_class.id),
                    "name": updated_class.name,
                    "course_code": updated_class.course.course_code
                    if updated_class.course
                    else None,
                }
            ), 200
        except ValueError:
            metrics.http_requests_total.labels(
                method="PUT", endpoint=f"/v1/classes/{class_id}", http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/{class_id}", error_type="bad_request"
            ).inc()
            return jsonify({"error": "Invalid class ID format"}), 400
        except CourseNotFoundError as e:
            logger.warning(f"Course not found during class update: {e.message}")
            metrics.http_requests_total.labels(
                method="PUT", endpoint=f"/v1/classes/{class_id}", http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/{class_id}", error_type="course_not_found"
            ).inc()
            return jsonify({"error": e.message, "error_code": e.error_code}), 400
        except MultipleCourseError as e:
            logger.warning(f"Multiple courses provided during class update: {e.message}")
            metrics.http_requests_total.labels(
                method="PUT", endpoint=f"/v1/classes/{class_id}", http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/{class_id}", error_type="multiple_course_error"
            ).inc()
            return jsonify({"error": e.message, "error_code": e.error_code}), 400
        except ClassManagementServiceError as e:
            logger.warning(f"Class management service error during update: {e.message}")
            metrics.http_requests_total.labels(
                method="PUT", endpoint=f"/v1/classes/{class_id}", http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/{class_id}", error_type="service_error"
            ).inc()
            return jsonify({"error": e.message, "error_code": e.error_code}), 400
        except Exception as e:
            logger.error(f"Error updating class: {e}", exc_info=True)
            metrics.http_requests_total.labels(
                method="PUT", endpoint=f"/v1/classes/{class_id}", http_status=500
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/{class_id}", error_type="server_error"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500


@class_bp.route("/<class_id>", methods=["DELETE"])
@inject
async def delete_class(
    class_id: str,
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
    metrics: FromDishka[CmsMetrics],
) -> Response | tuple[Response, int]:
    """Delete a class."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    with metrics.http_request_duration_seconds.labels(
        method="DELETE", endpoint=f"/v1/classes/{class_id}"
    ).time():
        try:
            class_uuid = uuid.UUID(class_id)
            deleted = await service.delete_class(class_uuid)

            if not deleted:
                metrics.http_requests_total.labels(
                    method="DELETE", endpoint=f"/v1/classes/{class_id}", http_status=404
                ).inc()
                metrics.api_errors_total.labels(
                    endpoint=f"/v1/classes/{class_id}", error_type="not_found"
                ).inc()
                return jsonify({"error": "Class not found"}), 404

            metrics.http_requests_total.labels(
                method="DELETE", endpoint=f"/v1/classes/{class_id}", http_status=200
            ).inc()
            return jsonify({"message": "Class deleted successfully"}), 200
        except ValueError:
            metrics.http_requests_total.labels(
                method="DELETE", endpoint=f"/v1/classes/{class_id}", http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/{class_id}", error_type="bad_request"
            ).inc()
            return jsonify({"error": "Invalid class ID format"}), 400
        except Exception as e:
            logger.error(f"Error deleting class: {e}", exc_info=True)
            metrics.http_requests_total.labels(
                method="DELETE", endpoint=f"/v1/classes/{class_id}", http_status=500
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/{class_id}", error_type="server_error"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500
