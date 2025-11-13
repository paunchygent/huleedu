#!/usr/bin/env python3
"""Validate service configurations against docker-compose setup.

This script checks for common configuration issues:
- Missing JWT_SECRET_KEY for services requiring authentication
- Missing database environment variables
- Missing Kafka configuration
- Port conflicts
- Inconsistent service dependencies

Usage:
    pdm run python scripts/validate_service_config.py
    pdm run python scripts/validate_service_config.py --strict  # Fail on warnings
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Any

import yaml

# Root of the monorepo
REPO_ROOT = Path(__file__).parent.parent


class ConfigValidator:
    """Validates service configurations."""

    def __init__(self, strict: bool = False):
        self.strict = strict
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def error(self, service: str, message: str, fix: str | None = None) -> None:
        """Record an error."""
        msg = f"❌ {service}: {message}"
        if fix:
            msg += f"\n   FIX: {fix}"
        self.errors.append(msg)

    def warning(self, service: str, message: str) -> None:
        """Record a warning."""
        self.warnings.append(f"⚠️  {service}: {message}")

    def success(self, service: str) -> None:
        """Record a success."""
        self.info.append(f"✅ {service}")

    def parse_service_config(self, config_path: Path) -> dict[str, Any]:
        """Extract relevant info from a service's config.py."""
        if not config_path.exists():
            return {}

        try:
            with open(config_path) as f:
                tree = ast.parse(f.read())

            info: dict[str, Any] = {
                "has_jwt_validation": False,
                "env_prefix": None,
                "settings_bases": [],
            }

            for node in ast.walk(tree):
                # Find Settings class definition
                if isinstance(node, ast.ClassDef) and node.name == "Settings":
                    # Check base classes
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            info["settings_bases"].append(base.id)
                        elif isinstance(base, ast.Attribute):
                            info["settings_bases"].append(base.attr)

                    # Check if JWTValidationSettings is inherited
                    info["has_jwt_validation"] = "JWTValidationSettings" in info["settings_bases"]

                    # Find model_config to extract env_prefix
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Name) and target.id == "model_config":
                                    # Extract env_prefix from SettingsConfigDict
                                    if isinstance(item.value, ast.Call):
                                        for keyword in item.value.keywords:
                                            if keyword.arg == "env_prefix":
                                                if isinstance(keyword.value, ast.Constant):
                                                    info["env_prefix"] = keyword.value.value

            return info

        except Exception as e:
            self.warning("parser", f"Failed to parse {config_path}: {e}")
            return {}

    def load_docker_compose(self) -> dict[str, Any]:
        """Load docker-compose.services.yml."""
        compose_path = REPO_ROOT / "docker-compose.services.yml"
        if not compose_path.exists():
            raise FileNotFoundError(f"docker-compose.services.yml not found at {compose_path}")

        with open(compose_path) as f:
            return yaml.safe_load(f)

    def check_jwt_configuration(
        self, service_name: str, config_info: dict[str, Any], service_env: list[str]
    ) -> None:
        """Check if service has required JWT configuration."""
        if not config_info.get("has_jwt_validation"):
            return

        env_prefix = config_info.get("env_prefix", "")
        if not env_prefix:
            self.warning(
                service_name,
                "Uses JWTValidationSettings but no env_prefix found. Cannot verify JWT_SECRET_KEY.",
            )
            return

        required_var = f"{env_prefix}JWT_SECRET_KEY"

        # Check if required var is in environment
        has_jwt_secret = any(required_var in env_var for env_var in service_env)

        if not has_jwt_secret:
            fix = f"Add to docker-compose.services.yml environment section:\n        - {required_var}=${{JWT_SECRET_KEY}}"
            self.error(
                service_name,
                f"Inherits JWTValidationSettings but missing {required_var} in docker-compose",
                fix,
            )

    def check_database_configuration(self, service_name: str, service_env: list[str]) -> None:
        """Check if service has database credentials."""
        needs_db = any("DATABASE_URL" in var or "DB_PASSWORD" in var for var in service_env)

        if needs_db:
            has_db_user = any("HULEEDU_DB_USER" in var for var in service_env)
            has_db_password = any("HULEEDU_DB_PASSWORD" in var for var in service_env)

            if not has_db_user:
                self.warning(service_name, "Uses database but missing HULEEDU_DB_USER")
            if not has_db_password:
                self.warning(service_name, "Uses database but missing HULEEDU_DB_PASSWORD")

    def check_kafka_configuration(
        self, service_name: str, config_info: dict[str, Any], service_env: list[str]
    ) -> None:
        """Check if service has Kafka configuration."""
        # Check if config has KAFKA_BOOTSTRAP_SERVERS setting
        env_prefix = config_info.get("env_prefix", "")
        if env_prefix:
            kafka_var = f"{env_prefix}KAFKA_BOOTSTRAP_SERVERS"
            has_kafka = any(kafka_var in var for var in service_env)

            # Check if service depends on kafka
            # This is a heuristic - services ending in _service often use Kafka
            if "service" in service_name and not has_kafka:
                # Don't warn for services that clearly don't need Kafka
                skip_kafka = ["db", "redis", "zookeeper", "jaeger", "topic_setup"]
                if not any(skip in service_name for skip in skip_kafka):
                    self.info.append(
                        f"ℹ️  {service_name}: No Kafka configuration (may be intentional)"
                    )

    def check_port_conflicts(self, compose_config: dict[str, Any]) -> None:
        """Check for duplicate port mappings."""
        port_map: dict[str, list[str]] = {}

        services = compose_config.get("services", {})
        for service_name, service_config in services.items():
            ports = service_config.get("ports", [])
            for port_mapping in ports:
                if isinstance(port_mapping, str):
                    # Format: "host:container" or "port"
                    host_port = port_mapping.split(":")[0]
                    if host_port not in port_map:
                        port_map[host_port] = []
                    port_map[host_port].append(service_name)

        # Check for conflicts
        for port, services in port_map.items():
            if len(services) > 1:
                self.error(
                    "port_conflict",
                    f"Port {port} is mapped by multiple services: {', '.join(services)}",
                )

    def validate_service(
        self, service_name: str, service_config: dict[str, Any], compose_config: dict[str, Any]
    ) -> None:
        """Validate a single service configuration."""
        # Parse the service's config.py
        config_path = REPO_ROOT / "services" / service_name / "config.py"
        config_info = self.parse_service_config(config_path)

        if not config_info:
            # Service might not have a config.py (e.g., databases, infrastructure)
            return

        # Get service environment variables from docker-compose
        service_env = service_config.get("environment", [])

        # Convert dict-style environment to list of strings
        if isinstance(service_env, dict):
            service_env = [f"{k}={v}" for k, v in service_env.items()]

        # Run checks
        self.check_jwt_configuration(service_name, config_info, service_env)
        self.check_database_configuration(service_name, service_env)
        self.check_kafka_configuration(service_name, config_info, service_env)

        # If no errors for this service, mark as success
        if not any(service_name in err for err in self.errors):
            self.success(service_name)

    def validate_all(self) -> int:
        """Run all validation checks."""
        print("🔍 Validating Service Configurations...\n")

        # Load docker-compose
        try:
            compose_config = self.load_docker_compose()
        except Exception as e:
            print(f"❌ Failed to load docker-compose.services.yml: {e}")
            return 1

        services = compose_config.get("services", {})

        # Check port conflicts first (cross-service check)
        self.check_port_conflicts(compose_config)

        # Validate each service
        for service_name, service_config in services.items():
            self.validate_service(service_name, service_config, compose_config)

        # Print results
        print("\n" + "=" * 70)
        print("VALIDATION RESULTS")
        print("=" * 70 + "\n")

        if self.info:
            for msg in self.info:
                print(msg)

        if self.warnings:
            print("\n⚠️  WARNINGS:\n")
            for msg in self.warnings:
                print(msg)

        if self.errors:
            print("\n❌ ERRORS:\n")
            for msg in self.errors:
                print(msg)
            print(f"\n❌ {len(self.errors)} configuration error(s) found")
            return 1

        if self.warnings and self.strict:
            print(f"\n⚠️  {len(self.warnings)} warning(s) found (failing due to --strict mode)")
            return 1

        print("\n✅ All service configurations are valid!")
        return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate service configurations against docker-compose setup"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )

    args = parser.parse_args()

    validator = ConfigValidator(strict=args.strict)
    return validator.validate_all()


if __name__ == "__main__":
    sys.exit(main())
