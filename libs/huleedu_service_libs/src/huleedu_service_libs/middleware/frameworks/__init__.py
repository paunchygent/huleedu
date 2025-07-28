"""Framework-specific middleware implementations."""

from huleedu_service_libs.middleware.frameworks.fastapi_metrics_middleware import (
    setup_standard_service_metrics_middleware,
)

__all__ = ["setup_standard_service_metrics_middleware"]

# Framework-specific imports should be done by the services that need them
# This keeps the service library framework-agnostic
