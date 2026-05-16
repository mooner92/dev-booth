"""Village router + service projection tests.

Reuses the same kanban.db fixture shape as test_kanban_reader.py — Village
relies on KanbanReader's CLI/SQLite fallback path, so the deterministic SQLite
fallback is exercised here.
"""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from dashboard.backend.main import app
from dashboard.backend.services import kanban_reader as kr
from dashboard.backend.services import village_status as vs


def _make_board(root, slug: str) -> None:
    board_dir = root / slug
    board_dir.mkdir(parents=True, exist_ok=True)
    db = board_dir / "kanban.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY, title TEXT, body TEXT, assignee TEXT,
            status TEXT, priority INTEGER, workspace_kind TEXT,
            created_at INTEGER, started_at INTEGER, completed_at INTEGER,
            result TEXT
        );
        CREATE TABLE task_comments (
            id INTEGER PRIMARY KEY, task_id TEXT, author TEXT, body TEXT,
            created_at INTEGER
        );
        """
    )
    conn.executemany(
        "INSERT INTO tasks (id,title,assignee,status,priority,workspace_kind,created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        [
            ("t_01", "[demo] fork & clone",     "conductor", "done",    1, "worktree", 1778801400),
            ("t_02", "[demo] orchestrate",      "conductor", "running", 1, "worktree", 1778801410),
            ("t_03", "[demo] structure scan",   "architect", "ready",   1, "worktree", 1778801420),
            ("t_04", "[demo] write tests",      "executor",  "blocked", 1, "worktree", 1778801430),
            ("t_05", "[demo] earlier exec done", "executor", "done",    1, "worktree", 1778801440),
        ],
    )
    conn.commit()
    conn.close()


@pytest.fixture
def boards_root(tmp_path, monkeypatch):
    root = tmp_path / "boards"
    root.mkdir()
    # village_status uses KANBAN_BOARDS_ROOT through kanban_reader; patch both.
    monkeypatch.setattr(kr, "KANBAN_BOARDS_ROOT", root)
    monkeypatch.setattr(vs, "KANBAN_BOARDS_ROOT", root)
    _make_board(root, "demo-board")
    # Force the SQLite fallback (CLI may not exist in CI).
    monkeypatch.setattr(kr.KanbanReader, "_run", staticmethod(lambda *a, **kw: None))
    return root


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ service
def test_get_village_state_shape_and_progress(boards_root):
    state = vs.get_village_state("demo-board")
    assert state["board"] == "demo-board"
    assert state["total"] == 5
    assert state["done"] == 2
    assert state["progress"] == 40  # round(2/5*100)
    assert set(state["agents"]) == {"conductor", "architect", "executor"}


def test_status_mapping_running_executing(boards_root):
    """conductor has a running task → village state 'executing', area 'desk'."""
    state = vs.get_village_state("demo-board")
    conductor = state["agents"]["conductor"]
    assert conductor["task_status"] == "running"
    assert conductor["state"] == "executing"
    assert conductor["area"] == "desk"
    # slug prefix stripped
    assert conductor["task"] == "orchestrate"


def test_picker_skips_ready_tasks(boards_root):
    """The picker prefers running > blocked > done. 'ready' (queued) is skipped,
    so an agent whose only task is ready shows as idle in the breakroom."""
    state = vs.get_village_state("demo-board")
    architect = state["agents"]["architect"]
    assert architect["task_status"] == "idle"
    assert architect["state"] == "idle"
    assert architect["area"] == "breakroom"


def test_status_mapping_blocked_error(boards_root):
    """executor has blocked + done — picker prefers blocked → village 'error'."""
    state = vs.get_village_state("demo-board")
    executor = state["agents"]["executor"]
    assert executor["task_status"] == "blocked"
    assert executor["state"] == "error"
    assert executor["area"] == "breakroom"
    assert executor["task"] == "write tests"


def test_empty_board_returns_empty_shape(tmp_path, monkeypatch):
    root = tmp_path / "boards"
    root.mkdir()
    monkeypatch.setattr(kr, "KANBAN_BOARDS_ROOT", root)
    monkeypatch.setattr(vs, "KANBAN_BOARDS_ROOT", root)
    state = vs.get_village_state("does-not-exist")
    assert state["board"] == "does-not-exist"
    assert state["total"] == 0
    assert state["done"] == 0
    assert state["progress"] == 0
    for name in ("conductor", "architect", "executor"):
        a = state["agents"][name]
        assert a["state"] == "idle"
        assert a["area"] == "breakroom"


def test_list_village_boards_filters_to_kanban_db(tmp_path, monkeypatch):
    root = tmp_path / "boards"
    root.mkdir()
    (root / "with-db").mkdir()
    (root / "with-db" / "kanban.db").touch()
    (root / "no-db").mkdir()  # no kanban.db
    (root / "stray.txt").write_text("not a board")
    monkeypatch.setattr(kr, "KANBAN_BOARDS_ROOT", root)
    monkeypatch.setattr(vs, "KANBAN_BOARDS_ROOT", root)
    assert vs.list_village_boards() == ["with-db"]


# ------------------------------------------------------------------ router
def test_get_boards_endpoint(boards_root, client):
    resp = client.get("/api/village/boards")
    assert resp.status_code == 200
    body = resp.json()
    assert "boards" in body
    assert "demo-board" in body["boards"]


def test_get_state_endpoint(boards_root, client):
    resp = client.get("/api/village/boards/demo-board/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["board"] == "demo-board"
    assert body["total"] == 5
    assert body["done"] == 2
    assert set(body["agents"]) == {"conductor", "architect", "executor"}
    assert body["agents"]["conductor"]["state"] == "executing"


def test_get_state_missing_board_returns_empty_not_404(boards_root, client):
    resp = client.get("/api/village/boards/no-such-board/state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["progress"] == 0
