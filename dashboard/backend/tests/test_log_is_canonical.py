"""US-007 — P1: the dashboard's canonical signal is log/ + queues/ ONLY.

``status.json`` is a user-mandated operator artifact written by the orchestrator
(``_write_status``). It must NOT be a dashboard input: the dashboard derives
state purely from ``<session>/log/messages.jsonl`` + ``<session>/queues/``.
This proves the orchestrator could write any status.json and the dashboard's
derived status is unaffected.
"""
from __future__ import annotations

import json
import time

from core.orchestrator import STAGE_NARRATION
from dashboard.backend.services import session_layout
from dashboard.backend.routers.sessions import _build_status


def _corpus_message(stage_no: int, created_ms: int) -> dict:
    _sid, body = STAGE_NARRATION[stage_no]
    return {
        "id": f"n-{stage_no}", "kind": "status", "from": "orchestrator", "to": "all",
        "body": body, "refs": {}, "priority": 30,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(created_ms / 1000)),
        "createdAtMs": created_ms,
    }


def test_session_layout_exposes_no_status_json_path(make_session):
    make_session("canon-test")
    layout = session_layout.resolve("canon-test")
    # the layout's filesystem surface is log/ + queues/ — never status.json
    assert layout.log_path.name == "messages.jsonl"
    assert layout.log_path.parent.name == "log"
    assert layout.queue_root.name == "queues"
    for value in vars(layout).values():
        assert "status.json" not in str(value), (
            f"SessionLayout must not reference status.json — found in {value!r}"
        )


def test_build_status_ignores_status_json_on_disk(make_session):
    base_ms = int(time.time() * 1000)
    messages = [_corpus_message(n, base_ms + n * 1000) for n in range(1, 4)]
    session_root = make_session("canon-test", messages=messages)

    layout = session_layout.resolve("canon-test")
    before = _build_status(layout)

    # the orchestrator drops a status.json claiming a totally different stage
    (session_root / "status.json").write_text(
        json.dumps({
            "session": "canon-test", "status": "completed", "current_step": 99,
            "current_agent": "bogus", "repo_url": "", "repo_name": "",
            "branch": "x", "started_at": "", "last_commit": {}, "test_results": {},
        }),
        encoding="utf-8",
    )
    after = _build_status(layout)

    # the dashboard never read status.json — derived status is byte-identical
    assert before == after
    assert after.current_stage == 3, "stage derives from the log, not status.json"
    assert after.current_stage != 99


def test_log_path_is_the_only_log_surface(make_session):
    session_root = make_session("canon-test")
    layout = session_layout.resolve("canon-test")
    assert layout.log_path == session_root / "log" / "messages.jsonl"
