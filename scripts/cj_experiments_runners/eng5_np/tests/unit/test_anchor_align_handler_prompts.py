"""Prompt wiring tests for AnchorAlignHandler language-control configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.cj_experiments_runners.eng5_np.handlers import AnchorAlignHandler
from scripts.cj_experiments_runners.eng5_np.inventory import RunnerInventory
from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
from scripts.cj_experiments_runners.eng5_np.settings import RunnerSettings
from scripts.cj_experiments_runners.eng5_np.tests.unit.anchor_align_test_helpers import (
    make_anchor_align_settings,
    make_inventory_with_anchors,
)


def _make_paths(tmp_path: Path) -> RunnerPaths:
    return RunnerPaths(
        repo_root=tmp_path,
        role_models_root=tmp_path,
        instructions_path=tmp_path / "instructions.md",
        prompt_path=tmp_path / "prompt.md",
        anchors_csv=tmp_path / "anchors.csv",
        anchors_xlsx=tmp_path / "anchors.xlsx",
        anchor_docs_dir=tmp_path / "anchors",
        student_docs_dir=tmp_path / "students",
        schema_path=tmp_path / "schema.json",
        artefact_output_dir=tmp_path,
    )


class TestAnchorAlignHandlerLanguageControlPrompts:
    """Tests focused on language-control prompt configuration."""

    def test_execute_with_language_control_prompts_wires_overrides_and_report(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Language-control prompts populate overrides and alignment report fields."""
        settings = make_anchor_align_settings(tmp_path)
        from common_core import LLMProviderType
        from common_core.events.cj_assessment_events import LLMConfigOverrides

        settings.llm_overrides = LLMConfigOverrides(
            provider_override=LLMProviderType.ANTHROPIC,
            model_override="claude-sonnet-4-5-20250929",
            temperature_override=0.2,
            max_tokens_override=1536,
        )
        settings.await_completion = True
        settings.use_kafka = True

        # Wire real 003 language-control prompt files into settings
        eng5_root = Path(__file__).resolve().parents[2]
        system_prompt_path = eng5_root / "prompts" / "system" / "003_language_control.txt"
        rubric_path = eng5_root / "prompts" / "rubric" / "003_language_control.txt"
        assert system_prompt_path.exists()
        assert rubric_path.exists()
        settings.system_prompt_file = system_prompt_path
        settings.rubric_file = rubric_path

        inventory = make_inventory_with_anchors(tmp_path, anchor_count=2)

        tmp_path / "schema.json"
        artefact_path = tmp_path / "assessment_run.anchor-align-test.json"
        report_path = tmp_path / "anchor_align_language_control.md"

        calls: dict[str, object] = {}

        def fake_ensure_schema_available(path: Path) -> dict:
            calls["schema_path"] = path
            return {"$id": "test-schema"}

        def fake_write_stub_artefact(
            *,
            settings: RunnerSettings,
            inventory: RunnerInventory,
            schema: dict,
        ) -> Path:
            calls["stub_settings_mode"] = settings.mode
            calls["stub_schema"] = schema
            return artefact_path

        async def fake_upload_essays_parallel(records, content_service_url: str):
            calls["upload_records"] = records
            calls["upload_url"] = content_service_url
            return {r.checksum: f"storage-{idx}" for idx, r in enumerate(records)}

        def fake_build_essay_refs(
            *,
            anchors,
            students,
            max_comparisons,
            storage_id_map,
            student_id_factory=None,
        ):
            calls["essay_refs_students"] = students
            return ["ref-1", "ref-2"]

        def fake_compose_cj_assessment_request(
            *,
            settings: RunnerSettings,
            essay_refs,
            prompt_reference,
        ):
            calls["compose_llm_overrides"] = settings.llm_overrides
            calls["compose_essay_refs"] = essay_refs
            return {"type": "ELS_CJAssessmentRequestV1"}

        def fake_write_cj_request_envelope(
            *,
            envelope,
            output_dir: Path,
        ) -> Path:
            calls["request_output_dir"] = output_dir
            return tmp_path / "request.json"

        async def fake_run_publish_and_capture(
            *,
            envelope,
            settings: RunnerSettings,
            hydrator,
        ):
            calls["published_envelope"] = envelope
            calls["published_settings_mode"] = settings.mode
            calls["published_hydrator"] = hydrator

        def fake_load_anchor_grade_map(_path: Path) -> dict[str, str]:
            return {"anchor_001": "A", "anchor_002": "C"}

        def fake_generate_alignment_report(
            *,
            hydrator,
            anchor_grade_map,
            system_prompt_text,
            rubric_text,
            batch_id: str,
            output_dir: Path,
        ) -> Path:
            calls["report_system_prompt_text"] = system_prompt_text
            calls["report_rubric_text"] = rubric_text
            calls["report_batch_id"] = batch_id
            calls["report_output_dir"] = output_dir
            return report_path

        def fake_log_validation_state(
            *,
            logger,
            artefact_path: Path,
            artefact_data: dict,
        ) -> None:
            calls["logged_artefact_path"] = artefact_path
            calls["logged_artefact_data"] = artefact_data

        class DummyHydrator:
            def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - trivial
                pass

        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.ensure_schema_available",
            fake_ensure_schema_available,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.write_stub_artefact",
            fake_write_stub_artefact,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.upload_essays_parallel",
            fake_upload_essays_parallel,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.build_essay_refs",
            fake_build_essay_refs,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.compose_cj_assessment_request",
            fake_compose_cj_assessment_request,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.write_cj_request_envelope",
            fake_write_cj_request_envelope,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.run_publish_and_capture",
            fake_run_publish_and_capture,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.load_anchor_grade_map",
            fake_load_anchor_grade_map,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.generate_alignment_report",
            fake_generate_alignment_report,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.log_validation_state",
            fake_log_validation_state,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.AssessmentRunHydrator",
            DummyHydrator,
        )

        handler = AnchorAlignHandler()
        exit_code = handler.execute(
            settings=settings,
            inventory=inventory,
            paths=_make_paths(tmp_path),
        )

        assert exit_code == 0

        # Loaded prompt files populate settings text fields
        assert settings.system_prompt_text is not None
        assert settings.rubric_text is not None

        overrides = calls["compose_llm_overrides"]
        assert overrides is not None
        # Base overrides preserved
        assert overrides.model_override == "claude-sonnet-4-5-20250929"
        assert overrides.temperature_override == 0.2
        assert overrides.max_tokens_override == 1536
        # Prompt overrides aligned with loaded prompt text
        assert overrides.system_prompt_override == settings.system_prompt_text
        assert overrides.judge_rubric_override == settings.rubric_text

        # Alignment report sees the same prompt texts
        assert calls["report_system_prompt_text"] == settings.system_prompt_text
        assert calls["report_rubric_text"] == settings.rubric_text

    def test_execute_preserves_gpt51_reasoning_overrides(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GPT-5.1 reasoning/verbosity overrides are preserved when prompts are applied."""
        settings = make_anchor_align_settings(tmp_path)
        from common_core import LLMProviderType
        from common_core.events.cj_assessment_events import LLMConfigOverrides

        settings.llm_overrides = LLMConfigOverrides(
            provider_override=LLMProviderType.OPENAI,
            model_override="gpt-5.1",
            temperature_override=None,
            max_tokens_override=None,
            reasoning_effort="medium",
            output_verbosity="high",
        )
        settings.await_completion = True
        settings.use_kafka = True

        # Wire real 003 language-control prompt files into settings
        eng5_root = Path(__file__).resolve().parents[2]
        system_prompt_path = eng5_root / "prompts" / "system" / "003_language_control.txt"
        rubric_path = eng5_root / "prompts" / "rubric" / "003_language_control.txt"
        assert system_prompt_path.exists()
        assert rubric_path.exists()
        settings.system_prompt_file = system_prompt_path
        settings.rubric_file = rubric_path

        inventory = make_inventory_with_anchors(tmp_path, anchor_count=2)

        tmp_path / "schema.json"
        artefact_path = tmp_path / "assessment_run.anchor-align-test.json"
        report_path = tmp_path / "anchor_align_language_control_gpt5_1.md"

        calls: dict[str, object] = {}

        def fake_ensure_schema_available(path: Path) -> dict:
            calls["schema_path"] = path
            return {"$id": "test-schema"}

        def fake_write_stub_artefact(
            *,
            settings: RunnerSettings,
            inventory: RunnerInventory,
            schema: dict,
        ) -> Path:
            calls["stub_settings_mode"] = settings.mode
            calls["stub_schema"] = schema
            return artefact_path

        async def fake_upload_essays_parallel(records, content_service_url: str):
            calls["upload_records"] = records
            calls["upload_url"] = content_service_url
            return {r.checksum: f"storage-{idx}" for idx, r in enumerate(records)}

        def fake_build_essay_refs(
            *,
            anchors,
            students,
            max_comparisons,
            storage_id_map,
            student_id_factory=None,
        ):
            calls["essay_refs_students"] = students
            return ["ref-1", "ref-2"]

        def fake_compose_cj_assessment_request(
            *,
            settings: RunnerSettings,
            essay_refs,
            prompt_reference,
        ):
            calls["compose_llm_overrides"] = settings.llm_overrides
            calls["compose_essay_refs"] = essay_refs
            return {"type": "ELS_CJAssessmentRequestV1"}

        def fake_write_cj_request_envelope(
            *,
            envelope,
            output_dir: Path,
        ) -> Path:
            calls["request_output_dir"] = output_dir
            return tmp_path / "request.json"

        async def fake_run_publish_and_capture(
            *,
            envelope,
            settings: RunnerSettings,
            hydrator,
        ):
            calls["published_envelope"] = envelope
            calls["published_settings_mode"] = settings.mode
            calls["published_hydrator"] = hydrator

        def fake_load_anchor_grade_map(_path: Path) -> dict[str, str]:
            return {"anchor_001": "A", "anchor_002": "C"}

        def fake_generate_alignment_report(
            *,
            hydrator,
            anchor_grade_map,
            system_prompt_text,
            rubric_text,
            batch_id: str,
            output_dir: Path,
        ) -> Path:
            calls["report_system_prompt_text"] = system_prompt_text
            calls["report_rubric_text"] = rubric_text
            calls["report_batch_id"] = batch_id
            calls["report_output_dir"] = output_dir
            return report_path

        def fake_log_validation_state(
            *,
            logger,
            artefact_path: Path,
            artefact_data: dict,
        ) -> None:
            calls["logged_artefact_path"] = artefact_path
            calls["logged_artefact_data"] = artefact_data

        class DummyHydrator:
            def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - trivial
                pass

        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.ensure_schema_available",
            fake_ensure_schema_available,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.write_stub_artefact",
            fake_write_stub_artefact,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.upload_essays_parallel",
            fake_upload_essays_parallel,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.build_essay_refs",
            fake_build_essay_refs,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.compose_cj_assessment_request",
            fake_compose_cj_assessment_request,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.write_cj_request_envelope",
            fake_write_cj_request_envelope,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.run_publish_and_capture",
            fake_run_publish_and_capture,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.load_anchor_grade_map",
            fake_load_anchor_grade_map,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.generate_alignment_report",
            fake_generate_alignment_report,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.log_validation_state",
            fake_log_validation_state,
        )
        monkeypatch.setattr(
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.AssessmentRunHydrator",
            DummyHydrator,
        )

        handler = AnchorAlignHandler()
        exit_code = handler.execute(
            settings=settings,
            inventory=inventory,
            paths=_make_paths(tmp_path),
        )

        assert exit_code == 0

        overrides = calls["compose_llm_overrides"]
        assert overrides is not None
        # GPT-5.1 provider/model preserved alongside reasoning controls
        assert overrides.model_override == "gpt-5.1"
        assert overrides.provider_override is not None
        assert "openai" in str(overrides.provider_override).lower()
        assert overrides.reasoning_effort == "medium"
        assert overrides.output_verbosity == "high"
