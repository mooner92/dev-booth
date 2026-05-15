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


def _collect_comments(reader: KanbanReader, tasks: list[dict]) -> list[dict]:
    comments: list[dict] = []
    for task in tasks[:_WS_COMMENT_TASK_LIMIT]:
        tid = task.get("id")
        if tid:
            comments.extend(reader.get_comments(tid))
    comments.sort(key=lambda c: c.get("created_at", 0))
    return comments[-_WS_COMMENT_LIMIT:]


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
                await websocket.send_json({
                    "type": "kanban_update",
                    "tasks": tasks,
                    "comments": comments,
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
