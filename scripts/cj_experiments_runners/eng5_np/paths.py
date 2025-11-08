"""Filesystem path helpers for ENG5 NP runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunnerPaths:
    """Concrete filesystem locations for ENG5 NP source assets."""

    repo_root: Path
    role_models_root: Path
    instructions_path: Path
    prompt_path: Path
    anchors_csv: Path
    anchors_xlsx: Path
    anchor_docs_dir: Path
    student_docs_dir: Path
    schema_path: Path
    artefact_output_dir: Path

    @classmethod
    def from_repo_root(cls, repo_root: Path) -> "RunnerPaths":
        role_models_root = repo_root / "test_uploads" / "ANCHOR ESSAYS" / "ROLE_MODELS_ENG5_NP_2016"
        return cls(
            repo_root=repo_root,
            role_models_root=role_models_root,
            instructions_path=role_models_root / "eng5_np_vt_2017_essay_instruction.md",
            prompt_path=role_models_root / "llm_prompt_cj_assessment_eng5.md",
            anchors_csv=role_models_root / "ANCHOR_ESSAYS_BAYESIAN_INFERENCE_DATA.csv",
            anchors_xlsx=role_models_root / "ANCHOR_ESSAYS_BAYESIAN_INFERENCE_DATA.xlsx",
            anchor_docs_dir=role_models_root / "anchor_essays",
            student_docs_dir=role_models_root / "student_essays",
            schema_path=(
                repo_root / "Documentation" / "schemas" / "eng5_np" / "assessment_run.schema.json"
            ),
            artefact_output_dir=repo_root / ".claude" / "research" / "data" / "eng5_np_2016",
        )
