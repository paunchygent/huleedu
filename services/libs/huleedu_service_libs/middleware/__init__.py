"""Middleware utilities for HuleEdu services.

Framework-specific middleware implementations are available in submodules:
- middleware.frameworks.quart_middleware for Quart applications
- middleware.frameworks.fastapi_middleware for FastAPI applications

Services should import the specific middleware they need directly.
"""

# No framework-specific imports here to keep the library framework-agnostic
# Services will import what they need from the frameworks submodule
