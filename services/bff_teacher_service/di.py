"""Dependency Injection providers for BFF Teacher Service.

Provides Dishka DI container setup with APP-scoped infrastructure
and REQUEST-scoped context providers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
from dishka import Provider, Scope, from_context, provide
from fastapi import Request
from huleedu_service_libs.error_handling import raise_authentication_error
from huleedu_service_libs.logging_utils import create_service_logger

from services.bff_teacher_service.clients.cms_client import CMSClientImpl
from services.bff_teacher_service.clients.ras_client import RASClientImpl
from services.bff_teacher_service.config import BFFTeacherSettings, settings
from services.bff_teacher_service.protocols import CMSClientProtocol, RASClientProtocol

logger = create_service_logger("bff_teacher.di")


class BFFTeacherProvider(Provider):
    """Infrastructure provider for BFF Teacher Service.

    Provides APP-scoped dependencies: config, HTTP client, service clients.
    """

    scope = Scope.APP

    @provide
    def get_config(self) -> BFFTeacherSettings:
        """Provide settings singleton."""
        return settings

    @provide(scope=Scope.APP)
    async def get_http_client(self, config: BFFTeacherSettings) -> AsyncIterator[httpx.AsyncClient]:
        """Provide shared HTTP client with connection pooling."""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                config.HTTP_CLIENT_TIMEOUT_SECONDS,
                connect=config.HTTP_CLIENT_CONNECT_TIMEOUT_SECONDS,
            )
        ) as client:
            yield client

    @provide(scope=Scope.APP)
    def provide_ras_client(self, http_client: httpx.AsyncClient) -> RASClientProtocol:
        """Provide RAS client singleton."""
        return RASClientImpl(http_client)

    @provide(scope=Scope.APP)
    def provide_cms_client(self, http_client: httpx.AsyncClient) -> CMSClientProtocol:
        """Provide CMS client singleton."""
        return CMSClientImpl(http_client)


class RequestContextProvider(Provider):
    """Request-scoped provider for correlation context.

    Extracts user_id from X-User-ID header (injected by API Gateway)
    and correlation_id from request state (set by CorrelationIDMiddleware).
    """

    request = from_context(provides=Request, scope=Scope.REQUEST)

    @provide(scope=Scope.REQUEST)
    def provide_correlation_id(self, request: Request) -> UUID:
        """Provide correlation ID from request state."""
        return getattr(request.state, "correlation_id", uuid4())

    @provide(scope=Scope.REQUEST, provides=str)
    def provide_user_id(self, request: Request) -> str:
        """Provide user ID from X-User-ID header.

        The API Gateway injects this header after JWT validation.
        Requests without this header are rejected as unauthenticated.
        """
        user_id = request.headers.get("X-User-ID")
        if not user_id:
            # Get correlation_id from request state (set by middleware) or generate one
            correlation_id = getattr(request.state, "correlation_id", uuid4())
            logger.error("Missing X-User-ID header - request bypassed gateway auth")
            raise_authentication_error(
                service="bff_teacher_service",
                operation="provide_user_id",
                message="Missing X-User-ID header - authentication required",
                correlation_id=correlation_id,
            )
        return user_id
