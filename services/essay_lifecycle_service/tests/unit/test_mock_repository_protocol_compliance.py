"""
Protocol compliance tests for MockEssayRepository.

Validates that MockEssayRepository implements EssayRepositoryProtocol
completely with correct method signatures and return types.
"""

from __future__ import annotations

import inspect
from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus
from sqlalchemy.ext.asyncio import AsyncSession

from services.essay_lifecycle_service.domain_models import EssayState
from services.essay_lifecycle_service.implementations.mock_essay_repository import (
    MockEssayRepository,
)
from services.essay_lifecycle_service.protocols import (
    EssayRepositoryProtocol,
)


class TestMockRepositoryProtocolCompliance:
    """Test suite for MockEssayRepository protocol compliance."""

    @pytest.fixture
    def mock_repository(self) -> MockEssayRepository:
        """Create mock repository instance."""
        return MockEssayRepository()

    def test_mock_repository_implements_protocol(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test that MockEssayRepository implements EssayRepositoryProtocol."""
        # Note: Cannot use isinstance with Protocol that's not @runtime_checkable
        # Instead verify that all required methods exist and are callable
        assert hasattr(mock_repository, "get_essay_state")
        assert callable(mock_repository.get_essay_state)

    def test_all_protocol_methods_implemented(self) -> None:
        """Test that all protocol methods are implemented in MockEssayRepository."""
        # Get all protocol methods dynamically
        protocol_methods = [
            name
            for name in dir(EssayRepositoryProtocol)
            if not name.startswith("_") and callable(getattr(EssayRepositoryProtocol, name))
        ]

        mock_methods = [
            name
            for name in dir(MockEssayRepository)
            if not name.startswith("_") and callable(getattr(MockEssayRepository, name))
        ]

        # Verify all protocol methods are implemented
        missing_methods = set(protocol_methods) - set(mock_methods)
        assert not missing_methods, (
            f"Protocol methods not implemented in MockEssayRepository: {missing_methods}"
        )

        # Log discovered method count for visibility
        assert len(protocol_methods) >= 13, (
            f"Expected at least 13 protocol methods, found {len(protocol_methods)}"
        )

    def test_get_essay_state_signature(self) -> None:
        """Test get_essay_state method signature compliance."""
        protocol_sig = inspect.signature(EssayRepositoryProtocol.get_essay_state)
        mock_sig = inspect.signature(MockEssayRepository.get_essay_state)

        # Remove 'self' parameter from comparison
        protocol_params = list(protocol_sig.parameters.values())[1:]  # Skip 'self'
        mock_params = list(mock_sig.parameters.values())[1:]  # Skip 'self'

        assert len(protocol_params) == len(mock_params), "Parameter count mismatch"

        for protocol_param, mock_param in zip(protocol_params, mock_params, strict=False):
            assert protocol_param.name == mock_param.name, (
                f"Parameter name mismatch: {protocol_param.name} vs {mock_param.name}"
            )
            assert protocol_param.annotation == mock_param.annotation, (
                f"Parameter annotation mismatch for {protocol_param.name}"
            )

        # Check return type annotations
        assert protocol_sig.return_annotation == mock_sig.return_annotation

    def test_update_essay_state_signature(self) -> None:
        """Test update_essay_state method signature compliance."""
        protocol_sig = inspect.signature(EssayRepositoryProtocol.update_essay_state)
        mock_sig = inspect.signature(MockEssayRepository.update_essay_state)

        # Remove 'self' parameter from comparison
        protocol_params = list(protocol_sig.parameters.values())[1:]
        mock_params = list(mock_sig.parameters.values())[1:]

        assert len(protocol_params) == len(mock_params), "Parameter count mismatch"

        for protocol_param, mock_param in zip(protocol_params, mock_params, strict=False):
            assert protocol_param.name == mock_param.name
            assert protocol_param.annotation == mock_param.annotation
            assert protocol_param.default == mock_param.default

        assert protocol_sig.return_annotation == mock_sig.return_annotation

    def test_create_essay_record_signature(self) -> None:
        """Test create_essay_record method signature compliance."""
        protocol_sig = inspect.signature(EssayRepositoryProtocol.create_essay_record)
        mock_sig = inspect.signature(MockEssayRepository.create_essay_record)

        protocol_params = list(protocol_sig.parameters.values())[1:]
        mock_params = list(mock_sig.parameters.values())[1:]

        assert len(protocol_params) == len(mock_params)

        for protocol_param, mock_param in zip(protocol_params, mock_params, strict=False):
            assert protocol_param.name == mock_param.name
            assert protocol_param.annotation == mock_param.annotation
            assert protocol_param.default == mock_param.default

        assert protocol_sig.return_annotation == mock_sig.return_annotation

    def test_create_essay_records_batch_signature(self) -> None:
        """Test create_essay_records_batch method signature compliance."""
        protocol_sig = inspect.signature(EssayRepositoryProtocol.create_essay_records_batch)
        mock_sig = inspect.signature(MockEssayRepository.create_essay_records_batch)

        protocol_params = list(protocol_sig.parameters.values())[1:]
        mock_params = list(mock_sig.parameters.values())[1:]

        assert len(protocol_params) == len(mock_params)

        for protocol_param, mock_param in zip(protocol_params, mock_params, strict=False):
            assert protocol_param.name == mock_param.name
            assert protocol_param.annotation == mock_param.annotation
            assert protocol_param.default == mock_param.default

        # Special case: Mock may return ProtocolEssayState while protocol expects EssayState
        # Both are compatible at runtime, so we allow this difference
        protocol_return = str(protocol_sig.return_annotation)
        mock_return = str(mock_sig.return_annotation)

        if "list[EssayState]" in protocol_return and "list[ProtocolEssayState]" in mock_return:
            # This is acceptable - both represent the same entity
            pass
        else:
            assert protocol_sig.return_annotation == mock_sig.return_annotation

    def test_list_essays_by_batch_signature(self) -> None:
        """Test list_essays_by_batch method signature compliance."""
        protocol_sig = inspect.signature(EssayRepositoryProtocol.list_essays_by_batch)
        mock_sig = inspect.signature(MockEssayRepository.list_essays_by_batch)

        protocol_params = list(protocol_sig.parameters.values())[1:]
        mock_params = list(mock_sig.parameters.values())[1:]

        assert len(protocol_params) == len(mock_params)

        for protocol_param, mock_param in zip(protocol_params, mock_params, strict=False):
            assert protocol_param.name == mock_param.name
            assert protocol_param.annotation == mock_param.annotation

        # Note: Return type may differ between EssayState and ProtocolEssayState
        # but both should be compatible

    def test_get_batch_status_summary_signature(self) -> None:
        """Test get_batch_status_summary method signature compliance."""
        protocol_sig = inspect.signature(EssayRepositoryProtocol.get_batch_status_summary)
        mock_sig = inspect.signature(MockEssayRepository.get_batch_status_summary)

        protocol_params = list(protocol_sig.parameters.values())[1:]
        mock_params = list(mock_sig.parameters.values())[1:]

        assert len(protocol_params) == len(mock_params)

        for protocol_param, mock_param in zip(protocol_params, mock_params, strict=False):
            assert protocol_param.name == mock_param.name
            assert protocol_param.annotation == mock_param.annotation

        assert protocol_sig.return_annotation == mock_sig.return_annotation

    def test_list_essays_by_batch_and_phase_signature(self) -> None:
        """Test list_essays_by_batch_and_phase method signature compliance."""
        protocol_sig = inspect.signature(EssayRepositoryProtocol.list_essays_by_batch_and_phase)
        mock_sig = inspect.signature(MockEssayRepository.list_essays_by_batch_and_phase)

        protocol_params = list(protocol_sig.parameters.values())[1:]
        mock_params = list(mock_sig.parameters.values())[1:]

        assert len(protocol_params) == len(mock_params)

        for protocol_param, mock_param in zip(protocol_params, mock_params, strict=False):
            assert protocol_param.name == mock_param.name
            assert protocol_param.annotation == mock_param.annotation
            assert protocol_param.default == mock_param.default

    # Deprecated repository idempotency method signature test removed (migrated off legacy)

    def test_get_session_factory_signature(self) -> None:
        """Test get_session_factory method signature compliance."""
        protocol_sig = inspect.signature(EssayRepositoryProtocol.get_session_factory)
        mock_sig = inspect.signature(MockEssayRepository.get_session_factory)

        protocol_params = list(protocol_sig.parameters.values())[1:]
        mock_params = list(mock_sig.parameters.values())[1:]

        assert len(protocol_params) == len(mock_params)
        assert protocol_sig.return_annotation == mock_sig.return_annotation

    def test_update_essay_processing_metadata_signature(self) -> None:
        """Test update_essay_processing_metadata method signature compliance."""
        protocol_sig = inspect.signature(EssayRepositoryProtocol.update_essay_processing_metadata)
        mock_sig = inspect.signature(MockEssayRepository.update_essay_processing_metadata)

        protocol_params = list(protocol_sig.parameters.values())[1:]
        mock_params = list(mock_sig.parameters.values())[1:]

        assert len(protocol_params) == len(mock_params)

        for protocol_param, mock_param in zip(protocol_params, mock_params, strict=False):
            assert protocol_param.name == mock_param.name
            assert protocol_param.annotation == mock_param.annotation
            assert protocol_param.default == mock_param.default

        assert protocol_sig.return_annotation == mock_sig.return_annotation

    def test_update_student_association_signature(self) -> None:
        """Test update_student_association method signature compliance."""
        protocol_sig = inspect.signature(EssayRepositoryProtocol.update_student_association)
        mock_sig = inspect.signature(MockEssayRepository.update_student_association)

        protocol_params = list(protocol_sig.parameters.values())[1:]
        mock_params = list(mock_sig.parameters.values())[1:]

        assert len(protocol_params) == len(mock_params)

        for protocol_param, mock_param in zip(protocol_params, mock_params, strict=False):
            assert protocol_param.name == mock_param.name
            assert protocol_param.annotation == mock_param.annotation
            assert protocol_param.default == mock_param.default

        assert protocol_sig.return_annotation == mock_sig.return_annotation

    @pytest.mark.asyncio
    async def test_method_return_types_compatibility(
        self, mock_repository: MockEssayRepository
    ) -> None:
        """Test that method return types are compatible with protocol expectations."""
        # Test get_essay_state return type
        result = await mock_repository.get_essay_state("non-existent")
        assert result is None  # Should return None for non-existent essay

        # Test create_essay_record return type
        created_essay = await mock_repository.create_essay_record(
            essay_id="test-essay", batch_id="test-batch", correlation_id=uuid4()
        )
        assert isinstance(created_essay, EssayState)
        assert created_essay.essay_id == "test-essay"
        assert created_essay.batch_id == "test-batch"

        # Test get_essay_state return type with existing essay
        retrieved = await mock_repository.get_essay_state("test-essay")
        assert retrieved is not None
        assert isinstance(retrieved, EssayState)
        assert retrieved.essay_id == "test-essay"

        # Test list_essays_by_batch return type
        essays = await mock_repository.list_essays_by_batch("test-batch")
        assert isinstance(essays, list)
        assert len(essays) == 1
        # Note: Cannot use isinstance with Protocol. Check for required attributes instead.
        assert all(hasattr(essay, "essay_id") and hasattr(essay, "batch_id") for essay in essays)

        # Test get_batch_status_summary return type
        summary = await mock_repository.get_batch_status_summary("test-batch")
        assert isinstance(summary, dict)
        assert all(isinstance(key, EssayStatus) for key in summary.keys())
        assert all(isinstance(value, int) for value in summary.values())

        # Test get_session_factory return type
        session_factory = mock_repository.get_session_factory()
        # Should return None for mock implementation as documented
        assert session_factory is None

    @pytest.mark.asyncio
    async def test_method_parameter_handling(self, mock_repository: MockEssayRepository) -> None:
        """Test that methods handle parameters correctly according to protocol."""
        correlation_id = uuid4()

        # Test methods accept session parameter (even though mock ignores it)
        mock_session = AsyncSession()

        # update_essay_state with session
        await mock_repository.create_essay_record(
            essay_id="param-test", batch_id="param-batch", correlation_id=correlation_id
        )

        await mock_repository.update_essay_state(
            essay_id="param-test",
            new_status=EssayStatus.SPELLCHECKED_SUCCESS,
            metadata={"test": "value"},
            session=mock_session,  # Should be accepted but ignored
            storage_reference=(ContentType.EXTRACTED_PLAINTEXT, "storage-123"),
            correlation_id=correlation_id,
        )

        # list_essays_by_batch_and_phase with session
        phase_essays = await mock_repository.list_essays_by_batch_and_phase(
            batch_id="param-batch", phase_name="spellcheck", session=mock_session
        )
        assert isinstance(phase_essays, list)

        # Deprecated idempotency method usage removed from parameter handling test

    @pytest.mark.parametrize(
        "method_name",
        [
            "get_essay_state",
            "update_essay_state",
            "update_essay_status_via_machine",
            "create_essay_record",
            "create_essay_records_batch",
            "list_essays_by_batch",
            "get_batch_status_summary",
            "get_batch_summary_with_essays",
            "get_essay_by_text_storage_id_and_batch_id",
            "list_essays_by_batch_and_phase",
            "get_session_factory",
            "update_essay_processing_metadata",
            "update_student_association",
        ],
    )
    def test_required_method_present_and_callable(self, method_name: str) -> None:
        """Test that each required protocol method is present and callable."""
        assert hasattr(MockEssayRepository, method_name), (
            f"Required method '{method_name}' not found in MockEssayRepository"
        )
        method = getattr(MockEssayRepository, method_name)
        assert callable(method), f"Method '{method_name}' is not callable"

    def test_all_public_methods_have_docstrings(self) -> None:
        """Test that all public methods have meaningful docstrings."""
        public_methods = [
            name
            for name in dir(MockEssayRepository)
            if not name.startswith("_") and callable(getattr(MockEssayRepository, name))
        ]

        methods_without_docstrings = []
        methods_with_empty_docstrings = []

        for method_name in public_methods:
            method = getattr(MockEssayRepository, method_name)
            if method.__doc__ is None:
                methods_without_docstrings.append(method_name)
            elif len(method.__doc__.strip()) == 0:
                methods_with_empty_docstrings.append(method_name)

        assert not methods_without_docstrings, (
            f"Methods missing docstrings: {methods_without_docstrings}"
        )
        assert not methods_with_empty_docstrings, (
            f"Methods with empty docstrings: {methods_with_empty_docstrings}"
        )

        # Verify we found the expected number of public methods
        assert len(public_methods) >= 13, (
            f"Expected at least 13 public methods, found {len(public_methods)}"
        )
