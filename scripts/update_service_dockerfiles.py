import json
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[1]

COMMON_COPY = """
COPY pyproject.toml pdm.lock ./
COPY libs/common_core/pyproject.toml libs/common_core/pyproject.toml
COPY libs/common_core/src/ libs/common_core/src/
COPY libs/huleedu_service_libs/pyproject.toml libs/huleedu_service_libs/pyproject.toml
COPY libs/huleedu_service_libs/src/ libs/huleedu_service_libs/src/
COPY libs/huleedu_nlp_shared/pyproject.toml libs/huleedu_nlp_shared/pyproject.toml
COPY libs/huleedu_nlp_shared/src/ libs/huleedu_nlp_shared/src/
COPY services/api_gateway_service/pyproject.toml services/api_gateway_service/pyproject.toml
COPY services/batch_conductor_service/pyproject.toml services/batch_conductor_service/pyproject.toml
COPY services/batch_orchestrator_service/pyproject.toml services/batch_orchestrator_service/pyproject.toml
COPY services/cj_assessment_service/pyproject.toml services/cj_assessment_service/pyproject.toml
COPY services/class_management_service/pyproject.toml services/class_management_service/pyproject.toml
COPY services/content_service/pyproject.toml services/content_service/pyproject.toml
COPY services/email_service/pyproject.toml services/email_service/pyproject.toml
COPY services/entitlements_service/pyproject.toml services/entitlements_service/pyproject.toml
COPY services/essay_lifecycle_service/pyproject.toml services/essay_lifecycle_service/pyproject.toml
COPY services/file_service/pyproject.toml services/file_service/pyproject.toml
COPY services/identity_service/pyproject.toml services/identity_service/pyproject.toml
COPY services/language_tool_service/pyproject.toml services/language_tool_service/pyproject.toml
COPY services/llm_provider_service/pyproject.toml services/llm_provider_service/pyproject.toml
COPY services/nlp_service/pyproject.toml services/nlp_service/pyproject.toml
COPY services/result_aggregator_service/pyproject.toml services/result_aggregator_service/pyproject.toml
COPY services/spellchecker_service/pyproject.toml services/spellchecker_service/pyproject.toml
COPY services/websocket_service/pyproject.toml services/websocket_service/pyproject.toml
""".strip()


SERVICES = {
    "api_gateway_service": {
        "cmd_dev": [
            "python","-m","uvicorn",
            "services.api_gateway_service.app.main:app","--host","0.0.0.0","--port","8080"
        ],
    },
    "batch_conductor_service": {
        "cmd_dev": [
            "python","-m","hypercorn",
            "services.batch_conductor_service.app:app","--bind","0.0.0.0:4002","--worker-class","asyncio"
        ],
    },
    "batch_orchestrator_service": {
        "cmd_dev": [
            "python","services/batch_orchestrator_service/app.py"
        ],
    },
    "cj_assessment_service": {
        "cmd_dev": [
            "python","services/cj_assessment_service/app.py"
        ],
    },
    "class_management_service": {
        "cmd_dev": [
            "python","services/class_management_service/app.py"
        ],
    },
    "content_service": {
        "cmd_dev": [
            "python","-m","hypercorn",
            "services.content_service.app:app","--bind","0.0.0.0:8000","--workers","4","--worker-class","asyncio"
        ],
        "post_copy_dev": ["RUN mkdir -p /data/huleedu_content_store"],
        "post_copy_prod": ["RUN mkdir -p /data/huleedu_content_store"],
        "post_chown_dev": ["RUN chown -R appuser:appuser /data/huleedu_content_store"],
        "post_chown_prod": ["RUN chown -R appuser:appuser /data/huleedu_content_store"],
        "extra_env": {"CONTENT_STORE_ROOT_PATH": "/data/huleedu_content_store"},
    },
    "email_service": {
        "cmd_dev": [
            "python","-m","hypercorn",
            "services.email_service.app:app","--bind","0.0.0.0:8080"
        ],
    },
    "entitlements_service": {
        "cmd_dev": [
            "python","-m","hypercorn",
            "services.entitlements_service.app:app","--bind","0.0.0.0:8083"
        ],
    },
    "essay_lifecycle_service": {
        "cmd_dev": [
            "python","services/essay_lifecycle_service/app.py"
        ],
    },
    "file_service": {
        "cmd_dev": [
            "python","services/file_service/app.py"
        ],
        "extra_packages": ["libmagic1", "pandoc"],
    },
    "identity_service": {
        "cmd_dev": [
            "python","-m","hypercorn",
            "services.identity_service.app:app","--bind","0.0.0.0:7005"
        ],
    },
    "language_tool_service": {
        "cmd_dev": [
            "python","services/language_tool_service/app.py"
        ],
        "cmd_prod": [
            "python","-m","hypercorn",
            "services.language_tool_service.app:app","--config",
            "python:services.language_tool_service.hypercorn_config"
        ],
        "extra_packages": ["wget", "unzip", "openjdk-21-jre-headless"],
        "extra_base": [
            "RUN mkdir -p /app/languagetool && \\",
            "    cd /app/languagetool && \\",
            "    wget -q https://languagetool.org/download/LanguageTool-stable.zip && \\",
            "    unzip -q LanguageTool-stable.zip && \\",
            "    mv LanguageTool-*/* . && \\",
            "    rm -rf LanguageTool-* LanguageTool-stable.zip",
        ],
    },
    "llm_provider_service": {
        "cmd_dev": [
            "python","services/llm_provider_service/app.py"
        ],
    },
    "result_aggregator_service": {
        "cmd_dev": [
            "python","services/result_aggregator_service/app.py"
        ],
    },
    "spellchecker_service": {
        "cmd_dev": [
            "python","services/spellchecker_service/app.py"
        ],
    },
    "websocket_service": {
        "cmd_dev": [
            "python","-m","uvicorn",
            "services.websocket_service.main:app","--host","0.0.0.0","--port","8080"
        ],
    },
}

def render_env(extra_env=None):
    lines = [
        "PYTHONUNBUFFERED=1",
        "PYTHONDONTWRITEBYTECODE=1",
        "PDM_USE_VENV=false",
        "PDM_IGNORE_ACTIVE_VENV=1",
        "PROJECT_ROOT=/app",
        "PYTHONPATH=/app",
        "ENV_TYPE=docker",
    ]
    if extra_env:
        for key, value in extra_env.items():
            lines.append(f"{key}={value}")
    joined = " \\\n    ".join(lines)
    return f"ENV {joined}"


def render_extra_packages(extra_packages: list[str] | None) -> str:
    if not extra_packages:
        return ""
    lines = [
        "RUN apt-get update && apt-get install -y \\",
        "    --no-install-recommends \\",
    ]
    lines.extend(f"    {pkg} \\" for pkg in extra_packages)
    lines.append("    && rm -rf /var/lib/apt/lists/*")
    return "\n".join(lines) + "\n"



def format_cmd(cmd):
    if cmd is None:
        return None
    full = ["pdm", "run", "-p", "/app", *cmd]
    return json.dumps(full)


def block(text: str) -> str:
    return f"{text}\n" if text else ""


def write_files():
    for service, meta in SERVICES.items():
        service_dir = REPO_ROOT / "services" / service
        if not service_dir.exists():
            continue
        env_block = render_env(meta.get("extra_env"))
        extra_packages_block = render_extra_packages(meta.get("extra_packages"))
        extra_base_lines = meta.get("extra_base", [])
        extra_base = ""
        if extra_base_lines:
            extra_base = "\n".join(extra_base_lines).strip() + "\n"
        cmd_dev = format_cmd(meta.get("cmd_dev"))
        cmd_prod = format_cmd(meta.get("cmd_prod", meta.get("cmd_dev")))
        post_copy_dev = "\n".join(meta.get("post_copy_dev", []))
        post_copy_prod = "\n".join(meta.get("post_copy_prod", []))
        post_chown_dev = "\n".join(meta.get("post_chown_dev", []))
        post_chown_prod = "\n".join(meta.get("post_chown_prod", []))
        base_common = (
            "ARG DEPS_IMAGE=huledu-deps:dev\n"
            "FROM ${DEPS_IMAGE} AS base\n\n"
            f"{env_block}\n\n"
            f"{extra_packages_block}"
            f"{extra_base}WORKDIR /app\n\n"
        )

        dev_content = (
            f"# Auto-generated development Dockerfile for {service}\n"
            f"{base_common}"
            "FROM base AS development\n"
            f"COPY --chown=appuser:appuser services/{service}/ /app/services/{service}/\n"
            f"{block(post_copy_dev)}"
            f"{block(post_chown_dev)}"
            "USER appuser\n"
            "WORKDIR /app\n"
            f"CMD {cmd_dev}\n"
        )

        prod_content = (
            f"# Auto-generated production Dockerfile for {service}\n"
            f"{base_common}"
            "FROM base AS production\n"
            f"COPY --chown=appuser:appuser services/{service}/ /app/services/{service}/\n"
            f"{block(post_copy_prod)}"
            f"{block(post_chown_prod)}"
            "USER appuser\n"
            "WORKDIR /app\n"
            f"CMD {cmd_prod}\n"
        )

        (service_dir / "Dockerfile.dev").write_text(dev_content)
        (service_dir / "Dockerfile").write_text(prod_content)


if __name__ == "__main__":
    write_files()
