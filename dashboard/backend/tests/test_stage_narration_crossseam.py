"""Cross-seam gate (v6) — the keyword-collision-prevention test.

The orchestration layer (``core/scenario.py``) and the dashboard's
``stage_mapper`` are two independently-evolving modules. v6's 21-stage micro
DAG fans the v5 12-stage flow through two TASK iterations, so the *strict
monotonic* invariant that held for v5 no longer applies — TASK-2's
implementation legitimately revisits the ``implementation`` dashboard stage
after TASK-1 reached ``tests_passed``.

What we still gate:
  1. STAGE_NARRATION covers every stage in STAGE_DAG.
  2. Every narration body resolves to a non-None dashboard stage.
  3. Stage 1 anchors to ``repo_clone`` and the final stage to ``pr_merged``.
  4. The *first TASK iteration* (stages 1..15) is monotonic non-decreasing.
"""
from __future__ import annotations

import pytest

from core.scenario import STAGE_DAG, STAGE_NARRATION
from dashboard.backend.services.stage_mapper import detect_stage


def test_corpus_covers_every_stage_in_dag():
    assert sorted(STAGE_NARRATION.keys()) == sorted(s.stage for s in STAGE_DAG)
    assert len(STAGE_DAG) == 21


@pytest.mark.parametrize("stage_no", sorted(STAGE_NARRATION.keys()))
def test_every_narration_body_detects_a_stage(stage_no):
    body = STAGE_NARRATION[stage_no]
    detected = detect_stage(body)
    assert detected is not None, (
        f"stage {stage_no} narration matched no stage_mapper keyword: {body!r}"
    )


def test_first_iteration_is_monotonic_non_decreasing():
    """Stages 1..15 (prep → analysis → plan → feature_branch → TASK-1 cycle)
    must monotonically advance — that's the v5 invariant we still want."""
    prev = 0
    trail = []
    for stage_no in range(1, 16):
        detected = detect_stage(STAGE_NARRATION[stage_no])
        assert detected is not None
        s = detected[0]
        trail.append(s)
        assert s >= prev, (
            f"stage {stage_no} regresses inside first TASK iteration: "
            f"detect_stage -> {s}, previous was {prev}. trail: {trail}"
        )
        prev = s


def test_first_and_last_anchor_correctly():
    """Stage 1 reads as repo_clone-era, the final stage as pr_merged-era."""
    final_stage = max(STAGE_NARRATION.keys())
    assert detect_stage(STAGE_NARRATION[1])[0] == 1
    assert detect_stage(STAGE_NARRATION[final_stage])[0] == 12
