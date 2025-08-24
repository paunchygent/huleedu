"""Mock policy loader implementation for testing.

This module provides a mock implementation of the policy loader
for use in development and testing environments.
"""

from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger

from services.entitlements_service.protocols import PolicyConfig

logger = create_service_logger("entitlements_service.mock_policy_loader")


class MockPolicyLoaderImpl:
    """Mock implementation of policy loader for testing."""

    def __init__(self) -> None:
        """Initialize mock policy loader with default test policies."""
        self._policies = PolicyConfig(
            costs={
                "batch_create": 0,
                "spellcheck": 0,
                "nlp_analysis": 0,
                "cj_assessment": 10,
                "ai_feedback": 5,
                "ai_grading": 8,
                "content_analysis": 3,
            },
            rate_limits={
                "batch_create": "60/hour",
                "cj_assessment": "100/day",
                "ai_feedback": "200/day",
                "ai_grading": "150/day",
                "content_upload": "500/hour",
            },
            signup_bonuses={
                "user": 50,
                "org": 500,
            },
            cache_ttl=300,
        )

    async def load_policies(self) -> PolicyConfig:
        """Load mock policy configuration.

        Returns:
            PolicyConfig with test policy settings
        """
        logger.debug("Loading mock policies")
        return self._policies

    async def get_cost(self, metric: str) -> int:
        """Get credit cost for a specific metric.

        Args:
            metric: Operation metric name

        Returns:
            Credit cost (0 for free operations)
        """
        cost = self._policies.costs.get(metric, 0)
        logger.debug(f"Mock cost for {metric}: {cost}")
        return cost

    async def get_rate_limit(self, metric: str) -> tuple[int, int]:
        """Get rate limit configuration for a metric.

        Args:
            metric: Operation metric name

        Returns:
            Tuple of (count, window_seconds), (0, 0) for unlimited
        """
        limit_str = self._policies.rate_limits.get(metric, "unlimited")

        if limit_str == "unlimited":
            logger.debug(f"Mock: No rate limit for {metric}")
            return (0, 0)

        # Parse "60/hour" or "100/day" format
        count_str, period = limit_str.split("/", 1)
        count = int(count_str)

        period_seconds = {
            "hour": 3600,
            "day": 86400,
            "week": 604800,
            "month": 2592000,
        }

        window_seconds = period_seconds.get(period, 3600)
        logger.debug(f"Mock rate limit for {metric}: {count}/{period} ({window_seconds}s)")

        return (count, window_seconds)

    async def reload_policies(self) -> None:
        """Force reload of policies (no-op for mock)."""
        logger.debug("Mock policy reload requested")

    def set_mock_policies(self, policies: PolicyConfig) -> None:
        """Set mock policy configuration for testing.

        Args:
            policies: PolicyConfig to use for testing
        """
        self._policies = policies
        logger.debug("Mock policies updated")

    def set_mock_cost(self, metric: str, cost: int) -> None:
        """Set mock cost for a specific metric.

        Args:
            metric: Operation metric name
            cost: Credit cost to set
        """
        self._policies.costs[metric] = cost
        logger.debug(f"Mock cost for {metric} set to {cost}")

    def set_mock_rate_limit(self, metric: str, limit: str) -> None:
        """Set mock rate limit for a specific metric.

        Args:
            metric: Operation metric name
            limit: Rate limit string (e.g., "100/day")
        """
        self._policies.rate_limits[metric] = limit
        logger.debug(f"Mock rate limit for {metric} set to {limit}")
