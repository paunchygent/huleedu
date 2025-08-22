"""
Service Test Manager

Explicit utilities for service health validation and testing.
Replaces pytest fixtures with clear, reusable utility classes.

Based on modern testing practices:
- Explicit resource management
- No hidden fixture magic
- Clear ownership of test resources
- Parallel test execution support
- Integrated test authentication
"""

import asyncio
from typing import Any, Dict, NamedTuple, Optional

import aiohttp
import httpx
from common_core.domain_enums import CourseCode
from huleedu_service_libs.logging_utils import create_service_logger

from tests.utils.auth_manager import AuthTestManager, AuthTestUser

logger = create_service_logger("test.service_manager")


class ServiceEndpoint(NamedTuple):
    """Service endpoint configuration."""

    name: str
    port: int
    has_http_api: bool = True
    has_metrics: bool = True


class ServiceTestManager:
    """
    Explicit service testing utilities with integrated authentication.

    Replaces session-scoped fixtures with explicit validation and caching.
    Includes proper test authentication for all service interactions.
    """

    # Service configuration - single source of truth
    SERVICE_ENDPOINTS = [
        ServiceEndpoint("content_service", 8001, has_http_api=True, has_metrics=True),
        ServiceEndpoint("batch_orchestrator_service", 5001, has_http_api=True, has_metrics=True),
        ServiceEndpoint("batch_conductor_service", 4002, has_http_api=True, has_metrics=True),
        ServiceEndpoint("essay_lifecycle_api", 6001, has_http_api=True, has_metrics=True),
        ServiceEndpoint("file_service", 7001, has_http_api=True, has_metrics=True),
        ServiceEndpoint("spellchecker_service", 8002, has_http_api=True, has_metrics=True),
        ServiceEndpoint("cj_assessment_service", 9095, has_http_api=True, has_metrics=True),
        ServiceEndpoint("class_management_service", 5002, has_http_api=True, has_metrics=True),
        ServiceEndpoint("result_aggregator_service", 4003, has_http_api=True, has_metrics=True),
        ServiceEndpoint("identity_service", 7005, has_http_api=True, has_metrics=True),
    ]

    def __init__(self, auth_manager: Optional[AuthTestManager] = None):
        """
        Initialize ServiceTestManager with optional authentication.

        Args:
            auth_manager: Authentication manager (creates default if None)
        """
        self._validated_endpoints: dict[str, Any] | None = None
        self._validation_lock = asyncio.Lock()
        self.auth_manager = auth_manager or AuthTestManager()

    async def get_validated_endpoints(self, force_revalidation: bool = False) -> dict[str, Any]:
        """
        Get validated service endpoints with caching.

        Performs validation once per test session unless force_revalidation=True.
        This replaces the session-scoped fixture pattern.
        """
        async with self._validation_lock:
            if self._validated_endpoints is None or force_revalidation:
                self._validated_endpoints = await self._validate_all_services()

            return self._validated_endpoints.copy()

    async def _validate_all_services(self) -> dict[str, Any]:
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
                                f"{service.name} health check failed: {response.status_code}",
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
        course_code: CourseCode | str = CourseCode.ENG5,
        user: Optional[AuthTestUser] = None,
        correlation_id: str | None = None,
        enable_cj_assessment: bool = False,
        class_id: str | None = None,
    ) -> tuple[str, str]:
        """
        Create a test batch via BOS API using lean registration model.

        Args:
            expected_essay_count: Number of essays expected in batch
            course_code: Course code for the batch
            user: Test user (uses default if None)
            correlation_id: Correlation ID for tracking

        Returns:
            tuple[str, str]: (batch_id, correlation_id)
        """
        endpoints = await self.get_validated_endpoints()

        if "batch_orchestrator_service" not in endpoints:
            raise RuntimeError("Batch Orchestrator Service not available for batch creation")

        import uuid

        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        if user is None:
            user = self.auth_manager.get_default_user()

        bos_base_url = endpoints["batch_orchestrator_service"]["base_url"]

        # Convert string course codes to CourseCode enum if possible, fallback to ENG5
        if isinstance(course_code, str):
            try:
                course_code_enum = CourseCode(course_code)
            except ValueError:
                # Invalid course code string, use default
                course_code_enum = CourseCode.ENG5
                logger.warning(
                    f"Invalid course code '{course_code}', using default {CourseCode.ENG5.value}"
                )
        else:
            course_code_enum = course_code

        # Generate unique essay instructions to prevent idempotency collisions
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        unique_instructions = (
            f"Test batch created by ServiceTestManager at {timestamp} (ID: {unique_id})"
        )

        batch_request = {
            "course_code": course_code_enum.value,
            "expected_essay_count": expected_essay_count,
            "essay_instructions": unique_instructions,
            "user_id": user.user_id,
            "enable_cj_assessment": enable_cj_assessment,
        }

        # Add class_id if provided (triggers REGULAR batch flow)
        if class_id is not None:
            batch_request["class_id"] = class_id

        # Get authentication headers
        auth_headers = self.auth_manager.get_auth_headers(user)
        headers = {
            **auth_headers,
            "X-Correlation-ID": correlation_id,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{bos_base_url}/v1/batches/register",
                json=batch_request,
                headers=headers,
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
        self,
        batch_id: str,
        files: list[dict[str, Any]],
        user: Optional[AuthTestUser] = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Upload files to File Service batch endpoint.

        Args:
            batch_id: Target batch ID
            files: List of file dictionaries with 'name' and 'content' keys
            user: Test user (uses default if None)
            correlation_id: Correlation ID for tracking

        Returns:
            dict[str, Any]: Upload response
        """
        endpoints = await self.get_validated_endpoints()

        if "file_service" not in endpoints:
            raise RuntimeError("File Service not available for file upload")

        if user is None:
            user = self.auth_manager.get_default_user()

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

            # Get authentication headers
            auth_headers = self.auth_manager.get_auth_headers(user)
            headers = auth_headers.copy()

            if correlation_id:
                headers["X-Correlation-ID"] = correlation_id

            async with session.post(
                f"{file_service_base}/v1/files/batch",
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status == 202:
                    result: dict[str, Any] = await response.json()
                    logger.info(f"File upload successful: {len(files)} files")
                    return result
                else:
                    error_text = await response.text()
                    raise RuntimeError(f"File upload failed: {response.status} - {error_text}")

    async def get_service_metrics(self, service_name: str, port: int) -> str | None:
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

    async def upload_content_directly(
        self, content: str, user: Optional[AuthTestUser] = None
    ) -> str:
        """
        Upload content directly to Content Service.

        Args:
            content: Text content to upload
            user: Test user (uses default if None)

        Returns:
            str: Content Service storage identifier
        """
        endpoints = await self.get_validated_endpoints()

        if "content_service" not in endpoints:
            raise RuntimeError("Content Service not available for direct content upload")

        if user is None:
            user = self.auth_manager.get_default_user()

        content_service_base = endpoints["content_service"]["base_url"]
        auth_headers = self.auth_manager.get_auth_headers(user)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{content_service_base}/v1/content",
                data=content.encode("utf-8"),
                headers=auth_headers,
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
                        f"Content Service upload failed: {response.status} - {error_text}",
                    )

    async def fetch_content_directly(
        self, storage_id: str, user: Optional[AuthTestUser] = None
    ) -> str:
        """
        Fetch content directly from Content Service.

        Args:
            storage_id: Content Service storage identifier
            user: Test user (uses default if None)

        Returns:
            str: Retrieved text content
        """
        endpoints = await self.get_validated_endpoints()

        if "content_service" not in endpoints:
            raise RuntimeError("Content Service not available for direct content fetch")

        if user is None:
            user = self.auth_manager.get_default_user()

        content_service_base = endpoints["content_service"]["base_url"]
        auth_headers = self.auth_manager.get_auth_headers(user)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{content_service_base}/v1/content/{storage_id}",
                headers=auth_headers,
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
                        f"Content Service fetch failed: {response.status} - {error_text}",
                    )

    async def make_request(
        self,
        method: str,
        service: str,
        path: str,
        json: dict[str, Any] | None = None,
        user: Optional[AuthTestUser] = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Make a generic HTTP request to a service.

        Args:
            method: HTTP method (GET, POST, etc.)
            service: Service name (e.g., 'class_management_service')
            path: URL path (e.g., '/api/v1/classes')
            json: JSON body for request
            user: Test user for authentication
            correlation_id: Correlation ID for tracking

        Returns:
            JSON response data
        """
        endpoints = await self.get_validated_endpoints()

        if service not in endpoints:
            raise RuntimeError(f"{service} not available")

        if user is None:
            user = self.auth_manager.get_default_user()

        service_base = endpoints[service]["base_url"]
        auth_headers = self.auth_manager.get_auth_headers(user)

        headers = {
            **auth_headers,
            "Content-Type": "application/json",
        }

        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=method,
                url=f"{service_base}{path}",
                json=json,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response_data: dict[str, Any] = await response.json()

                if response.status >= 400:
                    raise RuntimeError(
                        f"{service} request failed: {response.status} - {response_data}"
                    )

                return response_data

    def create_test_user(self, **kwargs) -> AuthTestUser:
        """Create a test user via the auth manager."""
        return self.auth_manager.create_test_user(**kwargs)

    def get_auth_headers(self, user: Optional[AuthTestUser] = None) -> Dict[str, str]:
        """Get authentication headers for a user."""
        return self.auth_manager.get_auth_headers(user)


# Global instance for convenience (but can be instantiated per test for isolation)
service_manager = ServiceTestManager()


# Convenience functions that mirror the old fixture interface
async def get_validated_service_endpoints(force_revalidation: bool = False) -> dict[str, Any]:
    """Convenience function that uses global service manager."""
    return await service_manager.get_validated_endpoints(force_revalidation)


async def create_test_batch(
    expected_essay_count: int,
    course_code: CourseCode | str = CourseCode.ENG5,
    user: Optional[AuthTestUser] = None,
    correlation_id: str | None = None,
    enable_cj_assessment: bool = False,
    class_id: str | None = None,
) -> tuple[str, str]:
    """Convenience function that uses global service manager."""
    return await service_manager.create_batch(
        expected_essay_count,
        course_code,
        user,
        correlation_id,
        enable_cj_assessment,
        class_id,
    )


async def upload_test_files(
    batch_id: str,
    files: list[dict[str, Any]],
    user: Optional[AuthTestUser] = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Convenience function that uses global service manager."""
    return await service_manager.upload_files(batch_id, files, user, correlation_id)
