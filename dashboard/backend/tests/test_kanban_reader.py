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
            ("t_01", "fork & clone", "conductor", "done", 1, "worktree", 1778801400),
            ("t_02", "initial scan", "conductor", "running", 1, "worktree", 1778801410),
            ("t_03", "structure analysis", "architect", "ready", 1, "worktree", 1778801420),
            ("t_09", "code review", "architect", "blocked", 1, "worktree", 1778801490),
        ],
    )
    conn.executemany(
        "INSERT INTO task_comments (id,task_id,author,body,created_at) VALUES (?,?,?,?,?)",
        [
            (1, "t_02", "conductor", "@architect 구조 분석 시작해주세요", 1778801411),
            (2, "t_02", "architect", "확인했습니다", 1778801412),
            # v6: comment on a different task — exercises the LEFT JOIN's
            # task_title resolution across multiple distinct task rows.
            (3, "t_01", "conductor", "▶ fork & clone 시작", 1778801401),
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
    assert tasks[0]["assignee"] == "conductor"
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
    assert [c["author"] for c in comments] == ["conductor", "architect"]


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


# ----------------------------------------- v5: get_runs / get_task_log
_RUNS_FIXTURE = """\
#    OUTCOME       PROFILE            ELAPSED  STARTED
  1  crashed       executor               40m  2026-05-15 04:19
     ✖ worker exited cleanly (rc=0) without calling kanban_complete or kanban_block — protocol violation
  2  (running)     executor              1.0h  2026-05-15 04:27
"""

_LOG_FIXTURE = """\
╭─ ⚕ Hermes ───────────────────────────────────────────────────────────────────╮
  Let's start by cloning the repository.
╰──────────────────────────────────────────────────────────────────────────────╯
  ┊ 💻 preparing terminal…
  ┊ 💻 $ git clone https://github.com/example/firebase-app  0.5s [error]
  ┊ 📋 preparing kanban_show…
  ┊ ⚡ kanban_show   0.0s
"""


def test_get_runs_parses_attempts(boards_root, monkeypatch):
    monkeypatch.setattr(KanbanReader, "_run",
                        staticmethod(lambda *a: _RUNS_FIXTURE if "runs" in a else None))
    runs = KanbanReader("demo-board").get_runs("t_02")
    assert len(runs) == 2
    assert runs[0]["attempt"] == 1 and runs[0]["outcome"] == "crashed"
    assert runs[0]["profile"] == "executor"
    assert "protocol violation" in runs[0].get("detail", "")
    assert runs[1]["attempt"] == 2 and runs[1]["outcome"] == "running"


def test_get_runs_empty_on_no_output(boards_root, monkeypatch):
    monkeypatch.setattr(KanbanReader, "_run", staticmethod(lambda *a: None))
    assert KanbanReader("demo-board").get_runs("missing") == []


def test_get_task_log_strips_decoration(boards_root, monkeypatch):
    monkeypatch.setattr(KanbanReader, "_run",
                        staticmethod(lambda *a: _LOG_FIXTURE if "log" in a else None))
    lines = KanbanReader("demo-board").get_task_log("t_02")
    bodies = [e["line"] for e in lines]
    # Box-drawing pure-decoration lines must be filtered out
    assert not any(b in ("", "─", "│") for b in bodies)
    assert any("git clone" in b for b in bodies)
    assert any("kanban_show" in b for b in bodies)


def test_get_task_log_limits_results(boards_root, monkeypatch):
    fixture = "\n".join(f"line {i}" for i in range(200))
    monkeypatch.setattr(KanbanReader, "_run",
                        staticmethod(lambda *a: fixture if "log" in a else None))
    lines = KanbanReader("demo-board").get_task_log("t_02", limit=10)
    assert len(lines) == 10
    # Returns the *most recent* lines (tail)
    assert lines[-1]["line"].endswith("199")


def test_route_task_log_projects_assignee(client, monkeypatch):
    # log returns content, runs returns empty
    def fake_run(*a):
        if "log" in a:
            return "agent says hello\nkanban_complete(summary=...)"
        if "runs" in a:
            return _RUNS_FIXTURE
        return None
    monkeypatch.setattr(KanbanReader, "_run", staticmethod(fake_run))
    resp = client.get("/api/kanban/boards/demo-board/tasks/t_02/log")
    assert resp.status_code == 200
    payload = resp.json()
    msgs = payload["messages"]
    assert len(msgs) == 2
    # Agent identity comes from task.assignee (t_02 is conductor in the fixture).
    assert all(m["from"] == "conductor" for m in msgs)
    # The kanban_* line should be tagged as a tool entry.
    assert msgs[1]["kind"] == "tool"
    # runs piggybacks on the same endpoint
    assert len(payload["runs"]) == 2


def test_route_task_log_unknown_board_404(client):
    assert client.get("/api/kanban/boards/ghost/tasks/t_02/log").status_code == 404


# ------------------------------------------ v6: get_all_comments / /timeline
def test_get_all_comments_joins_task_title(boards_root):
    """SQLite-direct LEFT JOIN attaches task_title to every comment, oldest-first."""
    rows = KanbanReader("demo-board").get_all_comments()
    assert len(rows) == 3
    # Each row carries the joined fields
    assert all("task_title" in r and "task_assignee" in r for r in rows)
    # Distinct task_titles prove the join works across multiple parent rows
    titles = {r["task_title"] for r in rows}
    assert {"fork & clone", "initial scan"}.issubset(titles)
    # Oldest-first ordering
    timestamps = [r["created_at"] for r in rows]
    assert timestamps == sorted(timestamps)


def test_get_all_comments_limit(boards_root):
    """`limit` returns the most-recent N (tail of the ordered list)."""
    rows = KanbanReader("demo-board").get_all_comments(limit=1)
    assert len(rows) == 1
    # tail = newest comment (t_02 architect '확인했습니다' @ 1778801412)
    assert rows[0]["body"] == "확인했습니다"


def test_route_timeline_projects_to_log_entry(client):
    """/timeline projects every row through _comment_to_log_entry server-side."""
    resp = client.get("/api/kanban/boards/demo-board/timeline")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) == 3
    first = entries[0]
    assert first["kind"] == "comment"
    assert first["to"] == "all"
    assert first["from"] in ("conductor", "architect")
    assert "task_title" in first and "task_id" in first
    # createdAtMs derives from seconds-epoch (×1000)
    assert isinstance(first["createdAtMs"], int) and first["createdAtMs"] > 0
    # createdAt is an ISO-8601 UTC string
    assert isinstance(first["createdAt"], str) and "T" in first["createdAt"]


def test_route_timeline_unknown_board_404(client):
    assert client.get("/api/kanban/boards/ghost/timeline").status_code == 404
