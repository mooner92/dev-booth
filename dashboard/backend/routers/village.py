"""Village pixel-office router.

Mirrors the read-only shape of :mod:`routers.kanban` (Hermes Kanban → JSON +
WebSocket) but projects board state into the agent-character view consumed by
``app/village/page.tsx``. Live updates poll ``kanban.db`` mtime every 2 s — the
same trigger the kanban WS uses — so a single hermes write fans out to both
endpoints without an extra subscriber on the DB.
"""
from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from ..services.village_status import (
    board_db_path,
    get_village_state,
    list_village_boards,
)

router = APIRouter(prefix="/api/village", tags=["village"])

_WS_POLL_INTERVAL_S = 2.0


@router.get("/boards")
def get_boards() -> dict:
    """List every Kanban board that has an on-disk kanban.db."""
    return {"boards": list_village_boards()}


@router.get("/boards/{board_slug}/state")
def get_state(board_slug: str) -> dict:
    """Current Village projection for ``board_slug``.

    Missing boards intentionally return the empty-shape (not 404) so the page
    can render a quiet office without an error toast.
    """
    return get_village_state(board_slug)


@router.websocket("/ws/{board_slug}")
async def village_ws(websocket: WebSocket, board_slug: str) -> None:
    """Push the Village projection whenever ``kanban.db`` mtime changes."""
    await websocket.accept()
    db_path = board_db_path(board_slug)
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
                state = await asyncio.to_thread(get_village_state, board_slug)
                await websocket.send_json({"type": "village_update", **state})
            await asyncio.sleep(_WS_POLL_INTERVAL_S)
    except WebSocketDisconnect:
        pass
    except (RuntimeError, ConnectionError):
        pass
    finally:
        with contextlib.suppress(RuntimeError):
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
