"""
Dynamic service discovery for E2E testing.
Queries Docker runtime for actual service endpoints.
"""

import re
import subprocess
from typing import Dict, Optional

from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("test.service_discovery")


class ServiceDiscovery:
    """Discovers service endpoints by inspecting Docker containers."""

    # Map container names to service names for our test framework
    CONTAINER_TO_SERVICE_MAP = {
        "huleedu_essay_lifecycle_api": "essay_lifecycle_service",
        "huleedu_batch_orchestrator_service": "batch_orchestrator_service",
        "huleedu_spellchecker_service": "spellchecker_service",
        "huleedu_cj_assessment_service": "cj_assessment_service",
        "huleedu_result_aggregator": "result_aggregator_service",
    }

    def discover_endpoints(self) -> Dict[str, str]:
        """
        Discover all service health endpoints from running Docker containers.

        Returns:
            Dict mapping service_name -> health endpoint URL

        Raises:
            RuntimeError: If required services are not running
        """
        endpoints = {}

        # Get container info using docker ps
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}:{{.Ports}}"],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to query Docker containers: {e}")

        # Parse container information
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            container_name, ports = line.split(":", 1)

            # Skip if not a service we care about
            if container_name not in self.CONTAINER_TO_SERVICE_MAP:
                continue

            # Extract the health check port
            health_port = self._extract_health_port(container_name, ports)
            if health_port:
                service_name = self.CONTAINER_TO_SERVICE_MAP[container_name]
                endpoints[service_name] = f"http://localhost:{health_port}/healthz"
                logger.info(f"Discovered {service_name} at port {health_port}")

        # Validate we found all required services
        missing = set(self.CONTAINER_TO_SERVICE_MAP.values()) - set(endpoints.keys())
        if missing:
            raise RuntimeError(
                f"Required services not running: {missing}\n"
                f"Start services with: docker compose up -d"
            )

        return endpoints

    def _extract_health_port(self, container_name: str, ports_string: str) -> Optional[int]:
        """
        Extract the health check port from Docker port mapping.

        Examples:
        - "0.0.0.0:8002->8002/tcp" -> 8002
        - "0.0.0.0:9095->9090/tcp" -> 9095 (host port)
        """
        # Match pattern like "0.0.0.0:8002->8002/tcp"
        pattern = r"0\.0\.0\.0:(\d+)->(\d+)/tcp"

        for match in re.finditer(pattern, ports_string):
            host_port = int(match.group(1))
            int(match.group(2))

            # For health checks, we need the host port
            return host_port

        logger.warning(f"Could not extract port for {container_name} from: {ports_string}")
        return None
