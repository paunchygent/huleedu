"""Unit tests for AnchorAlignHandler and anchor-align-test flow."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from scripts.cj_experiments_runners.eng5_np.handlers import AnchorAlignHandler
from scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler import (
    _load_prompt_file,
)
from scripts.cj_experiments_runners.eng5_np.inventory import (
    RunnerInventory,
)
from scripts.cj_experiments_runners.eng5_np.protocols import ModeHandlerProtocol
from scripts.cj_experiments_runners.eng5_np.settings import RunnerMode
from scripts.cj_experiments_runners.eng5_np.tests.unit.anchor_align_test_helpers import (
    make_anchor_align_settings,
    make_inventory_with_anchors,
)


class TestAnchorAlignHandlerProtocol:
    """Contract tests for AnchorAlignHandler protocol compliance."""

    def test_anchor_align_handler_implements_mode_handler_protocol(self) -> None:
        """AnchorAlignHandler instances satisfy ModeHandlerProtocol at runtime."""
        handler = AnchorAlignHandler()
        assert isinstance(handler, ModeHandlerProtocol)


class TestLoadPromptFile:
    """Tests for internal _load_prompt_file helper."""

    def test_load_prompt_file_returns_none_when_path_is_none(self) -> None:
        """None path returns None without error."""
        assert _load_prompt_file(None, "label") is None

    def test_load_prompt_file_raises_for_missing_file(self, tmp_path: Path) -> None:
        """Missing prompt file raises BadParameter with clear message."""
        missing = tmp_path / "missing.txt"
        with pytest.raises(typer.BadParameter) as exc:
            _load_prompt_file(missing, "system prompt")
        assert "system prompt file not found" in str(exc.value)

    def test_load_prompt_file_raises_for_empty_file(self, tmp_path: Path) -> None:
        """Empty prompt file raises BadParameter."""
        empty = tmp_path / "empty.txt"
        empty.write_text("   ", encoding="utf-8")
        with pytest.raises(typer.BadParameter) as exc:
            _load_prompt_file(empty, "judge rubric")
        assert "judge rubric file is empty" in str(exc.value)


class TestAnchorAlignHandlerExecute:
    """Behavioral tests for AnchorAlignHandler.execute."""

    def test_execute_requires_anchor_files(self, tmp_path: Path) -> None:
        """Handler raises when no anchor essays are present."""
        settings = make_anchor_align_settings(tmp_path)
        # Seed existing LLM overrides to verify they are preserved
        from common_core import LLMProviderType
        from common_core.events.cj_assessment_events import LLMConfigOverrides

        settings.llm_overrides = LLMConfigOverrides(
            provider_override=LLMProviderType.ANTHROPIC,
            model_override="claude-sonnet-4-5-20250929",
            temperature_override=0.1,
            max_tokens_override=2048,
        )
        # Seed existing LLM overrides to verify they are preserved
        from common_core import LLMProviderType
        from common_core.events.cj_assessment_events import LLMConfigOverrides

        settings.llm_overrides = LLMConfigOverrides(
            provider_override=LLMProviderType.ANTHROPIC,
            model_override="claude-sonnet-4-5-20250929",
            temperature_override=0.1,
            max_tokens_override=2048,
        )

        # Inventory with zero anchors
        inventory = make_inventory_with_anchors(tmp_path, anchor_count=0)

        class DummyPaths:
            """Minimal paths object exposing schema_path."""

            def __init__(self, schema: Path) -> None:
                self.schema_path = schema

        handler = AnchorAlignHandler()
        with pytest.raises(RuntimeError) as exc:
            handler.execute(
                settings=settings,
                inventory=inventory,
                paths=DummyPaths(tmp_path / "schema.json"),  # type: ignore[arg-type]
            )

        assert "Anchor essays are required for anchor-align-test mode" in str(exc.value)

    def test_execute_with_await_completion_generates_alignment_report(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Happy-path anchor-align-test run uploads anchors and generates a report."""
        from scripts.cj_experiments_runners.eng5_np.settings import RunnerSettings

        settings = make_anchor_align_settings(tmp_path)
        # Seed existing LLM overrides to verify they are preserved
        from common_core import LLMProviderType
        from common_core.events.cj_assessment_events import LLMConfigOverrides

        settings.llm_overrides = LLMConfigOverrides(
            provider_override=LLMProviderType.ANTHROPIC,
            model_override="claude-sonnet-4-5-20250929",
            temperature_override=0.1,
            max_tokens_override=2048,
        )
        settings.await_completion = True
        settings.use_kafka = True
        original_assignment_id = settings.assignment_id

        inventory = make_inventory_with_anchors(tmp_path, anchor_count=2)

        schema_path = tmp_path / "schema.json"
        artefact_path = tmp_path / "assessment_run.anchor-align-test.json"
        report_path = tmp_path / "anchor_align_TEST-BATCH-ANCHOR-ALIGN_20250101_000000.md"

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
            # Map all checksums to dummy storage IDs
            return {r.checksum: f"storage-{idx}" for idx, r in enumerate(records)}

        def fake_build_essay_refs(
            *,
            anchors,
            students,
            max_comparisons,
            storage_id_map,
            student_id_factory=None,
        ):
            calls["essay_refs_anchors"] = anchors
            calls["essay_refs_students"] = students
            calls["essay_refs_storage_map"] = storage_id_map
            return ["ref-1", "ref-2"]

        def fake_compose_cj_assessment_request(
            *,
            settings: RunnerSettings,
            essay_refs,
            prompt_reference,
        ):
            # Capture assignment_id at composition time (GUEST semantics)
            calls["compose_assignment_id"] = settings.assignment_id
            calls["compose_essay_refs"] = essay_refs
            calls["compose_prompt_ref"] = prompt_reference
            calls["compose_llm_overrides"] = settings.llm_overrides
            return {"type": "ELS_CJAssessmentRequestV1"}

        def fake_write_cj_request_envelope(
            *,
            envelope,
            output_dir: Path,
        ) -> Path:
            calls["request_envelope"] = envelope
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

        async def fake_publish_envelope_to_kafka(*, envelope, settings: RunnerSettings):
            calls["publish_only_envelope"] = envelope
            calls["publish_only_settings_mode"] = settings.mode

        def fake_load_anchor_grade_map(_path: Path) -> dict[str, str]:
            calls["grade_map_loaded"] = True
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
            calls["report_hydrator"] = hydrator
            calls["report_anchor_grade_map"] = anchor_grade_map
            calls["report_batch_id"] = batch_id
            calls["report_output_dir"] = output_dir
            calls["report_system_prompt_text"] = system_prompt_text
            calls["report_rubric_text"] = rubric_text
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

        # Patch dependencies on the handler module
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
            "scripts.cj_experiments_runners.eng5_np.handlers.anchor_align_handler.publish_envelope_to_kafka",
            fake_publish_envelope_to_kafka,
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

        class DummyPaths:
            """Minimal paths object exposing schema_path."""

            def __init__(self, schema: Path) -> None:
                self.schema_path = schema

        handler = AnchorAlignHandler()
        exit_code = handler.execute(
            settings=settings,
            inventory=inventory,
            paths=DummyPaths(schema_path),  # type: ignore[arg-type]
        )

        assert exit_code == 0

        # Schema and stub artefact setup
        assert calls["schema_path"] == schema_path
        assert calls["stub_settings_mode"] == RunnerMode.ANCHOR_ALIGN_TEST
        assert calls["stub_schema"] == {"$id": "test-schema"}

        # Upload and essay refs - all anchors treated as students
        upload_records = calls["upload_records"]
        assert len(upload_records) == 2
        assert calls["upload_url"] == settings.content_service_url

        assert calls["essay_refs_anchors"] == []
        assert len(calls["essay_refs_students"]) == 2
        assert isinstance(calls["essay_refs_storage_map"], dict)

        # Request composition uses GUEST semantics (assignment_id=None)
        assert calls["compose_assignment_id"] is None
        assert calls["compose_essay_refs"] == ["ref-1", "ref-2"]

        # Alignment report generation
        assert calls["grade_map_loaded"] is True
        assert calls["report_batch_id"] == settings.batch_id
        assert calls["report_output_dir"] == settings.output_dir
        assert calls["report_anchor_grade_map"] == {"anchor_001": "A", "anchor_002": "C"}
        # Custom prompts are passed through to report generator when provided
        # (in this test we did not supply prompt files, so they may be None)
        assert "report_system_prompt_text" in calls
        assert "report_rubric_text" in calls

        # LLM overrides from CLI (provider/model/etc.) are preserved when
        # AnchorAlignHandler adds prompt/rubric overrides.
        overrides = calls["compose_llm_overrides"]
        assert overrides is not None
        # Provider override preserved (string or enum)
        assert overrides.provider_override is not None
        assert "anthropic" in str(overrides.provider_override).lower()
        # Model + other overrides preserved
        assert overrides.model_override == "claude-sonnet-4-5-20250929"
        assert overrides.temperature_override == 0.1
        assert overrides.max_tokens_override == 2048

        # Validation logging uses artefact_path from stub writer
        assert calls["logged_artefact_path"] == artefact_path

        # Original assignment_id restored after execute()
        assert settings.assignment_id == original_assignment_id
