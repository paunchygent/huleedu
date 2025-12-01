"""Typer CLI integration tests for ENG5 NP runner."""

from __future__ import annotations

import uuid
from pathlib import Path

from typer.testing import CliRunner

from scripts.cj_experiments_runners.eng5_np import cli
from scripts.cj_experiments_runners.eng5_np.inventory import (
    DirectorySnapshot,
    FileRecord,
    RunnerInventory,
)
from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
from scripts.cj_experiments_runners.eng5_np.settings import RunnerMode

runner = CliRunner()


def _make_dummy_inventory(tmp_path: Path) -> RunnerInventory:
    """Create a small inventory used by CLI integration tests."""
    instructions = FileRecord(path=tmp_path / "instructions.md", exists=True)
    prompt = FileRecord(path=tmp_path / "prompt.md", exists=True)
    anchors_csv = FileRecord(path=tmp_path / "anchors.csv", exists=True)
    anchors_xlsx = FileRecord(path=tmp_path / "anchors.xlsx", exists=True)

    anchor_files = [
        FileRecord(
            path=tmp_path / "anchors" / "anchor_001.docx",
            exists=True,
            checksum="anchor-checksum-1",
        )
    ]
    student_files = [
        FileRecord(
            path=tmp_path / "students" / "student_001.docx",
            exists=True,
            checksum="student-checksum-1",
        )
    ]

    anchor_docs = DirectorySnapshot(root=tmp_path / "anchors", files=anchor_files)
    student_docs = DirectorySnapshot(root=tmp_path / "students", files=student_files)

    return RunnerInventory(
        instructions=instructions,
        prompt=prompt,
        anchors_csv=anchors_csv,
        anchors_xlsx=anchors_xlsx,
        anchor_docs=anchor_docs,
        student_docs=student_docs,
    )


class TestCliPlanMode:
    """Integration tests for PLAN mode CLI entrypoint."""

    def test_plan_mode_dispatches_to_plan_handler(self, tmp_path, monkeypatch):
        """`--mode plan` constructs handler and passes settings/inventory/paths."""
        dummy_inventory = _make_dummy_inventory(tmp_path)
        calls: dict[str, object] = {}

        class DummyHandler:
            def __init__(self) -> None:
                calls["handler_constructed"] = True

            def execute(self, settings, inventory, paths) -> int:  # noqa: ANN001
                calls["settings_mode"] = settings.mode
                calls["settings_batch_id"] = settings.batch_id
                calls["inventory"] = inventory
                calls["paths"] = paths
                return 0

        def fake_collect_inventory(paths: RunnerPaths) -> RunnerInventory:
            calls["collect_paths_repo_root"] = paths.repo_root
            return dummy_inventory

        def fake_ensure_comparison_capacity(*, anchors, students, max_comparisons):
            calls["ensure_capacity_called"] = True
            calls["anchors_count"] = anchors.count
            calls["students_count"] = students.count
            calls["max_comparisons"] = max_comparisons

        def fake_validate_llm_overrides(*, provider, model) -> None:
            calls["validated_llm_overrides"] = (provider, model)

        def fake_configure_cli_logging(verbose: bool) -> None:
            calls["configure_cli_logging_verbose"] = verbose

        def fake_setup_cli_logger(settings):
            class DummyLogger:
                def info(self, *_args, **_kwargs) -> None:
                    calls["logger_info_called"] = True

            return DummyLogger()

        def fake_gather_git_sha(_repo_root: Path) -> str:
            return "test-git-sha"

        # Patch CLI dependencies
        monkeypatch.setitem(cli.HANDLER_MAP, RunnerMode.PLAN, DummyHandler)
        monkeypatch.setattr(cli, "collect_inventory", fake_collect_inventory)
        monkeypatch.setattr(cli, "ensure_comparison_capacity", fake_ensure_comparison_capacity)
        monkeypatch.setattr(cli, "validate_llm_overrides", fake_validate_llm_overrides)
        monkeypatch.setattr(cli, "configure_cli_logging", fake_configure_cli_logging)
        monkeypatch.setattr(cli, "setup_cli_logger", fake_setup_cli_logger)
        monkeypatch.setattr(cli, "gather_git_sha", fake_gather_git_sha)

        # Avoid invoking real execute-mode logging in case modes change
        monkeypatch.setattr(cli, "configure_execute_logging", lambda *_, **__: None)

        result = runner.invoke(
            cli.app,
            [
                "--mode",
                "plan",
                "--batch-id",
                "plan-test-batch",
                "--kafka-bootstrap",
                "localhost:9093",
            ],
        )

        assert result.exit_code == 0
        assert calls["handler_constructed"] is True
        assert calls["settings_mode"] is RunnerMode.PLAN
        assert calls["settings_batch_id"] == "plan-test-batch"
        assert calls["inventory"] is dummy_inventory
        assert calls["ensure_capacity_called"] is True
        assert calls["anchors_count"] == dummy_inventory.anchor_docs.count
        assert calls["students_count"] == dummy_inventory.student_docs.count
        assert calls["max_comparisons"] is None
        assert calls["configure_cli_logging_verbose"] is False
        assert calls["logger_info_called"] is True


class TestCliExecuteValidation:
    """Validation tests for EXECUTE mode argument requirements."""

    def test_execute_mode_requires_assignment_and_course_ids(self):
        """EXECUTE mode errors when assignment_id or course_id is missing."""
        result = runner.invoke(cli.app, ["--mode", "execute"])

        # Typer exits with code 2 (usage error) on BadParameter
        assert result.exit_code == 2
        stderr_out = result.stdout + result.stderr
        # Message may be wrapped with line breaks; use a stable substring.
        assert "--assignment-id is required for execute" in stderr_out


class TestCliAnchorAlignMode:
    """Integration tests for anchor-align-test CLI behavior."""

    def test_anchor_align_mode_allows_missing_assignment_id(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """ANCHOR_ALIGN_TEST does not require --assignment-id and dispatches handler."""
        dummy_inventory = _make_dummy_inventory(tmp_path)
        calls: dict[str, object] = {}

        class DummyHandler:
            def __init__(self) -> None:
                calls["handler_constructed"] = True

            def execute(self, settings, inventory, paths) -> int:  # noqa: ANN001
                calls["settings_mode"] = settings.mode
                calls["settings_assignment_id"] = settings.assignment_id
                calls["inventory"] = inventory
                calls["paths"] = paths
                return 0

        def fake_collect_inventory(paths: RunnerPaths) -> RunnerInventory:
            calls["collect_paths_repo_root"] = paths.repo_root
            return dummy_inventory

        def fake_ensure_comparison_capacity(*, anchors, students, max_comparisons):
            calls["ensure_capacity_called"] = True
            calls["anchors_count"] = anchors.count
            calls["students_count"] = students.count
            calls["max_comparisons"] = max_comparisons

        def fake_validate_llm_overrides(*, provider, model) -> None:
            calls["validated_llm_overrides"] = (provider, model)

        def fake_configure_cli_logging(verbose: bool) -> None:
            calls["configure_cli_logging_verbose"] = verbose

        def fake_setup_cli_logger(settings):
            class DummyLogger:
                def info(self, *_args, **_kwargs) -> None:
                    calls["logger_info_called"] = True

            return DummyLogger()

        def fake_gather_git_sha(_repo_root: Path) -> str:
            return "test-git-sha"

        monkeypatch.setitem(cli.HANDLER_MAP, RunnerMode.ANCHOR_ALIGN_TEST, DummyHandler)
        monkeypatch.setattr(cli, "collect_inventory", fake_collect_inventory)
        monkeypatch.setattr(cli, "ensure_comparison_capacity", fake_ensure_comparison_capacity)
        monkeypatch.setattr(cli, "validate_llm_overrides", fake_validate_llm_overrides)
        monkeypatch.setattr(cli, "configure_cli_logging", fake_configure_cli_logging)
        monkeypatch.setattr(cli, "setup_cli_logger", fake_setup_cli_logger)
        monkeypatch.setattr(cli, "gather_git_sha", fake_gather_git_sha)
        monkeypatch.setattr(cli, "configure_execute_logging", lambda *_, **__: None)

        result = runner.invoke(
            cli.app,
            [
                "--mode",
                "anchor-align-test",
                "--batch-id",
                "anchor-align-cli-test",
                "--kafka-bootstrap",
                "localhost:9093",
                "--course-id",
                str(uuid.UUID("00000000-0000-0000-0000-000000000052")),
            ],
        )

        assert result.exit_code == 0
        assert calls["handler_constructed"] is True
        assert calls["settings_mode"] is RunnerMode.ANCHOR_ALIGN_TEST
        # assignment_id is allowed to be None here (GUEST flow)
        assert calls["settings_assignment_id"] is None
        assert calls["inventory"] is dummy_inventory
        assert calls["ensure_capacity_called"] is True

    def test_anchor_align_language_control_configuration_uses_sonnet_and_prompts(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """CLI wires Sonnet 4.5 + 003 language-control prompts into settings."""
        dummy_inventory = _make_dummy_inventory(tmp_path)
        calls: dict[str, object] = {}

        class DummyHandler:
            def __init__(self) -> None:
                calls["handler_constructed"] = True

            def execute(self, settings, inventory, paths) -> int:  # noqa: ANN001
                calls["settings"] = settings
                calls["inventory"] = inventory
                calls["paths"] = paths
                return 0

        def fake_collect_inventory(paths: RunnerPaths) -> RunnerInventory:
            calls["collect_paths_repo_root"] = paths.repo_root
            return dummy_inventory

        def fake_ensure_comparison_capacity(*, anchors, students, max_comparisons):
            calls["ensure_capacity_called"] = True
            calls["anchors_count"] = anchors.count
            calls["students_count"] = students.count
            calls["max_comparisons"] = max_comparisons

        def fake_validate_llm_overrides(*, provider, model) -> None:
            calls["validated_llm_overrides"] = (provider, model)

        def fake_configure_cli_logging(verbose: bool) -> None:
            calls["configure_cli_logging_verbose"] = verbose

        def fake_setup_cli_logger(settings):
            class DummyLogger:
                def info(self, *_args, **_kwargs) -> None:
                    calls["logger_info_called"] = True

            return DummyLogger()

        def fake_gather_git_sha(_repo_root: Path) -> str:
            return "test-git-sha"

        monkeypatch.setitem(cli.HANDLER_MAP, RunnerMode.ANCHOR_ALIGN_TEST, DummyHandler)
        monkeypatch.setattr(cli, "collect_inventory", fake_collect_inventory)
        monkeypatch.setattr(cli, "ensure_comparison_capacity", fake_ensure_comparison_capacity)
        monkeypatch.setattr(cli, "validate_llm_overrides", fake_validate_llm_overrides)
        monkeypatch.setattr(cli, "configure_cli_logging", fake_configure_cli_logging)
        monkeypatch.setattr(cli, "setup_cli_logger", fake_setup_cli_logger)
        monkeypatch.setattr(cli, "gather_git_sha", fake_gather_git_sha)
        monkeypatch.setattr(cli, "configure_execute_logging", lambda *_, **__: None)

        system_prompt_rel = (
            "scripts/cj_experiments_runners/eng5_np/prompts/system/003_language_control.txt"
        )
        rubric_rel = (
            "scripts/cj_experiments_runners/eng5_np/prompts/rubric/003_language_control.txt"
        )

        result = runner.invoke(
            cli.app,
            [
                "--mode",
                "anchor-align-test",
                "--batch-id",
                "anchor-align-language-control",
                "--kafka-bootstrap",
                "localhost:9093",
                "--course-id",
                str(uuid.UUID("00000000-0000-0000-0000-000000000052")),
                "--llm-provider",
                "anthropic",
                "--llm-model",
                "claude-sonnet-4-5-20250929",
                "--system-prompt",
                system_prompt_rel,
                "--rubric",
                rubric_rel,
            ],
        )

        assert result.exit_code == 0
        assert calls["handler_constructed"] is True
        settings = calls["settings"]
        assert settings.mode is RunnerMode.ANCHOR_ALIGN_TEST
        assert settings.llm_overrides is not None
        overrides = settings.llm_overrides
        assert overrides.model_override == "claude-sonnet-4-5-20250929"
        assert overrides.provider_override is not None
        assert "anthropic" in str(overrides.provider_override).lower()

        # Prompt file paths are propagated into settings
        assert settings.system_prompt_file is not None
        assert settings.rubric_file is not None
        assert str(settings.system_prompt_file).endswith(system_prompt_rel)
        assert str(settings.rubric_file).endswith(rubric_rel)

        # Manifest validation called with the exact CLI values
        assert calls["validated_llm_overrides"] == (
            "anthropic",
            "claude-sonnet-4-5-20250929",
        )

    def test_anchor_align_gpt51_reasoning_effort_flags(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """CLI wires GPT-5.1 + reasoning effort into settings for anchor-align-test."""
        dummy_inventory = _make_dummy_inventory(tmp_path)
        calls: dict[str, object] = {}

        class DummyHandler:
            def __init__(self) -> None:
                calls["handler_constructed"] = True

            def execute(self, settings, inventory, paths) -> int:  # noqa: ANN001
                calls["settings"] = settings
                calls["inventory"] = inventory
                calls["paths"] = paths
                return 0

        def fake_collect_inventory(paths: RunnerPaths) -> RunnerInventory:
            calls["collect_paths_repo_root"] = paths.repo_root
            return dummy_inventory

        def fake_ensure_comparison_capacity(*, anchors, students, max_comparisons):
            calls["ensure_capacity_called"] = True
            calls["anchors_count"] = anchors.count
            calls["students_count"] = students.count
            calls["max_comparisons"] = max_comparisons

        def fake_validate_llm_overrides(*, provider, model) -> None:
            calls["validated_llm_overrides"] = (provider, model)

        def fake_configure_cli_logging(verbose: bool) -> None:
            calls["configure_cli_logging_verbose"] = verbose

        def fake_setup_cli_logger(settings):
            class DummyLogger:
                def info(self, *_args, **_kwargs) -> None:
                    calls["logger_info_called"] = True

            return DummyLogger()

        def fake_gather_git_sha(_repo_root: Path) -> str:
            return "test-git-sha"

        monkeypatch.setitem(cli.HANDLER_MAP, RunnerMode.ANCHOR_ALIGN_TEST, DummyHandler)
        monkeypatch.setattr(cli, "collect_inventory", fake_collect_inventory)
        monkeypatch.setattr(cli, "ensure_comparison_capacity", fake_ensure_comparison_capacity)
        monkeypatch.setattr(cli, "validate_llm_overrides", fake_validate_llm_overrides)
        monkeypatch.setattr(cli, "configure_cli_logging", fake_configure_cli_logging)
        monkeypatch.setattr(cli, "setup_cli_logger", fake_setup_cli_logger)
        monkeypatch.setattr(cli, "gather_git_sha", fake_gather_git_sha)
        monkeypatch.setattr(cli, "configure_execute_logging", lambda *_, **__: None)

        result = runner.invoke(
            cli.app,
            [
                "--mode",
                "anchor-align-test",
                "--batch-id",
                "anchor-align-gpt5-1",
                "--kafka-bootstrap",
                "localhost:9093",
                "--course-id",
                str(uuid.UUID("00000000-0000-0000-0000-000000000052")),
                "--anchor-align-provider",
                "openai",
                "--anchor-align-model",
                "gpt-5.1",
                "--anchor-align-reasoning-effort",
                "medium",
                "--anchor-align-output-verbosity",
                "high",
            ],
        )

        assert result.exit_code == 0
        assert calls["handler_constructed"] is True
        settings = calls["settings"]
        assert settings.mode is RunnerMode.ANCHOR_ALIGN_TEST
        # Effective provider/model recorded on settings and overrides
        assert settings.anchor_align_llm_provider == "openai"
        assert settings.anchor_align_llm_model == "gpt-5.1"
        assert settings.anchor_align_reasoning_effort == "medium"
        assert settings.anchor_align_output_verbosity == "high"
        assert settings.llm_overrides is not None
        overrides = settings.llm_overrides
        assert overrides.model_override == "gpt-5.1"
        assert overrides.provider_override is not None
        assert "openai" in str(overrides.provider_override).lower()
        assert overrides.reasoning_effort == "medium"
        assert overrides.output_verbosity == "high"

        # Manifest validation called with effective GPT-5.1 config
        assert calls["validated_llm_overrides"] == ("openai", "gpt-5.1")
