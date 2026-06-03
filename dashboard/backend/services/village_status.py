"""Project a Hermes Kanban board into the Village pixel-office shape.

Reads through :class:`KanbanReader` (CLI-first, SQLite fallback) so this module
adds no parallel access layer. The output shape is consumed by
``routers/village.py`` and ``app/village/page.tsx``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .kanban_reader import KANBAN_BOARDS_ROOT, KanbanReader

VILLAGE_AGENTS: tuple[str, ...] = ("conductor", "architect", "executor")

# Raw Hermes kanban status -> Village high-level state
KANBAN_TO_VILLAGE: dict[str, str] = {
    "running":  "executing",
    "blocked":  "error",
    "done":     "idle",
    "todo":     "idle",
    "ready":    "syncing",
    "triage":   "idle",
    "archived": "idle",
}

# Static desk coordinate + display label (canvas anchors live in the frontend;
# these are kept here only so the API payload is self-describing).
AGENT_DESK: dict[str, dict[str, Any]] = {
    "conductor": {"x": 400, "y": 150, "label": "Conductor"},
    "architect": {"x": 200, "y": 300, "label": "Architect"},
    "executor":  {"x": 600, "y": 300, "label": "Executor"},
}

# Village state -> office area + emoji
STATE_POSITIONS: dict[str, dict[str, str]] = {
    "executing":   {"area": "desk",      "emoji": "💻"},
    "researching": {"area": "desk",      "emoji": "🔍"},
    "writing":     {"area": "desk",      "emoji": "📝"},
    "syncing":     {"area": "hallway",   "emoji": "🔄"},
    "idle":        {"area": "breakroom", "emoji": "☕"},
    "error":       {"area": "breakroom", "emoji": "⚠️"},
}

_SLUG_PREFIX_RE = re.compile(r"^\[[^\]]+\]\s*")


def list_village_boards() -> list[str]:
    """Every kanban board with a kanban.db on disk."""
    if not KANBAN_BOARDS_ROOT.is_dir():
        return []
    return sorted(
        d.name
        for d in KANBAN_BOARDS_ROOT.iterdir()
        if d.is_dir() and (d / "kanban.db").exists()
    )


def board_db_path(board_slug: str) -> Path:
    return KANBAN_BOARDS_ROOT / board_slug / "kanban.db"


def get_village_state(board_slug: str) -> dict[str, Any]:
    """Project a board's task state into Village display shape.

    Missing / empty boards return the empty-shape (not an error) so the page can
    render a quiet office instead of a 404.
    """
    reader = KanbanReader(board_slug)
    if not reader.exists:
        return _empty_state(board_slug)

    tasks = reader.list_tasks()
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == "done")
    progress = round(done / total * 100) if total > 0 else 0

    agents = {name: _agent_view(name, tasks) for name in VILLAGE_AGENTS}

    return {
        "board":    board_slug,
        "progress": progress,
        "done":     done,
        "total":    total,
        "agents":   agents,
    }


def _agent_view(agent_name: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick the most-relevant task for one agent and render its view."""
    current_task = _pick_task(agent_name, tasks)
    kanban_status = (current_task or {}).get("status") or "idle"
    village_state = KANBAN_TO_VILLAGE.get(kanban_status, "idle")
    position = STATE_POSITIONS.get(village_state, STATE_POSITIONS["idle"])
    desk = AGENT_DESK.get(agent_name, {"x": 0, "y": 0, "label": agent_name})

    task_title = ""
    if current_task and current_task.get("title"):
        task_title = _SLUG_PREFIX_RE.sub("", str(current_task["title"])).strip()

    return {
        "state":       village_state,
        "task":        task_title,
        "task_status": kanban_status,
        **position,
        **desk,
    }


def _pick_task(agent_name: str, tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Prefer running > blocked > most-recent-done for the agent."""
    running = next(
        (t for t in tasks
         if t.get("assignee") == agent_name and t.get("status") == "running"),
        None,
    )
    if running:
        return running
    blocked = next(
        (t for t in tasks
         if t.get("assignee") == agent_name and t.get("status") == "blocked"),
        None,
    )
    if blocked:
        return blocked
    return next(
        (t for t in reversed(tasks)
         if t.get("assignee") == agent_name and t.get("status") == "done"),
        None,
    )


def _empty_state(board_slug: str) -> dict[str, Any]:
    return {
        "board":    board_slug,
        "progress": 0,
        "done":     0,
        "total":    0,
        "agents": {
            name: {
                "state":       "idle",
                "task":        "",
                "task_status": "idle",
                **STATE_POSITIONS["idle"],
                **AGENT_DESK.get(name, {"x": 0, "y": 0, "label": name}),
            }
            for name in VILLAGE_AGENTS
        },
    }
