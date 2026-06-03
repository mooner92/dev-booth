"""POST /api/kanban/boards/{slug}/tasks/{id}/unblock — subprocess fully mocked.

These are unit tests against the FastAPI route. The hermes CLI is mocked at
the subprocess.run boundary in dashboard.backend.routers.kanban so the tests
never touch a real kanban.db.
"""
from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

from dashboard.backend.main import app

client = TestClient(app)

_URL = "/api/kanban/boards/test-board/tasks/t_abc123/unblock"


def _ok_run(*_args, **_kwargs):
    return SimpleNamespace(returncode=0, stdout="Unblocked t_abc123", stderr="")


def _fail_run(*_args, **_kwargs):
    return SimpleNamespace(returncode=1, stdout="", stderr="task not found")


def test_unblock_task_success():
    with mock.patch("dashboard.backend.routers.kanban.subprocess.run", side_effect=_ok_run):
        resp = client.post(_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["task_id"] == "t_abc123"
    assert body["board"] == "test-board"
    assert "Unblocked" in body["message"]


def test_unblock_task_failure():
    with mock.patch("dashboard.backend.routers.kanban.subprocess.run", side_effect=_fail_run):
        resp = client.post(_URL)
    assert resp.status_code == 400
    assert "task not found" in resp.json()["detail"]


def test_unblock_task_timeout():
    with mock.patch(
        "dashboard.backend.routers.kanban.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="hermes", timeout=10),
    ):
        resp = client.post(_URL)
    assert resp.status_code == 504
    assert "타임아웃" in resp.json()["detail"]
