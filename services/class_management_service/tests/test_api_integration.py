"""Integration tests for the Class Management Service API."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from common_core.domain_enums import CourseCode
from services.class_management_service.app import app
from services.class_management_service.protocols import (
    ClassManagementServiceProtocol,
)


class TestClassManagementApi:
    @pytest.fixture
    def mock_class_management_service(self) -> AsyncMock:
        """Create a mock for the class management service."""
        return AsyncMock(spec=ClassManagementServiceProtocol)

    @pytest.fixture
    async def app_client(
        self, mock_class_management_service: AsyncMock
    ) -> AsyncGenerator[QuartTestClient, None]:
        """Return a Quart test client configured with a mocked service."""

        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_class_management_service(
                self,
            ) -> ClassManagementServiceProtocol:
                return mock_class_management_service

        container = make_async_container(TestProvider())

        app.config.update({"TESTING": True})
        QuartDishka(app=app, container=container)

        async with app.test_client() as client:
            yield client

        await container.close()

    @pytest.mark.asyncio
    async def test_health_check(self, app_client: QuartTestClient) -> None:
        """Test the health check endpoint."""
        response = await app_client.get("/healthz")
        assert response.status_code == 200
        data = await response.get_json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_create_class(
        self, app_client: QuartTestClient, mock_class_management_service: AsyncMock
    ) -> None:
        """Test creating a new class."""
        mock_class = AsyncMock()
        mock_class.id = "test-class-id"
        mock_class.name = "Test Class"
        mock_class_management_service.register_new_class.return_value = mock_class

        headers = {"X-User-ID": "test-user"}
        payload = {"name": "Test Class", "course_codes": [CourseCode.ENG5.value]}
        response = await app_client.post("/v1/classes/", json=payload, headers=headers)

        assert response.status_code == 201
        data = await response.get_json()
        assert data["id"] == "test-class-id"
        assert data["name"] == "Test Class"

    @pytest.mark.asyncio
    async def test_create_student(
        self, app_client: QuartTestClient, mock_class_management_service: AsyncMock
    ) -> None:
        """Test creating a new student."""
        mock_student = AsyncMock()
        mock_student.id = "test-student-id"
        mock_student.first_name = "Test"
        mock_student.last_name = "Student"
        mock_class_management_service.add_student_to_class.return_value = mock_student

        headers = {"X-User-ID": "test-user"}
        payload = {
            "person_name": {"first_name": "Test", "last_name": "Student"},
            "email": "test.student@example.com",
        }
        response = await app_client.post(
            "/v1/classes/students", json=payload, headers=headers
        )

        assert response.status_code == 201
        data = await response.get_json()
        assert data["id"] == "test-student-id"
        assert data["full_name"] == "Test Student"
