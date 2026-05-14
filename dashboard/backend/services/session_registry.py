"""SessionListCache (A10): 5s TTL cache over the session list scan."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .. import config
from . import session_layout
from .models import SessionSummary


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="seconds")


class SessionListCache:
    def __init__(self, ttl_s: float = config.SESSION_LIST_TTL_S, sessions_root: Path | None = None):
        self.ttl_s = ttl_s
        self.sessions_root = sessions_root
        self._lock = threading.Lock()
        self._cached: Optional[list[SessionSummary]] = None
        self._cached_at: float = 0.0

    def invalidate(self) -> None:
        with self._lock:
            self._cached = None
            self._cached_at = 0.0

    def list(self) -> list[SessionSummary]:
        with self._lock:
            now = time.time()
            if self._cached is not None and (now - self._cached_at) < self.ttl_s:
                return list(self._cached)
            entries: list[SessionSummary] = []
            for layout in session_layout.iter_layouts(self.sessions_root):
                try:
                    mtime = layout.root.stat().st_mtime
                except OSError:
                    mtime = 0.0
                entries.append(SessionSummary(
                    name=layout.name,
                    root=str(layout.root),
                    has_log=layout.has_log,
                    has_queues=layout.has_queues,
                    agents=list(layout.agents),
                    last_modified=_iso(mtime) if mtime else None,
                ))
            self._cached = entries
            self._cached_at = now
            return list(entries)
