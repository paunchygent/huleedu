"""Integration tests for the Class Management Service API."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from common_core.domain_enums import CourseCode
from common_core.events.class_events import ClassUpdatedV1, StudentUpdatedV1
from common_core.events.envelope import EventEnvelope
from services.class_management_service.api_models import (
    UpdateClassRequest,
    UpdateStudentRequest,
)
from services.class_management_service.app import app
from services.class_management_service.implementations.class_management_service_impl import (
    ClassManagementServiceImpl,
)
from services.class_management_service.models_db import Student, UserClass
from services.class_management_service.protocols import (
    ClassEventPublisherProtocol,
    ClassManagementServiceProtocol,
    ClassRepositoryProtocol,
)


class TestClassManagementApi:
    @pytest.fixture
    def mock_class_repository(self) -> AsyncMock:
        """Create a mock for the class repository."""
        return AsyncMock(spec=ClassRepositoryProtocol)

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create a mock for the event publisher."""
        return AsyncMock(spec=ClassEventPublisherProtocol)

    @pytest.fixture
    async def app_client(
        self, mock_class_repository: AsyncMock, mock_event_publisher: AsyncMock
    ) -> AsyncGenerator[QuartTestClient, None]:
        """Return a Quart test client configured with mocked dependencies."""

        class TestProvider(Provider):
            @provide(scope=Scope.REQUEST)
            def provide_class_repository(self) -> ClassRepositoryProtocol:
                return mock_class_repository

            @provide(scope=Scope.REQUEST)
            def provide_event_publisher(self) -> ClassEventPublisherProtocol:
                return mock_event_publisher

            @provide(scope=Scope.REQUEST)
            def provide_class_management_service(
                self,
                repo: ClassRepositoryProtocol[UserClass, Student],
                publisher: ClassEventPublisherProtocol,
            ) -> ClassManagementServiceProtocol[UserClass, Student]:
                return ClassManagementServiceImpl[UserClass, Student](
                    repo=repo,
                    event_publisher=publisher,
                    user_class_type=UserClass,
                    student_type=Student,
                )

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
        self, app_client: QuartTestClient, mock_class_repository: AsyncMock
    ) -> None:
        """Test creating a new class."""
        mock_class = AsyncMock(spec=UserClass)
        mock_class.id = uuid.uuid4()
        mock_class.name = "Test Class"
        mock_course = AsyncMock()
        mock_course.course_code = CourseCode.ENG5
        mock_class.course = mock_course

        mock_class_repository.create_class.return_value = mock_class

        headers = {"X-User-ID": "test-user"}
        payload = {"name": "Test Class", "course_codes": [CourseCode.ENG5.value]}
        response = await app_client.post("/v1/classes/", json=payload, headers=headers)

        assert response.status_code == 201
        data = await response.get_json()
        assert data["id"] == str(mock_class.id)
        assert data["name"] == "Test Class"
        mock_class_repository.create_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_student(
        self, app_client: QuartTestClient, mock_class_repository: AsyncMock
    ) -> None:
        """Test creating a new student."""
        mock_student = AsyncMock(spec=Student)
        mock_student.id = uuid.uuid4()
        mock_student.first_name = "Test"
        mock_student.last_name = "Student"
        mock_student.email = "test.student@example.com"
        mock_student.classes = []  # Service expects an iterable
        mock_class_repository.create_student.return_value = mock_student

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
        assert data["id"] == str(mock_student.id)
        assert data["full_name"] == "Test Student"
        mock_class_repository.create_student.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_class_by_id(
        self, app_client: QuartTestClient, mock_class_repository: AsyncMock
    ) -> None:
        """Test retrieving a class by its ID."""
        class_id = uuid.uuid4()
        mock_class = AsyncMock(spec=UserClass)
        mock_class.id = class_id
        mock_class.name = "Found Class"
        mock_course = AsyncMock()
        mock_course.course_code = CourseCode.ENG5
        mock_class.course = mock_course

        mock_class_repository.get_class_by_id.return_value = mock_class

        headers = {"X-User-ID": "test-user"}
        response = await app_client.get(f"/v1/classes/{class_id}", headers=headers)

        assert response.status_code == 200
        data = await response.get_json()
        assert data["id"] == str(class_id)
        assert data["name"] == "Found Class"
        assert data["course_code"] == CourseCode.ENG5.value
        mock_class_repository.get_class_by_id.assert_called_once_with(class_id)

    @pytest.mark.asyncio
    async def test_get_class_by_id_not_found(
        self, app_client: QuartTestClient, mock_class_repository: AsyncMock
    ) -> None:
        """Test retrieving a class that does not exist."""
        class_id = uuid.uuid4()
        mock_class_repository.get_class_by_id.return_value = None

        headers = {"X-User-ID": "test-user"}
        response = await app_client.get(f"/v1/classes/{class_id}", headers=headers)

        assert response.status_code == 404
        mock_class_repository.get_class_by_id.assert_called_once_with(class_id)

    @pytest.mark.asyncio
    async def test_get_student_by_id(
        self, app_client: QuartTestClient, mock_class_repository: AsyncMock
    ) -> None:
        """Test retrieving a student by their ID."""
        student_id = uuid.uuid4()
        mock_student = AsyncMock(spec=Student)
        mock_student.id = student_id
        mock_student.first_name = "Jane"
        mock_student.last_name = "Doe"
        mock_student.email = "jane.doe@example.com"
        mock_student.classes = []
        mock_class_repository.get_student_by_id.return_value = mock_student

        headers = {"X-User-ID": "test-user"}
        response = await app_client.get(f"/v1/classes/students/{student_id}", headers=headers)

        assert response.status_code == 200
        data = await response.get_json()
        assert data["id"] == str(student_id)
        assert data["first_name"] == "Jane"
        mock_class_repository.get_student_by_id.assert_called_once_with(student_id)

    @pytest.mark.asyncio
    async def test_get_student_by_id_not_found(
        self, app_client: QuartTestClient, mock_class_repository: AsyncMock
    ) -> None:
        """Test retrieving a student that does not exist."""
        student_id = uuid.uuid4()
        mock_class_repository.get_student_by_id.return_value = None

        headers = {"X-User-ID": "test-user"}
        response = await app_client.get(f"/v1/classes/students/{student_id}", headers=headers)

        assert response.status_code == 404
        mock_class_repository.get_student_by_id.assert_called_once_with(student_id)

    @pytest.mark.asyncio
    async def test_update_class(
        self,
        app_client: QuartTestClient,
        mock_class_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test updating a class and verifying event publication."""
        class_id = uuid.uuid4()
        updated_class = AsyncMock(spec=UserClass)
        updated_class.id = class_id
        updated_class.name = "Updated Name"
        mock_course = AsyncMock()
        mock_course.course_code = CourseCode.SV1
        updated_class.course = mock_course
        mock_class_repository.update_class.return_value = updated_class

        headers = {"X-User-ID": "test-user"}
        payload = {"name": "Updated Name", "course_codes": [CourseCode.SV1.value]}
        response = await app_client.put(f"/v1/classes/{class_id}", json=payload, headers=headers)

        assert response.status_code == 200
        data = await response.get_json()
        assert data["name"] == "Updated Name"
        mock_class_repository.update_class.assert_called_once()
        mock_event_publisher.publish_class_event.assert_called_once()

        call_args = mock_event_publisher.publish_class_event.call_args[0][0]
        assert isinstance(call_args, EventEnvelope)
        assert isinstance(call_args.data, ClassUpdatedV1)
        assert call_args.data.class_id == str(class_id)
        assert call_args.data.class_designation == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_class_not_found(
        self, app_client: QuartTestClient, mock_class_repository: AsyncMock
    ) -> None:
        """Test updating a class that does not exist."""
        class_id = uuid.uuid4()
        mock_class_repository.update_class.return_value = None

        headers = {"X-User-ID": "test-user"}
        payload = {"name": "Updated Name"}
        response = await app_client.put(f"/v1/classes/{class_id}", json=payload, headers=headers)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_student(
        self,
        app_client: QuartTestClient,
        mock_class_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test updating a student and verifying event publication."""
        student_id = uuid.uuid4()
        updated_student = AsyncMock(spec=Student)
        updated_student.id = student_id
        updated_student.first_name = "John"
        updated_student.last_name = "Smith"
        updated_student.email = "john.smith@example.com"
        updated_student.classes = []
        mock_class_repository.update_student.return_value = updated_student

        headers = {"X-User-ID": "test-user"}
        payload = {"person_name": {"first_name": "John", "last_name": "Smith"}}
        response = await app_client.put(f"/v1/classes/students/{student_id}", json=payload, headers=headers)

        assert response.status_code == 200
        data = await response.get_json()
        assert data["first_name"] == "John"
        mock_class_repository.update_student.assert_called_once()
        mock_event_publisher.publish_class_event.assert_called_once()

        call_args = mock_event_publisher.publish_class_event.call_args[0][0]
        assert isinstance(call_args, EventEnvelope)
        assert isinstance(call_args.data, StudentUpdatedV1)
        assert call_args.data.student_id == str(student_id)
        assert call_args.data.first_name == "John"

    @pytest.mark.asyncio
    async def test_update_student_not_found(
        self, app_client: QuartTestClient, mock_class_repository: AsyncMock
    ) -> None:
        """Test updating a student that does not exist."""
        student_id = uuid.uuid4()
        mock_class_repository.update_student.return_value = None

        headers = {"X-User-ID": "test-user"}
        payload = {"person_name": {"first_name": "John", "last_name": "Smith"}}
        response = await app_client.put(f"/v1/classes/students/{student_id}", json=payload, headers=headers)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_class(
        self, app_client: QuartTestClient, mock_class_repository: AsyncMock
    ) -> None:
        """Test deleting a class successfully."""
        class_id = uuid.uuid4()
        mock_class_repository.delete_class.return_value = True

        headers = {"X-User-ID": "test-user"}
        response = await app_client.delete(f"/v1/classes/{class_id}", headers=headers)

        assert response.status_code == 200
        data = await response.get_json()
        assert data["message"] == "Class deleted successfully"
        mock_class_repository.delete_class.assert_called_once_with(class_id)

    @pytest.mark.asyncio
    async def test_delete_class_not_found(
        self, app_client: QuartTestClient, mock_class_repository: AsyncMock
    ) -> None:
        """Test deleting a class that does not exist."""
        class_id = uuid.uuid4()
        mock_class_repository.delete_class.return_value = False

        headers = {"X-User-ID": "test-user"}
        response = await app_client.delete(f"/v1/classes/{class_id}", headers=headers)

        assert response.status_code == 404
        mock_class_repository.delete_class.assert_called_once_with(class_id)

    @pytest.mark.asyncio
    async def test_delete_student(
        self, app_client: QuartTestClient, mock_class_repository: AsyncMock
    ) -> None:
        """Test deleting a student successfully."""
        student_id = uuid.uuid4()
        mock_class_repository.delete_student.return_value = True

        headers = {"X-User-ID": "test-user"}
        response = await app_client.delete(f"/v1/classes/students/{student_id}", headers=headers)

        assert response.status_code == 200
        data = await response.get_json()
        assert data["message"] == "Student deleted successfully"
        mock_class_repository.delete_student.assert_called_once_with(student_id)

    @pytest.mark.asyncio
    async def test_delete_student_not_found(
        self, app_client: QuartTestClient, mock_class_repository: AsyncMock
    ) -> None:
        """Test deleting a student that does not exist."""
        student_id = uuid.uuid4()
        mock_class_repository.delete_student.return_value = False

        headers = {"X-User-ID": "test-user"}
        response = await app_client.delete(f"/v1/classes/students/{student_id}", headers=headers)

        assert response.status_code == 404
        mock_class_repository.delete_student.assert_called_once_with(student_id)
