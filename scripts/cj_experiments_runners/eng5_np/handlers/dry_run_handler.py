"""DRY_RUN mode handler for ENG5 NP runner.

Creates stub artefact without publishing events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
import typer

from scripts.cj_experiments_runners.eng5_np.artefact_io import write_stub_artefact
from scripts.cj_experiments_runners.eng5_np.logging_support import (
    load_artefact_data,
    log_validation_state,
)
from scripts.cj_experiments_runners.eng5_np.schema import ensure_schema_available

if TYPE_CHECKING:
    from scripts.cj_experiments_runners.eng5_np.inventory import RunnerInventory
    from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
    from scripts.cj_experiments_runners.eng5_np.settings import RunnerSettings


logger = structlog.get_logger(__name__)


class DryRunHandler:
    """Handler for DRY_RUN mode.

    Creates stub artefact file for validation without publishing
    events or triggering actual assessment runs.
    """

    def execute(
        self,
        settings: RunnerSettings,
        inventory: RunnerInventory,
        paths: RunnerPaths,
    ) -> int:
        """Execute DRY_RUN mode logic.

        Args:
            settings: Runner configuration
            inventory: File inventory (anchors, students, prompt)
            paths: Path configuration

        Returns:
            Exit code (0 for success)
        """
        schema = ensure_schema_available(paths.schema_path)

        artefact_path = write_stub_artefact(
            settings=settings,
            inventory=inventory,
            schema=schema,
        )

        logger.info(
            "runner_dry_run_stub_created",
            artefact_path=str(artefact_path),
        )

        log_validation_state(
            logger=logger,
            artefact_path=artefact_path,
            artefact_data=load_artefact_data(artefact_path),
        )

        typer.echo(f"DRY_RUN complete. Stub artefact: {artefact_path}", err=True)

        return 0
