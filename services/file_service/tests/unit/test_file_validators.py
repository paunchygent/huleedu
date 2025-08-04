"""Unit tests for file validators following existing patterns."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from huleedu_service_libs.error_handling import HuleEduError

from services.file_service.implementations.file_validators import (
    MagicNumberValidator,
    TemporaryFileValidator,
)


class TestTemporaryFileValidator:
    """Test temporary file validation logic."""

    async def test_accepts_normal_files(self) -> None:
        """Test that normal files pass validation."""
        # Given
        validator = TemporaryFileValidator()
        file_name = "essay.docx"
        file_content = b"test content"
        correlation_id = uuid4()

        # When/Then - Should not raise
        await validator.validate(file_name, file_content, correlation_id)

    async def test_accepts_files_with_tilde_not_at_start(self) -> None:
        """Test that files with ~ not at the start pass validation."""
        # Given
        validator = TemporaryFileValidator()
        file_name = "essay~backup.docx"
        file_content = b"test content"
        correlation_id = uuid4()

        # When/Then - Should not raise
        await validator.validate(file_name, file_content, correlation_id)

    async def test_rejects_temporary_files(self) -> None:
        """Test that temporary Word files are rejected."""
        # Given
        validator = TemporaryFileValidator()
        file_name = "~$essay.docx"
        file_content = b"test content"
        correlation_id = uuid4()

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate(file_name, file_content, correlation_id)

        assert "temporary Word 'owner' file" in str(exc_info.value)

    async def test_rejects_various_temporary_file_patterns(self) -> None:
        """Test rejection of various temporary file name patterns."""
        # Given
        validator = TemporaryFileValidator()
        temp_file_names = [
            "~$document.docx",
            "~$report.doc",
            "~$gg Eriksson.docx",  # The actual problematic file from the task
            "~$test file with spaces.docx",
        ]
        correlation_id = uuid4()

        # When/Then
        for file_name in temp_file_names:
            with pytest.raises(HuleEduError) as exc_info:
                await validator.validate(file_name, b"content", correlation_id)
            assert "temporary Word 'owner' file" in str(exc_info.value)


class TestMagicNumberValidator:
    """Test MIME type validation using magic numbers."""

    @pytest.fixture
    def allowed_mime_types(self) -> set[str]:
        """Provide standard allowed MIME types."""
        return {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
            "text/plain",
            "application/pdf",
        }

    async def test_accepts_valid_mime_types(self, allowed_mime_types: set[str]) -> None:
        """Test that files with allowed MIME types pass validation."""
        # Given
        validator = MagicNumberValidator(allowed_mime_types)

        # Mock magic to return an allowed MIME type
        with patch.object(validator._magic, "from_buffer", return_value="text/plain"):
            # When/Then - Should not raise
            await validator.validate("test.txt", b"test content", uuid4())

    async def test_accepts_empty_files(self, allowed_mime_types: set[str]) -> None:
        """Test that empty files are accepted (will fail at extraction)."""
        # Given
        validator = MagicNumberValidator(allowed_mime_types)

        # When/Then - Should not raise
        await validator.validate("empty.txt", b"", uuid4())

    async def test_rejects_unsupported_mime_types(self, allowed_mime_types: set[str]) -> None:
        """Test that files with unsupported MIME types are rejected."""
        # Given
        validator = MagicNumberValidator(allowed_mime_types)
        file_name = "test.exe"
        file_content = b"MZ\x90\x00"  # PE executable header
        correlation_id = uuid4()

        # Mock magic to return an unsupported MIME type
        with patch.object(validator._magic, "from_buffer", return_value="application/x-executable"):
            # When/Then
            with pytest.raises(HuleEduError) as exc_info:
                await validator.validate(file_name, file_content, correlation_id)

            assert "File format 'application/x-executable' is not supported" in str(exc_info.value)

    async def test_validates_docx_mime_type(self, allowed_mime_types: set[str]) -> None:
        """Test validation of DOCX MIME type."""
        # Given
        validator = MagicNumberValidator(allowed_mime_types)
        docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        with patch.object(validator._magic, "from_buffer", return_value=docx_mime):
            # When/Then - Should not raise
            await validator.validate("essay.docx", b"PK\x03\x04", uuid4())

    async def test_validates_legacy_doc_mime_type(self, allowed_mime_types: set[str]) -> None:
        """Test validation of legacy DOC MIME type."""
        # Given
        validator = MagicNumberValidator(allowed_mime_types)
        doc_mime = "application/msword"

        with patch.object(validator._magic, "from_buffer", return_value=doc_mime):
            # When/Then - Should not raise
            await validator.validate("essay.doc", b"\xd0\xcf\x11\xe0", uuid4())

    async def test_logs_validation_failures(self, allowed_mime_types: set[str]) -> None:
        """Test that validation failures are properly logged."""
        # Given
        validator = MagicNumberValidator(allowed_mime_types)
        file_name = "malicious.bin"
        correlation_id = uuid4()

        with patch.object(validator._magic, "from_buffer", return_value="application/octet-stream"):
            # When/Then
            with pytest.raises(HuleEduError) as exc_info:
                await validator.validate(file_name, b"\x00\x01\x02", correlation_id)

            error = exc_info.value
            assert "application/octet-stream" in str(error)
            assert "not supported" in str(error)
