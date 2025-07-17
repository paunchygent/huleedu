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


class LLMProviderType(str, Enum):
    """Standardized LLM provider identifiers for HuleEdu platform."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    MOCK = "mock"
