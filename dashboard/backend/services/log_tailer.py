"""LogTailer: tails messages.jsonl, detects rotation, supports resume_from.

Per plan A8/A9:

- ``TailerState`` holds inode, byte offset, ring buffer (deque, maxlen=1000),
  last_seq, last_status_signal epoch.
- Rotation detection: ``os.fstat(fd).st_ino != self.state.inode`` → reset
  offset=0, emit reset signal.
- ``seq`` format: ``f"{inode}:{byte_offset}"``.
- ``resume_from`` semantics:
    - matching inode + offset within ring → replay newer entries
    - inode mismatch OR offset evicted from ring → require client to re-fetch
      via REST (server emits a reset signal)
- Persistence is **in-memory only**; on restart, tail seeks to EOF.

The tailer is intentionally synchronous and tiny — the SessionHub wraps it in
an asyncio polling task that calls ``read_new()`` every ``LOG_TAIL_INTERVAL_MS``.
"""
from __future__ import annotations

import json
import os
import threading
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .. import config
from .models import LogEntry


@dataclass
class TailerState:
    inode: int = 0
    offset: int = 0
    ring_buffer: deque = field(default_factory=lambda: deque(maxlen=config.LOG_RING_SIZE))
    last_seq: str = "0:0"
    last_status_signal: float = 0.0


@dataclass
class ReadResult:
    entries: list[tuple[str, LogEntry]]  # (seq, entry)
    rotated: bool = False
    reset_signal: Optional[dict] = None  # to broadcast as WSReset


def make_seq(inode: int, offset: int) -> str:
    return f"{inode}:{offset}"


def parse_seq(seq: str) -> tuple[int, int]:
    inode_s, _, off_s = seq.partition(":")
    try:
        return int(inode_s), int(off_s)
    except ValueError:
        return 0, 0


class LogTailer:
    """Tails a single ``messages.jsonl`` file.

    Thread-safe for concurrent calls to ``read_new`` and ``replay_from``
    via an internal lock — though in practice only one task tails per session.
    """

    def __init__(self, path: Path):
        self.path = path
        self.state = TailerState()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ tail
    def read_new(self) -> ReadResult:
        with self._lock:
            return self._read_new_locked()

    def _read_new_locked(self) -> ReadResult:
        if not self.path.exists():
            return ReadResult(entries=[])

        try:
            st = self.path.stat()
        except FileNotFoundError:
            return ReadResult(entries=[])

        current_inode = st.st_ino
        rotated = False
        reset_signal: Optional[dict] = None

        if self.state.inode == 0:
            # First read — start from beginning
            self.state.inode = current_inode
            self.state.offset = 0
        elif current_inode != self.state.inode:
            rotated = True
            reset_signal = {
                "reason": "rotation",
                "old_inode": self.state.inode,
                "new_inode": current_inode,
            }
            self.state.inode = current_inode
            self.state.offset = 0
            self.state.ring_buffer.clear()
        elif st.st_size < self.state.offset:
            # Truncate
            rotated = True
            reset_signal = {
                "reason": "truncate",
                "old_offset": self.state.offset,
                "new_size": st.st_size,
            }
            self.state.offset = 0
            self.state.ring_buffer.clear()

        new_entries: list[tuple[str, LogEntry]] = []
        try:
            with self.path.open("rb") as fh:
                fh.seek(self.state.offset)
                while True:
                    line_start = fh.tell()
                    raw = fh.readline()
                    if not raw:
                        break
                    # Skip partial lines (no trailing newline)
                    if not raw.endswith(b"\n"):
                        break
                    line = raw.decode("utf-8", errors="replace").rstrip("\n")
                    if not line:
                        self.state.offset = fh.tell()
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        # Mark unparseable line but keep advancing
                        data = {"body": line, "_parse_error": True}
                    entry = LogEntry.model_validate(data)
                    seq = make_seq(current_inode, line_start)
                    self.state.offset = fh.tell()
                    self.state.last_seq = make_seq(current_inode, self.state.offset)
                    self.state.ring_buffer.append((seq, entry))
                    new_entries.append((seq, entry))
        except OSError:
            return ReadResult(entries=new_entries, rotated=rotated, reset_signal=reset_signal)

        return ReadResult(entries=new_entries, rotated=rotated, reset_signal=reset_signal)

    # ----------------------------------------------------------------- resume
    def replay_from(self, resume_seq: Optional[str]) -> tuple[list[tuple[str, LogEntry]], Optional[str]]:
        """Replay ring buffer entries newer than ``resume_seq``.

        Returns ``(entries, reset_reason)``. If reset_reason is non-None, the
        caller MUST send a reset signal and the client must re-fetch via REST.
        """
        with self._lock:
            if not resume_seq:
                return list(self.state.ring_buffer), None
            inode, offset = parse_seq(resume_seq)
            if inode == 0:
                return list(self.state.ring_buffer), None
            if inode != self.state.inode:
                return [], "rotation"
            if not self.state.ring_buffer:
                if offset > self.state.offset:
                    return [], "offset_ahead"
                return [], None
            # Find first entry with seq > resume_seq
            replay: list[tuple[str, LogEntry]] = []
            evicted_oldest = True
            for seq, entry in self.state.ring_buffer:
                e_inode, e_off = parse_seq(seq)
                if e_inode == inode and e_off <= offset:
                    evicted_oldest = False
                    continue
                replay.append((seq, entry))
            # If we didn't see any entry at or before resume offset, the ring
            # may have evicted it — only emit ``ring_evicted`` if the requested
            # offset predates everything in the buffer.
            if evicted_oldest and replay:
                first_seq = self.state.ring_buffer[0][0]
                _, first_off = parse_seq(first_seq)
                if offset < first_off:
                    return [], "ring_evicted"
            return replay, None

    def snapshot_offset(self) -> str:
        with self._lock:
            return make_seq(self.state.inode, self.state.offset)


def iter_log_file(path: Path) -> Iterable[LogEntry]:
    """Stream parse a log file. Used by smoke tests and `/api/sessions/.../logs`
    when the tailer is not in play (e.g. cold REST call).
    """
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                data = {"body": line, "_parse_error": True}
            yield LogEntry.model_validate(data)
