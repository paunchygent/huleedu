"""Legacy import compatibility for CJ Assessment Service.

This module provides backward compatibility by re-exporting
the main workflow function from the new modular structure.
"""

from __future__ import annotations

# Re-export the main workflow function for backward compatibility
from .workflow_orchestrator import run_cj_assessment_workflow

__all__ = ["run_cj_assessment_workflow"]
