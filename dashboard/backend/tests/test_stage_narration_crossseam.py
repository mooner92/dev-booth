"""US-007 — CROSS-SEAM GATE (plan §7 / DD5).

The orchestrator's Canonical Narration Corpus (``core.orchestrator.STAGE_NARRATION``)
must map, body-for-body, onto the dashboard's ``stage_mapper.detect_stage``. This
is the CI-blocking gate that proves the two state machines agree: each corpus
body resolves to EXACTLY its own stage — no higher-stage keyword leakage.
"""
from __future__ import annotations

import pytest

from core.orchestrator import STAGE_NARRATION
from dashboard.backend.services.stage_mapper import STAGES, detect_stage


def test_corpus_has_all_twelve_stages():
    assert sorted(STAGE_NARRATION.keys()) == list(range(1, 13))


@pytest.mark.parametrize("stage_no", list(range(1, 13)))
def test_corpus_body_detects_as_exactly_its_stage(stage_no):
    stage_id, body = STAGE_NARRATION[stage_no]
    detected = detect_stage(body)
    assert detected is not None, f"stage {stage_no} body matched no keyword: {body!r}"
    assert detected == (stage_no, stage_id), (
        f"stage {stage_no} body detected as {detected}, expected ({stage_no}, {stage_id!r}) "
        f"— body: {body!r}"
    )


def test_corpus_stage_ids_match_stage_mapper():
    mapper_ids = {sid for _no, sid, _ko, _en in STAGES}
    for stage_no, (stage_id, _body) in STAGE_NARRATION.items():
        assert stage_id in mapper_ids, (
            f"corpus stage {stage_no} id {stage_id!r} is not a stage_mapper stage_id"
        )


def test_no_corpus_body_leaks_into_a_higher_stage():
    """detect_stage returns the HIGHEST match — so a body must contain no keyword
    from any stage above its own. The exact-equality test above already proves
    this, but assert it explicitly for clarity."""
    for stage_no, (_stage_id, body) in STAGE_NARRATION.items():
        detected = detect_stage(body)
        assert detected is not None
        assert detected[0] <= stage_no, (
            f"stage {stage_no} body leaked up to stage {detected[0]}"
        )
        # and it must not be lower either — it must be exact
        assert detected[0] == stage_no
