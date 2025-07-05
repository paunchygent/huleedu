"""Connection pool manager for optimized HTTP client performance."""

from __future__ import annotations

from typing import Dict

import aiohttp
from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.config import Settings

logger = create_service_logger("llm_provider_service.connection_pool_manager")


class ConnectionPoolManagerImpl:
    """Manages optimized HTTP connection pools for LLM providers.

    Phase 7 Performance Enhancement:
    - Provider-specific connection pools
    - Optimized connection limits and timeouts
    - Connection pool metrics tracking
    - Automatic connection health monitoring
    """

    def __init__(self, settings: Settings):
        """Initialize connection pool manager.

        Args:
            settings: Service settings
        """
        self.settings = settings
        self._sessions: Dict[str, aiohttp.ClientSession] = {}
        self._connector_pools: Dict[str, aiohttp.TCPConnector] = {}
        self._metrics_data: Dict[str, Dict[str, int]] = {}

    async def get_session(self, provider: str) -> aiohttp.ClientSession:
        """Get optimized session for specific provider.

        Args:
            provider: Provider name (openai, anthropic, google, openrouter)

        Returns:
            Optimized ClientSession for the provider
        """
        if provider not in self._sessions:
            await self._create_provider_session(provider)

        session = self._sessions[provider]
        await self._update_connection_metrics(provider, session)
        return session

    async def _create_provider_session(self, provider: str) -> None:
        """Create optimized session for specific provider."""
        # Provider-specific connection limits
        connection_limits = self._get_provider_connection_limits(provider)

        # Create optimized connector
        connector = aiohttp.TCPConnector(
            limit=connection_limits["total_pool_size"],
            limit_per_host=connection_limits["per_host_limit"],
            ttl_dns_cache=300,  # 5 minutes DNS cache
            use_dns_cache=True,
            enable_cleanup_closed=True,
            keepalive_timeout=30,  # Keep connections alive for 30 seconds
            ssl=False if provider == "mock" else True,  # SSL configuration
        )

        # Create optimized timeout
        timeout = aiohttp.ClientTimeout(
            total=connection_limits["total_timeout"],
            connect=connection_limits["connect_timeout"],
            sock_read=connection_limits["read_timeout"],
        )

        # Create session with optimizations
        session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=self._get_provider_headers(provider),
            raise_for_status=False,  # Handle status codes manually for better error control
            trust_env=True,  # Use proxy settings from environment
        )

        self._sessions[provider] = session
        self._connector_pools[provider] = connector
        self._metrics_data[provider] = {
            "total_connections": 0,
            "active_connections": 0,
            "pool_size": connection_limits["total_pool_size"],
        }

        logger.info(
            f"Created optimized HTTP session for {provider}: "
            f"pool_size={connection_limits['total_pool_size']}, "
            f"per_host={connection_limits['per_host_limit']}, "
            f"timeout={connection_limits['total_timeout']}s"
        )

    def _get_provider_connection_limits(self, provider: str) -> Dict[str, int]:
        """Get provider-specific connection limits optimized for performance."""
        base_config = {
            "total_pool_size": 100,
            "per_host_limit": 20,
            "total_timeout": 60,
            "connect_timeout": 10,
            "read_timeout": 45,
        }

        # Provider-specific optimizations
        provider_configs = {
            "openai": {
                "total_pool_size": 50,  # OpenAI has good connection handling
                "per_host_limit": 15,
                "total_timeout": 30,  # OpenAI is generally fast
                "connect_timeout": 5,
                "read_timeout": 25,
            },
            "anthropic": {
                "total_pool_size": 40,  # Anthropic Claude API
                "per_host_limit": 12,
                "total_timeout": 45,  # Anthropic can be slower for large outputs
                "connect_timeout": 8,
                "read_timeout": 35,
            },
            "google": {
                "total_pool_size": 60,  # Google has robust infrastructure
                "per_host_limit": 18,
                "total_timeout": 40,
                "connect_timeout": 6,
                "read_timeout": 30,
            },
            "openrouter": {
                "total_pool_size": 30,  # OpenRouter proxy service
                "per_host_limit": 10,
                "total_timeout": 50,  # May route through multiple providers
                "connect_timeout": 10,
                "read_timeout": 40,
            },
        }

        return provider_configs.get(provider, base_config)

    def _get_provider_headers(self, provider: str) -> Dict[str, str]:
        """Get provider-specific HTTP headers for optimization."""
        common_headers = {
            "User-Agent": (
                f"HuleEdu-LLM-Service/{getattr(self.settings, 'SERVICE_VERSION', '1.0.0')}"
            ),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Connection": "keep-alive",  # Ensure keep-alive for connection reuse
        }

        # Provider-specific headers
        if provider == "openai":
            common_headers.update(
                {
                    "OpenAI-Beta": "assistants=v1",  # Enable latest features
                }
            )
        elif provider == "anthropic":
            common_headers.update(
                {
                    "Anthropic-Version": "2023-06-01",  # Latest stable API version
                }
            )
        elif provider == "google":
            # Note: X-Goog-User-Project header causes 403 permission errors
            # Google Generative AI API works better without this header
            pass

        return common_headers

    async def _update_connection_metrics(
        self, provider: str, session: aiohttp.ClientSession
    ) -> None:
        """Update connection pool metrics for monitoring."""
        try:
            connector = session.connector
            if connector and hasattr(connector, "_conns"):
                # Get connection statistics
                total_connections = sum(len(conns) for conns in connector._conns.values())

                # Update metrics data
                self._metrics_data[provider].update(
                    {
                        "total_connections": total_connections,
                        "active_connections": len(getattr(connector, "_acquired", {})),
                    }
                )

                # Update Prometheus metrics if available
                await self._record_connection_pool_metrics(provider)

        except Exception as e:
            logger.debug(f"Failed to update connection metrics for {provider}: {e}")

    async def _record_connection_pool_metrics(self, provider: str) -> None:
        """Record connection pool metrics to Prometheus."""
        try:
            from services.llm_provider_service.metrics import get_llm_metrics

            metrics = get_llm_metrics()

            pool_data = self._metrics_data[provider]

            # Update pool size gauge
            pool_size_metric = metrics.get("llm_provider_connection_pool_size")
            if pool_size_metric:
                pool_size_metric.labels(provider=provider).set(pool_data["pool_size"])

            # Update active connections gauge
            active_metric = metrics.get("llm_provider_connection_pool_active")
            if active_metric:
                active_metric.labels(provider=provider).set(pool_data["active_connections"])

        except Exception:
            # Don't let metrics recording break connection management
            pass

    async def get_connection_stats(self, provider: str) -> Dict[str, int]:
        """Get connection statistics for a provider.

        Args:
            provider: Provider name

        Returns:
            Dictionary with connection statistics
        """
        if provider in self._sessions:
            await self._update_connection_metrics(provider, self._sessions[provider])
            return self._metrics_data.get(provider, {})
        return {}

    async def health_check_connections(self) -> Dict[str, bool]:
        """Perform health check on all connection pools.

        Returns:
            Dictionary mapping provider names to health status
        """
        health_status = {}

        for provider, session in self._sessions.items():
            try:
                # Simple health check - verify session is not closed
                health_status[provider] = not session.closed

                # If session is closed, attempt to recreate
                if session.closed:
                    logger.warning(f"Session for {provider} is closed, recreating...")
                    await self._create_provider_session(provider)
                    health_status[provider] = True

            except Exception as e:
                logger.error(f"Health check failed for {provider}: {e}")
                health_status[provider] = False

        return health_status

    async def cleanup(self) -> None:
        """Clean up all sessions and connection pools."""
        for provider, session in self._sessions.items():
            try:
                if not session.closed:
                    await session.close()
                logger.info(f"Closed HTTP session for {provider}")
            except Exception as e:
                logger.error(f"Error closing session for {provider}: {e}")

        self._sessions.clear()
        self._connector_pools.clear()
        self._metrics_data.clear()

    async def optimize_for_load(self, expected_load: Dict[str, int]) -> None:
        """Dynamically optimize connection pools based on expected load.

        Args:
            expected_load: Dictionary mapping provider names to expected request volume
        """
        for provider, load in expected_load.items():
            if provider in self._sessions:
                current_config = self._get_provider_connection_limits(provider)

                # Adjust pool size based on load
                if load > 100:  # High load
                    current_config["total_pool_size"] = min(
                        200, current_config["total_pool_size"] * 2
                    )
                    current_config["per_host_limit"] = min(50, current_config["per_host_limit"] * 2)
                elif load < 10:  # Low load
                    current_config["total_pool_size"] = max(
                        10, current_config["total_pool_size"] // 2
                    )
                    current_config["per_host_limit"] = max(5, current_config["per_host_limit"] // 2)

                # Recreate session with new limits if significant change
                logger.info(f"Optimizing connection pool for {provider} based on load: {load}")
                await self._create_provider_session(provider)
