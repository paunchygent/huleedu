"""Test the service discovery mechanism."""

import pytest

from tests.utils.service_discovery import ServiceDiscovery


def test_service_discovery_finds_all_required_services():
    """Verify service discovery can find all required services."""
    discovery = ServiceDiscovery()

    # This will raise RuntimeError if services aren't running
    endpoints = discovery.discover_endpoints()

    # Verify we found all required services
    required_services = {
        "essay_lifecycle_service",
        "batch_orchestrator_service",
        "spellchecker_service",
        "cj_assessment_service",
        "result_aggregator_service",
    }

    assert set(endpoints.keys()) == required_services

    # Verify endpoints have correct format
    for service, endpoint in endpoints.items():
        assert endpoint.startswith("http://localhost:")
        assert endpoint.endswith("/healthz")

    # Log discovered configuration for debugging
    print("\nDiscovered Service Configuration:")
    for service, endpoint in sorted(endpoints.items()):
        print(f"  {service}: {endpoint}")


def test_service_discovery_error_when_services_not_running():
    """Verify service discovery provides helpful error when services aren't running."""
    discovery = ServiceDiscovery()

    # Mock the container map to simulate missing services
    original_map = discovery.CONTAINER_TO_SERVICE_MAP
    discovery.CONTAINER_TO_SERVICE_MAP = {"non_existent_container": "missing_service"}

    try:
        with pytest.raises(RuntimeError) as exc_info:
            discovery.discover_endpoints()

        assert "Required services not running" in str(exc_info.value)
        assert "docker compose up -d" in str(exc_info.value)
    finally:
        # Restore original map
        discovery.CONTAINER_TO_SERVICE_MAP = original_map
