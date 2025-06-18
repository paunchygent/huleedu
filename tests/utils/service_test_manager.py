"""
Service Test Manager

Explicit utilities for service health validation and testing.
Replaces pytest fixtures with clear, reusable utility classes.

Based on modern testing practices:
- Explicit resource management
- No hidden fixture magic
- Clear ownership of test resources
- Parallel test execution support
"""

import asyncio
from typing import Any, Dict, List, NamedTuple, Optional

import aiohttp
import httpx
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("test.service_manager")


class ServiceEndpoint(NamedTuple):
    """Service endpoint configuration."""

    name: str
    port: int
    has_http_api: bool = True
    has_metrics: bool = True


class ServiceTestManager:
    """
    Explicit service testing utilities.

    Replaces session-scoped fixtures with explicit validation and caching.
    """

    # Service configuration - single source of truth
    SERVICE_ENDPOINTS = [
        ServiceEndpoint("content_service", 8001, has_http_api=True, has_metrics=True),
        ServiceEndpoint("batch_orchestrator_service", 5001, has_http_api=True, has_metrics=True),
        ServiceEndpoint("essay_lifecycle_service", 6001, has_http_api=True, has_metrics=True),
        ServiceEndpoint("file_service", 7001, has_http_api=True, has_metrics=True),
        ServiceEndpoint("spell_checker_service", 8002, has_http_api=True, has_metrics=True),
        ServiceEndpoint("cj_assessment_service", 9095, has_http_api=True, has_metrics=True),
    ]

    def __init__(self):
        self._validated_endpoints: Optional[Dict[str, Any]] = None
        self._validation_lock = asyncio.Lock()

    async def get_validated_endpoints(self, force_revalidation: bool = False) -> Dict[str, Any]:
        """
        Get validated service endpoints with caching.

        Performs validation once per test session unless force_revalidation=True.
        This replaces the session-scoped fixture pattern.
        """
        async with self._validation_lock:
            if self._validated_endpoints is None or force_revalidation:
                self._validated_endpoints = await self._validate_all_services()

            return self._validated_endpoints.copy()

    async def _validate_all_services(self) -> Dict[str, Any]:
        """Validate all services and return their configuration."""
        validated_endpoints = {}

        async with httpx.AsyncClient(timeout=10.0) as client:
            for service in self.SERVICE_ENDPOINTS:
                if service.has_http_api:
                    # Validate HTTP API health
                    health_url = f"http://localhost:{service.port}/healthz"
                    try:
                        response = await client.get(health_url)
                        if response.status_code != 200:
                            logger.warning(
                                f"{service.name} health check failed: {response.status_code}"
                            )
                            continue

                        response_data = response.json()
                        if "status" not in response_data or "message" not in response_data:
                            logger.warning(f"{service.name} invalid health response format")
                            continue

                        validated_endpoints[service.name] = {
                            "health_url": health_url,
                            "metrics_url": f"http://localhost:{service.port}/metrics",
                            "base_url": f"http://localhost:{service.port}",
                            "status": "healthy",
                        }
                        logger.info(f"✅ {service.name} HTTP API healthy")

                    except (httpx.ConnectError, httpx.TimeoutException) as e:
                        logger.warning(f"⚠️  {service.name} not accessible: {e}")
                        continue

                if service.has_metrics:
                    # Validate metrics endpoint
                    metrics_url = f"http://localhost:{service.port}/metrics"
                    try:
                        response = await client.get(metrics_url)
                        if response.status_code != 200:
                            logger.warning(f"{service.name} metrics endpoint failed")
                            continue

                        # Validate Prometheus format
                        metrics_text = response.text
                        content_type = response.headers.get("content-type", "")

                        if "text/plain" not in content_type:
                            logger.warning(f"{service.name} invalid metrics Content-Type")
                            continue

                        if metrics_text.strip():
                            if "# HELP" not in metrics_text or "# TYPE" not in metrics_text:
                                logger.warning(f"{service.name} invalid Prometheus format")
                                continue

                        if service.name not in validated_endpoints:
                            validated_endpoints[service.name] = {}
                        validated_endpoints[service.name]["metrics_url"] = metrics_url
                        validated_endpoints[service.name]["metrics_status"] = "valid"
                        logger.info(f"📊 {service.name} metrics endpoint valid")

                    except (httpx.ConnectError, httpx.TimeoutException) as e:
                        logger.warning(f"⚠️  {service.name} metrics not accessible: {e}")

        return validated_endpoints

    async def create_batch(
        self,
        expected_essay_count: int,
        course_code: str = "TEST",
        class_designation: str = "UtilityTest",
        correlation_id: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Create a test batch via BOS API.

        Returns (batch_id, correlation_id).
        Replaces the batch_creation_helper fixture.
        """
        endpoints = await self.get_validated_endpoints()

        if "batch_orchestrator_service" not in endpoints:
            raise RuntimeError("Batch Orchestrator Service not available for batch creation")

        import uuid

        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        bos_base_url = endpoints["batch_orchestrator_service"]["base_url"]

        batch_request = {
            "course_code": course_code,
            "class_designation": class_designation,
            "expected_essay_count": expected_essay_count,
            "essay_instructions": "Test batch created by ServiceTestManager",
            "teacher_name": "Test Teacher - ServiceTestManager",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{bos_base_url}/v1/batches/register",
                json=batch_request,
                headers={"X-Correlation-ID": correlation_id},
            ) as response:
                if response.status != 202:
                    error_text = await response.text()
                    raise RuntimeError(f"Batch creation failed: {response.status} - {error_text}")

                result = await response.json()
                batch_id = result["batch_id"]
                returned_correlation_id = result["correlation_id"]

                logger.info(f"Created batch {batch_id} with correlation {returned_correlation_id}")
                return batch_id, returned_correlation_id

    async def upload_files(
        self, batch_id: str, files: List[Dict[str, Any]], correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
                Upload files to File Service batch endpoint.
        '
                Replaces the file_upload_helper fixture.
        """
        endpoints = await self.get_validated_endpoints()

        if "file_service" not in endpoints:
            raise RuntimeError("File Service not available for file upload")

        file_service_base = endpoints["file_service"]["base_url"]

        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field("batch_id", batch_id)

            for file_info in files:
                data.add_field(
                    "files",
                    file_info["content"],
                    filename=file_info["name"],
                    content_type="text/plain",
                )

            headers = {}
            if correlation_id:
                headers["X-Correlation-ID"] = correlation_id

            async with session.post(
                f"{file_service_base}/v1/files/batch",
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status == 202:
                    result: Dict[str, Any] = await response.json()
                    logger.info(f"File upload successful: {len(files)} files")
                    return result
                else:
                    error_text = await response.text()
                    raise RuntimeError(f"File upload failed: {response.status} - {error_text}")

    async def get_service_metrics(self, service_name: str, port: int) -> Optional[str]:
        """
        Get metrics data from a specific service.

        Returns metrics text or None if not available.
        """
        metrics_url = f"http://localhost:{port}/metrics"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(metrics_url)
                if response.status_code == 200:
                    return response.text
                else:
                    logger.warning(f"{service_name} metrics failed: {response.status_code}")
                    return None
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning(f"⚠️  {service_name} metrics not accessible: {e}")
            return None

    async def upload_content_directly(self, content: str) -> str:
        """
        Upload content directly to Content Service.

        Used for pipeline testing where content needs to be uploaded directly
        to Content Service (not via File Service batch upload).

        Args:
            content: Text content to upload

        Returns:
            storage_id: Content Service storage identifier

        Raises:
            RuntimeError: If Content Service is not available or upload fails
        """
        endpoints = await self.get_validated_endpoints()

        if "content_service" not in endpoints:
            raise RuntimeError("Content Service not available for direct content upload")

        content_service_base = endpoints["content_service"]["base_url"]

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{content_service_base}/v1/content",
                data=content.encode("utf-8"),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 201:
                    result = await response.json()
                    storage_id: str = result["storage_id"]
                    logger.info(f"Content uploaded directly to Content Service: {storage_id}")
                    return storage_id
                else:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Content Service upload failed: {response.status} - {error_text}"
                    )

    async def fetch_content_directly(self, storage_id: str) -> str:
        """
        Fetch content directly from Content Service.

        Used for pipeline testing to retrieve processed content from Content Service.

        Args:
            storage_id: Content Service storage identifier

        Returns:
            content: Retrieved text content

        Raises:
            RuntimeError: If Content Service is not available or fetch fails
        """
        endpoints = await self.get_validated_endpoints()

        if "content_service" not in endpoints:
            raise RuntimeError("Content Service not available for direct content fetch")

        content_service_base = endpoints["content_service"]["base_url"]

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{content_service_base}/v1/content/{storage_id}",
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    content_bytes = await response.read()
                    content: str = content_bytes.decode("utf-8")
                    logger.info(f"Content fetched directly from Content Service: {storage_id}")
                    return content
                else:
                    error_text = await response.text()
                    raise RuntimeError(
                        f"Content Service fetch failed: {response.status} - {error_text}"
                    )


# Global instance for convenience (but can be instantiated per test for isolation)
service_manager = ServiceTestManager()


# Convenience functions that mirror the old fixture interface
async def get_validated_service_endpoints(force_revalidation: bool = False) -> Dict[str, Any]:
    """Convenience function that uses global service manager."""
    return await service_manager.get_validated_endpoints(force_revalidation)


async def create_test_batch(
    expected_essay_count: int,
    course_code: str = "TEST",
    class_designation: str = "UtilityTest",
    correlation_id: Optional[str] = None,
) -> tuple[str, str]:
    """Convenience function that uses global service manager."""
    return await service_manager.create_batch(
        expected_essay_count, course_code, class_designation, correlation_id
    )


async def upload_test_files(
    batch_id: str, files: List[Dict[str, Any]], correlation_id: Optional[str] = None
) -> Dict[str, Any]:
    """Convenience function that uses global service manager."""
    return await service_manager.upload_files(batch_id, files, correlation_id)
