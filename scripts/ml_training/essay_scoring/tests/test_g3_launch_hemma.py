"""Tests for canonical Gate G3 Hemma launcher orchestration helpers.

Purpose:
    Validate that the launch wrapper enforces fail-closed preflight semantics
    and builds the ROCm-safe transformer command path.

Relationships:
    - Targets `scripts.ml_training.essay_scoring.g3_launch_hemma`.
    - Avoids network/SSH by injecting deterministic fake remote runner outputs.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from scripts.ml_training.essay_scoring.g3_launch_hemma import (
    DEFAULT_REMOTE_REPO_ROOT,
    RUN_NAME_TEMPLATE_TOKEN,
    G3LaunchConfig,
    G3LaunchError,
    RemoteCommandResult,
    build_launch_script,
    build_preflight_script,
    build_transformer_command,
    run_g3_launch,
)


@dataclass
class _QueuedRunner:
    """Deterministic remote runner stub that returns queued results."""

    queued: list[RemoteCommandResult]

    def __call__(self, *, host: str, script: str) -> RemoteCommandResult:
        del host
        del script
        if not self.queued:
            raise AssertionError("No queued remote result available.")
        return self.queued.pop(0)


class _NeverCallRunner:
    """Remote runner guard that must never be called."""

    def __call__(self, *, host: str, script: str) -> RemoteCommandResult:
        del host
        del script
        raise AssertionError("Remote runner should not be called.")


def test_build_transformer_command_uses_container_python_and_required_flags() -> None:
    command = build_transformer_command(G3LaunchConfig())

    assert "python -m scripts.ml_training.essay_scoring.cli transformer-finetune" in command
    assert f"--run-name {RUN_NAME_TEMPLATE_TOKEN}" in command
    assert "${RUN_NAME}" not in command
    assert "--chunk-overlap-tokens 128" in command
    assert "--require-gpu" in command
    assert "--mixed-precision none" in command
    assert "pdm run" not in command


def test_build_preflight_script_enforces_gpu_and_cli_contract() -> None:
    script = build_preflight_script(config=G3LaunchConfig())

    assert "MISSING_IMAGE_LABEL:org.huleedu.transformer_train.base_image" in script
    assert "UNSUPPORTED_BASE_IMAGE:${BASE_IMAGE_LABEL}" in script
    assert "BASE_IMAGE_OK:${BASE_IMAGE_LABEL}" in script
    assert "torch.cuda.is_available()" in script
    assert "UNSUPPORTED_HIP_VERSION" in script
    assert "UNSUPPORTED_TORCH_VERSION" in script
    assert "UNSUPPORTED_PYTHON_VERSION" in script
    assert "PRECISION_CANARY_OK" in script
    assert "NO_COLOR=1 COLUMNS=240" in script
    assert "MISSING_FLAG:--chunk-overlap-tokens" in script
    assert "MISSING_FLAG:--require-gpu" in script
    assert "MISSING_MODULE:peft" in script
    assert "LORA_MODULES_OK" in script
    assert "STALE_SCREEN:ellipse_gate_g3_1_transformer_lora_prompt_holdout" in script


def test_build_preflight_script_skips_lora_module_check_when_lora_disabled() -> None:
    script = build_preflight_script(config=G3LaunchConfig(use_lora=False))
    assert "MISSING_MODULE:peft" not in script
    assert "LORA_MODULES_OK" not in script


def test_build_launch_script_uses_bash_array_with_safe_run_name_injection() -> None:
    script = build_launch_script(config=G3LaunchConfig())
    assert "CMD=(" in script
    assert '"$RUN_NAME"' in script
    assert "printf '%q ' \"${CMD[@]}\"" in script
    assert RUN_NAME_TEMPLATE_TOKEN not in script


def test_default_remote_repo_root_uses_huleedu_spelling() -> None:
    assert DEFAULT_REMOTE_REPO_ROOT == "/home/paunchygent/apps/huleedu"


def test_run_g3_launch_fails_fast_for_legacy_huledu_remote_root() -> None:
    config = G3LaunchConfig(remote_repo_root="/home/paunchygent/apps/huledu")
    with pytest.raises(G3LaunchError, match="Canonical Hemma repo root"):
        run_g3_launch(config=config, remote_runner=_NeverCallRunner())


def test_run_g3_launch_fails_fast_for_empty_approved_base_images() -> None:
    config = G3LaunchConfig(approved_transformer_base_images=())
    with pytest.raises(G3LaunchError, match="approved_transformer_base_images must not be empty"):
        run_g3_launch(config=config, remote_runner=_NeverCallRunner())


def test_run_g3_launch_returns_run_markers_when_remote_steps_pass() -> None:
    runner = _QueuedRunner(
        queued=[
            RemoteCommandResult(
                return_code=0, stdout="GPU_PREFLIGHT_OK\nPREFLIGHT_OK\n", stderr=""
            ),
            RemoteCommandResult(
                return_code=0,
                stdout=(
                    "RUN_NAME=ellipse_gate_g3_1_transformer_lora_prompt_holdout_20990101_000000\n"
                    "DRIVER_LOG=output/essay_scoring/example.driver.log\n"
                    "LAUNCH_OK\n"
                ),
                stderr="",
            ),
        ]
    )

    result = run_g3_launch(config=G3LaunchConfig(), remote_runner=runner)

    assert result.run_name == "ellipse_gate_g3_1_transformer_lora_prompt_holdout_20990101_000000"
    assert result.driver_log == "output/essay_scoring/example.driver.log"


def test_run_g3_launch_fails_closed_without_launch_markers() -> None:
    runner = _QueuedRunner(
        queued=[
            RemoteCommandResult(return_code=0, stdout="PREFLIGHT_OK\n", stderr=""),
            RemoteCommandResult(return_code=0, stdout="LAUNCH_OK\n", stderr=""),
        ]
    )

    with pytest.raises(G3LaunchError, match="RUN_NAME/DRIVER_LOG"):
        run_g3_launch(config=G3LaunchConfig(), remote_runner=runner)
