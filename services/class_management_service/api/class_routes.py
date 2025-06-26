"""API routes for Class Management Service."""

from __future__ import annotations

import uuid

from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from services.class_management_service.api_models import (
    CreateClassRequest,
    CreateStudentRequest,
    UpdateClassRequest,
    UpdateStudentRequest,
)
from services.class_management_service.models_db import Student, UserClass
from services.class_management_service.protocols import ClassManagementServiceProtocol

logger = create_service_logger("class_management_service.api.class")
class_bp = Blueprint("class_routes", __name__)


@class_bp.route("/", methods=["POST"])
@inject
async def create_class(
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
) -> Response | tuple[Response, int]:
    """Create a new class."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    try:
        data = await request.get_json()
        create_request = CreateClassRequest(**data)
        correlation_id = uuid.uuid4()  # Generate correlation ID

        new_class = await service.register_new_class(
            user_id, create_request, correlation_id
        )

        return jsonify({"id": str(new_class.id), "name": new_class.name}), 201
    except Exception as e:
        logger.error(f"Error creating class: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@class_bp.route("/<class_id>", methods=["GET"])
@inject
async def get_class(
    class_id: str,
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
) -> Response | tuple[Response, int]:
    """Retrieve a class by ID."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    try:
        class_uuid = uuid.UUID(class_id)
        class_obj = await service.get_class_by_id(class_uuid)

        if not class_obj:
            return jsonify({"error": "Class not found"}), 404

        return jsonify({
            "id": str(class_obj.id),
            "name": class_obj.name,
            "course_code": class_obj.course.course_code if class_obj.course else None
        }), 200
    except ValueError:
        return jsonify({"error": "Invalid class ID format"}), 400
    except Exception as e:
        logger.error(f"Error retrieving class: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@class_bp.route("/<class_id>", methods=["PUT"])
@inject
async def update_class(
    class_id: str,
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
) -> Response | tuple[Response, int]:
    """Update a class."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    try:
        class_uuid = uuid.UUID(class_id)
        data = await request.get_json()
        update_request = UpdateClassRequest(**data)
        correlation_id = uuid.uuid4()

        updated_class = await service.update_class(
            user_id, class_uuid, update_request, correlation_id
        )

        if not updated_class:
            return jsonify({"error": "Class not found"}), 404

        return jsonify({
            "id": str(updated_class.id),
            "name": updated_class.name,
            "course_code": updated_class.course.course_code if updated_class.course else None
        }), 200
    except ValueError:
        return jsonify({"error": "Invalid class ID format"}), 400
    except Exception as e:
        logger.error(f"Error updating class: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@class_bp.route("/<class_id>", methods=["DELETE"])
@inject
async def delete_class(
    class_id: str,
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
) -> Response | tuple[Response, int]:
    """Delete a class."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    try:
        class_uuid = uuid.UUID(class_id)
        deleted = await service.delete_class(class_uuid)

        if not deleted:
            return jsonify({"error": "Class not found"}), 404

        return jsonify({"message": "Class deleted successfully"}), 200
    except ValueError:
        return jsonify({"error": "Invalid class ID format"}), 400
    except Exception as e:
        logger.error(f"Error deleting class: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@class_bp.route("/students", methods=["POST"])
@inject
async def create_student(
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
) -> Response | tuple[Response, int]:
    """Create a new student and associate with classes."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    try:
        data = await request.get_json()
        create_request = CreateStudentRequest(**data)
        correlation_id = uuid.uuid4()

        new_student = await service.add_student_to_class(
            user_id, create_request, correlation_id
        )

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
        return jsonify({"error": "Internal server error"}), 500


@class_bp.route("/students/<student_id>", methods=["GET"])
@inject
async def get_student(
    student_id: str,
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
) -> Response | tuple[Response, int]:
    """Retrieve a student by ID."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    try:
        student_uuid = uuid.UUID(student_id)
        student_obj = await service.get_student_by_id(student_uuid)

        if not student_obj:
            return jsonify({"error": "Student not found"}), 404

        return jsonify({
            "id": str(student_obj.id),
            "first_name": student_obj.first_name,
            "last_name": student_obj.last_name,
            "email": student_obj.email,
            "class_ids": [str(c.id) for c in student_obj.classes]
        }), 200
    except ValueError:
        return jsonify({"error": "Invalid student ID format"}), 400
    except Exception as e:
        logger.error(f"Error retrieving student: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@class_bp.route("/students/<student_id>", methods=["PUT"])
@inject
async def update_student(
    student_id: str,
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
) -> Response | tuple[Response, int]:
    """Update a student."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    try:
        student_uuid = uuid.UUID(student_id)
        data = await request.get_json()
        update_request = UpdateStudentRequest(**data)
        correlation_id = uuid.uuid4()

        updated_student = await service.update_student(
            user_id, student_uuid, update_request, correlation_id
        )

        if not updated_student:
            return jsonify({"error": "Student not found"}), 404

        return jsonify({
            "id": str(updated_student.id),
            "first_name": updated_student.first_name,
            "last_name": updated_student.last_name,
            "email": updated_student.email,
            "class_ids": [str(c.id) for c in updated_student.classes]
        }), 200
    except ValueError:
        return jsonify({"error": "Invalid student ID format"}), 400
    except Exception as e:
        logger.error(f"Error updating student: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@class_bp.route("/students/<student_id>", methods=["DELETE"])
@inject
async def delete_student(
    student_id: str,
    service: FromDishka[ClassManagementServiceProtocol[UserClass, Student]],
) -> Response | tuple[Response, int]:
    """Delete a student."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        return jsonify({"error": "User authentication required"}), 401

    try:
        student_uuid = uuid.UUID(student_id)
        deleted = await service.delete_student(student_uuid)

        if not deleted:
            return jsonify({"error": "Student not found"}), 404

        return jsonify({"message": "Student deleted successfully"}), 200
    except ValueError:
        return jsonify({"error": "Invalid student ID format"}), 400
    except Exception as e:
        logger.error(f"Error deleting student: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
