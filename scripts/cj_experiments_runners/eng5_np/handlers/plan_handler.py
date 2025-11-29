"""PLAN mode handler for ENG5 NP runner.

Displays file inventory and validation state without side effects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
import typer

from scripts.cj_experiments_runners.eng5_np.inventory import print_inventory
from scripts.cj_experiments_runners.eng5_np.logging_support import log_validation_state
from scripts.cj_experiments_runners.eng5_np.settings import RunnerMode

if TYPE_CHECKING:
    from scripts.cj_experiments_runners.eng5_np.inventory import RunnerInventory
    from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
    from scripts.cj_experiments_runners.eng5_np.settings import RunnerSettings


logger = structlog.get_logger(__name__)


class PlanHandler:
    """Handler for PLAN mode.

    Displays inventory and validation snapshot without creating artefacts
    or publishing events. Used for preview and validation before execution.
    """

    def execute(
        self,
        settings: RunnerSettings,
        inventory: RunnerInventory,
        paths: RunnerPaths,  # noqa: ARG002 - Required by ModeHandlerProtocol
    ) -> int:
        """Execute PLAN mode logic.

        Args:
            settings: Runner configuration
            inventory: File inventory (anchors, students, prompt)
            paths: Path configuration

        Returns:
            Exit code (0 for success)
        """
        logger.info(
            "runner_plan_inventory",
            anchor_count=inventory.anchor_docs.count,
            student_count=inventory.student_docs.count,
            prompt_path=str(inventory.prompt.path),
        )

        print_inventory(inventory)

        plan_snapshot = self._build_plan_snapshot(inventory)

        log_validation_state(
            logger=logger,
            artefact_path=settings.output_dir / f"assessment_run.{RunnerMode.PLAN.value}.json",
            artefact_data=plan_snapshot,
        )

        typer.echo(
            f"PLAN mode complete. Inventory: {inventory.anchor_docs.count} anchors, "
            f"{inventory.student_docs.count} students",
            err=True,
        )

        return 0

    def _build_plan_snapshot(self, inventory: RunnerInventory) -> dict:
        """Build validation snapshot for PLAN mode.

        Args:
            inventory: File inventory

        Returns:
            Snapshot dictionary for validation logging
        """
        return {
            "validation": {
                "manifest": [],
                "artefact_checksum": None,
                "runner_status": {
                    "mode": RunnerMode.PLAN.value,
                    "partial_data": False,
                    "timeout_seconds": 0.0,
                    "observed_events": {
                        "llm_comparisons": 0,
                        "assessment_results": 0,
                        "completions": 0,
                    },
                    "inventory": {
                        "anchors": inventory.anchor_docs.count,
                        "students": inventory.student_docs.count,
                        "prompt_path": str(inventory.prompt.path),
                    },
                },
            }
        }
