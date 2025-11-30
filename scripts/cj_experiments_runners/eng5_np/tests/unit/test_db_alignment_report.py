"""Unit tests for db_alignment_report helper functions.

These tests exercise the pure helpers used to reconstruct ENG5 alignment
metrics from CJ database rows, plus a small async smoke test for the
end-to-end generate_db_alignment_report entry point with stubbed DB hooks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.cj_experiments_runners.eng5_np import db_alignment_report as mod
from scripts.cj_experiments_runners.eng5_np.utils import make_anchor_key


class TestBuildAnchorGradeAndFilenameMaps:
    """Tests for _build_anchor_grade_and_filename_maps."""

    def test_builds_grade_and_filename_maps_from_anchor_dir(self, tmp_path: Path):
        """Anchor directory yields grade and filename maps keyed by anchor key."""
        anchor_dir = tmp_path / "anchors"
        anchor_dir.mkdir()

        file_a = anchor_dir / "anchor_essay_eng_5_17_vt_001_A.docx"
        file_b = anchor_dir / "anchor_essay_eng_5_17_vt_002_B.docx"
        file_a.write_text("dummy A")
        file_b.write_text("dummy B")

        grade_map, filename_map = mod._build_anchor_grade_and_filename_maps(anchor_dir)

        key_a = make_anchor_key(file_a.stem)
        key_b = make_anchor_key(file_b.stem)

        assert grade_map[key_a] == "A"
        assert grade_map[key_b] == "B"
        assert filename_map[key_a] == file_a.name
        assert filename_map[key_b] == file_b.name


class TestBuildBtSummaryFromDb:
    """Tests for _build_bt_summary_from_db."""

    def test_assigns_ranks_by_descending_score(self):
        """Higher BT score gets lower (better) rank."""
        bt_rows: list[dict[str, Any]] = [
            {
                "els_essay_id": "essay_low",
                "current_bt_score": -1.0,
                "current_bt_se": 0.2,
                "comparison_count": 5,
                "is_anchor": False,
            },
            {
                "els_essay_id": "essay_high",
                "current_bt_score": 2.0,
                "current_bt_se": 0.1,
                "comparison_count": 7,
                "is_anchor": True,
            },
        ]

        summary = mod._build_bt_summary_from_db(bt_rows)

        assert len(summary) == 2
        assert summary[0]["essay_id"] == "essay_high"
        assert summary[0]["rank"] == 1
        assert summary[1]["essay_id"] == "essay_low"
        assert summary[1]["rank"] == 2


class TestBuildLlmComparisonsFromDb:
    """Tests for _build_llm_comparisons_from_db."""

    def test_only_successful_comparisons_included(self):
        """Only rows with winner essay_a/essay_b are converted."""
        comparisons = [
            {
                "id": 1,
                "essay_a_els_id": "A1",
                "essay_b_els_id": "B1",
                "winner": "essay_a",
                "confidence": 3.0,
                "justification": "A1 better",
            },
            {
                "id": 2,
                "essay_a_els_id": "A2",
                "essay_b_els_id": "B2",
                "winner": "essay_b",
                "confidence": 4.0,
                "justification": "B2 better",
            },
            {
                "id": 3,
                "essay_a_els_id": "A3",
                "essay_b_els_id": "B3",
                "winner": None,
                "confidence": None,
                "justification": None,
            },
        ]

        records = mod._build_llm_comparisons_from_db(comparisons)

        assert len(records) == 2
        # First record: essay_a wins
        rec1 = records[0]
        assert rec1["winner_id"] == "A1"
        assert rec1["loser_id"] == "B1"
        assert rec1["status"] == "succeeded"
        # Second record: essay_b wins
        rec2 = records[1]
        assert rec2["winner_id"] == "B2"
        assert rec2["loser_id"] == "A2"


@pytest.mark.asyncio
async def test_generate_db_alignment_report_smoke(monkeypatch, tmp_path: Path):
    """Smoke test: end-to-end generate_db_alignment_report with stubbed DB.

    This avoids real DB access by stubbing connect/get_* helpers and verifies
    that a markdown report is produced with expected sections.
    """

    class DummyConn:
        async def close(self) -> None:  # pragma: no cover - trivial
            return None

    async def fake_connect_to_db() -> DummyConn:
        return DummyConn()

    async def fake_get_batch_info(conn: DummyConn, batch_identifier: str | int) -> dict[str, Any]:
        return {"id": 1, "bos_batch_id": "test-batch"}

    async def fake_get_comparison_results(
        conn: DummyConn, cj_batch_id: int
    ) -> list[dict[str, Any]]:
        # Build IDs that map cleanly onto generated anchor keys.
        return [
            {
                "id": 1,
                "essay_a_els_id": "student::ANCHOR1_A",
                "essay_b_els_id": "student::ANCHOR2_C",
                "winner": "essay_a",
                "confidence": 3.5,
                "justification": "ANCHOR1 better",
                "request_correlation_id": None,
                "submitted_at": None,
                "completed_at": None,
                "error_code": None,
            }
        ]

    async def fake_get_bt_stats(conn: DummyConn, cj_batch_id: int) -> list[dict[str, Any]]:
        return [
            {
                "els_essay_id": "student::ANCHOR1_A",
                "current_bt_score": 1.0,
                "current_bt_se": 0.1,
                "comparison_count": 1,
                "is_anchor": False,
                "processing_metadata": None,
            },
            {
                "els_essay_id": "student::ANCHOR2_C",
                "current_bt_score": -1.0,
                "current_bt_se": 0.2,
                "comparison_count": 1,
                "is_anchor": False,
                "processing_metadata": None,
            },
        ]

    # Patch DB helpers inside the module under test
    monkeypatch.setattr(mod, "connect_to_db", fake_connect_to_db)
    monkeypatch.setattr(mod, "get_batch_info", fake_get_batch_info)
    monkeypatch.setattr(mod, "get_comparison_results", fake_get_comparison_results)
    monkeypatch.setattr(mod, "get_bradley_terry_stats", fake_get_bt_stats)

    # Create a small anchor directory that matches the fake IDs
    anchor_dir = tmp_path / "anchors"
    anchor_dir.mkdir()
    (anchor_dir / "ANCHOR1_A.docx").write_text("anchor 1")
    (anchor_dir / "ANCHOR2_C.docx").write_text("anchor 2")

    output_dir = tmp_path / "out"
    summary_path, diag_path = await mod.generate_db_alignment_report(
        cj_batch_id=1,
        bos_batch_id=None,
        anchor_dir=anchor_dir,
        output_dir=output_dir,
    )

    assert summary_path.exists()
    assert diag_path.exists()
    content = summary_path.read_text(encoding="utf-8")
    # Basic sanity checks on report structure
    assert "Anchor Alignment Report" in content
    assert "## Summary Metrics" in content
    assert "## Per-Anchor Results" in content
    assert "ANCHOR1_A.docx" in content or "ANCHOR1_A.DOCX" in content
