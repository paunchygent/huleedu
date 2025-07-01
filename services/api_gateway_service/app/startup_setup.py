"""Startup setup for API Gateway Service."""

from __future__ import annotations

from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs import init_tracing
from services.api_gateway_service.app.di import ApiGatewayProvider

logger = create_service_logger("api_gateway_service.startup")


def create_di_container():
    """Create and configure the DI container."""
    try:
        logger.info("Creating DI container...")
        container = make_async_container(ApiGatewayProvider())
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


def setup_tracing(app: FastAPI):
    """Setup distributed tracing for the API Gateway."""
    try:
        logger.info("Initializing distributed tracing...")
        tracer = init_tracing("api_gateway_service")
        # Store tracer in app state for access in routes
        app.state.tracer = tracer
        
        # TODO: Add FastAPI middleware for tracing when available
        # For now, tracing will be manual in routes that need it
        
        logger.info("Distributed tracing initialized successfully")
        return tracer
    except Exception as e:
        logger.error(f"Failed to initialize tracing: {e}", exc_info=True)
        # Don't fail startup if tracing fails
        return None


async def shutdown_services() -> None:
    """Gracefully shutdown all services."""
    logger.info("API Gateway Service shutdown completed")
