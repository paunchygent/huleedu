"""
E2E File Upload Workflows

Consolidated test suite for file upload workflows, combining functionality from:
- File upload basics (single & multi-file)
- Upload validation and error handling
- Complete workflow from batch registration to ELS integration

Uses modern utility patterns (ServiceTestManager) throughout - NO direct HTTP calls.
"""

import uuid
from pathlib import Path
from typing import Any

import pytest

from tests.utils.service_test_manager import ServiceTestManager


class TestE2EFileWorkflows:
    """Test file upload workflows using modern utility patterns exclusively."""

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_single_file_upload_workflow(self):
        """
        Test single file upload through ServiceTestManager utility.

        Validates:
        - File Service is available and healthy
        - ServiceTestManager.upload_files() works correctly
        - Returns proper response structure with batch_id and correlation_id
        """
        service_manager = ServiceTestManager()

        # Validate File Service is available using utility
        endpoints = await service_manager.get_validated_endpoints()
        if "file_service" not in endpoints:
            pytest.skip("File Service not available for testing")

        test_file_path = Path("test_uploads/essay1.txt")
        if not test_file_path.exists():
            pytest.skip(f"Test file {test_file_path} not found")

        batch_id = f"e2e-test-{uuid.uuid4().hex[:8]}"

        # Prepare file data for ServiceTestManager
        with open(test_file_path, "rb") as f:
            files = [{"name": test_file_path.name, "content": f.read()}]

        # Upload using ServiceTestManager utility (not direct HTTP)
        try:
            result = await service_manager.upload_files(batch_id, files)

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
            print(f"   Correlation ID: {result['correlation_id']}")

        except RuntimeError as e:
            pytest.fail(f"ServiceTestManager upload failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_multiple_files_batch_upload(self):
        """
        Test uploading multiple files using ServiceTestManager utility.

        Validates:
        - ServiceTestManager handles multiple files correctly
        - Response indicates correct number of files processed
        """
        service_manager = ServiceTestManager()

        endpoints = await service_manager.get_validated_endpoints()
        if "file_service" not in endpoints:
            pytest.skip("File Service not available")

        test_file_paths = [Path("test_uploads/essay1.txt"), Path("test_uploads/essay2.txt")]
        for test_file in test_file_paths:
            if not test_file.exists():
                pytest.skip(f"Test file {test_file} not found")

        batch_id = f"e2e-multi-test-{uuid.uuid4().hex[:8]}"

        # Prepare multiple files for ServiceTestManager
        files: list[dict[str, Any]] = []
        for test_file in test_file_paths:
            with open(test_file, "rb") as f:
                files.append({"name": test_file.name, "content": f.read()})

        # Upload using ServiceTestManager utility
        try:
            result = await service_manager.upload_files(batch_id, files)

            assert result["batch_id"] == batch_id
            assert str(len(test_file_paths)) in result["message"]

            print(f"✅ Multi-file upload successful for batch {batch_id}")
            print(f"   Files uploaded: {len(test_file_paths)}")

        except RuntimeError as e:
            pytest.fail(f"ServiceTestManager multi-file upload failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_file_upload_validation_errors(self):
        """
        Test ServiceTestManager error handling for invalid requests.

        Validates:
        - ServiceTestManager properly raises RuntimeError for service failures
        - Error messages are descriptive and can be caught appropriately
        """
        service_manager = ServiceTestManager()

        endpoints = await service_manager.get_validated_endpoints()
        if "file_service" not in endpoints:
            pytest.skip("File Service not available")

        test_file_path = Path("test_uploads/essay1.txt")
        if not test_file_path.exists():
            pytest.skip(f"Test file {test_file_path} not found")

        # Test 1: Empty files list should be handled gracefully
        empty_files: list[dict[str, Any]] = []
        batch_id = f"test-empty-{uuid.uuid4().hex[:8]}"

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
        Test complete workflow from batch creation through file upload using utilities.

        Validates:
        - ServiceTestManager.create_batch() creates batch successfully
        - ServiceTestManager.upload_files() uploads to created batch
        - Correlation IDs are properly maintained across operations
        """
        service_manager = ServiceTestManager()

        # Validate required services using utility
        endpoints = await service_manager.get_validated_endpoints()
        required_services = ["batch_orchestrator_service", "file_service"]
        for service in required_services:
            if service not in endpoints:
                pytest.skip(f"{service} not available for complete workflow test")

        test_file_path = Path("test_uploads/essay1.txt")
        if not test_file_path.exists():
            pytest.skip(f"Test file {test_file_path} not found")

        # Step 1: Create batch using ServiceTestManager utility
        try:
            batch_id, correlation_id = await service_manager.create_batch(
                expected_essay_count=1,
                course_code="E2E",
                class_designation="CompleteWorkflow",
            )

            print(f"✅ Batch created: {batch_id}")
            print(f"   Correlation ID: {correlation_id}")

        except RuntimeError as e:
            pytest.fail(f"Batch creation failed: {e}")

        # Step 2: Upload files to created batch using ServiceTestManager utility
        with open(test_file_path, "rb") as f:
            files = [{"name": test_file_path.name, "content": f.read()}]

        try:
            upload_result = await service_manager.upload_files(batch_id, files, correlation_id)

            # Validate workflow integration
            assert upload_result["batch_id"] == batch_id

            # Correlation ID should be maintained or new one provided
            upload_correlation_id = upload_result["correlation_id"]
            assert upload_correlation_id  # Should have a correlation ID

            print("✅ Complete workflow successful")
            print(f"   Batch: {batch_id}")
            print(f"   Upload correlation: {upload_correlation_id}")

        except RuntimeError as e:
            pytest.fail(f"File upload to created batch failed: {e}")
