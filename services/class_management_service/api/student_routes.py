"""API routes for Student Management in Class Management Service."""

from __future__ import annotations

import uuid

from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from services.class_management_service.api_models import (
    CreateStudentRequest,
    UpdateStudentRequest,
)
from services.class_management_service.metrics import CmsMetrics
from services.class_management_service.models_db import Student, UserClass
from services.class_management_service.protocols import ClassManagementServiceProtocol

logger = create_service_logger("class_management_service.api.student")
student_bp = Blueprint("student_routes", __name__)


@student_bp.route("/students", methods=["POST"])
@inject
async def add_student_to_class(
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
    metrics: FromDishka[CmsMetrics],
) -> Response | tuple[Response, int]:
    """Create a new student and associate with classes."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    with metrics.http_request_duration_seconds.labels(
        method="POST", endpoint="/v1/classes/students"
    ).time():
        try:
            data = await request.get_json()
            create_request = CreateStudentRequest(**data)
            correlation_id = uuid.uuid4()

            new_student = await service.add_student_to_class(
                user_id, create_request, correlation_id
            )

            metrics.http_requests_total.labels(
                method="POST", endpoint="/v1/classes/students", http_status=201
            ).inc()
            metrics.student_creations_total.inc()
            return (
                jsonify(
                    {
                        "id": str(new_student.id),
                        "full_name": f"{new_student.first_name} {new_student.last_name}",
                    }
                ),
                201,
            )
        except Exception as e:
            logger.error(f"Error creating student: {e}", exc_info=True)
            metrics.http_requests_total.labels(
                method="POST", endpoint="/v1/classes/students", http_status=500
            ).inc()
            metrics.api_errors_total.labels(
                endpoint="/v1/classes/students", error_type="server_error"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500


@student_bp.route("/students/<student_id>", methods=["GET"])
@inject
async def get_student(
    student_id: str,
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
    metrics: FromDishka[CmsMetrics],
) -> Response | tuple[Response, int]:
    """Retrieve a student by ID."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    with metrics.http_request_duration_seconds.labels(
        method="GET", endpoint=f"/v1/classes/students/{student_id}"
    ).time():
        try:
            student_uuid = uuid.UUID(student_id)
            student_obj = await service.get_student_by_id(student_uuid)

            if not student_obj:
                metrics.http_requests_total.labels(
                    method="GET", endpoint=f"/v1/classes/students/{student_id}", http_status=404
                ).inc()
                metrics.api_errors_total.labels(
                    endpoint=f"/v1/classes/students/{student_id}", error_type="not_found"
                ).inc()
                return jsonify({"error": "Student not found"}), 404

            metrics.http_requests_total.labels(
                method="GET", endpoint=f"/v1/classes/students/{student_id}", http_status=200
            ).inc()
            return jsonify(
                {
                    "id": str(student_obj.id),
                    "first_name": student_obj.first_name,
                    "last_name": student_obj.last_name,
                    "email": student_obj.email,
                    "class_ids": [str(c.id) for c in student_obj.classes],
                }
            ), 200
        except ValueError:
            metrics.http_requests_total.labels(
                method="GET", endpoint=f"/v1/classes/students/{student_id}", http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/students/{student_id}", error_type="bad_request"
            ).inc()
            return jsonify({"error": "Invalid student ID format"}), 400
        except Exception as e:
            logger.error(f"Error retrieving student: {e}", exc_info=True)
            metrics.http_requests_total.labels(
                method="GET", endpoint=f"/v1/classes/students/{student_id}", http_status=500
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/students/{student_id}", error_type="server_error"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500


@student_bp.route("/students/<student_id>", methods=["PUT"])
@inject
async def update_student(
    student_id: str,
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
    metrics: FromDishka[CmsMetrics],
) -> Response | tuple[Response, int]:
    """Update a student."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    with metrics.http_request_duration_seconds.labels(
        method="PUT", endpoint=f"/v1/classes/students/{student_id}"
    ).time():
        try:
            student_uuid = uuid.UUID(student_id)
            data = await request.get_json()
            update_request = UpdateStudentRequest(**data)
            correlation_id = uuid.uuid4()

            updated_student = await service.update_student(
                user_id, student_uuid, update_request, correlation_id
            )

            if not updated_student:
                metrics.http_requests_total.labels(
                    method="PUT", endpoint=f"/v1/classes/students/{student_id}", http_status=404
                ).inc()
                metrics.api_errors_total.labels(
                    endpoint=f"/v1/classes/students/{student_id}", error_type="not_found"
                ).inc()
                return jsonify({"error": "Student not found"}), 404

            metrics.http_requests_total.labels(
                method="PUT", endpoint=f"/v1/classes/students/{student_id}", http_status=200
            ).inc()
            return jsonify(
                {
                    "id": str(updated_student.id),
                    "first_name": updated_student.first_name,
                    "last_name": updated_student.last_name,
                    "email": updated_student.email,
                    "class_ids": [str(c.id) for c in updated_student.classes],
                }
            ), 200
        except ValueError:
            metrics.http_requests_total.labels(
                method="PUT", endpoint=f"/v1/classes/students/{student_id}", http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/students/{student_id}", error_type="bad_request"
            ).inc()
            return jsonify({"error": "Invalid student ID format"}), 400
        except Exception as e:
            logger.error(f"Error updating student: {e}", exc_info=True)
            metrics.http_requests_total.labels(
                method="PUT", endpoint=f"/v1/classes/students/{student_id}", http_status=500
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/students/{student_id}", error_type="server_error"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500


@student_bp.route("/students/<student_id>", methods=["DELETE"])
@inject
async def delete_student(
    student_id: str,
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
    metrics: FromDishka[CmsMetrics],
) -> Response | tuple[Response, int]:
    """Delete a student."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    with metrics.http_request_duration_seconds.labels(
        method="DELETE", endpoint=f"/v1/classes/students/{student_id}"
    ).time():
        try:
            student_uuid = uuid.UUID(student_id)
            deleted = await service.delete_student(student_uuid)

            if not deleted:
                metrics.http_requests_total.labels(
                    method="DELETE", endpoint=f"/v1/classes/students/{student_id}", http_status=404
                ).inc()
                metrics.api_errors_total.labels(
                    endpoint=f"/v1/classes/students/{student_id}", error_type="not_found"
                ).inc()
                return jsonify({"error": "Student not found"}), 404

            metrics.http_requests_total.labels(
                method="DELETE", endpoint=f"/v1/classes/students/{student_id}", http_status=200
            ).inc()
            return jsonify({"message": "Student deleted successfully"}), 200
        except ValueError:
            metrics.http_requests_total.labels(
                method="DELETE", endpoint=f"/v1/classes/students/{student_id}", http_status=400
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/students/{student_id}", error_type="bad_request"
            ).inc()
            return jsonify({"error": "Invalid student ID format"}), 400
        except Exception as e:
            logger.error(f"Error deleting student: {e}", exc_info=True)
            metrics.http_requests_total.labels(
                method="DELETE", endpoint=f"/v1/classes/students/{student_id}", http_status=500
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=f"/v1/classes/students/{student_id}", error_type="server_error"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500
