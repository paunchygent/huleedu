"""Startup setup for API Gateway Service."""

from __future__ import annotations

from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI

from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.middleware.frameworks.fastapi_middleware import setup_tracing_middleware
from huleedu_service_libs.middleware.frameworks.fastapi_metrics_middleware import (
    setup_standard_service_metrics_middleware,
)
from services.api_gateway_service.app.auth_provider import AuthProvider
from services.api_gateway_service.app.di import ApiGatewayProvider

logger = create_service_logger("api_gateway_service.startup")


def create_di_container():
    """Create and configure the DI container."""
    try:
        logger.info("Creating DI container...")
        container = make_async_container(
            ApiGatewayProvider(),
            AuthProvider(),
            FastapiProvider(),  # Provides Request object to context
        )
        logger.info("DI container created successfully")
        return container
    except Exception as e:
        logger.critical(f"Failed to create DI container: {e}", exc_info=True)
        raise


def setup_dependency_injection(app: FastAPI, container):
    """Setup Dishka integration with FastAPI."""
    try:
        logger.info("Setting up dependency injection...")
        setup_dishka(container, app)
        logger.info("Dependency injection setup completed")
    except Exception as e:
        logger.critical(f"Failed to setup dependency injection: {e}", exc_info=True)
        raise


def setup_tracing_and_middleware(app: FastAPI):
    """Setup distributed tracing and tracing middleware for the API Gateway."""
    try:
        logger.info("Initializing distributed tracing...")
        tracer = init_tracing("api_gateway_service")
        
        # Store tracer in app state for access in routes
        app.state.tracer = tracer
        
        # Add FastAPI tracing middleware from service libraries
        setup_tracing_middleware(app, tracer)
        logger.info("Tracing middleware added successfully")

        logger.info("Distributed tracing initialized successfully")
        return tracer
    except Exception as e:
        logger.error(f"Failed to initialize tracing: {e}", exc_info=True)
        # Don't fail startup if tracing fails
        return None


def setup_standard_metrics_middleware(app: FastAPI, registry=None):
    """Setup standard HTTP metrics middleware for the API Gateway.
    
    This adds infrastructure-level HTTP metrics while preserving existing 
    business-specific GatewayMetrics for route-level metrics.
    
    Args:
        app: FastAPI application instance
        registry: Optional Prometheus registry for test isolation
    """
    try:
        logger.info("Setting up standard HTTP metrics middleware...")
        setup_standard_service_metrics_middleware(app, "api_gateway", registry=registry)
        logger.info("Standard HTTP metrics middleware added successfully")
    except Exception as e:
        logger.error(f"Failed to setup metrics middleware: {e}", exc_info=True)
        # Don't fail startup if metrics middleware fails


async def shutdown_services() -> None:
    """Gracefully shutdown all services."""
    logger.info("API Gateway Service shutdown completed")
