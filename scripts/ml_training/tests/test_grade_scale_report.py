from __future__ import annotations

import numpy as np
import pytest

from scripts.ml_training.essay_scoring.dataset import EssayRecord
from scripts.ml_training.essay_scoring.reports.grade_scale_report import generate_grade_scale_report


def _record(record_id: str, *, prompt: str, essay: str) -> EssayRecord:
    return EssayRecord(
        record_id=record_id,
        task_type="1",
        question=prompt,
        essay=essay,
        overall=6.0,
        component_scores={},
    )


def test_generate_grade_scale_report_writes_markdown(tmp_path) -> None:
    records = [
        _record("r1", prompt="P1", essay="A short essay."),
        _record("r2", prompt="P1", essay="Another essay with more words."),
        _record("r3", prompt="P2", essay="Third essay."),
    ]
    y_true = np.array([1.0, 2.0, 2.0], dtype=np.float32)
    y_pred = np.array([1.1, 1.9, 2.2], dtype=np.float32)

    out = tmp_path / "report.md"
    generate_grade_scale_report(
        records,
        y_true,
        y_pred,
        dataset_source="unit-test-dataset",
        min_band=1.0,
        max_band=9.0,
        output_path=out,
    )

    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "Score-Scale Behavior Report" in content
    assert "unit-test-dataset" in content


def test_generate_grade_scale_report_rejects_mismatched_inputs(tmp_path) -> None:
    records = [_record("r1", prompt="P1", essay="Essay.")]
    out = tmp_path / "report.md"

    with pytest.raises(ValueError, match="matching lengths"):
        generate_grade_scale_report(
            records,
            np.array([1.0, 2.0], dtype=np.float32),
            np.array([1.0], dtype=np.float32),
            dataset_source="unit-test-dataset",
            min_band=1.0,
            max_band=9.0,
            output_path=out,
        )
