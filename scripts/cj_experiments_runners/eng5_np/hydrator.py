"""Artefact hydration logic for ENG5 NP runner."""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

import typer
from common_core.events.cj_assessment_events import AssessmentResultV1
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1
from huleedu_service_libs.logging_utils import create_service_logger, log_event_processing

from scripts.cj_experiments_runners.eng5_np.events import (
    write_assessment_result_event,
    write_llm_comparison_event,
)
from scripts.cj_experiments_runners.eng5_np.utils import sha256_of_file

_LOGGER = create_service_logger("eng5_np_hydrator")

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class AssessmentRunHydrator:
    """Updates ENG5 NP artefacts with live comparison and result data."""

    def __init__(
        self,
        *,
        artefact_path: Path,
        output_dir: Path,
        grade_scale: str,
        batch_id: str,
        batch_uuid: UUID,
    ) -> None:
        self.artefact_path = artefact_path
        self.output_dir = output_dir
        self.grade_scale = grade_scale
        self.batch_label = batch_id
        self.batch_uuid = str(batch_uuid)
        (self.output_dir / "events").mkdir(parents=True, exist_ok=True)
        self._seen_request_ids: set[str] = set()
        self._runner_status: dict[str, Any] = {
            "partial_data": False,
            "timeout_seconds": 0.0,
            "observed_events": {
                "llm_comparisons": 0,
                "assessment_results": 0,
                "completions": 0,
            },
        }
        self._logger = _LOGGER.bind(
            batch_id=batch_id,
            batch_uuid=self.batch_uuid,
            grade_scale=grade_scale,
            artefact_path=str(self.artefact_path),
        )
        self._logger.info(
            "hydrator_initialized",
            output_dir=str(self.output_dir),
        )

    def mark_timeout(self, elapsed: float) -> None:
        self._runner_status["partial_data"] = True
        self._runner_status["timeout_seconds"] = round(max(elapsed, 0.0), 2)
        self._logger.warning(
            "hydrator_timeout_marked",
            elapsed_seconds=self._runner_status["timeout_seconds"],
        )

    def record_completion_seen(self) -> None:
        self._runner_status["observed_events"]["completions"] += 1
        self._logger.info(
            "completion_event_recorded",
            total_completions=self._runner_status["observed_events"]["completions"],
        )

    def runner_status(self) -> dict[str, Any]:
        """Expose current runner status for external logging."""

        return self._runner_status

    def _increment_event(self, key: str) -> None:
        self._runner_status["observed_events"][key] += 1

    def apply_llm_comparison(self, envelope: EventEnvelope[LLMComparisonResultV1]) -> None:
        """Persist LLM callback and append it to the artefact if it matches the batch."""

        request_id = envelope.data.request_id
        if not request_id:
            raise ValueError(
                "LLMComparisonResultV1 missing request_id; cannot hydrate artefact",
            )
        if request_id in self._seen_request_ids:
            typer.echo(
                f"Skipping duplicate LLM comparison callback for request_id={request_id}",
                err=True,
            )
            self._logger.warning(
                "duplicate_llm_comparison_skipped",
                request_id=request_id,
            )
            return

        metadata = envelope.data.request_metadata or {}
        batch_hint = metadata.get("batch_id") or metadata.get("bos_batch_id")
        if batch_hint and batch_hint != self.batch_uuid:
            self._logger.debug(
                "comparison_batch_mismatch_skipped",
                request_id=request_id,
                comparison_batch=batch_hint,
            )
            return

        write_llm_comparison_event(envelope=envelope, output_dir=self.output_dir)

        artefact = self._load_artefact()
        record = self._build_comparison_record(artefact, envelope)
        artefact.setdefault("llm_comparisons", []).append(record)
        self._increment_event("llm_comparisons")
        self._update_costs(artefact, envelope)
        self._seen_request_ids.add(request_id)
        self._write_artefact(artefact)
        log_event_processing(
            logger=self._logger,
            message="llm_comparison_hydrated",
            envelope=envelope,
            request_id=request_id,
            event_count=self._runner_status["observed_events"]["llm_comparisons"],
        )

    def apply_assessment_result(self, envelope: EventEnvelope[AssessmentResultV1]) -> None:
        """Persist and hydrate Bradley–Terry and grade projection outputs."""

        if envelope.data.batch_id != self.batch_uuid:
            self._logger.debug(
                "assessment_result_batch_mismatch_skipped",
                event_batch=envelope.data.batch_id,
            )
            return

        write_assessment_result_event(envelope=envelope, output_dir=self.output_dir)

        artefact = self._load_artefact()
        artefact["bt_summary"] = self._build_bt_entries(envelope)
        artefact["grade_projections"] = self._build_grade_projections(envelope)
        self._increment_event("assessment_results")
        self._write_artefact(artefact)
        log_event_processing(
            logger=self._logger,
            message="assessment_result_hydrated",
            envelope=envelope,
            event_count=self._runner_status["observed_events"]["assessment_results"],
        )

    def _load_artefact(self) -> dict[str, Any]:
        return json.loads(self.artefact_path.read_text(encoding="utf-8"))

    def _write_artefact(self, artefact: dict[str, Any]) -> None:
        manifest_entries = []
        for rel_path in sorted(self._manifest_targets()):
            abs_path = self.output_dir / rel_path
            manifest_entries.append(
                {
                    "path": rel_path,
                    "sha256": sha256_of_file(abs_path),
                    "bytes": abs_path.stat().st_size,
                }
            )

        validation_block = artefact.setdefault("validation", {})
        validation_block["manifest"] = manifest_entries
        validation_block["artefact_checksum"] = ""
        validation_block["runner_status"] = self._runner_status

        serialized = json.dumps(artefact, indent=2)
        checksum = sha256(serialized.encode("utf-8")).hexdigest()
        validation_block["artefact_checksum"] = checksum
        # Re-serialize with updated checksum to ensure integrity
        self.artefact_path.write_text(json.dumps(artefact, indent=2), encoding="utf-8")
        self._logger.debug(
            "artefact_manifest_updated",
            manifest_entries=len(manifest_entries),
            checksum=checksum,
        )

    def _manifest_targets(self) -> list[str]:
        targets: list[str] = []
        for subdir in ("requests", "events"):
            base = self.output_dir / subdir
            if not base.exists():
                continue
            for path in base.rglob("*.json"):
                targets.append(str(path.relative_to(self.output_dir)))
        return targets

    def _build_comparison_record(
        self,
        artefact: dict[str, Any],
        envelope: EventEnvelope[LLMComparisonResultV1],
    ) -> dict[str, Any]:
        metadata = envelope.data.request_metadata or {}
        essay_a = metadata.get("essay_a_id")
        essay_b = metadata.get("essay_b_id")
        prompt_hash = metadata.get("prompt_sha256")
        if not essay_a or not essay_b:
            raise ValueError(
                "Comparison callback missing essay identifiers; "
                f"correlation={envelope.correlation_id}",
            )
        if not prompt_hash or not _HEX_64.fullmatch(str(prompt_hash)):
            raise ValueError(
                f"Comparison callback missing prompt hash; correlation={envelope.correlation_id}",
            )

        winner = envelope.data.winner
        if winner and winner.value.lower() == "essay_a":
            winner_id, loser_id = essay_a, essay_b
        elif winner and winner.value.lower() == "essay_b":
            winner_id, loser_id = essay_b, essay_a
        else:
            winner_id, loser_id = essay_a, essay_b

        sequence = len(artefact.get("llm_comparisons", [])) + 1
        status = "failed" if envelope.data.is_error else "succeeded"
        record: dict[str, Any] = {
            "sequence": sequence,
            "request_id": envelope.data.request_id,
            "correlation_id": str(envelope.correlation_id),
            "winner_id": winner_id,
            "loser_id": loser_id,
            "essay_a_id": essay_a,
            "essay_b_id": essay_b,
            "prompt_hash": prompt_hash,
            "provider": envelope.data.provider.value,
            "model": envelope.data.model,
            "tokens_prompt": envelope.data.token_usage.prompt_tokens,
            "tokens_completion": envelope.data.token_usage.completion_tokens,
            "cost_usd": envelope.data.cost_estimate,
            "started_at": envelope.data.requested_at.isoformat(),
            "completed_at": envelope.data.completed_at.isoformat(),
            "status": status,
        }

        if envelope.data.is_error and envelope.data.error_detail:
            record["failure_reason"] = envelope.data.error_detail.message
            record["error_code"] = envelope.data.error_detail.error_code.value

        return record

    def _build_bt_entries(
        self, envelope: EventEnvelope[AssessmentResultV1]
    ) -> list[dict[str, Any]]:
        comparison_count = envelope.data.assessment_metadata.get("comparison_count", 0)
        entries: list[dict[str, Any]] = []
        for essay in envelope.data.essay_results:
            entries.append(
                {
                    "essay_id": essay.essay_id,
                    "theta": essay.bt_score,
                    "standard_error": 0.0,
                    "rank": essay.rank,
                    "comparison_count": comparison_count,
                    "is_anchor": essay.is_anchor,
                    "anchor_grade": essay.letter_grade if essay.is_anchor else None,
                    "grade_projection": essay.letter_grade,
                }
            )
        return entries

    def _build_grade_projections(
        self, envelope: EventEnvelope[AssessmentResultV1]
    ) -> list[dict[str, Any]]:
        metadata = envelope.data.assessment_metadata or {}
        summary = metadata.get("grade_projection_summary", {})
        probabilities = summary.get("grade_probabilities", {})

        projections: list[dict[str, Any]] = []
        for essay in envelope.data.essay_results:
            probs = probabilities.get(essay.essay_id, {essay.letter_grade: 1.0})
            projections.append(
                {
                    "essay_id": essay.essay_id,
                    "grade_scale": self.grade_scale,
                    "grade": essay.letter_grade,
                    "probabilities": probs,
                    "primary_anchor_id": None,
                    "anchor_alignment": None,
                }
            )
        return projections

    def _update_costs(
        self,
        artefact: dict[str, Any],
        envelope: EventEnvelope[LLMComparisonResultV1],
    ) -> None:
        costs = artefact.setdefault("costs", {"total_usd": 0.0, "token_counts": []})
        costs["total_usd"] = round(costs.get("total_usd", 0.0) + envelope.data.cost_estimate, 6)
        totals = {
            (entry["provider"], entry["model"]): entry for entry in costs.get("token_counts", [])
        }
        key = (envelope.data.provider.value, envelope.data.model)
        entry = totals.get(key)
        if not entry:
            entry = {
                "provider": key[0],
                "model": key[1],
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "usd": 0.0,
            }
            costs["token_counts"].append(entry)
            totals[key] = entry

        entry["prompt_tokens"] += envelope.data.token_usage.prompt_tokens
        entry["completion_tokens"] += envelope.data.token_usage.completion_tokens
        entry["usd"] = round(entry["usd"] + envelope.data.cost_estimate, 6)
