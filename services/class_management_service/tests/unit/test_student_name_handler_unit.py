"""
Unit tests for StudentNameHandler domain logic behavior.

Tests focus on business logic and behavior rather than implementation details.
Uses protocol-based mocking following established patterns.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core.metadata_models import PersonNameV1
from huleedu_service_libs.error_handling import HuleEduError

from services.class_management_service.domain_handlers.student_name_handler import (
    BatchStudentNameItem,
    BatchStudentNamesResponse,
    EssayStudentAssociationResponse,
    StudentNameHandler,
)
from services.class_management_service.protocols import ClassRepositoryProtocol


class TestStudentNameHandler:
    """Tests for StudentNameHandler business logic behavior."""

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock repository following protocol."""
        return AsyncMock(spec=ClassRepositoryProtocol)

    @pytest.fixture
    def handler(self, mock_repository: AsyncMock) -> StudentNameHandler:
        """Create handler with mocked repository."""
        return StudentNameHandler(repository=mock_repository)

    @pytest.fixture
    def batch_id(self) -> str:
        """Sample batch ID for testing."""
        return str(uuid4())

    @pytest.fixture
    def essay_id(self) -> str:
        """Sample essay ID for testing."""
        return str(uuid4())

    @pytest.fixture
    def correlation_id(self) -> UUID:
        """Sample correlation ID for testing."""
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
    def sample_batch_mapping(
        self, sample_person_name: PersonNameV1
    ) -> dict[str, UUID | PersonNameV1]:
        """Create sample batch mapping for testing."""
        return {
            "essay_id": uuid4(),
            "student_id": uuid4(),
            "student_person_name": sample_person_name,
        }

    @pytest.fixture
    def sample_essay_association(
        self, sample_person_name: PersonNameV1
    ) -> dict[str, UUID | PersonNameV1]:
        """Create sample essay association for testing."""
        return {
            "essay_id": uuid4(),
            "student_id": uuid4(),
            "student_person_name": sample_person_name,
        }

    class TestGetBatchStudentNames:
        """Tests for get_batch_student_names behavior."""

        async def test_returns_batch_response_when_associations_exist(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            batch_id: str,
            correlation_id: UUID,
            sample_person_name: PersonNameV1,
        ) -> None:
            """Should return BatchStudentNamesResponse with PersonNameV1 when associations exist."""
            essay_id = uuid4()
            student_id = uuid4()
            mapping = {
                "essay_id": essay_id,
                "student_id": student_id,
                "student_person_name": sample_person_name,
            }
            mock_repository.get_batch_student_names.return_value = [mapping]

            result = await handler.get_batch_student_names(batch_id, correlation_id)

            assert isinstance(result, BatchStudentNamesResponse)
            assert len(result.items) == 1

            item = result.items[0]
            assert isinstance(item, BatchStudentNameItem)
            assert item.essay_id == essay_id
            assert item.student_id == student_id
            assert isinstance(item.student_person_name, PersonNameV1)
            assert item.student_person_name.first_name == "Åsa"
            assert item.student_person_name.last_name == "Öberg"
            assert item.student_person_name.legal_full_name == "Åsa Öberg"

            mock_repository.get_batch_student_names.assert_called_once_with(
                UUID(batch_id), correlation_id
            )

        async def test_returns_batch_response_with_multiple_associations(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            batch_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should return BatchStudentNamesResponse with multiple items when multiple associations exist."""
            mappings = [
                {
                    "essay_id": uuid4(),
                    "student_id": uuid4(),
                    "student_person_name": PersonNameV1(
                        first_name="Åsa", last_name="Öberg", legal_full_name="Åsa Öberg"
                    ),
                },
                {
                    "essay_id": uuid4(),
                    "student_id": uuid4(),
                    "student_person_name": PersonNameV1(
                        first_name="Erik", last_name="Ångström", legal_full_name="Erik Ångström"
                    ),
                },
            ]
            mock_repository.get_batch_student_names.return_value = mappings

            result = await handler.get_batch_student_names(batch_id, correlation_id)

            assert isinstance(result, BatchStudentNamesResponse)
            assert len(result.items) == 2

            # Verify first item
            assert result.items[0].student_person_name.first_name == "Åsa"
            assert result.items[0].student_person_name.last_name == "Öberg"

            # Verify second item with different Swedish characters
            assert result.items[1].student_person_name.first_name == "Erik"
            assert result.items[1].student_person_name.last_name == "Ångström"

        async def test_returns_empty_list_when_no_associations(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            batch_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should return empty list when batch has no associations."""
            mock_repository.get_batch_student_names.return_value = []

            result = await handler.get_batch_student_names(batch_id, correlation_id)

            assert isinstance(result, BatchStudentNamesResponse)
            assert len(result.items) == 0
            assert result.items == []

            mock_repository.get_batch_student_names.assert_called_once_with(
                UUID(batch_id), correlation_id
            )

        @pytest.mark.parametrize(
            "invalid_batch_id",
            [
                "not-a-uuid",
                "123-456-789",
                "",
                "completely-invalid",
                "12345678-1234-1234-1234-12345678901Z",  # Invalid character at end
            ],
        )
        async def test_raises_validation_error_for_invalid_batch_id(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            invalid_batch_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should raise HuleEduError for invalid batch UUID."""
            with pytest.raises(HuleEduError) as exc_info:
                await handler.get_batch_student_names(invalid_batch_id, correlation_id)

            error = exc_info.value
            assert "Invalid batch_id format" in str(error)

            # Repository should not be called for invalid UUID
            mock_repository.get_batch_student_names.assert_not_called()

        async def test_raises_processing_error_on_repository_exception(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            batch_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should raise processing error when repository raises exception."""
            mock_repository.get_batch_student_names.side_effect = RuntimeError(
                "Database connection failed"
            )

            with pytest.raises(HuleEduError) as exc_info:
                await handler.get_batch_student_names(batch_id, correlation_id)

            error = exc_info.value
            assert "Failed to retrieve batch student names" in str(error)
            assert "Database connection failed" in str(error)

            mock_repository.get_batch_student_names.assert_called_once_with(
                UUID(batch_id), correlation_id
            )

        async def test_handles_empty_person_names_gracefully(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            batch_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should handle empty person names by preserving them in response."""
            mapping = {
                "essay_id": uuid4(),
                "student_id": uuid4(),
                "student_person_name": PersonNameV1(
                    first_name="", last_name="", legal_full_name=""
                ),
            }
            mock_repository.get_batch_student_names.return_value = [mapping]

            result = await handler.get_batch_student_names(batch_id, correlation_id)

            assert isinstance(result, BatchStudentNamesResponse)
            assert len(result.items) == 1

            item = result.items[0]
            assert item.student_person_name.first_name == ""
            assert item.student_person_name.last_name == ""
            assert item.student_person_name.legal_full_name == ""

        async def test_correlation_id_propagation_to_repository(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            batch_id: str,
        ) -> None:
            """Should propagate correlation_id to repository call correctly."""
            specific_correlation_id = uuid4()
            mock_repository.get_batch_student_names.return_value = []

            await handler.get_batch_student_names(batch_id, specific_correlation_id)

            mock_repository.get_batch_student_names.assert_called_once_with(
                UUID(batch_id), specific_correlation_id
            )

        async def test_to_dict_serialization_works_correctly(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            batch_id: str,
            correlation_id: UUID,
            sample_person_name: PersonNameV1,
        ) -> None:
            """Should create response that serializes correctly to dict."""
            essay_id = uuid4()
            student_id = uuid4()
            mapping = {
                "essay_id": essay_id,
                "student_id": student_id,
                "student_person_name": sample_person_name,
            }
            mock_repository.get_batch_student_names.return_value = [mapping]

            result = await handler.get_batch_student_names(batch_id, correlation_id)
            dict_result = result.to_dict()

            assert isinstance(dict_result, list)
            assert len(dict_result) == 1

            item_dict = dict_result[0]
            assert item_dict["essay_id"] == str(essay_id)
            assert item_dict["student_id"] == str(student_id)
            assert item_dict["student_person_name"]["first_name"] == "Åsa"
            assert item_dict["student_person_name"]["last_name"] == "Öberg"
            assert item_dict["student_person_name"]["legal_full_name"] == "Åsa Öberg"

    class TestGetEssayStudentAssociation:
        """Tests for get_essay_student_association behavior."""

        async def test_returns_association_response_when_association_exists(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            essay_id: str,
            correlation_id: UUID,
            sample_person_name: PersonNameV1,
        ) -> None:
            """Should return EssayStudentAssociationResponse when association exists."""
            essay_uuid = UUID(essay_id)
            student_id = uuid4()
            association = {
                "essay_id": essay_uuid,
                "student_id": student_id,
                "student_person_name": sample_person_name,
            }
            mock_repository.get_essay_student_association.return_value = association

            result = await handler.get_essay_student_association(essay_id, correlation_id)

            assert isinstance(result, EssayStudentAssociationResponse)
            assert result.essay_id == essay_uuid
            assert result.student_id == student_id
            assert isinstance(result.student_person_name, PersonNameV1)
            assert result.student_person_name.first_name == "Åsa"
            assert result.student_person_name.last_name == "Öberg"
            assert result.student_person_name.legal_full_name == "Åsa Öberg"

            mock_repository.get_essay_student_association.assert_called_once_with(
                essay_uuid, correlation_id
            )

        async def test_returns_none_when_no_association_exists(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            essay_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should return None when essay has no student association."""
            mock_repository.get_essay_student_association.return_value = None

            result = await handler.get_essay_student_association(essay_id, correlation_id)

            assert result is None

            mock_repository.get_essay_student_association.assert_called_once_with(
                UUID(essay_id), correlation_id
            )

        @pytest.mark.parametrize(
            "invalid_essay_id",
            [
                "not-a-uuid",
                "123-456-789",
                "",
                "completely-invalid",
                "12345678-1234-1234-1234-12345678901X",  # Invalid character at end
            ],
        )
        async def test_raises_validation_error_for_invalid_essay_id(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            invalid_essay_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should raise HuleEduError for invalid essay UUID."""
            with pytest.raises(HuleEduError) as exc_info:
                await handler.get_essay_student_association(invalid_essay_id, correlation_id)

            error = exc_info.value
            assert "Invalid essay_id format" in str(error)

            # Repository should not be called for invalid UUID
            mock_repository.get_essay_student_association.assert_not_called()

        async def test_raises_processing_error_on_repository_exception(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            essay_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should raise processing error when repository raises exception."""
            mock_repository.get_essay_student_association.side_effect = RuntimeError(
                "Database query failed"
            )

            with pytest.raises(HuleEduError) as exc_info:
                await handler.get_essay_student_association(essay_id, correlation_id)

            error = exc_info.value
            assert "Failed to retrieve essay student association" in str(error)
            assert "Database query failed" in str(error)

            mock_repository.get_essay_student_association.assert_called_once_with(
                UUID(essay_id), correlation_id
            )

        async def test_handles_empty_person_names_in_association(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            essay_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should handle empty person names by preserving them in response."""
            association = {
                "essay_id": UUID(essay_id),
                "student_id": uuid4(),
                "student_person_name": PersonNameV1(
                    first_name="", last_name="", legal_full_name=""
                ),
            }
            mock_repository.get_essay_student_association.return_value = association

            result = await handler.get_essay_student_association(essay_id, correlation_id)

            assert isinstance(result, EssayStudentAssociationResponse)
            assert result.student_person_name.first_name == ""
            assert result.student_person_name.last_name == ""
            assert result.student_person_name.legal_full_name == ""

        async def test_correlation_id_propagation_in_association_call(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            essay_id: str,
        ) -> None:
            """Should propagate correlation_id to repository call correctly."""
            specific_correlation_id = uuid4()
            mock_repository.get_essay_student_association.return_value = None

            await handler.get_essay_student_association(essay_id, specific_correlation_id)

            mock_repository.get_essay_student_association.assert_called_once_with(
                UUID(essay_id), specific_correlation_id
            )

        async def test_association_to_dict_serialization_works_correctly(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            essay_id: str,
            correlation_id: UUID,
            sample_person_name: PersonNameV1,
        ) -> None:
            """Should create association response that serializes correctly to dict."""
            essay_uuid = UUID(essay_id)
            student_id = uuid4()
            association = {
                "essay_id": essay_uuid,
                "student_id": student_id,
                "student_person_name": sample_person_name,
            }
            mock_repository.get_essay_student_association.return_value = association

            result = await handler.get_essay_student_association(essay_id, correlation_id)

            assert result is not None
            dict_result = result.to_dict()

            assert isinstance(dict_result, dict)
            assert dict_result["essay_id"] == str(essay_uuid)
            assert dict_result["student_id"] == str(student_id)
            assert dict_result["student_person_name"]["first_name"] == "Åsa"
            assert dict_result["student_person_name"]["last_name"] == "Öberg"
            assert dict_result["student_person_name"]["legal_full_name"] == "Åsa Öberg"

        async def test_handles_swedish_characters_in_names_correctly(
            self,
            handler: StudentNameHandler,
            mock_repository: AsyncMock,
            essay_id: str,
            correlation_id: UUID,
        ) -> None:
            """Should handle Swedish characters Å, Ä, Ö correctly in all name fields."""
            complex_swedish_name = PersonNameV1(
                first_name="Åsa-Märta",
                last_name="Öberg-Ångström",
                legal_full_name="Åsa-Märta Öberg-Ångström",
            )
            association = {
                "essay_id": UUID(essay_id),
                "student_id": uuid4(),
                "student_person_name": complex_swedish_name,
            }
            mock_repository.get_essay_student_association.return_value = association

            result = await handler.get_essay_student_association(essay_id, correlation_id)

            assert result is not None
            assert result.student_person_name.first_name == "Åsa-Märta"
            assert result.student_person_name.last_name == "Öberg-Ångström"
            assert result.student_person_name.legal_full_name == "Åsa-Märta Öberg-Ångström"

            # Verify serialization preserves Swedish characters
            dict_result = result.to_dict()
            assert dict_result["student_person_name"]["first_name"] == "Åsa-Märta"
            assert dict_result["student_person_name"]["last_name"] == "Öberg-Ångström"
            assert (
                dict_result["student_person_name"]["legal_full_name"] == "Åsa-Märta Öberg-Ångström"
            )
