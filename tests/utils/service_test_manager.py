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
import time
from typing import Any, Dict, NamedTuple, Optional

import aiohttp
import httpx
from common_core.domain_enums import CourseCode
from common_core.metadata_models import StorageReferenceMetadata
from huleedu_service_libs.logging_utils import create_service_logger

from tests.utils.auth_manager import AuthTestManager, AuthTestUser
from tests.utils.prompt_reference import make_prompt_ref, serialize_prompt_ref

logger = create_service_logger("test.service_manager")


class ServiceHealthCache:
    """Shared cache for service health validation across all test instances."""

    def __init__(self):
        self._endpoints: dict[str, Any] = {}  # Always initialized, never None
        self._cache_timestamp: float = 0.0  # Always initialized, never None
        self.lock = asyncio.Lock()
        self.cache_ttl = 60.0  # 60 seconds cache

    def _is_cache_valid(self) -> bool:
        """Check if the current cache is still valid."""
        if not self._endpoints:  # Empty dict means not initialized
            return False
        return (time.time() - self._cache_timestamp) < self.cache_ttl

    async def get_or_validate(self, validator_func) -> dict[str, Any]:
        """Get cached endpoints or validate if cache is stale."""
        async with self.lock:
            if self._is_cache_valid():
                logger.info("✅ Using cached service endpoints")
                return self._endpoints.copy()

            logger.info("🔄 Validating services (cache expired or empty)")
            self._endpoints = await validator_func()
            self._cache_timestamp = time.time()
            return self._endpoints.copy()


# Shared cache instance across all ServiceTestManager instances
_shared_health_cache = ServiceHealthCache()


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
        ServiceEndpoint("api_gateway_service", 8080, has_http_api=True, has_metrics=True),
        ServiceEndpoint("content_service", 8001, has_http_api=True, has_metrics=True),
        ServiceEndpoint("batch_orchestrator_service", 5001, has_http_api=True, has_metrics=True),
        ServiceEndpoint("batch_conductor_service", 4002, has_http_api=True, has_metrics=True),
        ServiceEndpoint("essay_lifecycle_api", 6001, has_http_api=True, has_metrics=True),
        ServiceEndpoint("file_service", 7001, has_http_api=True, has_metrics=True),
        ServiceEndpoint("spellchecker_service", 8002, has_http_api=True, has_metrics=True),
        ServiceEndpoint("cj_assessment_service", 9095, has_http_api=True, has_metrics=True),
        ServiceEndpoint("llm_provider_service", 8090, has_http_api=True, has_metrics=True),
        ServiceEndpoint("class_management_service", 5002, has_http_api=True, has_metrics=True),
        ServiceEndpoint("result_aggregator_service", 4003, has_http_api=True, has_metrics=True),
        ServiceEndpoint("identity_service", 7005, has_http_api=True, has_metrics=True),
        ServiceEndpoint("entitlements_service", 8083, has_http_api=True, has_metrics=True),
        ServiceEndpoint("language_tool_service", 8085, has_http_api=True, has_metrics=True),
    ]

    def __init__(self, auth_manager: Optional[AuthTestManager] = None):
        """
        Initialize ServiceTestManager with optional authentication.

        Args:
            auth_manager: Authentication manager (creates default if None)
        """
        self.auth_manager = auth_manager or AuthTestManager()

    async def get_validated_endpoints(self, force_revalidation: bool = False) -> dict[str, Any]:
        """
        Get validated service endpoints with shared caching and TTL.

        Uses shared cache with 60-second TTL across all test instances.
        Performs validation once per session unless force_revalidation=True.
        """
        if force_revalidation:
            # Force cache invalidation by setting timestamp to 0
            _shared_health_cache._cache_timestamp = 0.0

        return await _shared_health_cache.get_or_validate(self._validate_all_services)

    async def _validate_all_services(self) -> dict[str, Any]:
        """Validate all services in parallel using asyncio.gather()."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Create validation tasks for all services in parallel
            validation_tasks = [
                self._validate_single_service(client, service) for service in self.SERVICE_ENDPOINTS
            ]

            # Run all validations in parallel
            service_results = await asyncio.gather(*validation_tasks, return_exceptions=True)

            # Collect successful validations
            validated_endpoints = {}
            for i, result in enumerate(service_results):
                if isinstance(result, Exception):
                    logger.warning(f"Service validation failed: {result}")
                    continue

                if result:  # Service validation returned data
                    service_name = self.SERVICE_ENDPOINTS[i].name
                    validated_endpoints[service_name] = result

            logger.info(
                f"✅ Validated {len(validated_endpoints)}/{len(self.SERVICE_ENDPOINTS)} "
                f"services in parallel"
            )
            return validated_endpoints

    async def _validate_single_service(
        self, client: httpx.AsyncClient, service: ServiceEndpoint
    ) -> dict[str, Any] | None:
        """Validate a single service's health and metrics endpoints."""
        service_config = {}

        # Validate HTTP API health
        if service.has_http_api:
            health_url = f"http://localhost:{service.port}/healthz"
            try:
                response = await client.get(health_url)
                if response.status_code != 200:
                    logger.warning(f"{service.name} health check failed: {response.status_code}")
                    return None

                response_data = response.json()
                if "status" not in response_data or "message" not in response_data:
                    logger.warning(f"{service.name} invalid health response format")
                    return None

                service_config.update(
                    {
                        "health_url": health_url,
                        "metrics_url": f"http://localhost:{service.port}/metrics",
                        "base_url": f"http://localhost:{service.port}",
                        "status": "healthy",
                    }
                )
                logger.info(f"✅ {service.name} HTTP API healthy")

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.warning(f"⚠️  {service.name} not accessible: {e}")
                return None

        # Validate metrics endpoint
        if service.has_metrics:
            metrics_url = f"http://localhost:{service.port}/metrics"
            try:
                response = await client.get(metrics_url)
                if response.status_code != 200:
                    logger.warning(f"{service.name} metrics endpoint failed")
                    return service_config if service_config else None

                # Validate Prometheus format
                metrics_text = response.text
                content_type = response.headers.get("content-type", "")

                if "text/plain" not in content_type:
                    logger.warning(f"{service.name} invalid metrics Content-Type")
                    return service_config if service_config else None

                if metrics_text.strip():
                    if "# HELP" not in metrics_text or "# TYPE" not in metrics_text:
                        logger.warning(f"{service.name} invalid Prometheus format")
                        return service_config if service_config else None

                service_config["metrics_url"] = metrics_url
                service_config["metrics_status"] = "valid"
                logger.info(f"📊 {service.name} metrics endpoint valid")

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.warning(f"⚠️  {service.name} metrics not accessible: {e}")

        return service_config if service_config else None

    async def create_batch_via_agw(
        self,
        expected_essay_count: int,
        course_code: CourseCode | str = CourseCode.ENG5,
        user: Optional[AuthTestUser] = None,
        correlation_id: str | None = None,
        enable_cj_assessment: bool = False,
        class_id: str | None = None,
        essay_ids: list[str] | None = None,
        cj_default_llm_model: str | None = None,
        cj_default_temperature: float | None = None,
        student_prompt_ref: StorageReferenceMetadata | None = None,
    ) -> tuple[str, str]:
        """
        Create a test batch via API Gateway (AGW).

        Identity is injected at the edge by AGW; do not include user_id/org_id in the body.

        Returns:
            tuple[str, str]: (batch_id, correlation_id)
        """
        endpoints = await self.get_validated_endpoints()

        if "api_gateway_service" not in endpoints:
            raise RuntimeError("API Gateway Service not available for batch creation")

        import datetime
        import uuid

        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        if user is None:
            user = self.auth_manager.get_default_user()

        agw_base_url = endpoints["api_gateway_service"]["base_url"]

        # Convert string course codes to CourseCode enum if possible, fallback to ENG5
        if isinstance(course_code, str):
            try:
                course_code_enum = CourseCode(course_code)
            except ValueError:
                course_code_enum = CourseCode.ENG5
                logger.warning(
                    f"Invalid course code '{course_code}', using default {CourseCode.ENG5.value}"
                )
        else:
            course_code_enum = course_code

        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        prompt_label = f"Test batch prompt via AGW at {timestamp} (corr: {correlation_id[:8]})"
        prompt_ref = student_prompt_ref
        if prompt_ref is None:
            prompt_text = (
                f"{prompt_label}. This prompt was auto-generated for functional testing flows."
            )
            prompt_storage_id = await self.upload_content_directly(prompt_text, user=user)
            prompt_ref = make_prompt_ref(prompt_storage_id)

        payload: dict[str, Any] = {
            "expected_essay_count": expected_essay_count,
            "course_code": course_code_enum.value,
            "enable_cj_assessment": enable_cj_assessment,
            "student_prompt_ref": serialize_prompt_ref(prompt_ref),
        }

        if class_id is not None:
            payload["class_id"] = class_id
        if essay_ids is not None:
            payload["essay_ids"] = essay_ids
        if cj_default_llm_model is not None:
            payload["cj_default_llm_model"] = cj_default_llm_model
        if cj_default_temperature is not None:
            payload["cj_default_temperature"] = cj_default_temperature

        # Build minimal headers for AGW: Authorization + Correlation
        bearer = self.auth_manager.generate_jwt_token(user)
        headers = {
            "Authorization": f"Bearer {bearer}",
            "X-Correlation-ID": correlation_id,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{agw_base_url}/v1/batches/register",
                json=payload,
                headers=headers,
            ) as response:
                if response.status not in (200, 202):
                    error_text = await response.text()
                    raise RuntimeError(
                        f"AGW batch creation failed: {response.status} - {error_text}"
                    )

                result = await response.json()
                batch_id = result.get("batch_id")
                returned_correlation_id = result.get("correlation_id", correlation_id)
                if not batch_id:
                    raise RuntimeError(f"AGW response missing batch_id: {result}")

                logger.info(
                    f"Created batch via AGW {batch_id} with correlation {returned_correlation_id}"
                )
                return batch_id, returned_correlation_id

    async def create_batch(
        self,
        expected_essay_count: int,
        course_code: CourseCode | str = CourseCode.ENG5,
        user: Optional[AuthTestUser] = None,
        correlation_id: str | None = None,
        enable_cj_assessment: bool = False,
        class_id: str | None = None,
        student_prompt_ref: StorageReferenceMetadata | None = None,
    ) -> tuple[str, str]:
        """
        Create a test batch via API Gateway.

        All client-facing test flows use AGW as the entry point.
        Identity is injected at the edge; do not include user_id in the body.

        Args:
            expected_essay_count: Number of essays expected in batch
            course_code: Course code for the batch
            user: Test user (uses default if None)
            correlation_id: Correlation ID for tracking
            enable_cj_assessment: Enable CJ assessment for the batch
            class_id: Optional class ID (triggers REGULAR batch flow)

        Returns:
            tuple[str, str]: (batch_id, correlation_id)
        """
        return await self.create_batch_via_agw(
            expected_essay_count=expected_essay_count,
            course_code=course_code,
            user=user,
            correlation_id=correlation_id,
            enable_cj_assessment=enable_cj_assessment,
            class_id=class_id,
            student_prompt_ref=student_prompt_ref,
        )

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

        # Prefer uploading via API Gateway to exercise edge identity injection
        if "api_gateway_service" not in endpoints:
            raise RuntimeError("API Gateway Service not available for file upload")

        if user is None:
            user = self.auth_manager.get_default_user()

        agw_base_url = endpoints["api_gateway_service"]["base_url"]

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
                f"{agw_base_url}/v1/files/batch",
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status in (201, 202):
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
