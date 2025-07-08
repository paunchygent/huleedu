"""Class Management Service for HuleEdu.

This package provides functionality for managing classes, students, and related operations
in the HuleEdu platform.
"""

# Core components
# Subpackages
from services.class_management_service.api_models import (
    CreateClassRequest,
    CreateStudentRequest,
    UpdateClassRequest,
    UpdateStudentRequest,
)
from services.class_management_service.config import Settings, settings
from services.class_management_service.models_db import Course, Student, UserClass
from services.class_management_service.protocols import (
    ClassEventPublisherProtocol,
    ClassManagementServiceProtocol,
    ClassRepositoryProtocol,
    T,
    U,
)

from . import api, implementations
from .app import app

# Define public API
__all__ = [
    # Core components
    "app",
    "Settings",
    "settings",
    # Protocols and Type Parameters
    "ClassRepositoryProtocol",
    "ClassEventPublisherProtocol",
    "ClassManagementServiceProtocol",
    "T",  # Generic type parameter for UserClass
    "U",  # Generic type parameter for Student
    # Models
    "UserClass",
    "Student",
    "Course",
    # API Models
    "CreateClassRequest",
    "CreateStudentRequest",
    "UpdateClassRequest",
    "UpdateStudentRequest",
    # Subpackages
    "api",
    "implementations",
]
