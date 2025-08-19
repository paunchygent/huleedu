"""
Integration tests for internal API routes.

Tests the internal endpoints for student name resolution following the established
Quart+Dishka testing patterns.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core.metadata_models import PersonNameV1
from dishka import Provider, Scope, make_async_container, provide
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.class_management_service.app import app
from services.class_management_service.domain_handlers.student_name_handler import (
    BatchStudentNameItem,
    BatchStudentNamesResponse,
    EssayStudentAssociationResponse,
    StudentNameHandler,
)


class TestInternalRoutes:
    """Test internal API endpoints using proper Quart+Dishka patterns."""

    @pytest.fixture
    def mock_student_name_handler(self) -> AsyncMock:
        """Create mock student name handler."""
        return AsyncMock(spec=StudentNameHandler)

    @pytest.fixture
    def sample_batch_id(self) -> str:
        """Sample batch ID for testing."""
        return str(uuid4())

    @pytest.fixture
    def sample_essay_id(self) -> str:
        """Sample essay ID for testing."""
        return str(uuid4())

    @pytest.fixture
    def sample_student_id(self) -> UUID:
        """Sample student ID for testing."""
        return uuid4()

    @pytest.fixture
    def sample_person_name(self) -> PersonNameV1:
        """Create sample PersonNameV1 with Swedish characters."""
        return PersonNameV1(
            first_name="Åsa",
            last_name="Öberg",
            legal_full_name="Åsa Öberg",
        )

    @pytest.fixture
    def sample_batch_student_names_response(
        self,
        sample_essay_id: str,
        sample_student_id: UUID,
        sample_person_name: PersonNameV1,
    ) -> BatchStudentNamesResponse:
        """Create sample batch student names response."""
        items = [
            BatchStudentNameItem(
                essay_id=UUID(sample_essay_id),
                student_id=sample_student_id,
                student_person_name=sample_person_name,
            )
        ]
        return BatchStudentNamesResponse(items=items)

    @pytest.fixture
    def sample_essay_association_response(
        self,
        sample_essay_id: str,
        sample_student_id: UUID,
        sample_person_name: PersonNameV1,
    ) -> EssayStudentAssociationResponse:
        """Create sample essay student association response."""
        return EssayStudentAssociationResponse(
            essay_id=UUID(sample_essay_id),
            student_id=sample_student_id,
            student_person_name=sample_person_name,
        )

    @pytest.fixture
    async def app_client(
        self,
        mock_student_name_handler: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """
        Return a Quart test client configured with mocked dependencies using Dishka.
        This fixture overrides production providers with test providers that supply our mocks.
        """

        # 1. Define a test-specific provider that provides our mocks
        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_student_name_handler(self) -> StudentNameHandler:
                return mock_student_name_handler

        # 2. Create a new container with our test provider
        container = make_async_container(TestProvider())

        # 3. Apply the container to the app instance for the test
        app.config.update({"TESTING": True})
        QuartDishka(app=app, container=container)

        async with app.test_client() as client:
            yield client

        # 4. Clean up the container after the test
        await container.close()

    class TestGetBatchStudentNames:
        """Tests for GET /internal/v1/batches/{batch_id}/student-names endpoint."""

        async def test_returns_student_names_when_associations_exist(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
            sample_batch_id: str,
            sample_batch_student_names_response: BatchStudentNamesResponse,
        ) -> None:
            """Should return 200 with PersonNameV1 list when associations exist."""
            # Arrange
            mock_student_name_handler.get_batch_student_names.return_value = (
                sample_batch_student_names_response
            )

            # Act
            response = await app_client.get(f"/internal/v1/batches/{sample_batch_id}/student-names")

            # Assert
            assert response.status_code == 200
            data = await response.get_json()
            assert isinstance(data, list)
            assert len(data) == 1

            student_item = data[0]
            assert "essay_id" in student_item
            assert "student_id" in student_item
            assert "student_person_name" in student_item

            person_name = student_item["student_person_name"]
            assert person_name["first_name"] == "Åsa"
            assert person_name["last_name"] == "Öberg"
            assert person_name["legal_full_name"] == "Åsa Öberg"

            # Verify handler was called with correct arguments
            mock_student_name_handler.get_batch_student_names.assert_called_once()
            call_args = mock_student_name_handler.get_batch_student_names.call_args[0]
            assert call_args[0] == sample_batch_id
            # Second argument should be UUID (correlation_id)
            assert isinstance(call_args[1], UUID)

        async def test_returns_empty_list_when_no_associations(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
            sample_batch_id: str,
        ) -> None:
            """Should return 200 with empty list when batch has no associations."""
            # Arrange
            empty_response = BatchStudentNamesResponse(items=[])
            mock_student_name_handler.get_batch_student_names.return_value = empty_response

            # Act
            response = await app_client.get(f"/internal/v1/batches/{sample_batch_id}/student-names")

            # Assert
            assert response.status_code == 200
            data = await response.get_json()
            assert isinstance(data, list)
            assert len(data) == 0

            # Verify handler was called
            mock_student_name_handler.get_batch_student_names.assert_called_once()

        async def test_returns_400_for_invalid_batch_id(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
        ) -> None:
            """Should return 400 for invalid batch UUID."""
            # Arrange
            from huleedu_service_libs.error_handling import raise_validation_error

            def raise_validation(*_: Any, **__: Any) -> None:
                raise_validation_error(
                    service="class_management_service",
                    operation="get_batch_student_names",
                    field="batch_id",
                    message="Invalid batch_id format",
                    correlation_id=uuid4(),
                )

            mock_student_name_handler.get_batch_student_names.side_effect = raise_validation
            invalid_batch_id = "not-a-uuid"

            # Act
            response = await app_client.get(
                f"/internal/v1/batches/{invalid_batch_id}/student-names"
            )

            # Assert
            assert response.status_code == 400
            data = await response.get_json()
            assert "error" in data

        async def test_handles_correlation_id_from_headers(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
            sample_batch_id: str,
            sample_batch_student_names_response: BatchStudentNamesResponse,
        ) -> None:
            """Should use correlation ID from X-Correlation-ID header."""
            # Arrange
            correlation_id = uuid4()
            mock_student_name_handler.get_batch_student_names.return_value = (
                sample_batch_student_names_response
            )

            # Act
            response = await app_client.get(
                f"/internal/v1/batches/{sample_batch_id}/student-names",
                headers={"X-Correlation-ID": str(correlation_id)},
            )

            # Assert
            assert response.status_code == 200
            # Verify handler was called with the provided correlation ID
            call_args = mock_student_name_handler.get_batch_student_names.call_args[0]
            assert call_args[1] == correlation_id

        async def test_generates_correlation_id_if_missing(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
            sample_batch_id: str,
            sample_batch_student_names_response: BatchStudentNamesResponse,
        ) -> None:
            """Should generate correlation ID if not provided in headers."""
            # Arrange
            mock_student_name_handler.get_batch_student_names.return_value = (
                sample_batch_student_names_response
            )

            # Act
            response = await app_client.get(f"/internal/v1/batches/{sample_batch_id}/student-names")

            # Assert
            assert response.status_code == 200
            # Verify handler was called with a generated UUID
            call_args = mock_student_name_handler.get_batch_student_names.call_args[0]
            assert isinstance(call_args[1], UUID)

        async def test_handles_multiple_students_with_unicode_names(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
            sample_batch_id: str,
        ) -> None:
            """Should handle multiple students with Unicode characters in names correctly."""
            # Arrange
            items = [
                BatchStudentNameItem(
                    essay_id=uuid4(),
                    student_id=uuid4(),
                    student_person_name=PersonNameV1(
                        first_name="François",
                        last_name="Müller",
                        legal_full_name="François Müller",
                    ),
                ),
                BatchStudentNameItem(
                    essay_id=uuid4(),
                    student_id=uuid4(),
                    student_person_name=PersonNameV1(
                        first_name="José",
                        last_name="García",
                        legal_full_name="José García",
                    ),
                ),
            ]
            unicode_response = BatchStudentNamesResponse(items=items)
            mock_student_name_handler.get_batch_student_names.return_value = unicode_response

            # Act
            response = await app_client.get(f"/internal/v1/batches/{sample_batch_id}/student-names")

            # Assert
            assert response.status_code == 200
            data = await response.get_json()
            assert len(data) == 2

            # Check first student
            assert data[0]["student_person_name"]["first_name"] == "François"
            assert data[0]["student_person_name"]["last_name"] == "Müller"

            # Check second student
            assert data[1]["student_person_name"]["first_name"] == "José"
            assert data[1]["student_person_name"]["last_name"] == "García"

        async def test_handles_processing_error_from_handler(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
            sample_batch_id: str,
        ) -> None:
            """Should return 400 when handler raises processing error."""
            # Arrange
            from huleedu_service_libs.error_handling import raise_processing_error

            def raise_processing(*_: Any, **__: Any) -> None:
                raise_processing_error(
                    service="class_management_service",
                    operation="get_batch_student_names",
                    message="Database connection failed",
                    correlation_id=uuid4(),
                )

            mock_student_name_handler.get_batch_student_names.side_effect = raise_processing

            # Act
            response = await app_client.get(f"/internal/v1/batches/{sample_batch_id}/student-names")

            # Assert
            assert response.status_code == 400
            data = await response.get_json()
            assert "error" in data

    class TestGetEssayStudentAssociation:
        """Tests for GET /internal/v1/associations/essay/{essay_id} endpoint."""

        async def test_returns_association_when_exists(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
            sample_essay_id: str,
            sample_essay_association_response: EssayStudentAssociationResponse,
        ) -> None:
            """Should return 200 with PersonNameV1 when association exists."""
            # Arrange
            mock_student_name_handler.get_essay_student_association.return_value = (
                sample_essay_association_response
            )

            # Act
            response = await app_client.get(f"/internal/v1/associations/essay/{sample_essay_id}")

            # Assert
            assert response.status_code == 200
            data = await response.get_json()
            assert "essay_id" in data
            assert "student_id" in data
            assert "student_person_name" in data

            person_name = data["student_person_name"]
            assert person_name["first_name"] == "Åsa"
            assert person_name["last_name"] == "Öberg"
            assert person_name["legal_full_name"] == "Åsa Öberg"

            # Verify handler was called with correct arguments
            mock_student_name_handler.get_essay_student_association.assert_called_once()
            call_args = mock_student_name_handler.get_essay_student_association.call_args[0]
            assert call_args[0] == sample_essay_id
            # Second argument should be UUID (correlation_id)
            assert isinstance(call_args[1], UUID)

        async def test_returns_404_when_association_not_found(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
            sample_essay_id: str,
        ) -> None:
            """Should return 404 when essay association not found."""
            # Arrange
            mock_student_name_handler.get_essay_student_association.return_value = None

            # Act
            response = await app_client.get(f"/internal/v1/associations/essay/{sample_essay_id}")

            # Assert
            assert response.status_code == 404
            data = await response.get_json()
            assert "error" in data
            assert data["error"] == "Essay student association not found"

            # Verify handler was called
            mock_student_name_handler.get_essay_student_association.assert_called_once()

        async def test_returns_400_for_invalid_essay_id(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
        ) -> None:
            """Should return 400 for invalid essay UUID."""
            # Arrange
            from huleedu_service_libs.error_handling import raise_validation_error

            def raise_validation(*_: Any, **__: Any) -> None:
                raise_validation_error(
                    service="class_management_service",
                    operation="get_essay_student_association",
                    field="essay_id",
                    message="Invalid essay_id format",
                    correlation_id=uuid4(),
                )

            mock_student_name_handler.get_essay_student_association.side_effect = raise_validation
            invalid_essay_id = "not-a-uuid"

            # Act
            response = await app_client.get(f"/internal/v1/associations/essay/{invalid_essay_id}")

            # Assert
            assert response.status_code == 400
            data = await response.get_json()
            assert "error" in data

        async def test_handles_correlation_id_from_headers(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
            sample_essay_id: str,
            sample_essay_association_response: EssayStudentAssociationResponse,
        ) -> None:
            """Should use correlation ID from X-Correlation-ID header."""
            # Arrange
            correlation_id = uuid4()
            mock_student_name_handler.get_essay_student_association.return_value = (
                sample_essay_association_response
            )

            # Act
            response = await app_client.get(
                f"/internal/v1/associations/essay/{sample_essay_id}",
                headers={"X-Correlation-ID": str(correlation_id)},
            )

            # Assert
            assert response.status_code == 200
            # Verify handler was called with the provided correlation ID
            call_args = mock_student_name_handler.get_essay_student_association.call_args[0]
            assert call_args[1] == correlation_id

        async def test_generates_correlation_id_if_missing(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
            sample_essay_id: str,
            sample_essay_association_response: EssayStudentAssociationResponse,
        ) -> None:
            """Should generate correlation ID if not provided in headers."""
            # Arrange
            mock_student_name_handler.get_essay_student_association.return_value = (
                sample_essay_association_response
            )

            # Act
            response = await app_client.get(f"/internal/v1/associations/essay/{sample_essay_id}")

            # Assert
            assert response.status_code == 200
            # Verify handler was called with a generated UUID
            call_args = mock_student_name_handler.get_essay_student_association.call_args[0]
            assert isinstance(call_args[1], UUID)

        async def test_handles_unicode_names_in_response(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
            sample_essay_id: str,
        ) -> None:
            """Should handle Unicode characters in names correctly."""
            # Arrange
            unicode_response = EssayStudentAssociationResponse(
                essay_id=UUID(sample_essay_id),
                student_id=uuid4(),
                student_person_name=PersonNameV1(
                    first_name="François",
                    last_name="Müller",
                    legal_full_name="François Müller",
                ),
            )
            mock_student_name_handler.get_essay_student_association.return_value = unicode_response

            # Act
            response = await app_client.get(f"/internal/v1/associations/essay/{sample_essay_id}")

            # Assert
            assert response.status_code == 200
            data = await response.get_json()
            assert data["student_person_name"]["first_name"] == "François"
            assert data["student_person_name"]["last_name"] == "Müller"

        async def test_handles_processing_error_from_handler(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
            sample_essay_id: str,
        ) -> None:
            """Should return 400 when handler raises processing error."""
            # Arrange
            from huleedu_service_libs.error_handling import raise_processing_error

            def raise_processing(*_: Any, **__: Any) -> None:
                raise_processing_error(
                    service="class_management_service",
                    operation="get_essay_student_association",
                    message="Database connection failed",
                    correlation_id=uuid4(),
                )

            mock_student_name_handler.get_essay_student_association.side_effect = raise_processing

            # Act
            response = await app_client.get(f"/internal/v1/associations/essay/{sample_essay_id}")

            # Assert
            assert response.status_code == 400
            data = await response.get_json()
            assert "error" in data

        @pytest.mark.parametrize(
            "invalid_essay_id",
            [
                "not-a-uuid",
                "123-456-789",
                "completely-invalid",
            ],
        )
        async def test_returns_400_for_various_invalid_essay_ids(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
            invalid_essay_id: str,
        ) -> None:
            """Should return 400 for various invalid UUID formats."""
            # Arrange
            from huleedu_service_libs.error_handling import raise_validation_error

            def raise_validation(*_: Any, **__: Any) -> None:
                raise_validation_error(
                    service="class_management_service",
                    operation="get_essay_student_association",
                    field="essay_id",
                    message=f"Invalid essay_id format: {invalid_essay_id}",
                    correlation_id=uuid4(),
                )

            mock_student_name_handler.get_essay_student_association.side_effect = raise_validation

            # Act
            response = await app_client.get(f"/internal/v1/associations/essay/{invalid_essay_id}")

            # Assert
            assert response.status_code == 400
            data = await response.get_json()
            assert "error" in data

        async def test_handles_invalid_correlation_id_header(
            self,
            app_client: QuartTestClient,
            mock_student_name_handler: AsyncMock,
            sample_essay_id: str,
            sample_essay_association_response: EssayStudentAssociationResponse,
        ) -> None:
            """Should generate new correlation ID if provided one is invalid."""
            # Arrange
            mock_student_name_handler.get_essay_student_association.return_value = (
                sample_essay_association_response
            )

            # Act
            response = await app_client.get(
                f"/internal/v1/associations/essay/{sample_essay_id}",
                headers={"X-Correlation-ID": "invalid-uuid"},
            )

            # Assert
            assert response.status_code == 200
            # Verify handler was called with a generated UUID (not the invalid one)
            call_args = mock_student_name_handler.get_essay_student_association.call_args[0]
            assert isinstance(call_args[1], UUID)
