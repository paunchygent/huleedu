"""Test providers for BFF Teacher Service tests.

Provides Dishka DI test providers following API Gateway pattern.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import Mock
from uuid import UUID, uuid4

import httpx
from dishka import Provider, Scope, provide
from fastapi import Request

from services.bff_teacher_service.clients.cms_client import CMSClientImpl
from services.bff_teacher_service.clients.ras_client import RASClientImpl
from services.bff_teacher_service.config import BFFTeacherSettings
from services.bff_teacher_service.protocols import CMSClientProtocol, RASClientProtocol


class AuthTestProvider(Provider):
    """Test authentication provider for mock user_id and correlation_id.

    Replaces RequestContextProvider in tests.
    """

    def __init__(
        self,
        user_id: str = "test-user-123",
        correlation_id: UUID | None = None,
    ):
        super().__init__()
        self.user_id = user_id
        self.correlation_id = correlation_id or uuid4()

    @provide(scope=Scope.REQUEST)
    def provide_mock_request(self) -> Request:
        """Provide mock request with correlation_id in state."""
        mock_request = Mock(spec=Request)
        mock_request.state.correlation_id = self.correlation_id
        mock_request.headers = {"X-User-ID": self.user_id}
        return mock_request

    @provide(scope=Scope.REQUEST, provides=str)
    def provide_user_id(self) -> str:
        """Provide mock user ID for testing."""
        return self.user_id

    @provide(scope=Scope.REQUEST)
    def provide_correlation_id(self) -> UUID:
        """Provide mock correlation ID for testing."""
        return self.correlation_id


class InfrastructureTestProvider(Provider):
    """Test provider for BFF infrastructure dependencies.

    Provides real httpx.AsyncClient for respx mocking and real client
    implementations that use it.
    """

    scope = Scope.APP

    def __init__(self, settings: BFFTeacherSettings | None = None):
        super().__init__()
        self._settings = settings or BFFTeacherSettings(
            SERVICE_NAME="bff_teacher_service_test",
            RAS_URL="http://localhost:4003",
            CMS_URL="http://localhost:5002",
        )

    @provide
    def get_config(self) -> BFFTeacherSettings:
        """Provide test settings."""
        return self._settings

    @provide(scope=Scope.APP)
    async def get_http_client(self) -> AsyncIterator[httpx.AsyncClient]:
        """Provide real HTTP client for respx mocking."""
        async with httpx.AsyncClient() as client:
            yield client

    @provide(scope=Scope.APP)
    def provide_ras_client(self, http_client: httpx.AsyncClient) -> RASClientProtocol:
        """Provide RAS client for testing."""
        return RASClientImpl(http_client)

    @provide(scope=Scope.APP)
    def provide_cms_client(self, http_client: httpx.AsyncClient) -> CMSClientProtocol:
        """Provide CMS client for testing."""
        return CMSClientImpl(http_client)
