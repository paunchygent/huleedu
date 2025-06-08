"""Shared utilities for Pipeline State Management integration tests.

Common imports, constants, and documentation for the modularized pipeline state management tests.
This file supports the following test modules:
- test_pipeline_state_management_progression.py
- test_pipeline_state_management_failures.py
- test_pipeline_state_management_edge_cases.py
- test_pipeline_state_management_scenarios.py

Integration Testing Scope:
Tests the dynamic pipeline orchestration logic using real business logic components.
Validates ProcessingPipelineState management, phase progression, and pipeline completion.

Following 070-testing-and-quality-assurance.mdc:
- Mock only external boundaries (event publisher, specialized service clients)
- Test real business logic components (PipelinePhaseCoordinator, repository operations)
- Limited scope component interactions (not full E2E)

INTEGRATION BOUNDARIES TESTED:
- Real DefaultPipelinePhaseCoordinator business logic
- Real ProcessingPipelineState management and persistence
- Real pipeline sequence determination and progression logic
- Real next-phase command generation logic
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from common_core.pipeline_models import PhaseName
from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations.batch_repository_impl import (
    MockBatchRepositoryImpl,
)
from services.batch_orchestrator_service.implementations.pipeline_phase_coordinator_impl import (
    DefaultPipelinePhaseCoordinator,
)

# Export commonly used classes and functions for test modules
__all__ = [
    "AsyncMock",
    "UUID",
    "uuid4",
    "pytest",
    "PhaseName",
    "BatchRegistrationRequestV1",
    "MockBatchRepositoryImpl",
    "DefaultPipelinePhaseCoordinator",
]
