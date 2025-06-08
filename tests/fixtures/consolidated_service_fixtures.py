"""
Consolidated Service Fixtures

Eliminates redundancy by providing reusable service health validation,
metrics testing, and Kafka setup utilities used across functional tests.

Replaces duplicate health check logic found in:
- test_service_health.py
- test_pattern_alignment_validation.py
- test_metrics_endpoints.py
- Various test_e2e_*.py files
- validation_coordination_utils.py
"""

import asyncio
import json
import uuid
from typing import Any, Dict, List, NamedTuple

import aiohttp
import httpx
import pytest
from aiokafka import AIOKafkaConsumer
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("test.consolidated_fixtures")


class ServiceEndpoint(NamedTuple):
    """Service endpoint configuration."""
    name: str
    port: int
    has_http_api: bool = True
    has_metrics: bool = True


class KafkaTestConfig(NamedTuple):
    """Kafka testing configuration."""
    bootstrap_servers: str
    topics: Dict[str, str]
    assignment_timeout: int


def create_kafka_test_config(
    bootstrap_servers: str = "localhost:9093",
    topics: Dict[str, str] | None = None,
    assignment_timeout: int = 15
) -> KafkaTestConfig:
    """Create KafkaTestConfig with default topics if not provided."""
    if topics is None:
        # Default HuleEdu event topics
        topics = {
            "batch_registered": "huleedu.batch.essays.registered.v1",
            "content_provisioned": "huleedu.file.essay.content.provisioned.v1",
            "validation_failed": "huleedu.file.essay.validation.failed.v1",
            "batch_ready": "huleedu.els.batch.essays.ready.v1",
            "batch_spellcheck_initiate": "huleedu.batch.spellcheck.initiate.command.v1",
            "spellcheck_completed": "huleedu.essay.spellcheck.completed.v1",
            "batch_cj_assessment_initiate": "huleedu.batch.cj_assessment.initiate.command.v1",
            "cj_assessment_completed": "huleedu.essay.cj_assessment.completed.v1",
            "els_batch_phase_outcome": "huleedu.els.batch_phase.outcome.v1",
            "pipeline_progress": "huleedu.batch.pipeline.progress.updated.v1",
        }
    return KafkaTestConfig(bootstrap_servers, topics, assignment_timeout)


# Service configuration - single source of truth
SERVICE_ENDPOINTS = [
    ServiceEndpoint("content_service", 8001, has_http_api=True, has_metrics=True),
    ServiceEndpoint("batch_orchestrator_service", 5001, has_http_api=True, has_metrics=True),
    ServiceEndpoint("essay_lifecycle_service", 6001, has_http_api=True, has_metrics=True),
    ServiceEndpoint("file_service", 7001, has_http_api=True, has_metrics=True),
    ServiceEndpoint("spell_checker_service", 8002, has_http_api=False, has_metrics=True),
    ServiceEndpoint("cj_assessment_service", 9095, has_http_api=False, has_metrics=True),
]


@pytest.fixture(scope="session")
async def validated_service_endpoints():
    """
    Session-scoped fixture that validates all services are healthy once per test session.

    Returns dict mapping service names to their validated endpoints.
    Eliminates redundant health checks across multiple test files.
    """
    validated_endpoints = {}

    async with httpx.AsyncClient(timeout=10.0) as client:
        for service in SERVICE_ENDPOINTS:
            if service.has_http_api:
                # Validate HTTP API health
                health_url = f"http://localhost:{service.port}/healthz"
                try:
                    response = await client.get(health_url)
                    assert response.status_code == 200, f"{service.name} health check failed"

                    response_data = response.json()
                    assert "status" in response_data, f"{service.name} missing 'status' field"
                    assert "message" in response_data, f"{service.name} missing 'message' field"

                    validated_endpoints[service.name] = {
                        "health_url": health_url,
                        "metrics_url": f"http://localhost:{service.port}/metrics",
                        "base_url": f"http://localhost:{service.port}",
                        "status": "healthy"
                    }
                    logger.info(f"✅ {service.name} HTTP API healthy")

                except (httpx.ConnectError, httpx.TimeoutException, AssertionError) as e:
                    pytest.skip(f"{service.name} not accessible: {e}")

            if service.has_metrics:
                # Validate metrics endpoint
                metrics_url = f"http://localhost:{service.port}/metrics"
                try:
                    response = await client.get(metrics_url)
                    assert response.status_code == 200, f"{service.name} metrics endpoint failed"

                    # Validate Prometheus format
                    metrics_text = response.text
                    content_type = response.headers.get("content-type", "")
                    assert "text/plain" in content_type, f"{service.name} invalid Content-Type"

                    if metrics_text.strip():
                        assert "# HELP" in metrics_text, f"{service.name} missing HELP comments"
                        assert "# TYPE" in metrics_text, f"{service.name} missing TYPE declarations"

                    if service.name not in validated_endpoints:
                        validated_endpoints[service.name] = {}
                    validated_endpoints[service.name]["metrics_url"] = metrics_url
                    validated_endpoints[service.name]["metrics_status"] = "valid"
                    logger.info(f"📊 {service.name} metrics endpoint valid")

                except (httpx.ConnectError, httpx.TimeoutException, AssertionError) as e:
                    logger.warning(f"⚠️  {service.name} metrics not accessible: {e}")

    return validated_endpoints


@pytest.fixture
async def kafka_consumer_factory():
    """
    Factory fixture for creating properly configured Kafka consumers.

    Eliminates duplicate Kafka consumer setup across E2E tests.
    Handles partition assignment and seeking to latest offset.
    """
    created_consumers = []

    async def create_consumer(
        test_name: str,
        topics: List[str] | None = None,
        config: KafkaTestConfig | None = None
    ) -> AIOKafkaConsumer:
        """Create and start a Kafka consumer with proper setup."""
        if config is None:
            config = create_kafka_test_config()

        if topics is None:
            topics = list(config.topics.values())

        consumer_group_id = f"test_{test_name}_{uuid.uuid4().hex[:8]}"

        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=config.bootstrap_servers,
            group_id=consumer_group_id,
            auto_offset_reset="latest",
            enable_auto_commit=False,
            value_deserializer=lambda x: json.loads(x.decode("utf-8")),
        )

        await consumer.start()
        created_consumers.append(consumer)
        logger.info(f"Consumer started for test: {test_name}")

        # Wait for partition assignment and seek to end
        partitions_assigned = False
        start_time = asyncio.get_event_loop().time()

        while not partitions_assigned:
            if asyncio.get_event_loop().time() - start_time > config.assignment_timeout:
                raise RuntimeError(
                    f"Kafka consumer for {test_name} did not get partition assignment"
                )

            assigned_partitions = consumer.assignment()
            if assigned_partitions:
                logger.info(f"Consumer assigned partitions: {assigned_partitions}")
                await consumer.seek_to_end()
                logger.info("Consumer positioned at end of all topics")
                partitions_assigned = True
            else:
                await asyncio.sleep(0.2)

        return consumer

    yield create_consumer

    # Cleanup all created consumers
    for consumer in created_consumers:
        try:
            await consumer.stop()
        except Exception as e:
            logger.warning(f"Error stopping consumer: {e}")


@pytest.fixture
async def service_interaction_client():
    """
    Factory for creating HTTP clients for service interactions.

    Provides common timeout and error handling for service API calls.
    """
    async def create_client(timeout: float = 30.0) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers={"Content-Type": "application/json"}
        )

    return create_client


@pytest.fixture
async def batch_creation_helper(validated_service_endpoints):
    """
    Helper for creating test batches via BOS API.

    Eliminates duplicate batch creation logic across E2E tests.
    """
    async def create_test_batch(
        expected_essay_count: int,
        course_code: str = "TEST",
        class_designation: str = "ConsolidatedTest",
        correlation_id: str | None = None
    ) -> tuple[str, str]:
        """Create a batch and return (batch_id, correlation_id)."""
        if "batch_orchestrator_service" not in validated_service_endpoints:
            pytest.skip("BOS not available for batch creation")

        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        batch_request = {
            "course_code": course_code,
            "class_designation": class_designation,
            "expected_essay_count": expected_essay_count,
            "essay_instructions": "Test batch created by consolidated fixtures",
            "teacher_name": "Test Teacher - Consolidated Fixtures",
        }

        bos_base_url = validated_service_endpoints["batch_orchestrator_service"]["base_url"]

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{bos_base_url}/v1/batches/register",
                json=batch_request,
                headers={"X-Correlation-ID": correlation_id}
            ) as response:
                if response.status != 202:
                    response_text = await response.text()
                    raise RuntimeError(
                        f"Batch creation failed: {response.status} - {response_text}"
                    )

                result = await response.json()
                batch_id = result["batch_id"]
                logger.info(f"Created test batch {batch_id} with {expected_essay_count} essays")
                return batch_id, correlation_id

    return create_test_batch


@pytest.fixture
async def file_upload_helper(validated_service_endpoints):
    """
    Helper for uploading files via File Service.

    Eliminates duplicate file upload logic across E2E tests.
    """
    async def upload_files(
        batch_id: str,
        files: List[Dict[str, Any]],
        correlation_id: str | None = None
    ) -> Dict[str, Any]:
        """Upload files to File Service batch endpoint."""
        if "file_service" not in validated_service_endpoints:
            pytest.skip("File Service not available for file upload")

        file_service_base = validated_service_endpoints["file_service"]["base_url"]

        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field("batch_id", batch_id)

            for file_info in files:
                data.add_field(
                    "files",
                    file_info["content"],
                    filename=file_info["name"],
                    content_type="text/plain"
                )

            headers = {}
            if correlation_id:
                headers["X-Correlation-ID"] = correlation_id

            async with session.post(
                f"{file_service_base}/v1/files/batch",
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 202:
                    result: Dict[str, Any] = await response.json()
                    logger.info(f"File upload successful: {len(files)} files")
                    return result
                else:
                    error_text = await response.text()
                    raise AssertionError(f"File upload failed: {response.status} - {error_text}")

    return upload_files


# Legacy compatibility - provide same interface as validation_coordination_utils
@pytest.fixture
def kafka_test_config():
    """Provide Kafka test configuration for backward compatibility."""
    return create_kafka_test_config()


@pytest.fixture
def service_endpoints_config():
    """Provide service endpoint configuration for tests."""
    return {service.name: service for service in SERVICE_ENDPOINTS}
