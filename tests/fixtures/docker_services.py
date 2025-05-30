"""
Docker Service Fixtures

Provides pytest fixtures for managing Docker Compose services during functional testing.
Includes service health waiting, cleanup, and isolated test environments.
"""

import asyncio
import subprocess
import time
from typing import Dict, List, Optional

import pytest


class DockerComposeManager:
    """Manager for Docker Compose operations during testing."""

    def __init__(self, compose_file: str = "docker-compose.yml"):
        self.compose_file = compose_file
        self.services_started = False

    async def start_services(self, services: Optional[List[str]] = None) -> bool:
        """Start Docker Compose services and wait for them to be healthy."""
        try:
            cmd = ["docker-compose", "-f", self.compose_file, "up", "-d"]
            if services:
                cmd.extend(services)

            subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.services_started = True

            # Wait for services to be healthy
            await self.wait_for_service_health()
            return True

        except subprocess.CalledProcessError as e:
            print(f"Failed to start Docker services: {e.stderr}")
            return False

    async def stop_services(self) -> bool:
        """Stop Docker Compose services."""
        try:
            cmd = ["docker-compose", "-f", self.compose_file, "down"]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.services_started = False
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to stop Docker services: {e.stderr}")
            return False

    async def wait_for_service_health(self, timeout: int = 60) -> bool:
        """Wait for all services to be healthy."""
        import httpx

        services = [
            ("content_service", 8001, "/healthz"),
            ("batch_orchestrator_service", 5001, "/healthz"),
            ("essay_lifecycle_service", 6001, "/healthz"),
        ]

        start_time = time.time()

        async with httpx.AsyncClient() as client:
            while time.time() - start_time < timeout:
                all_healthy = True

                for service_name, port, endpoint in services:
                    try:
                        url = f"http://localhost:{port}{endpoint}"
                        response = await client.get(url, timeout=5.0)
                        if response.status_code != 200:
                            all_healthy = False
                            break
                    except Exception:
                        all_healthy = False
                        break

                if all_healthy:
                    return True

                await asyncio.sleep(2)

        return False


@pytest.fixture(scope="session")
async def docker_services():
    """Session-scoped fixture that manages Docker Compose services for all tests."""
    manager = DockerComposeManager()

    # Start services at beginning of test session
    success = await manager.start_services()
    if not success:
        pytest.skip("Failed to start Docker services")

    yield manager

    # Cleanup at end of test session
    await manager.stop_services()


@pytest.fixture(scope="function")
async def isolated_services():
    """Function-scoped fixture for tests requiring isolated service state."""
    manager = DockerComposeManager()

    # Start fresh services for this test
    await manager.start_services()

    yield manager

    # Clean up after test
    await manager.stop_services()


@pytest.fixture
def service_urls() -> Dict[str, str]:
    """Provides service URLs for testing."""
    return {
        "content_service": "http://localhost:8001",
        "batch_orchestrator_service": "http://localhost:5001",
        "essay_lifecycle_service": "http://localhost:6001",
        "spell_checker_metrics": "http://localhost:8002",
    }


# TODO: Add container log capture fixtures
# TODO: Add service isolation fixtures
# TODO: Add database reset fixtures
