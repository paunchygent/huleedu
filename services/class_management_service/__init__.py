"""Class Management Service for HuleEdu.

This package provides functionality for managing classes, students, and related operations
in the HuleEdu platform.
"""

# Core components
# Subpackages
from . import api, implementations
from .api_models import (
    CreateClassRequest,
    CreateStudentRequest,
    UpdateClassRequest,
    UpdateStudentRequest,
)
from .app import app
from .config import Settings, settings
from .models_db import Course, Student, UserClass
from .protocols import (
    ClassEventPublisherProtocol,
    ClassManagementServiceProtocol,
    ClassRepositoryProtocol,
    T,
    U,
)

# Define public API
__all__ = [
    # Core components
    'app',
    'Settings',
    'settings',

    # Protocols and Type Parameters
    'ClassRepositoryProtocol',
    'ClassEventPublisherProtocol',
    'ClassManagementServiceProtocol',
    'T',  # Generic type parameter for UserClass
    'U',  # Generic type parameter for Student

    # Models
    'UserClass',
    'Student',
    'Course',

    # API Models
    'CreateClassRequest',
    'CreateStudentRequest',
    'UpdateClassRequest',
    'UpdateStudentRequest',

    # Subpackages
    'api',
    'implementations',
]
