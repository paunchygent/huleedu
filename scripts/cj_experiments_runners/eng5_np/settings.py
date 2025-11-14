"""Runner configuration objects for ENG5 NP CLI."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from common_core.domain_enums import CourseCode, Language
from common_core.events.cj_assessment_events import LLMConfigOverrides


class RunnerMode(str, Enum):
    """CLI operating modes."""

    PLAN = "plan"
    DRY_RUN = "dry-run"
    EXECUTE = "execute"


@dataclass
class RunnerSettings:
    assignment_id: uuid.UUID
    course_id: uuid.UUID
    grade_scale: str
    mode: RunnerMode
    use_kafka: bool
    output_dir: Path
    runner_version: str
    git_sha: str
    batch_uuid: uuid.UUID
    batch_id: str
    user_id: str
    org_id: str | None
    course_code: CourseCode
    language: Language
    correlation_id: uuid.UUID
    kafka_bootstrap: str
    kafka_client_id: str
    content_service_url: str
    cj_service_url: str | None = None
    llm_overrides: LLMConfigOverrides | None = None
    max_comparisons: int | None = None
    await_completion: bool = False
    completion_timeout: float = 1800.0
