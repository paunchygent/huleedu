"""Essay Lifecycle Service client implementation for Batch Orchestrator Service."""

from __future__ import annotations

from aiohttp import ClientSession
from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.protocols import EssayLifecycleClientProtocol


class DefaultEssayLifecycleClientImpl(EssayLifecycleClientProtocol):
    """Default implementation of EssayLifecycleClientProtocol."""

    def __init__(self, http_session: ClientSession, settings: Settings) -> None:
        """Initialize with HTTP client and settings dependencies."""
        self.http_session = http_session
        self.settings = settings

    async def request_essay_phase_initiation(
        self,
        batch_id: str,
        essay_ids: list[str],
        phase: str,
    ) -> None:
        """Mock implementation - logs the request."""
        # TODO: Implement actual HTTP call to Essay Lifecycle Service
