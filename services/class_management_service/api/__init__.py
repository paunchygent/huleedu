"""API package for Class Management Service.

This package contains the API endpoints and request/response models for the
Class Management Service.
"""

from .class_routes import class_bp
from .health_routes import health_bp

__all__ = ["class_bp", "health_bp"]
