"""Read-only Kanban board reader for the Dev-Booth dashboard (A3-lite).

Plan v4 P4: the sanctioned read path is the CLI ``hermes kanban ... --json``;
direct SQLite is the documented fallback only. CLI command form (Phase 0
verified): ``--board <slug>`` is a ``hermes kanban``-LEVEL flag and must come
BEFORE the subcommand.

Named-board DB layout: ``~/.hermes/kanban/boards/<slug>/kanban.db``.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Optional

HERMES_BIN = "/home/mooner92/.local/bin/hermes"
KANBAN_BOARDS_ROOT = Path.home() / ".hermes" / "kanban" / "boards"

# tasks columns the dashboard surfaces (subset of the 27-col schema)
_TASK_FIELDS = (
    "id", "title", "body", "assignee", "status", "priority",
    "workspace_kind", "created_at", "started_at", "completed_at", "result",
)
_STATUSES = ("triage", "todo", "ready", "running", "blocked", "done", "archived")


def list_boards() -> list[dict[str, str]]:
    """Every Kanban board with an on-disk DB under the named-boards root."""
    boards: list[dict[str, str]] = []
    if KANBAN_BOARDS_ROOT.is_dir():
        for d in sorted(KANBAN_BOARDS_ROOT.iterdir()):
            if d.is_dir() and (d / "kanban.db").exists():
                boards.append({"slug": d.name})
    return boards


class KanbanReader:
    """Read-only view of one named Kanban board."""

    def __init__(self, board_slug: str):
        self.board_slug = board_slug
        self.db_path = KANBAN_BOARDS_ROOT / board_slug / "kanban.db"

    @property
    def exists(self) -> bool:
        return self.db_path.exists()

    # ----------------------------------------------------------- tasks
    def list_tasks(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        """All tasks on the board (CLI --json preferred, SQLite fallback)."""
        tasks = self._cli_list_tasks()
        if tasks is None:
            tasks = self._sqlite_list_tasks()
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        return tasks

    def _cli_list_tasks(self) -> Optional[list[dict[str, Any]]]:
        out = self._run("--board", self.board_slug, "list", "--json")
        if out is None:
            return None
        try:
            data = json.loads(out)
        except json.JSONDecodeError:
            return None
        rows = data if isinstance(data, list) else data.get("tasks", [])
        return [self._project(r) for r in rows]

    def _sqlite_list_tasks(self) -> list[dict[str, Any]]:
        if not self.exists:
            return []
        cols = ", ".join(_TASK_FIELDS)
        with self._connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    f"SELECT {cols} FROM tasks ORDER BY created_at ASC"
                )
            ]

    # -------------------------------------------------------- comments
    def get_comments(self, task_id: str) -> list[dict[str, Any]]:
        """Comment thread for a task (the agent-to-agent conversation)."""
        out = self._run("--board", self.board_slug, "show", task_id, "--json")
        if out is not None:
            try:
                data = json.loads(out)
                if isinstance(data, dict) and "comments" in data:
                    return list(data["comments"])
            except json.JSONDecodeError:
                pass
        return self._sqlite_comments(task_id)

    def _sqlite_comments(self, task_id: str) -> list[dict[str, Any]]:
        if not self.exists:
            return []
        with self._connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT id, task_id, author, body, created_at "
                    "FROM task_comments WHERE task_id = ? ORDER BY created_at ASC",
                    (task_id,),
                )
            ]

    # ----------------------------------------------------------- stats
    def get_board_stats(self) -> dict[str, int]:
        """Per-status task counts. SQLite COUNT (the CLI `stats` verb has no
        --json output, so SQLite is the read path here)."""
        stats = {s: 0 for s in _STATUSES}
        if not self.exists:
            return stats
        with self._connect() as c:
            for status, count in c.execute(
                "SELECT status, COUNT(*) FROM tasks GROUP BY status"
            ):
                if status in stats:
                    stats[status] = count
        return stats

    # --------------------------------------------------------- helpers
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _project(row: dict[str, Any]) -> dict[str, Any]:
        """Keep only the dashboard-facing fields from a CLI task row."""
        return {k: row.get(k) for k in _TASK_FIELDS}

    @staticmethod
    def _run(*args: str) -> Optional[str]:
        """Run ``hermes kanban <args>``; return stdout or None on any failure."""
        try:
            result = subprocess.run(
                [HERMES_BIN, "kanban", *args],
                capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout if result.returncode == 0 else None
