"""Canonical local-orchestrated Hemma launcher for transformer Gate G3 runs.

Purpose:
    Provide one fail-closed executable path (`g3-launch-hemma`) that performs
    deterministic Hemma preflight checks and launches detached G3.1 training
    on the dedicated ROCm container.

Relationships:
    - Invoked by `scripts.ml_training.essay_scoring.commands.g3_launch_commands`.
    - Launch target is the existing `transformer-finetune` CLI contract.
    - Reuses frozen ELLIPSE/splits/feature-store lineage defined in handoff.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from typing import Protocol

DEFAULT_REMOTE_HOST = "hemma"
DEFAULT_REMOTE_REPO_ROOT = "/home/paunchygent/apps/huleedu"
DEFAULT_TRAINING_CONTAINER = "huleedu_essay_transformer_train"
DEFAULT_RUN_NAME_PREFIX = "ellipse_gate_g3_1_transformer_lora_prompt_holdout"
DEFAULT_MODEL_NAME = "microsoft/deberta-v3-base"
DEFAULT_APPROVED_TRANSFORMER_BASE_IMAGE = (
    "rocm/pytorch:rocm7.2_ubuntu24.04_py3.12_pytorch_release_2.9.1"
)
DEFAULT_REQUIRED_HIP_VERSION_PREFIX = "7.2"
DEFAULT_REQUIRED_TORCH_VERSION_PREFIX = "2.9"
DEFAULT_REQUIRED_PYTHON_VERSION_PREFIX = "3.12"

DEFAULT_SPLITS_PATH = (
    "output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json"
)
DEFAULT_ELLIPSE_TRAIN_PATH = (
    "output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/"
    "ellipse_train_prepared.csv"
)
DEFAULT_ELLIPSE_TEST_PATH = (
    "output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/"
    "ellipse_test_prepared.csv"
)
DEFAULT_REUSE_CV_FEATURE_STORE_DIR = (
    "output/essay_scoring/20260204_144831_ellipse_cv_combined_prompt_holdout_20260204_150321/"
    "cv_feature_store"
)


class G3LaunchError(RuntimeError):
    """Raised when Hemma preflight or launch validation fails."""


@dataclass(frozen=True)
class G3FrozenInputs:
    """Frozen Gate G3 file lineage paths, relative to Hemma repo root."""

    splits_path: str = DEFAULT_SPLITS_PATH
    ellipse_train_path: str = DEFAULT_ELLIPSE_TRAIN_PATH
    ellipse_test_path: str = DEFAULT_ELLIPSE_TEST_PATH
    reuse_cv_feature_store_dir: str = DEFAULT_REUSE_CV_FEATURE_STORE_DIR


@dataclass(frozen=True)
class G3LaunchConfig:
    """Execution settings for canonical Gate G3 detached launch."""

    remote_host: str = DEFAULT_REMOTE_HOST
    remote_repo_root: str = DEFAULT_REMOTE_REPO_ROOT
    training_container: str = DEFAULT_TRAINING_CONTAINER
    run_name_prefix: str = DEFAULT_RUN_NAME_PREFIX
    model_name: str = DEFAULT_MODEL_NAME
    max_length: int = 512
    chunk_overlap_tokens: int = 128
    train_batch_size: int = 4
    eval_batch_size: int = 8
    gradient_accumulation_steps: int = 8
    num_epochs: int = 5
    early_stopping_patience: int = 2
    mixed_precision: str = "none"
    gradient_checkpointing: bool = True
    use_lora: bool = True
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.1
    random_seed: int = 42
    require_gpu: bool = True
    approved_transformer_base_images: tuple[str, ...] = (DEFAULT_APPROVED_TRANSFORMER_BASE_IMAGE,)
    required_hip_version_prefix: str = DEFAULT_REQUIRED_HIP_VERSION_PREFIX
    required_torch_version_prefix: str = DEFAULT_REQUIRED_TORCH_VERSION_PREFIX
    required_python_version_prefix: str = DEFAULT_REQUIRED_PYTHON_VERSION_PREFIX
    frozen_inputs: G3FrozenInputs = G3FrozenInputs()


@dataclass(frozen=True)
class RemoteCommandResult:
    """Result payload for one remote ssh script execution."""

    return_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class G3LaunchResult:
    """Outcome payload for canonical launcher execution."""

    run_name: str
    driver_log: str
    preflight_stdout: str
    launch_stdout: str


RUN_NAME_TEMPLATE_TOKEN = "__G3_RUN_NAME__"


class RemoteRunner(Protocol):
    """Callable protocol for remote script execution (injectable for tests)."""

    def __call__(self, *, host: str, script: str) -> RemoteCommandResult:
        """Execute script on remote host and return process output."""


def default_remote_runner(*, host: str, script: str) -> RemoteCommandResult:
    """Run a bash script on the remote host over ssh."""

    completed = subprocess.run(
        ["ssh", host, "/bin/bash", "-s"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    return RemoteCommandResult(
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_g3_launch(
    *,
    config: G3LaunchConfig,
    remote_runner: RemoteRunner = default_remote_runner,
) -> G3LaunchResult:
    """Run fail-closed preflight and detached Gate G3 launch on Hemma."""

    _validate_config(config=config)

    preflight_script = build_preflight_script(config=config)
    preflight_result = remote_runner(host=config.remote_host, script=preflight_script)
    _require_success(step="preflight", result=preflight_result)
    _assert_marker(
        step="preflight",
        output=preflight_result.stdout,
        marker="PREFLIGHT_OK",
    )

    launch_script = build_launch_script(config=config)
    launch_result = remote_runner(host=config.remote_host, script=launch_script)
    _require_success(step="launch", result=launch_result)
    _assert_marker(step="launch", output=launch_result.stdout, marker="LAUNCH_OK")

    values = _parse_key_value_lines(launch_result.stdout)
    run_name = values.get("RUN_NAME")
    driver_log = values.get("DRIVER_LOG")
    if run_name is None or driver_log is None:
        raise G3LaunchError(
            "Launch completed but RUN_NAME/DRIVER_LOG markers were missing.\n"
            f"stdout:\n{launch_result.stdout}\n"
            f"stderr:\n{launch_result.stderr}"
        )

    return G3LaunchResult(
        run_name=run_name,
        driver_log=driver_log,
        preflight_stdout=preflight_result.stdout,
        launch_stdout=launch_result.stdout,
    )


def _validate_config(*, config: G3LaunchConfig) -> None:
    """Validate launcher config invariants before any remote execution."""

    if config.remote_repo_root.rstrip("/") == "/home/paunchygent/apps/huledu":
        raise G3LaunchError(
            "Invalid remote_repo_root '/home/paunchygent/apps/huledu'. "
            "Canonical Hemma repo root per AGENTS.md is "
            "'/home/paunchygent/apps/huleedu'."
        )
    if not config.approved_transformer_base_images:
        raise G3LaunchError("approved_transformer_base_images must not be empty.")
    if any(not image.strip() for image in config.approved_transformer_base_images):
        raise G3LaunchError("approved_transformer_base_images cannot contain empty values.")
    if not config.required_hip_version_prefix.strip():
        raise G3LaunchError("required_hip_version_prefix must not be empty.")
    if not config.required_torch_version_prefix.strip():
        raise G3LaunchError("required_torch_version_prefix must not be empty.")
    if not config.required_python_version_prefix.strip():
        raise G3LaunchError("required_python_version_prefix must not be empty.")


def build_transformer_command_parts(config: G3LaunchConfig) -> list[str]:
    """Build `transformer-finetune` argv parts with a run-name template token."""

    parts = [
        "sudo",
        "-n",
        "docker",
        "exec",
        config.training_container,
        "python",
        "-m",
        "scripts.ml_training.essay_scoring.cli",
        "transformer-finetune",
        "--scheme",
        "prompt_holdout",
        "--splits-path",
        config.frozen_inputs.splits_path,
        "--ellipse-train-path",
        config.frozen_inputs.ellipse_train_path,
        "--ellipse-test-path",
        config.frozen_inputs.ellipse_test_path,
        "--reuse-cv-feature-store-dir",
        config.frozen_inputs.reuse_cv_feature_store_dir,
        "--run-name",
        RUN_NAME_TEMPLATE_TOKEN,
        "--model-name",
        config.model_name,
        "--max-length",
        str(config.max_length),
        "--chunk-overlap-tokens",
        str(config.chunk_overlap_tokens),
        "--train-batch-size",
        str(config.train_batch_size),
        "--eval-batch-size",
        str(config.eval_batch_size),
        "--gradient-accumulation-steps",
        str(config.gradient_accumulation_steps),
        "--num-epochs",
        str(config.num_epochs),
        "--early-stopping-patience",
        str(config.early_stopping_patience),
        "--mixed-precision",
        config.mixed_precision,
        "--lora-r",
        str(config.lora_r),
        "--lora-alpha",
        str(config.lora_alpha),
        "--lora-dropout",
        str(config.lora_dropout),
        "--random-seed",
        str(config.random_seed),
    ]
    if config.gradient_checkpointing:
        parts.append("--gradient-checkpointing")
    else:
        parts.append("--no-gradient-checkpointing")
    if config.use_lora:
        parts.append("--use-lora")
    else:
        parts.append("--no-use-lora")
    if config.require_gpu:
        parts.append("--require-gpu")
    else:
        parts.append("--no-require-gpu")
    return parts


def build_transformer_command(config: G3LaunchConfig) -> str:
    """Build a quoted transformer command template string for diagnostics/tests."""

    return " ".join(shlex.quote(part) for part in build_transformer_command_parts(config))


def build_preflight_script(*, config: G3LaunchConfig) -> str:
    """Build remote preflight script that fails closed before launch."""

    required_paths = [
        config.frozen_inputs.splits_path,
        config.frozen_inputs.ellipse_train_path,
        config.frozen_inputs.ellipse_test_path,
        config.frozen_inputs.reuse_cv_feature_store_dir,
    ]
    quoted_required_paths = "\n".join(f"  {shlex.quote(path)}" for path in required_paths)
    quoted_approved_base_images = "\n".join(
        f"  {shlex.quote(image)}" for image in config.approved_transformer_base_images
    )
    run_prefix = shlex.quote(config.run_name_prefix)
    repo_root = shlex.quote(config.remote_repo_root)
    container = shlex.quote(config.training_container)
    required_hip_prefix = config.required_hip_version_prefix
    required_torch_prefix = config.required_torch_version_prefix
    required_python_prefix = config.required_python_version_prefix
    canary_precision = config.mixed_precision
    lora_module_check = ""
    if config.use_lora:
        lora_module_check = (
            f"sudo docker exec {container} python - <<'PY'\n"
            "try:\n"
            "    import peft\n"
            "except ModuleNotFoundError:\n"
            "    raise SystemExit('MISSING_MODULE:peft')\n"
            "print('LORA_MODULES_OK')\n"
            "PY\n"
        )
    return (
        "set -euo pipefail\n"
        f"cd {repo_root}\n"
        "test -f pyproject.toml || { echo 'MISSING_PYPROJECT'; exit 1; }\n"
        "while read -r required_path; do\n"
        '  [ -e "$required_path" ] || { echo "MISSING_PATH:$required_path"; exit 1; }\n'
        "done <<'PATHS'\n"
        f"{quoted_required_paths}\n"
        "PATHS\n"
        f"sudo docker ps --format '{{{{.Names}}}}' | grep -Fxq {container} || "
        f"{{ echo 'MISSING_CONTAINER:{config.training_container}'; exit 1; }}\n"
        f"BASE_IMAGE_LABEL=$(sudo docker inspect --format "
        "'{{ index .Config.Labels \"org.huleedu.transformer_train.base_image\" }}' "
        f"{container})\n"
        '[ -n "$BASE_IMAGE_LABEL" ] && [ "$BASE_IMAGE_LABEL" != "<no value>" ] || '
        "{ echo 'MISSING_IMAGE_LABEL:org.huleedu.transformer_train.base_image'; exit 1; }\n"
        "base_image_ok=false\n"
        "while read -r approved_base_image; do\n"
        '  [ "$BASE_IMAGE_LABEL" = "$approved_base_image" ] && base_image_ok=true && break\n'
        "done <<'APPROVED_BASE_IMAGES'\n"
        f"{quoted_approved_base_images}\n"
        "APPROVED_BASE_IMAGES\n"
        'if [ "$base_image_ok" != true ]; then\n'
        '  echo "UNSUPPORTED_BASE_IMAGE:${BASE_IMAGE_LABEL}"\n'
        "  exit 1\n"
        "fi\n"
        'echo "BASE_IMAGE_OK:${BASE_IMAGE_LABEL}"\n'
        f"sudo docker exec {container} python - <<'PY'\n"
        "import platform\n"
        "import torch\n"
        "hip = getattr(torch.version, 'hip', None)\n"
        "if not torch.cuda.is_available() or hip is None:\n"
        "    raise SystemExit('GPU_PREFLIGHT_FAILED')\n"
        f"if not str(hip).startswith({required_hip_prefix!r}):\n"
        "    raise SystemExit(f'UNSUPPORTED_HIP_VERSION:{hip}')\n"
        "torch_version = str(torch.__version__)\n"
        f"if not torch_version.startswith({required_torch_prefix!r}):\n"
        "    raise SystemExit(f'UNSUPPORTED_TORCH_VERSION:{torch_version}')\n"
        "python_version = platform.python_version()\n"
        f"if not python_version.startswith({required_python_prefix!r}):\n"
        "    raise SystemExit(f'UNSUPPORTED_PYTHON_VERSION:{python_version}')\n"
        "print('GPU_PREFLIGHT_OK')\n"
        "print(f'HIP_VERSION:{hip}')\n"
        "print(f'TORCH_VERSION:{torch_version}')\n"
        "print(f'PYTHON_VERSION:{python_version}')\n"
        "PY\n"
        f"sudo docker exec {container} python - <<'PY'\n"
        "import torch\n"
        f"precision_mode = {canary_precision!r}\n"
        "device = torch.device('cuda')\n"
        "use_autocast = False\n"
        "dtype = None\n"
        "if precision_mode == 'bf16':\n"
        "    use_autocast = True\n"
        "    dtype = torch.bfloat16\n"
        "elif precision_mode == 'fp16':\n"
        "    use_autocast = True\n"
        "    dtype = torch.float16\n"
        "elif precision_mode == 'auto':\n"
        "    if torch.cuda.is_bf16_supported():\n"
        "        use_autocast = True\n"
        "        dtype = torch.bfloat16\n"
        "    else:\n"
        "        use_autocast = True\n"
        "        dtype = torch.float16\n"
        "elif precision_mode != 'none':\n"
        "    raise SystemExit(f'UNSUPPORTED_PRECISION_MODE:{precision_mode}')\n"
        "\n"
        "torch.manual_seed(0)\n"
        "model = torch.nn.Sequential(\n"
        "    torch.nn.Linear(64, 32),\n"
        "    torch.nn.GELU(),\n"
        "    torch.nn.Linear(32, 1),\n"
        ").to(device)\n"
        "optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)\n"
        "inputs = torch.randn(8, 64, device=device)\n"
        "targets = torch.randn(8, 1, device=device)\n"
        "optimizer.zero_grad(set_to_none=True)\n"
        "with torch.amp.autocast(device_type='cuda', dtype=dtype, enabled=use_autocast):\n"
        "    predictions = model(inputs)\n"
        "    loss = torch.nn.functional.mse_loss(predictions, targets)\n"
        "if not torch.isfinite(loss):\n"
        "    raise SystemExit('CANARY_NONFINITE_LOSS')\n"
        "use_scaler = dtype == torch.float16\n"
        "scaler = torch.amp.GradScaler('cuda', enabled=use_scaler)\n"
        "if use_scaler:\n"
        "    scaler.scale(loss).backward()\n"
        "    scaler.unscale_(optimizer)\n"
        "    for parameter in model.parameters():\n"
        "        grad = parameter.grad\n"
        "        if grad is None:\n"
        "            continue\n"
        "        if not torch.isfinite(grad).all():\n"
        "            raise SystemExit('CANARY_NONFINITE_GRAD')\n"
        "    scaler.step(optimizer)\n"
        "    scaler.update()\n"
        "else:\n"
        "    loss.backward()\n"
        "    for parameter in model.parameters():\n"
        "        grad = parameter.grad\n"
        "        if grad is None:\n"
        "            continue\n"
        "        if not torch.isfinite(grad).all():\n"
        "            raise SystemExit('CANARY_NONFINITE_GRAD')\n"
        "    optimizer.step()\n"
        "with torch.no_grad():\n"
        "    for parameter in model.parameters():\n"
        "        if not torch.isfinite(parameter).all():\n"
        "            raise SystemExit('CANARY_NONFINITE_PARAM')\n"
        "print('PRECISION_CANARY_OK')\n"
        "PY\n"
        f"sudo docker exec {container} /bin/bash -lc "
        '"NO_COLOR=1 COLUMNS=240 python -m scripts.ml_training.essay_scoring.cli '
        'transformer-finetune --help" >/tmp/g3_transformer_help.txt\n'
        "grep -q -- '--chunk-overlap-tokens' /tmp/g3_transformer_help.txt || "
        "{ echo 'MISSING_FLAG:--chunk-overlap-tokens'; exit 1; }\n"
        "grep -q -- '--require-gpu' /tmp/g3_transformer_help.txt || "
        "{ echo 'MISSING_FLAG:--require-gpu'; exit 1; }\n"
        f"{lora_module_check}"
        f"if /usr/bin/screen -ls 2>/dev/null | grep -q {run_prefix}; then "
        f"echo 'STALE_SCREEN:{config.run_name_prefix}'; exit 1; "
        "fi\n"
        "echo 'PREFLIGHT_OK'\n"
    )


def build_launch_script(*, config: G3LaunchConfig) -> str:
    """Build remote detached launch script for canonical Gate G3 execution."""

    repo_root = shlex.quote(config.remote_repo_root)
    run_prefix = shlex.quote(config.run_name_prefix)
    command_parts = build_transformer_command_parts(config)
    command_parts_lines = "\n".join(
        '  "$RUN_NAME"' if part == RUN_NAME_TEMPLATE_TOKEN else f"  {shlex.quote(part)}"
        for part in command_parts
    )
    return (
        "set -euo pipefail\n"
        f"cd {repo_root}\n"
        "mkdir -p output/essay_scoring\n"
        f"RUN_NAME={run_prefix}_$(date +%Y%m%d_%H%M%S)\n"
        "DRIVER_LOG=output/essay_scoring/${RUN_NAME}.driver.log\n"
        "CMD=(\n"
        f"{command_parts_lines}\n"
        ")\n"
        'CMD_STR="$(printf \'%q \' "${CMD[@]}")"\n'
        '/usr/bin/screen -S "${RUN_NAME}" -dm /bin/bash -lc '
        '"${CMD_STR} 2>&1 | tee ${DRIVER_LOG}"\n'
        "sleep 2\n"
        'if ! /usr/bin/screen -ls | grep -q "${RUN_NAME}"; then\n'
        "  echo 'LAUNCH_FAILED_SCREEN_EXIT'\n"
        '  [ -f "${DRIVER_LOG}" ] && tail -n 80 "${DRIVER_LOG}" || true\n'
        "  exit 1\n"
        "fi\n"
        'echo "RUN_NAME=${RUN_NAME}"\n'
        'echo "DRIVER_LOG=${DRIVER_LOG}"\n'
        "echo 'LAUNCH_OK'\n"
    )


def _parse_key_value_lines(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key and value:
            values[key.strip()] = value.strip()
    return values


def _assert_marker(*, step: str, output: str, marker: str) -> None:
    if marker not in output:
        raise G3LaunchError(f"{step} missing marker '{marker}'. Output:\n{output}")


def _require_success(*, step: str, result: RemoteCommandResult) -> None:
    if result.return_code == 0:
        return
    raise G3LaunchError(
        f"{step} failed with exit code {result.return_code}.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
