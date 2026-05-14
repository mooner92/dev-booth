"""SessionHub + HubRegistry: per-session pubsub fan-out for WebSocket clients.

Each ``SessionHub`` owns one ``LogTailer`` and broadcasts to N async queues.
``dropped_subscribers_total`` is a process-wide counter that lights up
slow-consumer events for observability (C7).
"""
from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .. import config
from . import awg_inspector, session_layout, stage_mapper
from .log_tailer import LogTailer
from .models import LogEntry, StatusSnapshot


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")


# Process-wide metrics counters (Prometheus-style; exposed by /api/metrics/preset
# in this codebase rather than a real client library for simplicity).
class _Counters:
    def __init__(self):
        self._lock = threading.Lock()
        self.dropped_subscribers_total: dict[str, int] = {}
        self.ws_reconnects_total: dict[str, int] = {}
        self.ws_heartbeats_missed_total: int = 0

    def inc_dropped(self, session: str, n: int = 1) -> None:
        with self._lock:
            self.dropped_subscribers_total[session] = self.dropped_subscribers_total.get(session, 0) + n

    def inc_reconnect(self, session: str, n: int = 1) -> None:
        with self._lock:
            self.ws_reconnects_total[session] = self.ws_reconnects_total.get(session, 0) + n

    def inc_heartbeat_missed(self, n: int = 1) -> None:
        with self._lock:
            self.ws_heartbeats_missed_total += n

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "dropped_subscribers_total": dict(self.dropped_subscribers_total),
                "ws_reconnects_total": dict(self.ws_reconnects_total),
                "ws_heartbeats_missed_total": self.ws_heartbeats_missed_total,
            }


COUNTERS = _Counters()


class SessionHub:
    def __init__(self, name: str, sessions_root: Path | None = None):
        self.name = name
        self.layout = session_layout.resolve(name, sessions_root)
        self.tailer = LogTailer(self.layout.log_path)
        self.stage_tracker = stage_mapper.StageTracker()
        self.subscribers: set[asyncio.Queue] = set()
        self.status_cache: Optional[StatusSnapshot] = None
        self._tail_task: Optional[asyncio.Task] = None
        self._stopped = asyncio.Event()
        self._lock = asyncio.Lock()
        self._last_activity = time.time()

    # ----------------------------------------------------------- subscribers
    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=config.WS_BROADCAST_QUEUE_MAX)
        async with self._lock:
            self.subscribers.add(q)
            await self._ensure_tail_task()
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            self.subscribers.discard(q)

    async def _ensure_tail_task(self) -> None:
        if self._tail_task and not self._tail_task.done():
            return
        self._stopped.clear()
        self._tail_task = asyncio.create_task(self._tail_loop(), name=f"tail:{self.name}")

    async def stop(self) -> None:
        self._stopped.set()
        if self._tail_task:
            try:
                await asyncio.wait_for(self._tail_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._tail_task.cancel()

    # ------------------------------------------------------------- broadcast
    async def broadcast(self, msg: dict) -> None:
        self._last_activity = time.time()
        dead: list[asyncio.Queue] = []
        for q in list(self.subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                dead.append(q)
        if dead:
            COUNTERS.inc_dropped(self.name, n=len(dead))
            for q in dead:
                self.subscribers.discard(q)

    # ---------------------------------------------------------------- status
    def derive_status(self) -> StatusSnapshot:
        depths = awg_inspector.queue_depths(self.layout.root, self.layout.agents or None)
        any_running = any(d.inbox + d.processing > 0 for d in depths.values())
        state: str
        if any_running:
            state = "running"
        elif self.tailer.state.last_seq != "0:0":
            state = "idle"
        else:
            state = "unknown"

        # current stage
        stage_no = 0
        stage_id: Optional[str] = None
        current = self.stage_tracker.current()
        if current:
            stage_no, stage_id = current

        last_active = None
        ring = list(self.tailer.state.ring_buffer)
        if ring:
            _, last_entry = ring[-1]
            last_active = last_entry.created_at

        snap = StatusSnapshot(
            session=self.name,
            state=state,
            current_stage=stage_no,
            current_stage_id=stage_id,
            current_agent=None,
            last_active_at=last_active,
            queues=depths,
        )
        self.status_cache = snap
        return snap

    # ----------------------------------------------------------- tail loop
    async def _tail_loop(self) -> None:
        interval = config.LOG_TAIL_INTERVAL_MS / 1000.0
        while not self._stopped.is_set():
            try:
                result = self.tailer.read_new()
                if result.reset_signal:
                    await self.broadcast({
                        "type": "reset",
                        "ts": _now_iso(),
                        "reason": result.reset_signal.get("reason", "rotation"),
                        "seq": self.tailer.snapshot_offset(),
                    })
                if result.entries:
                    for seq, entry in result.entries:
                        if entry.body and entry.created_at_ms is not None:
                            self.stage_tracker.observe(entry.body, entry.created_at_ms)
                        await self.broadcast({
                            "type": "log",
                            "ts": _now_iso(),
                            "seq": seq,
                            "entry": entry.model_dump(by_alias=True),
                        })
                    # Push status update piggyback
                    snap = self.derive_status()
                    await self.broadcast({
                        "type": "status",
                        "ts": _now_iso(),
                        "status": snap.model_dump(),
                    })
            except Exception as exc:  # noqa: BLE001
                await self.broadcast({"type": "error", "ts": _now_iso(), "error": str(exc)[:200]})
            await asyncio.sleep(interval)


class HubRegistry:
    def __init__(self, sessions_root: Path | None = None):
        self.sessions_root = sessions_root
        self._hubs: dict[str, SessionHub] = {}
        self._lock = asyncio.Lock()

    async def get(self, name: str) -> SessionHub:
        async with self._lock:
            hub = self._hubs.get(name)
            if hub is None:
                hub = SessionHub(name, self.sessions_root)
                self._hubs[name] = hub
            return hub

    async def close_all(self) -> None:
        async with self._lock:
            hubs = list(self._hubs.values())
            self._hubs.clear()
        for hub in hubs:
            await hub.stop()
