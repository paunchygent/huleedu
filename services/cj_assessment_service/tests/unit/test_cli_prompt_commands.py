"""CLI tests for student prompt management commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from services.cj_assessment_service.cli import config, instructions, main, prompts

runner = CliRunner()


@pytest.fixture(autouse=True)
def reset_token_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure commands never attempt real authentication."""
    # Patch config where it is used (commands use make_admin_request via AuthManager)
    monkeypatch.setattr(config, "CJ_ADMIN_TOKEN_OVERRIDE", "test-token")


class TestPromptsUploadCommand:
    def test_upload_with_file_success(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        recorded: dict[str, Any] = {}

        def fake_admin_request(method: str, path: str, json_body: Any | None = None) -> Any:
            recorded.update({"method": method, "path": path, "json": json_body})
            return {
                "assignment_id": "assignment-1",
                "student_prompt_storage_id": "storage-123",
                "prompt_text": json_body["prompt_text"] if json_body else None,
            }

        # Patch where it is USED: in prompts.py
        monkeypatch.setattr(prompts, "make_admin_request", fake_admin_request)

        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Prompt content from file", encoding="utf-8")

        result = runner.invoke(
            main.app,
            [
                "prompts",
                "upload",
                "--assignment-id",
                "assignment-1",
                "--prompt-file",
                str(prompt_file),
            ],
        )

        assert result.exit_code == 0
        assert "Student prompt uploaded successfully" in result.stdout
        assert recorded["method"] == "POST"
        assert recorded["path"] == "/student-prompts"
        assert recorded["json"]["assignment_id"] == "assignment-1"
        assert recorded["json"]["prompt_text"] == "Prompt content from file"

    def test_upload_with_inline_text_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def fake_admin_request(method: str, path: str, json_body: Any | None = None) -> Any:
            assert isinstance(json_body, dict), "Expected dict json_body"
            captured["json"] = json_body
            return {
                "assignment_id": json_body["assignment_id"],
                "student_prompt_storage_id": "inline-storage",
                "prompt_text": json_body["prompt_text"],
            }

        monkeypatch.setattr(prompts, "make_admin_request", fake_admin_request)

        result = runner.invoke(
            main.app,
            [
                "prompts",
                "upload",
                "--assignment-id",
                "assignment-42",
                "--prompt-text",
                "Inline prompt value",
            ],
        )

        assert result.exit_code == 0
        assert captured["json"]["assignment_id"] == "assignment-42"
        assert captured["json"]["prompt_text"] == "Inline prompt value"

    def test_upload_requires_exactly_one_input(self) -> None:
        result = runner.invoke(
            main.app,
            [
                "prompts",
                "upload",
                "--assignment-id",
                "assignment-1",
            ],
        )

        assert result.exit_code == 2
        assert "Provide exactly one of" in (result.stdout + result.stderr)

    def test_upload_rejects_both_inputs(self, tmp_path: Path) -> None:
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Some prompt", encoding="utf-8")

        result = runner.invoke(
            main.app,
            [
                "prompts",
                "upload",
                "--assignment-id",
                "assignment-1",
                "--prompt-file",
                str(prompt_file),
                "--prompt-text",
                "Also prompt",
            ],
        )

        assert result.exit_code == 2
        assert "Provide exactly one of" in (result.stdout + result.stderr)

    def test_upload_missing_file_path(self) -> None:
        result = runner.invoke(
            main.app,
            [
                "prompts",
                "upload",
                "--assignment-id",
                "assignment-1",
                "--prompt-file",
                "does-not-exist.txt",
            ],
        )

        assert result.exit_code == 1
        assert "File not found" in (result.stdout + result.stderr)

    def test_upload_empty_inline_prompt(self) -> None:
        result = runner.invoke(
            main.app,
            [
                "prompts",
                "upload",
                "--assignment-id",
                "assignment-1",
                "--prompt-text",
                "   ",
            ],
        )

        assert result.exit_code == 2
        assert "Prompt content cannot be empty" in (result.stdout + result.stderr)

    def test_upload_api_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def failing_admin_request(method: str, path: str, json_body: Any | None = None) -> Any:
            raise typer.Exit(code=1)

        monkeypatch.setattr(prompts, "make_admin_request", failing_admin_request)

        result = runner.invoke(
            main.app,
            [
                "prompts",
                "upload",
                "--assignment-id",
                "assignment-1",
                "--prompt-text",
                "Prompt",
            ],
        )

        assert result.exit_code == 1


class TestPromptsGetCommand:
    def test_get_prints_prompt_to_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        expected = {
            "assignment_id": "assignment-1",
            "student_prompt_storage_id": "storage-111",
            "prompt_text": "Prompt body",
            "grade_scale": "swedish_8_anchor",
            "created_at": "2025-11-10T00:00:00+00:00",
        }

        monkeypatch.setattr(prompts, "make_admin_request", lambda *_args, **_kwargs: expected)

        result = runner.invoke(main.app, ["prompts", "get", "assignment-1"])

        assert result.exit_code == 0
        assert "Student Prompt Details" in result.stdout
        assert "storage-111" in result.stdout
        assert "Prompt body" in result.stdout

    def test_get_writes_prompt_to_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            prompts,
            "make_admin_request",
            lambda *_args, **_kwargs: {
                "assignment_id": "assignment-1",
                "student_prompt_storage_id": "storage-abc",
                "prompt_text": "Prompt file content",
                "grade_scale": "swedish_8_anchor",
                "created_at": "2025-11-10T00:00:00+00:00",
            },
        )

        output_path = tmp_path / "output.txt"
        result = runner.invoke(
            main.app,
            [
                "prompts",
                "get",
                "assignment-1",
                "--output-file",
                str(output_path),
            ],
        )

        assert result.exit_code == 0
        assert output_path.read_text(encoding="utf-8") == "Prompt file content"

    def test_get_requires_string_prompt_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            prompts,
            "make_admin_request",
            lambda *_args, **_kwargs: {
                "assignment_id": "assignment-1",
                "student_prompt_storage_id": "storage-abc",
                "prompt_text": 5,
                "grade_scale": "swedish_8_anchor",
                "created_at": "2025-11-10T00:00:00+00:00",
            },
        )

        result = runner.invoke(main.app, ["prompts", "get", "assignment-1"])

        assert result.exit_code == 1
        assert "prompt_text field is not a string" in (result.stdout + result.stderr)

    def test_get_api_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            prompts,
            "make_admin_request",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(typer.Exit(code=1)),
        )

        result = runner.invoke(main.app, ["prompts", "get", "assignment-1"])

        assert result.exit_code == 1


class TestInstructionCreateCommand:
    def test_create_without_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payloads: list[dict[str, Any]] = []

        def fake_admin_request(method: str, path: str, json_body: Any | None = None) -> Any:
            assert isinstance(json_body, dict), "Expected dict json_body"
            payloads.append(json_body)
            return {
                "assignment_id": json_body["assignment_id"],
                "grade_scale": json_body["grade_scale"],
            }

        # Patch where it is used: instructions.py
        monkeypatch.setattr(instructions, "make_admin_request", fake_admin_request)
        monkeypatch.setattr(instructions, "upload_prompt_helper", lambda *_args, **_kwargs: None)

        result = runner.invoke(
            main.app,
            [
                "instructions",
                "create",
                "--assignment-id",
                "assignment-55",
                "--instructions-text",
                "Instruction body",
                "--grade-scale",
                "swedish_8_anchor",
            ],
        )

        assert result.exit_code == 0
        assert payloads[0]["assignment_id"] == "assignment-55"
        assert "student_prompt_storage_id" not in payloads[0]

    def test_create_with_prompt_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Prompt content", encoding="utf-8")

        payloads: list[dict[str, Any]] = []

        def fake_admin_request(method: str, path: str, json_body: Any | None = None) -> Any:
            assert isinstance(json_body, dict), "Expected dict json_body"
            payloads.append(json_body)
            return json_body

        upload_calls: list[tuple[str, str]] = []

        def fake_upload_helper(assignment_id: str, content: str) -> str:
            upload_calls.append((assignment_id, content))
            return "storage-upload"

        monkeypatch.setattr(instructions, "make_admin_request", fake_admin_request)
        monkeypatch.setattr(instructions, "upload_prompt_helper", fake_upload_helper)

        result = runner.invoke(
            main.app,
            [
                "instructions",
                "create",
                "--assignment-id",
                "assignment-99",
                "--instructions-text",
                "Instruction text",
                "--grade-scale",
                "swedish_8_anchor",
                "--prompt-file",
                str(prompt_file),
            ],
        )

        assert result.exit_code == 0
        assert upload_calls == [("assignment-99", "Prompt content")]
        assert payloads[0]["student_prompt_storage_id"] == "storage-upload"

    def test_create_with_prompt_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payloads: list[dict[str, Any]] = []

        def fake_admin_request(method: str, path: str, json_body: Any | None = None) -> Any:
            assert isinstance(json_body, dict), "Expected dict json_body"
            payloads.append(json_body)
            return json_body

        monkeypatch.setattr(instructions, "make_admin_request", fake_admin_request)
        monkeypatch.setattr(instructions, "upload_prompt_helper", lambda *_: "prompt-storage")

        result = runner.invoke(
            main.app,
            [
                "instructions",
                "create",
                "--assignment-id",
                "assignment-100",
                "--instructions-text",
                "Instruction text",
                "--grade-scale",
                "swedish_8_anchor",
                "--prompt-text",
                "Inline prompt",
            ],
        )

        assert result.exit_code == 0
        assert payloads[0]["student_prompt_storage_id"] == "prompt-storage"

    def test_create_prompt_requires_assignment(self) -> None:
        result = runner.invoke(
            main.app,
            [
                "instructions",
                "create",
                "--course-id",
                "course-1",
                "--prompt-text",
                "Prompt",
                "--grade-scale",
                "swedish_8_anchor",
                "--instructions-text",
                "Instruction",
            ],
        )

        assert result.exit_code == 2
        assert "Student prompt can only be uploaded" in (result.stdout + result.stderr)

    def test_create_rejects_both_prompt_inputs(self, tmp_path: Path) -> None:
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Prompt", encoding="utf-8")

        result = runner.invoke(
            main.app,
            [
                "instructions",
                "create",
                "--assignment-id",
                "assignment-1",
                "--instructions-text",
                "Instruction",
                "--grade-scale",
                "swedish_8_anchor",
                "--prompt-file",
                str(prompt_file),
                "--prompt-text",
                "Prompt",
            ],
        )

        assert result.exit_code == 2
        assert "Provide at most one" in (result.stdout + result.stderr)
