from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from scripts.cj_experiments_runners.eng5_np.paths import RunnerPaths
from scripts.cj_experiments_runners.eng5_np.system_prompt import build_cj_system_prompt
from scripts.cj_experiments_runners.eng5_np.text_extraction import extract_text

app = typer.Typer(help="Export ENG5 runner assets into a prompt cache benchmark fixture JSON.")


def _load_docs(path: Path, limit: int | None) -> list[dict[str, str]]:
    docs: list[dict[str, str]] = []
    for idx, file_path in enumerate(sorted(path.glob("*.docx"))):
        if limit is not None and idx >= limit:
            break
        docs.append(
            {
                "id": file_path.stem,
                "text": extract_text(file_path),
            }
        )
    return docs


@app.command()
def export(
    output: Path = typer.Option(
        Path("data/eng5_prompt_cache_fixture.json"),
        "--output",
        "-o",
        help="Destination JSON file.",
    ),
    max_anchors: int = typer.Option(12, "--anchors", help="Number of anchors to include"),
    max_students: int = typer.Option(12, "--students", help="Number of students to include"),
) -> None:
    """Extract ENG5 anchor/student essays + prompts into a reusable JSON fixture."""

    repo_root = Path(__file__).resolve().parents[2]
    paths = RunnerPaths.from_repo_root(repo_root)

    anchors = _load_docs(paths.anchor_docs_dir, max_anchors)
    students = _load_docs(paths.student_docs_dir, max_students)

    if not anchors or not students:
        typer.echo("No anchors or students found; ensure ENG5 assets are present.", err=True)
        raise typer.Exit(code=1)

    assessment_context: dict[str, Any] = {
        "student_prompt_text": paths.instructions_path.read_text(encoding="utf-8"),
        "assessment_instructions": paths.prompt_path.read_text(encoding="utf-8"),
        "judge_rubric_text": (
            (paths.role_models_root / "llm_prompt_cj_assessment_eng5.md").read_text(
                encoding="utf-8"
            )
        ),
        "system_prompt": build_cj_system_prompt(),
    }

    fixture = {
        "name": "eng5",
        "assignment_id": "eng5-role-models",
        "assessment_context": assessment_context,
        "anchors": anchors,
        "students": students,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"Wrote ENG5 prompt cache fixture to {output}")


if __name__ == "__main__":
    app()
