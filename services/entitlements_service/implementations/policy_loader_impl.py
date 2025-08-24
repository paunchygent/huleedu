"""Policy loader implementation for Entitlements Service.

This module provides YAML-based policy configuration loading with Redis
caching for performance and hot-reload capabilities.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.entitlements_service.protocols import PolicyConfig

logger = create_service_logger("entitlements_service.policy_loader")


class PolicyLoaderImpl:
    """Implementation of policy loader with YAML file and Redis caching."""

    def __init__(
        self,
        redis_client: AtomicRedisClientProtocol,
        config_path: str = "policies/default.yaml",
        cache_ttl: int = 300,
    ) -> None:
        """Initialize policy loader.

        Args:
            redis_client: Redis client for caching
            config_path: Path to policy YAML file
            cache_ttl: Cache TTL in seconds
        """
        self.redis_client = redis_client
        self.config_path = config_path
        self.cache_ttl = cache_ttl
        self.cache_key = "entitlements:policies:v1"

        # Resolve full path relative to service directory
        if not os.path.isabs(config_path):
            service_dir = Path(__file__).parent.parent
            self.full_config_path = service_dir / config_path
        else:
            self.full_config_path = Path(config_path)

    async def load_policies(self) -> PolicyConfig:
        """Load and cache policy configuration from file.

        Returns:
            PolicyConfig with current policy settings

        Raises:
            FileNotFoundError: If policy file doesn't exist
            yaml.YAMLError: If policy file is invalid YAML
            ValueError: If policy structure is invalid
        """
        logger.info(f"Loading policies from {self.full_config_path}")

        if not self.full_config_path.exists():
            raise FileNotFoundError(f"Policy file not found: {self.full_config_path}")

        try:
            # Load policy from file
            with open(self.full_config_path, "r", encoding="utf-8") as f:
                policy_data = yaml.safe_load(f)

            if not policy_data:
                raise ValueError("Policy file is empty or invalid")

            # Validate policy structure
            self._validate_policy_structure(policy_data)

            # Create PolicyConfig object
            policy_config = PolicyConfig(
                costs=policy_data.get("costs", {}),
                rate_limits=policy_data.get("rate_limits", {}),
                signup_bonuses=policy_data.get("signup_bonuses", {}),
                cache_ttl=policy_data.get("cache_ttl", self.cache_ttl),
            )

            # Cache in Redis
            try:
                cache_data = policy_config.model_dump()
                await self.redis_client.setex(
                    self.cache_key,
                    self.cache_ttl,
                    json.dumps(cache_data),
                )
                logger.info("Policies cached in Redis", extra={"cache_ttl": self.cache_ttl})
            except Exception as e:
                logger.warning(f"Failed to cache policies in Redis: {e}")

            logger.info(
                "Policies loaded successfully", extra={"costs_count": len(policy_config.costs)}
            )
            return policy_config

        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in policy file: {e}")
            raise

    async def get_cost(self, metric: str) -> int:
        """Get credit cost for a specific metric.

        Args:
            metric: Operation metric name

        Returns:
            Credit cost (0 for free operations)
        """
        policies = await self._get_cached_policies()
        cost = policies.costs.get(metric, 0)

        if cost == 0:
            logger.debug(f"Free operation: {metric}")
        else:
            logger.debug(f"Credit cost for {metric}: {cost}")

        return cost

    async def get_rate_limit(self, metric: str) -> tuple[int, int]:
        """Get rate limit configuration for a metric.

        Args:
            metric: Operation metric name

        Returns:
            Tuple of (count, window_seconds), (0, 0) for unlimited

        Raises:
            ValueError: If rate limit format is invalid
        """
        policies = await self._get_cached_policies()
        limit_str = policies.rate_limits.get(metric, "unlimited")

        if limit_str == "unlimited":
            logger.debug(f"No rate limit for {metric}")
            return (0, 0)

        try:
            # Parse "60/hour" or "100/day" format
            if "/" not in limit_str:
                raise ValueError(f"Invalid rate limit format: {limit_str}")

            count_str, period = limit_str.split("/", 1)
            count = int(count_str)

            # Convert period to seconds
            period_seconds = {
                "hour": 3600,
                "day": 86400,
                "week": 604800,
                "month": 2592000,  # 30 days
            }

            if period not in period_seconds:
                raise ValueError(f"Invalid rate limit period: {period}")

            window_seconds = period_seconds[period]
            logger.debug(f"Rate limit for {metric}: {count}/{period} ({window_seconds}s)")

            return (count, window_seconds)

        except (ValueError, IndexError) as e:
            logger.error(f"Invalid rate limit format for {metric}: {limit_str}")
            raise ValueError(f"Invalid rate limit format for {metric}: {limit_str}") from e

    async def reload_policies(self) -> None:
        """Force reload of policies from file and update cache."""
        logger.info("Force reloading policies")

        # Clear cache first
        try:
            await self.redis_client.delete(self.cache_key)
            logger.debug("Policy cache cleared")
        except Exception as e:
            logger.warning(f"Failed to clear policy cache: {e}")

        # Reload from file
        await self.load_policies()

    async def _get_cached_policies(self) -> PolicyConfig:
        """Get policies from cache or load from file if not cached.

        Returns:
            PolicyConfig with current policy settings
        """
        try:
            # Try to get from cache first
            cached_data = await self.redis_client.get(self.cache_key)

            if cached_data:
                logger.debug("Using cached policies")
                policy_dict = json.loads(cached_data)
                return PolicyConfig(**policy_dict)

        except Exception as e:
            logger.warning(f"Failed to retrieve cached policies: {e}")

        # Cache miss - load from file
        logger.debug("Policy cache miss - loading from file")
        return await self.load_policies()

    def _validate_policy_structure(self, policy_data: dict[str, Any]) -> None:
        """Validate the structure of policy data.

        Args:
            policy_data: Raw policy data from YAML

        Raises:
            ValueError: If policy structure is invalid
        """
        required_sections = ["costs", "rate_limits", "signup_bonuses"]

        for section in required_sections:
            if section not in policy_data:
                raise ValueError(f"Missing required policy section: {section}")

            if not isinstance(policy_data[section], dict):
                raise ValueError(f"Policy section '{section}' must be a dictionary")

        # Validate costs are non-negative integers
        for metric, cost in policy_data["costs"].items():
            if not isinstance(cost, int) or cost < 0:
                raise ValueError(f"Invalid cost for {metric}: must be non-negative integer")

        # Validate rate limits format
        for metric, limit in policy_data["rate_limits"].items():
            if not isinstance(limit, str):
                raise ValueError(f"Invalid rate limit for {metric}: must be string")

            if limit != "unlimited" and "/" not in limit:
                raise ValueError(f"Invalid rate limit format for {metric}: {limit}")

        # Validate signup bonuses are non-negative integers
        for subject_type, bonus in policy_data["signup_bonuses"].items():
            if not isinstance(bonus, int) or bonus < 0:
                raise ValueError(
                    f"Invalid signup bonus for {subject_type}: must be non-negative integer"
                )

        logger.debug("Policy structure validation passed")
