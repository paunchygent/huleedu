"""BFF Teacher Service clients module.

Contains HTTP clients for internal service communication.
"""

from services.bff_teacher_service.clients.cms_client import CMSClientImpl
from services.bff_teacher_service.clients.ras_client import RASClientImpl

__all__ = ["RASClientImpl", "CMSClientImpl"]
