"""Tests for POST /api/sessions/start and GET /api/github/status."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.backend.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ /sessions/start

def test_post_sessions_start_happy_path(tmp_path: Path, monkeypatch, client):
    """Happy path: valid slug, no existing dir → 200 + correct body shape."""
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    monkeypatch.setenv("DEVBOOTH_SESSIONS_ROOT", str(sessions_root))

    # Prevent the background task from actually running subprocess
    monkeypatch.setattr(
        "dashboard.backend.routers.sessions._run_session_seed",
        lambda *args, **kwargs: None,
    )

    resp = client.post("/api/sessions/start", json={
        "session_name": "my-test-session",
        "repo_url": "https://github.com/example/repo",
        "goal": "테스트 목표",
        "mode": "dryrun",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_name"] == "my-test-session"
    assert body["status"] == "starting"


def test_post_sessions_start_duplicate_409(tmp_path: Path, monkeypatch, client):
    """Duplicate session dir → 409."""
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    (sessions_root / "existing-session").mkdir()
    monkeypatch.setenv("DEVBOOTH_SESSIONS_ROOT", str(sessions_root))

    monkeypatch.setattr(
        "dashboard.backend.routers.sessions._run_session_seed",
        lambda *args, **kwargs: None,
    )

    resp = client.post("/api/sessions/start", json={
        "session_name": "existing-session",
        "repo_url": "https://github.com/example/repo",
    })
    assert resp.status_code == 409


def test_post_sessions_start_invalid_slug_400(tmp_path: Path, monkeypatch, client):
    """Invalid slug (special chars) → 400."""
    sessions_root = tmp_path / "sessions"
    sessions_root.mkdir()
    monkeypatch.setenv("DEVBOOTH_SESSIONS_ROOT", str(sessions_root))

    resp = client.post("/api/sessions/start", json={
        "session_name": "bad name!@#",
        "repo_url": "https://github.com/example/repo",
    })
    assert resp.status_code == 400


# ------------------------------------------------------------------ /github/status

def test_get_github_status_logged_in(monkeypatch, client):
    """subprocess returns CrownClownCrowd in output → logged_in True."""
    import subprocess as _sp

    class _FakeResult:
        stdout = "Logged in to github.com as CrownClownCrowd\n"
        stderr = ""

    monkeypatch.setattr(_sp, "run", lambda *a, **kw: _FakeResult())

    resp = client.get("/api/github/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["logged_in"] is True
    assert body["account"] == "CrownClownCrowd"
    assert body["target"] == "mooner92"


def test_get_github_status_failure(monkeypatch, client):
    """subprocess raises OSError → logged_in False, graceful response."""
    import subprocess as _sp

    monkeypatch.setattr(_sp, "run", lambda *a, **kw: (_ for _ in ()).throw(OSError("gh not found")))

    resp = client.get("/api/github/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["logged_in"] is False
    assert body["account"] is None
    assert body["target"] == "mooner92"
