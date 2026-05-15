"""Cross-seam gate (plan v4 DD5/§7) — the keyword-collision-prevention test.

The orchestration layer (``core/scenario.py``) and the dashboard's
``stage_mapper`` are two independently-evolving modules. This CI-blocking gate
proves they stay in sync: every ``STAGE_NARRATION`` body must (a) be detectable
by the dashboard's ``detect_stage`` and (b) never trip a *higher* stage than the
one before it — so the dashboard's derived stage progresses monotonically as the
12-stage DAG advances and never regresses.

Note: STAGE_NARRATION is intentionally a coarse 12->~8 mapping onto
stage_mapper's scale (several Dev-Booth stages share one dashboard stage). The
invariant under test is *monotonic non-decreasing*, not 1:1 equality.
"""
from __future__ import annotations

import pytest

from core.scenario import STAGE_DAG, STAGE_NARRATION
from dashboard.backend.services.stage_mapper import detect_stage


def test_corpus_has_all_twelve_stages():
    assert sorted(STAGE_NARRATION.keys()) == list(range(1, 13))
    assert len(STAGE_DAG) == 12


@pytest.mark.parametrize("stage_no", list(range(1, 13)))
def test_every_narration_body_detects_a_stage(stage_no):
    body = STAGE_NARRATION[stage_no]
    detected = detect_stage(body)
    assert detected is not None, (
        f"stage {stage_no} narration matched no stage_mapper keyword: {body!r}"
    )


def test_detected_stages_are_monotonic_non_decreasing():
    """The dashboard's derived stage must never go backwards as the DAG advances."""
    prev = 0
    trail = []
    for stage_no in range(1, 13):
        detected = detect_stage(STAGE_NARRATION[stage_no])
        assert detected is not None
        s = detected[0]
        trail.append(s)
        assert s >= prev, (
            f"stage {stage_no} regresses: detect_stage -> {s}, previous was {prev}. "
            f"trail so far: {trail}"
        )
        prev = s


def test_first_and_last_anchor_correctly():
    """Stage 1 must read as repo_clone-era, stage 12 as pr_merged-era."""
    assert detect_stage(STAGE_NARRATION[1])[0] == 1
    assert detect_stage(STAGE_NARRATION[12])[0] == 12
