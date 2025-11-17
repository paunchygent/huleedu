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


class LLMBatchingMode(str, Enum):
    """Queue/batching modes shared between CJ Assessment and LLM Provider Service."""

    PER_REQUEST = "per_request"
    SERIAL_BUNDLE = "serial_bundle"
    PROVIDER_BATCH_API = "provider_batch_api"
