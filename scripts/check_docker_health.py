#!/usr/bin/env python3
"""
Docker Health Check Script for HuleEdu Platform
Inspects all Docker containers and their health status.
"""

import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List


def run_command(cmd: List[str]) -> tuple[str, int]:
    """Run a shell command and return output and return code."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.stdout.strip(), result.returncode
    except Exception as e:
        return f"Error running command: {e}", 1


def get_container_info() -> List[Dict[str, Any]]:
    """Get detailed information about all Docker containers."""
    cmd = [
        "docker",
        "ps",
        "-a",
        "--format",
        "{{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}\t{{.CreatedAt}}",
    ]
    output, returncode = run_command(cmd)

    if returncode != 0:
        print(f"Error getting container info: {output}")
        return []

    containers = []
    for line in output.split("\n"):
        if line.strip():
            parts = line.split("\t")
            if len(parts) >= 4:
                containers.append(
                    {
                        "name": parts[0],
                        "status": parts[1],
                        "ports": parts[2] if len(parts) > 2 else "",
                        "image": parts[3] if len(parts) > 3 else "",
                        "created": parts[4] if len(parts) > 4 else "",
                    }
                )

    return containers


def get_container_health(container_name: str) -> str:
    """Get health status of a specific container."""
    cmd = ["docker", "inspect", "--format", "{{.State.Health.Status}}", container_name]
    output, returncode = run_command(cmd)

    if returncode != 0:
        return "no-healthcheck"

    return output if output else "no-healthcheck"


def get_compose_services() -> List[str]:
    """Get list of services defined in docker-compose files."""
    cmd = ["docker", "compose", "config", "--services"]
    output, returncode = run_command(cmd)

    if returncode != 0:
        print(f"Warning: Could not get compose services: {output}")
        return []

    return [service.strip() for service in output.split("\n") if service.strip()]


def check_docker_daemon() -> bool:
    """Check if Docker daemon is running."""
    cmd = ["docker", "info"]
    _, returncode = run_command(cmd)
    return returncode == 0


def main():
    """Main function to check Docker container health."""
    print("=" * 80)
    print("HuleEdu Platform - Docker Container Health Check")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Check if Docker daemon is running
    if not check_docker_daemon():
        print("❌ Docker daemon is not running or not accessible!")
        print("Please start Docker and try again.")
        sys.exit(1)

    print("✅ Docker daemon is running")
    print()

    # Get all containers
    containers = get_container_info()

    if not containers:
        print("⚠️  No Docker containers found")
        print("You may need to start your services with: docker compose up -d")
        return

    # Get compose services for comparison
    compose_services = get_compose_services()

    print(f"Found {len(containers)} Docker containers:")
    print("-" * 80)

    running_containers = 0
    healthy_containers = 0
    unhealthy_containers = 0

    for container in containers:
        name = container["name"]
        status = container["status"]
        ports = container["ports"]
        image = container["image"]

        # Determine status emoji
        if "Up" in status:
            status_emoji = "🟢"
            running_containers += 1
        elif "Exited" in status:
            status_emoji = "🔴"
        else:
            status_emoji = "🟡"

        # Get health status
        health = get_container_health(name)
        if health == "healthy":
            health_emoji = "💚"
            healthy_containers += 1
        elif health == "unhealthy":
            health_emoji = "❤️"
            unhealthy_containers += 1
        elif health == "starting":
            health_emoji = "🟡"
        else:
            health_emoji = "⚪"  # no healthcheck

        print(f"{status_emoji} {name}")
        print(f"   Status: {status}")
        print(f"   Health: {health} {health_emoji}")
        print(f"   Image:  {image}")
        if ports:
            print(f"   Ports:  {ports}")
        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total containers: {len(containers)}")
    print(f"Running: {running_containers}")
    print(f"Healthy: {healthy_containers}")
    print(f"Unhealthy: {unhealthy_containers}")

    if compose_services:
        print(f"Compose services defined: {len(compose_services)}")

        # Check for missing services
        container_names = [c["name"] for c in containers]
        missing_services = []
        for service in compose_services:
            # Docker compose prefixes container names
            expected_name = f"huleedu_{service}"
            if expected_name not in container_names and service not in container_names:
                missing_services.append(service)

        if missing_services:
            print(f"⚠️  Services not running: {', '.join(missing_services)}")

    # Health recommendations
    print()
    print("RECOMMENDATIONS")
    print("-" * 40)

    if unhealthy_containers > 0:
        print("❌ Some containers are unhealthy. Check logs with:")
        print("   docker compose logs <service_name>")

    if running_containers == 0:
        print("🚀 Start all services with:")
        print("   docker compose up -d")
    elif running_containers < len(compose_services):
        print("🔄 Start missing services with:")
        print("   docker compose up -d")
    else:
        print("✅ All expected containers appear to be running!")

    print("\n📊 For detailed logs: docker compose logs -f")
    print("🔍 For specific service: docker compose logs -f <service_name>")


if __name__ == "__main__":
    main()
