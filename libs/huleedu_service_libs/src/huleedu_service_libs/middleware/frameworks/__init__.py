"""Framework-specific middleware implementations."""

# Framework-specific imports should be done by the services that need them
# This keeps the service library framework-agnostic

# DO NOT import framework-specific modules at package level
# Import them only when explicitly requested to avoid dependency forcing

__all__ = ["setup_standard_service_metrics_middleware"]


def setup_standard_service_metrics_middleware(*args, **kwargs):
    """FastAPI-specific metrics middleware - lazy import to avoid forcing FastAPI dependency."""
    from huleedu_service_libs.middleware.frameworks.fastapi_metrics_middleware import (
        setup_standard_service_metrics_middleware as _setup_fastapi_metrics,
    )

    return _setup_fastapi_metrics(*args, **kwargs)
