"""US-007 — observability: the dashboard derives the right stage from the
orchestrator's narration log (plan §5).

Builds a fixture session whose log holds the orchestrator's Canonical Narration
Corpus markers for stages 1->5, then hits the real FastAPI app via TestClient
and asserts ``GET /api/sessions/<name>/status`` reports ``current_stage == 5``.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from core.orchestrator import STAGE_NARRATION


def _corpus_message(stage_no: int, created_ms: int) -> dict:
    """One orchestrator narration line in AWG log format."""
    _stage_id, body = STAGE_NARRATION[stage_no]
    return {
        "id": f"narration-{stage_no}",
        "kind": "status",
        "from": "orchestrator",
        "to": "all",
        "body": body,
        "refs": {},
        "priority": 30,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created_ms / 1000)),
        "createdAtMs": created_ms,
    }


@pytest.fixture()
def client(make_session):
    # session whose log carries stage 1->5 narration markers, all within the
    # 60s StageTracker conflict window so highest-stage-wins -> stage 5.
    base_ms = int(time.time() * 1000)
    messages = [_corpus_message(n, base_ms + n * 1000) for n in range(1, 6)]
    make_session("obs-test", messages=messages)

    from dashboard.backend.main import app
    with TestClient(app) as c:
        yield c


def test_dashboard_reports_current_stage_from_narration(client):
    resp = client.get("/api/sessions/obs-test/status")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_stage"] == 5, body
    assert body["current_stage_id"] == "implementation", body


def test_dashboard_lists_the_session(client):
    resp = client.get("/api/sessions")
    assert resp.status_code == 200, resp.text
    names = {s["name"] for s in resp.json()}
    assert "obs-test" in names


def test_unknown_session_is_404(client):
    resp = client.get("/api/sessions/no-such-session/status")
    assert resp.status_code == 404
