"""
common_core.config_enums - Enums related to service configuration.
"""

from __future__ import annotations

from enum import Enum


class Environment(str, Enum):
    """Defines application environments."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"
