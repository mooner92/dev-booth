"""WebSocket router (/ws/{session}) — see plan §4.5 / A9 / C5."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from .. import config
from ..services import session_layout
from ..services.session_hub import COUNTERS, HubRegistry

router = APIRouter(tags=["ws"])


WS_CODE_IDLE_TIMEOUT = 4001
WS_CODE_SLOW_CONSUMER = 4002
WS_CODE_ROTATION_RESET = 4003
WS_CODE_SERVER_SHUTDOWN = 4004
WS_CODE_SESSION_NOT_FOUND = 4005


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")


@router.websocket("/ws/{session}")
async def session_socket(websocket: WebSocket, session: str) -> None:
    try:
        layout = session_layout.resolve(session)
    except ValueError:
        await websocket.close(code=WS_CODE_SESSION_NOT_FOUND, reason="invalid session name")
        return
    if not layout.root.exists():
        await websocket.close(code=WS_CODE_SESSION_NOT_FOUND, reason="session not found")
        return

    await websocket.accept()

    hubs: HubRegistry = websocket.app.state.hub_registry
    hub = await hubs.get(session)
    queue = await hub.subscribe()

    # 1. hello
    await websocket.send_json({
        "type": "hello",
        "session": session,
        "version": config.VERSION,
        "server_time": _now_iso(),
    })

    # 2. wait for subscribe (optional resume_from)
    resume_from: str | None = None
    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
        if isinstance(first, dict) and first.get("type") == "subscribe":
            resume_from = first.get("resume_from")
    except asyncio.TimeoutError:
        pass
    except Exception:  # noqa: BLE001
        pass

    # 3. replay from tailer ring buffer
    if resume_from is not None:
        replay, reset_reason = hub.tailer.replay_from(resume_from)
        if reset_reason:
            await websocket.send_json({
                "type": "reset",
                "ts": _now_iso(),
                "reason": reset_reason,
                "seq": hub.tailer.snapshot_offset(),
            })
        else:
            for seq, entry in replay:
                await websocket.send_json({
                    "type": "log",
                    "ts": _now_iso(),
                    "seq": seq,
                    "entry": entry.model_dump(by_alias=True),
                })

    # 4. realtime fan-out + heartbeat
    last_client_msg = asyncio.get_event_loop().time()

    async def reader() -> None:
        nonlocal last_client_msg
        try:
            while True:
                msg = await websocket.receive_json()
                last_client_msg = asyncio.get_event_loop().time()
                if isinstance(msg, dict) and msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "ts": _now_iso()})
        except WebSocketDisconnect:
            return
        except Exception:  # noqa: BLE001
            return

    reader_task = asyncio.create_task(reader())

    try:
        while True:
            try:
                outgoing = await asyncio.wait_for(queue.get(), timeout=config.WS_HEARTBEAT_INTERVAL_S)
                await websocket.send_json(outgoing)
            except asyncio.TimeoutError:
                # heartbeat
                await websocket.send_json({"type": "heartbeat", "ts": _now_iso()})
                # idle close check
                now = asyncio.get_event_loop().time()
                if now - last_client_msg > config.WS_IDLE_TIMEOUT_S:
                    await websocket.close(code=WS_CODE_IDLE_TIMEOUT, reason="idle timeout")
                    break
            except WebSocketDisconnect:
                break
    except Exception:  # noqa: BLE001
        COUNTERS.inc_reconnect(session)
    finally:
        reader_task.cancel()
        await hub.unsubscribe(queue)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close()
            except Exception:  # noqa: BLE001
                pass
