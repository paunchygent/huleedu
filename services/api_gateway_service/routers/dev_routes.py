"""
Development routes for API Gateway Service.

Provides mock data endpoints and utilities optimized for Svelte 5 + Vite frontend development.
Only available in development environment for security isolation.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field

from common_core.status_enums import BatchStatus, EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("api_gateway.dev_routes")
router = APIRouter(tags=["Development"])


class MockNotificationRequest(BaseModel):
    """Request model for triggering mock WebSocket notifications."""

    notification_type: str = Field(description="Type of notification to trigger")
    payload: dict[str, Any] | None = Field(
        default=None, description="Optional payload data for the notification"
    )
    user_id: str | None = Field(default=None, description="Target user ID (optional)")


class TestTokenRequest(BaseModel):
    """Request model for generating test JWT tokens."""

    user_type: Literal["teacher", "student", "admin"] = Field(
        default="teacher", description="Type of user for the token"
    )
    class_id: str | None = Field(default=None, description="Associated class ID (optional)")
    expires_minutes: int = Field(
        default=60, description="Token expiration time in minutes", ge=1, le=1440
    )
    custom_claims: dict[str, Any] | None = Field(
        default=None, description="Custom JWT claims for testing specific scenarios"
    )


@router.get("/mock/classes")
async def get_mock_classes() -> dict[str, Any]:
    """Return mock class data optimized for Svelte 5 $state() runes.

    Provides realistic class data with various states for UI testing.
    Structure optimized for reactive Svelte 5 patterns.
    """
    return {
        "classes": [
            {
                "id": "class-001",
                "name": "Advanced Writing Workshop",
                "description": "Senior-level creative writing and essay composition",
                "teacher_id": "teacher-001",
                "student_count": 28,
                "active_batches": 3,
                "completed_batches": 12,
                "created_at": "2024-09-01T10:00:00Z",
                "updated_at": "2024-11-15T14:30:00Z",
                "status": "active",
            },
            {
                "id": "class-002",
                "name": "Freshman Composition",
                "description": "Introduction to academic writing and research",
                "teacher_id": "teacher-001",
                "student_count": 35,
                "active_batches": 1,
                "completed_batches": 8,
                "created_at": "2024-09-01T11:00:00Z",
                "updated_at": "2024-11-20T09:15:00Z",
                "status": "active",
            },
            {
                "id": "class-003",
                "name": "Technical Writing",
                "description": "Business and technical communication skills",
                "teacher_id": "teacher-002",
                "student_count": 22,
                "active_batches": 2,
                "completed_batches": 6,
                "created_at": "2024-09-15T13:00:00Z",
                "updated_at": "2024-11-18T16:45:00Z",
                "status": "active",
            },
        ],
        "metadata": {
            "total_classes": 3,
            "total_students": 85,
            "total_active_batches": 6,
            "generated_at": datetime.now(UTC).isoformat(),
        },
    }


@router.get("/mock/students/{class_id}")
async def get_mock_students(class_id: str) -> dict[str, Any]:
    """Return mock student data for a specific class.

    Provides student roster data with realistic variations for different UI states.
    """
    if class_id not in ["class-001", "class-002", "class-003"]:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Mock class {class_id} not found"
        )

    base_students = [
        {
            "id": f"student-{i:03d}",
            "name": f"Student {i:03d}",
            "email": f"student{i:03d}@university.edu",
            "class_id": class_id,
            "enrolled_at": "2024-09-01T10:00:00Z",
            "essays_submitted": max(0, i % 8),
            "essays_processed": max(0, (i % 8) - 1),
            "status": "active" if i % 10 != 0 else "inactive",
        }
        for i in range(1, 26)  # 25 students per class
    ]

    return {
        "students": base_students,
        "metadata": {
            "class_id": class_id,
            "total_students": len(base_students),
            "active_students": len([s for s in base_students if s["status"] == "active"]),
            "generated_at": datetime.now(UTC).isoformat(),
        },
    }


@router.get("/mock/essays/{status}")
async def get_mock_essays_by_status(status: str) -> dict[str, Any]:
    """Return mock essays filtered by processing status.

    Provides essay data for different processing states to test UI workflows.
    """
    # Validate status against actual enum values
    try:
        essay_status = EssayStatus(status)
    except ValueError:
        valid_statuses = [s.value for s in EssayStatus]
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{status}'. Valid statuses: {valid_statuses}",
        ) from None

    # Generate mock essays with the specified status
    essays = [
        {
            "id": f"essay-{status}-{i:03d}",
            "filename": f"Essay_{i:03d}_{status}.docx",
            "student_id": f"student-{(i % 25) + 1:03d}",
            "batch_id": f"batch-{(i % 3) + 1:03d}",
            "class_id": f"class-{((i % 3) + 1):03d}",
            "status": status,
            "word_count": 500 + (i * 50),
            "uploaded_at": (datetime.now(UTC) - timedelta(hours=i)).isoformat(),
            "last_updated": datetime.now(UTC).isoformat(),
            "processing_phases": {
                "spellcheck": "completed" if essay_status != EssayStatus.UPLOADED else "pending",
                "ai_feedback": "in_progress" if "ai_feedback" in status else "pending",
                "cj_assessment": "pending",
            },
        }
        for i in range(1, 11)  # 10 essays per status
    ]

    return {
        "essays": essays,
        "metadata": {
            "status_filter": status,
            "total_count": len(essays),
            "generated_at": datetime.now(UTC).isoformat(),
        },
    }


@router.get("/mock/batches")
async def get_mock_batches() -> dict[str, Any]:
    """Return mock batch processing data with various states.

    Provides comprehensive batch data covering all processing states for UI testing.
    """
    batches = []

    # Generate batches across different statuses
    for i, batch_status in enumerate(BatchStatus, 1):
        batches.append(
            {
                "id": f"batch-{i:03d}",
                "name": f"Batch {i:03d} - {batch_status.value.replace('_', ' ').title()}",
                "class_id": f"class-{((i % 3) + 1):03d}",
                "teacher_id": f"teacher-{((i % 2) + 1):03d}",
                "status": batch_status.value,
                "essay_count": max(1, i % 15),
                "processed_essays": max(0, (i % 15) - 2),
                "failed_essays": 1 if "failed" in batch_status.value else 0,
                "created_at": (datetime.now(UTC) - timedelta(days=i)).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
                "pipeline_progress": {
                    "spellcheck": 85 if i % 4 == 0 else 100,
                    "ai_feedback": 60 if i % 3 == 0 else 0,
                    "cj_assessment": 30 if i % 5 == 0 else 0,
                },
            }
        )

    return {
        "batches": batches,
        "metadata": {
            "total_batches": len(batches),
            "status_distribution": {bs.value: 1 for bs in BatchStatus},
            "generated_at": datetime.now(UTC).isoformat(),
        },
    }


@router.get("/mock/reactive-state")
async def get_mock_reactive_state() -> dict[str, Any]:
    """Return mock state data structured for Svelte 5 reactive patterns.

    Optimized data structure for Svelte 5 runes ($state, $derived, $effect).
    Includes loading states, error states, and reactive data patterns.
    """
    return {
        "app_state": {
            "user": {
                "id": "teacher-001",
                "name": "Dr. Sarah Johnson",
                "email": "s.johnson@university.edu",
                "role": "teacher",
                "preferences": {
                    "theme": "light",
                    "notifications_enabled": True,
                    "auto_refresh": True,
                },
            },
            "loading_states": {
                "batches_loading": False,
                "essays_loading": True,
                "websocket_connecting": False,
            },
            "error_states": {
                "last_error": None,
                "network_error": False,
                "validation_errors": [],
            },
            "ui_state": {
                "selected_class_id": "class-001",
                "active_tab": "batches",
                "sidebar_collapsed": False,
                "modal_open": False,
            },
        },
        "reactive_counters": {
            "total_essays": 150,
            "processing_essays": 23,
            "completed_essays": 127,
            "active_batches": 6,
            "unread_notifications": 3,
        },
        "real_time_updates": {
            "last_update": datetime.now(UTC).isoformat(),
            "update_frequency": 5000,  # milliseconds
            "websocket_status": "connected",
        },
        "metadata": {
            "optimized_for": "Svelte 5 runes ($state, $derived, $effect)",
            "generated_at": datetime.now(UTC).isoformat(),
        },
    }


@router.post("/mock/websocket/trigger")
async def trigger_mock_notification(request: MockNotificationRequest) -> dict[str, Any]:
    """Trigger WebSocket notifications optimized for Svelte 5 reactive updates.

    Simulates real-time notifications for testing frontend reactive patterns.
    """
    notification_id = str(uuid4())
    timestamp = datetime.now(UTC).isoformat()

    # Generate realistic notification based on type
    # Ensure payload is a dict for safe mutation
    payload: dict[str, Any] = dict(request.payload or {})
    notification_data = {
        "notification_id": notification_id,
        "type": request.notification_type,
        "timestamp": timestamp,
        "user_id": request.user_id or "teacher-001",
        "payload": payload,
    }

    # Add type-specific mock data
    if request.notification_type == "batch_completed":
        payload.update(
            {
                "batch_id": "batch-001",
                "total_essays": 25,
                "success_count": 23,
                "failure_count": 2,
            }
        )
    elif request.notification_type == "essay_status_update":
        payload.update(
            {
                "essay_id": "essay-001",
                "old_status": "spellchecking_in_progress",
                "new_status": "spellchecked_success",
            }
        )
    elif request.notification_type == "pipeline_progress":
        payload.update(
            {
                "batch_id": "batch-002",
                "phase": "ai_feedback",
                "progress_percentage": 65,
                "estimated_completion": (
                    datetime.now(UTC) + timedelta(minutes=15)
                ).isoformat(),
            }
        )

    logger.info(f"Mock WebSocket notification triggered: {request.notification_type}")

    return {
        "triggered": True,
        "notification": notification_data,
        "message": f"Mock {request.notification_type} notification triggered successfully",
        "svelte5_integration": {
            "reactive_pattern": "$effect(() => { /* handle notification */ })",
            "state_update": "$state.notifications.unshift(notification)",
        },
    }


@router.post("/auth/test-token")
async def generate_test_token(request: TestTokenRequest) -> dict[str, Any]:
    """Generate a test JWT token for development with configurable claims.

    Creates realistic JWT tokens for testing authentication flows in development.
    """
    # Generate mock JWT payload
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=request.expires_minutes)

    base_claims = {
        "user_id": f"{request.user_type}-001",
        "email": f"test.{request.user_type}@university.edu",
        "role": request.user_type,
        "name": f"Test {request.user_type.title()}",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": "huledu-api-gateway",
        "sub": f"{request.user_type}-001",
    }

    if request.class_id:
        base_claims["class_id"] = request.class_id
        base_claims["class_name"] = f"Test Class {request.class_id}"

    if request.custom_claims:
        base_claims.update(request.custom_claims)

    # Generate a mock JWT token (in real implementation, would use actual JWT library)
    mock_token = f"mock-jwt-{secrets.token_urlsafe(32)}"

    logger.info(f"Test JWT token generated for {request.user_type} user")

    return {
        "access_token": mock_token,
        "token_type": "bearer",
        "expires_in": request.expires_minutes * 60,
        "expires_at": exp.isoformat(),
        "claims": base_claims,
        "usage": {
            "header": f"Authorization: Bearer {mock_token}",
            "curl_example": f'curl -H "Authorization: Bearer {mock_token}" http://localhost:4001/api/health',
        },
        "note": "This is a mock token for development only. Use with existing auth middleware.",
    }
