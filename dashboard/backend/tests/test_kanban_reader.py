"""Phase 6 — KanbanReader + /api/kanban routes (A3-lite).

Exercises the SQLite fallback path (deterministic) against a fixture kanban.db
shaped like the real 6-table schema, and the REST routes via TestClient.
"""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from dashboard.backend.services import kanban_reader as kr
from dashboard.backend.services.kanban_reader import KanbanReader


def _make_board(root, slug: str) -> None:
    """Create a fixture kanban.db under <root>/<slug>/kanban.db."""
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
            ("t_01", "fork & clone", "openclaw", "done", 1, "worktree", 1778801400),
            ("t_02", "initial scan", "openclaw", "running", 1, "worktree", 1778801410),
            ("t_03", "structure analysis", "hermes-a", "ready", 1, "worktree", 1778801420),
            ("t_09", "code review", "hermes-a", "blocked", 1, "worktree", 1778801490),
        ],
    )
    conn.executemany(
        "INSERT INTO task_comments (id,task_id,author,body,created_at) VALUES (?,?,?,?,?)",
        [
            (1, "t_02", "openclaw", "@hermes-a 구조 분석 시작해주세요", 1778801411),
            (2, "t_02", "hermes-a", "확인했습니다", 1778801412),
        ],
    )
    conn.commit()
    conn.close()


@pytest.fixture
def boards_root(tmp_path, monkeypatch):
    root = tmp_path / "boards"
    root.mkdir()
    monkeypatch.setattr(kr, "KANBAN_BOARDS_ROOT", root)
    # patch the router module's imported symbol too
    from dashboard.backend.routers import kanban as kanban_router
    monkeypatch.setattr(kanban_router, "KANBAN_BOARDS_ROOT", root)
    _make_board(root, "demo-board")
    return root


# ----------------------------------------------------------- KanbanReader
def test_reader_exists_flag(boards_root):
    assert KanbanReader("demo-board").exists is True
    assert KanbanReader("no-such-board").exists is False


def test_list_tasks_sqlite_fallback(boards_root, monkeypatch):
    # force the SQLite path by making the CLI return None
    monkeypatch.setattr(KanbanReader, "_run", staticmethod(lambda *a: None))
    tasks = KanbanReader("demo-board").list_tasks()
    assert [t["id"] for t in tasks] == ["t_01", "t_02", "t_03", "t_09"]
    assert tasks[0]["assignee"] == "openclaw"
    assert tasks[3]["status"] == "blocked"


def test_list_tasks_status_filter(boards_root, monkeypatch):
    monkeypatch.setattr(KanbanReader, "_run", staticmethod(lambda *a: None))
    running = KanbanReader("demo-board").list_tasks(status="running")
    assert len(running) == 1 and running[0]["id"] == "t_02"


def test_board_stats(boards_root):
    stats = KanbanReader("demo-board").get_board_stats()
    assert stats["done"] == 1
    assert stats["running"] == 1
    assert stats["ready"] == 1
    assert stats["blocked"] == 1
    assert stats["todo"] == 0


def test_get_comments_sqlite_fallback(boards_root, monkeypatch):
    monkeypatch.setattr(KanbanReader, "_run", staticmethod(lambda *a: None))
    comments = KanbanReader("demo-board").get_comments("t_02")
    assert [c["author"] for c in comments] == ["openclaw", "hermes-a"]


# ----------------------------------------------------------- REST routes
@pytest.fixture
def client(boards_root):
    from dashboard.backend.main import app
    with TestClient(app) as c:
        yield c


def test_route_boards(client):
    resp = client.get("/api/kanban/boards")
    assert resp.status_code == 200
    assert {"slug": "demo-board"} in resp.json()["boards"]


def test_route_tasks(client, monkeypatch):
    monkeypatch.setattr(KanbanReader, "_run", staticmethod(lambda *a: None))
    resp = client.get("/api/kanban/boards/demo-board/tasks")
    assert resp.status_code == 200
    assert len(resp.json()["tasks"]) == 4


def test_route_tasks_unknown_board_404(client):
    assert client.get("/api/kanban/boards/ghost/tasks").status_code == 404


def test_route_stats(client):
    resp = client.get("/api/kanban/boards/demo-board/stats")
    assert resp.status_code == 200
    assert resp.json()["done"] == 1


def test_route_comments(client, monkeypatch):
    monkeypatch.setattr(KanbanReader, "_run", staticmethod(lambda *a: None))
    resp = client.get("/api/kanban/boards/demo-board/tasks/t_02/comments")
    assert resp.status_code == 200
    assert len(resp.json()["comments"]) == 2
