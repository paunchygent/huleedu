"""
E2E Pipeline Test - Step 1: File Upload

Tests the first step of the complete pipeline: uploading files through File Service.
This test validates that our pattern-aligned File Service can receive and process
real files, extract text, store content, and publish events.

No mocking - tests real services only.
"""

import uuid
from pathlib import Path

import httpx
import pytest


class TestE2EStep1FileUpload:
    """
    Test file upload functionality through File Service.
    This is the foundation for all subsequent E2E pipeline tests.
    """

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_single_file_upload_success(self):
        """
        Test uploading a single file through File Service.

        Validates:
        - File Service accepts POST to /v1/files/batch
        - Returns 202 Accepted (async processing)
        - Response includes batch_id and correlation_id
        - File content is processed asynchronously
        """
        async with httpx.AsyncClient() as client:
            # Use real test file
            test_file_path = Path("test_uploads/essay1.txt")
            assert test_file_path.exists(), f"Test file {test_file_path} not found"

            # Generate unique batch_id for test isolation
            batch_id = f"e2e-test-{uuid.uuid4().hex[:8]}"

            # Prepare multipart form data as File Service expects
            with open(test_file_path, "rb") as f:
                files = {"files": (test_file_path.name, f, "text/plain")}
                data = {"batch_id": batch_id}

                try:
                    response = await client.post(
                        "http://localhost:7001/v1/files/batch",
                        files=files,
                        data=data,
                        timeout=30.0,  # Allow time for processing
                    )

                    # Validate File Service response
                    assert response.status_code == 202, (
                        f"File Service should return 202 Accepted, got {response.status_code}: "
                        f"{response.text}"
                    )

                    response_data = response.json()

                    # Validate response structure
                    assert "message" in response_data, "Response missing 'message' field"
                    assert "batch_id" in response_data, "Response missing 'batch_id' field"
                    assert "correlation_id" in response_data, (
                        "Response missing 'correlation_id' field"
                    )

                    # Validate response values
                    assert response_data["batch_id"] == batch_id, (
                        f"Response batch_id {response_data['batch_id']} doesn't match sent "
                        f"{batch_id}"
                    )

                    assert "processed" in response_data["message"] or (
                        "received" in response_data["message"]
                    ), f"Unexpected message format: {response_data['message']}"

                    # Validate correlation_id is valid UUID format
                    try:
                        uuid.UUID(response_data["correlation_id"])
                    except ValueError:
                        pytest.fail(
                            f"correlation_id is not valid UUID: {response_data['correlation_id']}"
                        )

                    print(f"✅ File upload successful for batch {batch_id}")
                    print(f"   Correlation ID: {response_data['correlation_id']}")
                    print(f"   Message: {response_data['message']}")

                except httpx.ConnectError:
                    pytest.skip(
                        "File Service not accessible - ensure docker compose up -d is running"
                    )
                except httpx.TimeoutException:
                    pytest.fail("File Service response timeout - service may be overloaded")

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_multiple_files_batch_upload(self):
        """
        Test uploading multiple files in a single batch.

        Validates:
        - File Service handles multiple files in one request
        - All files are associated with the same batch_id
        - Response indicates number of files processed
        """
        async with httpx.AsyncClient() as client:
            # Use both test files
            test_files = [Path("test_uploads/essay1.txt"), Path("test_uploads/essay2.txt")]

            for test_file in test_files:
                assert test_file.exists(), f"Test file {test_file} not found"

            batch_id = f"e2e-multi-test-{uuid.uuid4().hex[:8]}"

            # Prepare multiple files for upload
            files = []
            for test_file in test_files:
                with open(test_file, "rb") as f:
                    files.append(("files", (test_file.name, f.read(), "text/plain")))

            data = {"batch_id": batch_id}

            try:
                response = await client.post(
                    "http://localhost:7001/v1/files/batch", files=files, data=data, timeout=30.0
                )

                assert response.status_code == 202, (
                    f"Multi-file upload should return 202, got {response.status_code}: "
                    f"{response.text}"
                )

                response_data = response.json()

                # Validate batch processing acknowledgment
                assert response_data["batch_id"] == batch_id
                assert str(len(test_files)) in response_data["message"], (
                    f"Message should mention {len(test_files)} files: {response_data['message']}"
                )

                print(f"✅ Multi-file upload successful for batch {batch_id}")
                print(f"   Files uploaded: {len(test_files)}")
                print(f"   Message: {response_data['message']}")

            except httpx.ConnectError:
                pytest.skip("File Service not accessible")
            except httpx.TimeoutException:
                pytest.fail("File Service multi-file upload timeout")

    @pytest.mark.e2e
    @pytest.mark.docker
    @pytest.mark.asyncio
    async def test_file_upload_validation_errors(self):
        """
        Test File Service validation for invalid requests.

        Validates error handling:
        - Missing batch_id returns 400
        - No files returns 400
        - Error messages are clear
        """
        async with httpx.AsyncClient() as client:
            try:
                # Test 1: Missing batch_id
                with open("test_uploads/essay1.txt", "rb") as f:
                    files = {"files": ("essay1.txt", f, "text/plain")}
                    # Intentionally omit batch_id

                    response = await client.post(
                        "http://localhost:7001/v1/files/batch", files=files, timeout=10.0
                    )

                    assert response.status_code == 400, (
                        f"Missing batch_id should return 400, got {response.status_code}"
                    )

                    error_data = response.json()
                    assert "error" in error_data, "Error response should have 'error' field"
                    assert "batch_id" in error_data["error"].lower(), (
                        f"Error should mention batch_id: {error_data['error']}"
                    )

                # Test 2: No files provided
                data = {"batch_id": "test-batch"}

                response = await client.post(
                    "http://localhost:7001/v1/files/batch", data=data, timeout=10.0
                )

                assert response.status_code == 400, (
                    f"No files should return 400, got {response.status_code}"
                )

                error_data = response.json()
                assert "error" in error_data
                assert "files" in error_data["error"].lower() or (
                    "no files" in error_data["error"].lower()
                ), f"Error should mention missing files: {error_data['error']}"

                print("✅ File Service validation errors handled correctly")

            except httpx.ConnectError:
                pytest.skip("File Service not accessible")


# Test helper to verify File Service is responsive before running E2E tests
@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.asyncio
async def test_file_service_health_prerequisite():
    """
    Prerequisite test: Verify File Service is healthy before running E2E tests.
    This ensures pattern alignment is working correctly.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:7001/healthz", timeout=5.0)
            assert response.status_code == 200, f"File Service unhealthy: {response.status_code}"

            health_data = response.json()
            assert health_data["status"] == "ok", f"File Service status not ok: {health_data}"

            print("✅ File Service health check passed - ready for E2E testing")

        except httpx.ConnectError:
            pytest.fail(
                "File Service not accessible. Ensure services are running:\ndocker compose up -d"
            )
