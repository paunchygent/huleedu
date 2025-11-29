"""Base handler utilities and context for ENG5 NP runner.

Provides shared context and utilities used by all mode handlers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from scripts.cj_experiments_runners.eng5_np.hydrator import AssessmentRunHydrator
    from scripts.cj_experiments_runners.eng5_np.inventory import RunnerInventory
    from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
    from scripts.cj_experiments_runners.eng5_np.settings import RunnerSettings


logger = structlog.get_logger(__name__)


@dataclass
class HandlerContext:
    """Shared context passed to and updated by mode handlers.

    Attributes:
        settings: Runner configuration
        inventory: File inventory (anchors, students, prompt)
        paths: Path configuration
        artefact_path: Path to stub artefact file (set by handlers)
        hydrator: Result hydrator for await_completion mode
        schema: Loaded JSON schema for validation
    """

    settings: RunnerSettings
    inventory: RunnerInventory
    paths: RunnerPaths
    artefact_path: Path | None = None
    hydrator: AssessmentRunHydrator | None = None
    schema: dict[str, Any] | None = field(default_factory=dict)

    def with_artefact(self, artefact_path: Path) -> HandlerContext:
        """Return new context with artefact path set.

        Args:
            artefact_path: Path to the stub artefact file

        Returns:
            New HandlerContext with updated artefact_path
        """
        return HandlerContext(
            settings=self.settings,
            inventory=self.inventory,
            paths=self.paths,
            artefact_path=artefact_path,
            hydrator=self.hydrator,
            schema=self.schema,
        )

    def with_hydrator(self, hydrator: AssessmentRunHydrator) -> HandlerContext:
        """Return new context with hydrator set.

        Args:
            hydrator: AssessmentRunHydrator for result collection

        Returns:
            New HandlerContext with updated hydrator
        """
        return HandlerContext(
            settings=self.settings,
            inventory=self.inventory,
            paths=self.paths,
            artefact_path=self.artefact_path,
            hydrator=hydrator,
            schema=self.schema,
        )

    def with_schema(self, schema: dict[str, Any]) -> HandlerContext:
        """Return new context with schema set.

        Args:
            schema: Loaded JSON schema for validation

        Returns:
            New HandlerContext with updated schema
        """
        return HandlerContext(
            settings=self.settings,
            inventory=self.inventory,
            paths=self.paths,
            artefact_path=self.artefact_path,
            hydrator=self.hydrator,
            schema=schema,
        )
