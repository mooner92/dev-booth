"""Kanban dashboard router (read-only) — A3-lite.

Surfaces the Hermes Kanban board the agents coordinate on, so the existing
Dev-Booth dashboard (port 7000, dashboard.excusa.uk) shows live task state +
agent comment threads without a custom data layer.
"""
from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from ..services.kanban_reader import KANBAN_BOARDS_ROOT, KanbanReader, list_boards

router = APIRouter(prefix="/api/kanban", tags=["kanban"])

_WS_POLL_INTERVAL_S = 2.0
_WS_COMMENT_TASK_LIMIT = 12   # tasks whose comment threads the WS pushes
_WS_COMMENT_LIMIT = 150       # most-recent comments pushed per update
_WS_LOG_TASK_LIMIT = 5        # v5: tasks whose worker logs the WS pushes
_WS_LOG_LINE_LIMIT = 50       # most-recent log lines per active task
_WS_TIMELINE_LIMIT = 100      # v6: team-timeline entries pushed per update


@router.get("/boards")
def get_boards() -> dict:
    return {"boards": list_boards()}


@router.get("/boards/{board_slug}/tasks")
def get_tasks(board_slug: str, status: str | None = None) -> dict:
    reader = KanbanReader(board_slug)
    if not reader.exists:
        raise HTTPException(status_code=404, detail=f"board {board_slug!r} not found")
    return {"tasks": reader.list_tasks(status)}


@router.get("/boards/{board_slug}/stats")
def get_stats(board_slug: str) -> dict:
    reader = KanbanReader(board_slug)
    if not reader.exists:
        raise HTTPException(status_code=404, detail=f"board {board_slug!r} not found")
    return reader.get_board_stats()


@router.get("/boards/{board_slug}/tasks/{task_id}/comments")
def get_task_comments(board_slug: str, task_id: str) -> dict:
    reader = KanbanReader(board_slug)
    if not reader.exists:
        raise HTTPException(status_code=404, detail=f"board {board_slug!r} not found")
    return {"comments": reader.get_comments(task_id)}


@router.get("/boards/{board_slug}/tasks/{task_id}/log")
def get_task_log(board_slug: str, task_id: str) -> dict:
    """v5: surface the worker transcript (``hermes kanban log``) so the
    dashboard ChatStream can render per-turn agent activity. Falls back
    to runs+comments via the same reader when ``log`` is empty."""
    reader = KanbanReader(board_slug)
    if not reader.exists:
        raise HTTPException(status_code=404, detail=f"board {board_slug!r} not found")
    # Determine the agent identity from the task row (NOT log-content regex).
    assignee = "system"
    for t in reader.list_tasks():
        if t.get("id") == task_id:
            assignee = t.get("assignee") or "system"
            break
    raw = reader.get_task_log(task_id)
    messages = [_to_log_entry(task_id, assignee, i, e) for i, e in enumerate(raw)]
    return {"messages": messages, "runs": reader.get_runs(task_id)}


def _to_log_entry(task_id: str, assignee: str, idx: int, raw: dict) -> dict:
    """Project a worker-log line into the dashboard's LogEntry shape."""
    body = raw.get("line", "")
    return {
        "id":        f"log-{task_id}-{idx}",
        "from":      assignee,
        "to":        None,
        "kind":      "tool" if body.lstrip().startswith("kanban_") else "text",
        "body":      body,
        "createdAt": None,    # hermes log has no per-line timestamps in v0.13.0
    }


# ----------------------------------------------------- v6: team timeline
@router.get("/boards/{board_slug}/timeline")
def get_timeline(board_slug: str, limit: int = 200) -> dict:
    """v6/v7: aggregate every kanban_comment + task done/blocked transition on
    the board, oldest-first, projected to LogEntry shape. Powers the
    dashboard's '팀 타임라인' tab."""
    reader = KanbanReader(board_slug)
    if not reader.exists:
        raise HTTPException(status_code=404, detail=f"board {board_slug!r} not found")
    return {"entries": _collect_timeline(reader, limit=limit)}


def _comment_to_log_entry(row: dict) -> dict:
    """Project a task_comments row into the LogEntry shape (kind='comment')."""
    cid = row.get("id")
    ts = row.get("created_at")  # seconds-epoch
    return {
        "id":          f"comment-{cid}",
        "from":        row.get("author") or "system",
        "to":          "all",
        "kind":        "comment",
        "body":        row.get("body") or "",
        "task_id":     row.get("task_id"),
        "task_title":  row.get("task_title"),
        "createdAt":   _epoch_to_iso(ts),
        "createdAtMs": (int(ts) if ts else 0) * 1000,
    }


def _status_event_to_log_entry(row: dict) -> dict:
    """Project a done/blocked task row into the LogEntry shape
    (kind='status_change'). Mirrors comment shape so the frontend timeline
    renders both event types side-by-side."""
    tid = row.get("task_id")
    ts = row.get("event_at")
    status = row.get("status") or ""
    title = row.get("task_title") or ""
    if status == "done":
        body = f"✅ 완료: {title}"
    elif status == "blocked":
        body = f"⊘ 차단됨: {title}"
    else:
        body = f"{status}: {title}"
    return {
        "id":          f"status-{status}-{tid}",
        "from":        row.get("task_assignee") or "system",
        "to":          "all",
        "kind":        "status_change",
        "body":        body,
        "task_id":     tid,
        "task_title":  title,
        "createdAt":   _epoch_to_iso(ts),
        "createdAtMs": (int(ts) if ts else 0) * 1000,
    }


def _epoch_to_iso(ts) -> str | None:
    """seconds-epoch → ISO-8601 UTC string, or None on missing input."""
    if ts is None:
        return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()


def _collect_timeline(reader: KanbanReader, limit: int = _WS_TIMELINE_LIMIT) -> list[dict]:
    """WS-bounded timeline projection — comments + done/blocked status events,
    merged in chronological order."""
    events: list[dict] = []
    events.extend(_comment_to_log_entry(r) for r in reader.get_all_comments(limit=limit))
    events.extend(_status_event_to_log_entry(r) for r in reader.get_status_change_events(limit=limit))
    events.sort(key=lambda e: e.get("createdAtMs") or 0)
    return events[-limit:]


def _collect_comments(reader: KanbanReader, tasks: list[dict]) -> list[dict]:
    comments: list[dict] = []
    for task in tasks[:_WS_COMMENT_TASK_LIMIT]:
        tid = task.get("id")
        if tid:
            comments.extend(reader.get_comments(tid))
    comments.sort(key=lambda c: c.get("created_at", 0))
    return comments[-_WS_COMMENT_LIMIT:]


def _collect_logs(reader: KanbanReader, tasks: list[dict]) -> dict[str, list[dict]]:
    """Pull worker logs only for active tasks — guardrail against subprocess
    storms. 'Active' = status in {running, ready}, capped at _WS_LOG_TASK_LIMIT."""
    logs: dict[str, list[dict]] = {}
    active = [t for t in tasks if t.get("status") in ("running", "ready")][:_WS_LOG_TASK_LIMIT]
    for t in active:
        tid = t.get("id")
        if not tid:
            continue
        assignee = t.get("assignee") or "system"
        raw = reader.get_task_log(tid, limit=_WS_LOG_LINE_LIMIT)
        if raw:
            logs[tid] = [_to_log_entry(tid, assignee, i, e) for i, e in enumerate(raw)]
    return logs


@router.websocket("/ws/kanban/{board_slug}")
async def kanban_ws(websocket: WebSocket, board_slug: str) -> None:
    """Push the board's tasks + comment threads whenever kanban.db changes."""
    await websocket.accept()
    reader = KanbanReader(board_slug)
    db_path = KANBAN_BOARDS_ROOT / board_slug / "kanban.db"
    last_mtime = -1.0
    try:
        while True:
            if websocket.client_state != WebSocketState.CONNECTED:
                break
            try:
                mtime = db_path.stat().st_mtime
            except OSError:
                mtime = 0.0
            if mtime != last_mtime:
                last_mtime = mtime
                tasks = await asyncio.to_thread(reader.list_tasks)
                comments = await asyncio.to_thread(_collect_comments, reader, tasks)
                logs = await asyncio.to_thread(_collect_logs, reader, tasks)
                timeline = await asyncio.to_thread(_collect_timeline, reader)
                await websocket.send_json({
                    "type": "kanban_update",
                    "tasks": tasks,
                    "comments": comments,
                    "logs": logs,
                    "timeline": timeline,
                })
            await asyncio.sleep(_WS_POLL_INTERVAL_S)
    except WebSocketDisconnect:
        pass
    except (RuntimeError, ConnectionError):
        pass
    finally:
        with contextlib.suppress(RuntimeError):
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
