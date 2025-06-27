from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..config import settings
from ..routers import batch_routes, class_routes, file_routes, status_routes, websocket_routes
from .di import ApiGatewayProvider
from .rate_limiter import limiter


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.SERVICE_NAME,
        version="1.0.0",
    )

    # Add Rate Limiting Middleware
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit exceeded: {exc.detail}"},
        )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # Include routers
    app.include_router(class_routes.router, prefix="/v1", tags=["Classes"])
    app.include_router(status_routes.router, prefix="/v1", tags=["Status"])
    app.include_router(batch_routes.router, prefix="/v1", tags=["Batches"])
    app.include_router(file_routes.router, prefix="/v1", tags=["Files"])
    app.include_router(websocket_routes.router, prefix="/ws/v1/status", tags=["WebSocket Status"])

    # Setup Dishka DI
    container = make_async_container(ApiGatewayProvider())
    setup_dishka(container, app)

    return app


app = create_app()
