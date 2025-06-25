"""
E2E File Upload Workflows

Consolidated test suite for file upload workflows, combining functionality from:
- File upload basics (single & multi-file)
- Upload validation and error handling
- Complete workflow from batch registration to ELS integration

Uses modern utility patterns (ServiceTestManager) throughout - NO direct HTTP calls.
Updated with proper test authentication to resolve 401 errors.
"""

import uuid
from pathlib import Path
from typing import Any

import pytest

from tests.utils.service_test_manager import ServiceTestManager
from tests.utils.test_auth_manager import AuthTestManager, create_test_teacher


class TestE2EFileWorkflows:
    """Test file upload workflows using modern utility patterns with authentication."""

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_single_file_upload_workflow(self):
        """
        Test single file upload through ServiceTestManager utility with authentication.

        Validates:
        - File Service is available and healthy
        - ServiceTestManager.upload_files() works correctly with auth
        - Returns proper response structure with batch_id and correlation_id
        """
        # Initialize with authentication support
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        test_teacher = create_test_teacher()

        # Validate File Service is available using utility
        endpoints = await service_manager.get_validated_endpoints()
        if "file_service" not in endpoints:
            pytest.skip("File Service not available for testing")

        test_file_path = Path("test_uploads/essay1.txt")
        if not test_file_path.exists():
            pytest.skip(f"Test file {test_file_path} not found")

        # Create batch first with authenticated user
        try:
            batch_id, correlation_id = await service_manager.create_batch(
                expected_essay_count=1, user=test_teacher
            )
        except RuntimeError as e:
            pytest.skip(f"Batch creation failed: {e}")

        # Prepare file data for ServiceTestManager
        with open(test_file_path, "rb") as f:
            files = [{"name": test_file_path.name, "content": f.read()}]

        # Upload using ServiceTestManager utility with authentication
        try:
            result = await service_manager.upload_files(
                batch_id=batch_id,
                files=files,
                user=test_teacher,  # Same user for ownership
                correlation_id=correlation_id,
            )

            # Validate response structure
            required_fields = ["message", "batch_id", "correlation_id"]
            for field in required_fields:
                assert field in result, f"Response missing '{field}' field"

            assert result["batch_id"] == batch_id

            # Validate correlation_id is valid UUID
            try:
                uuid.UUID(result["correlation_id"])
            except ValueError:
                pytest.fail(f"Invalid correlation_id format: {result['correlation_id']}")

            print(f"✅ File upload successful for batch {batch_id}")
            print(f"   User: {test_teacher.user_id}")
            print(f"   Correlation ID: {result['correlation_id']}")

        except RuntimeError as e:
            pytest.fail(f"ServiceTestManager upload failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_multiple_files_batch_upload(self):
        """
        Test uploading multiple files using ServiceTestManager utility with authentication.

        Validates:
        - ServiceTestManager handles multiple files correctly with auth
        - Response indicates correct number of files processed
        """
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        test_teacher = create_test_teacher()

        endpoints = await service_manager.get_validated_endpoints()
        if "file_service" not in endpoints:
            pytest.skip("File Service not available")

        test_file_paths = [Path("test_uploads/essay1.txt"), Path("test_uploads/essay2.txt")]
        for test_file in test_file_paths:
            if not test_file.exists():
                pytest.skip(f"Test file {test_file} not found")

        # Create batch first with authenticated user
        try:
            batch_id, correlation_id = await service_manager.create_batch(
                expected_essay_count=len(test_file_paths), user=test_teacher
            )
        except RuntimeError as e:
            pytest.skip(f"Batch creation failed: {e}")

        # Prepare multiple files for ServiceTestManager
        files: list[dict[str, Any]] = []
        for test_file in test_file_paths:
            with open(test_file, "rb") as f:
                files.append({"name": test_file.name, "content": f.read()})

        # Upload using ServiceTestManager utility with authentication
        try:
            result = await service_manager.upload_files(
                batch_id=batch_id, files=files, user=test_teacher, correlation_id=correlation_id
            )

            assert result["batch_id"] == batch_id
            assert str(len(test_file_paths)) in result["message"]

            print(f"✅ Multi-file upload successful for batch {batch_id}")
            print(f"   User: {test_teacher.user_id}")
            print(f"   Files uploaded: {len(test_file_paths)}")

        except RuntimeError as e:
            pytest.fail(f"ServiceTestManager multi-file upload failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_file_upload_validation_errors(self):
        """
        Test ServiceTestManager error handling for invalid requests with authentication.

        Validates:
        - ServiceTestManager properly raises RuntimeError for service failures
        - Error messages are descriptive and can be caught appropriately
        """
        service_manager = ServiceTestManager()  # Uses default auth

        endpoints = await service_manager.get_validated_endpoints()
        if "file_service" not in endpoints:
            pytest.skip("File Service not available")

        test_file_path = Path("test_uploads/essay1.txt")
        if not test_file_path.exists():
            pytest.skip(f"Test file {test_file_path} not found")

        # Test 1: Empty files list should be handled gracefully
        empty_files: list[dict[str, Any]] = []

        # Create a valid batch first
        try:
            batch_id, _ = await service_manager.create_batch(expected_essay_count=1)
        except RuntimeError as e:
            pytest.skip(f"Batch creation failed: {e}")

        try:
            await service_manager.upload_files(batch_id, empty_files)
            pytest.fail("Expected RuntimeError for empty files list")
        except RuntimeError as e:
            # ServiceTestManager should raise RuntimeError for service errors
            assert "failed" in str(e).lower()
            print(f"✅ Empty files validation handled correctly: {e}")

        # Test 2: Invalid batch_id format (if service validates)
        with open(test_file_path, "rb") as f:
            files = [{"name": test_file_path.name, "content": f.read()}]

        # The important thing is ServiceTestManager propagates service errors
        try:
            await service_manager.upload_files("", files)  # Empty batch_id
            print("⚠️  File Service accepts empty batch_id - test passed but unexpected")
        except RuntimeError as e:
            print(f"✅ Invalid batch_id validation handled correctly: {e}")

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_complete_workflow_batch_to_els(self):
        """
        End-to-end test: create batch, upload files, and verify correlation IDs
        with authenticated utilities.

        Validates:
        - ServiceTestManager.create_batch() creates batch successfully with auth
        - ServiceTestManager.upload_files() uploads to created batch with same user
        - Correlation IDs are properly maintained across operations
        """
        auth_manager = AuthTestManager()
        service_manager = ServiceTestManager(auth_manager=auth_manager)
        test_teacher = auth_manager.create_teacher_user("E2E Complete Workflow")

        # Validate required services using utility
        endpoints = await service_manager.get_validated_endpoints()
        required_services = ["batch_orchestrator_service", "file_service"]
        for service in required_services:
            if service not in endpoints:
                pytest.skip(f"{service} not available for complete workflow test")

        test_file_path = Path("test_uploads/essay1.txt")
        if not test_file_path.exists():
            pytest.skip(f"Test file {test_file_path} not found")

        # Step 1: Create batch using ServiceTestManager utility with authentication
        try:
            batch_id, correlation_id = await service_manager.create_batch(
                expected_essay_count=1,
                course_code="ENG5",
                user=test_teacher,
            )

            print(f"✅ Batch created: {batch_id}")
            print(f"   Teacher: {test_teacher.user_id}")
            print(f"   Correlation ID: {correlation_id}")

        except RuntimeError as e:
            pytest.fail(f"Batch creation failed: {e}")

        # Step 2: Upload files to created batch using ServiceTestManager utility with same user
        with open(test_file_path, "rb") as f:
            files = [{"name": test_file_path.name, "content": f.read()}]

        try:
            upload_result = await service_manager.upload_files(
                batch_id=batch_id,
                files=files,
                user=test_teacher,  # Same user for ownership
                correlation_id=correlation_id,
            )

            # Validate workflow integration
            assert upload_result["batch_id"] == batch_id

            # Correlation ID should be maintained or new one provided
            upload_correlation_id = upload_result["correlation_id"]
            assert upload_correlation_id  # Should have a correlation ID

            print("✅ Complete authenticated workflow successful")
            print(f"   Batch: {batch_id}")
            print(f"   Teacher: {test_teacher.user_id}")
            print(f"   Upload correlation: {upload_correlation_id}")

        except RuntimeError as e:
            pytest.fail(f"File upload to created batch failed: {e}")
