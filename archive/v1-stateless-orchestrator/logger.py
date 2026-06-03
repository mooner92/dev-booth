"""Direct-append session log writer for the Dev-Booth orchestrator.

This module is the orchestrator's **own** progress-narration channel. It writes
``kind:"status"`` lines straight to ``<session>/log/messages.jsonl`` in the exact
AWG line format the dashboard's ``LogEntry`` model and ``StageTracker`` expect.

DESIGN CONSTRAINTS (plan v3 P3 / DD2 / DD4 — enforced, not optional):
  * This module **MUST NOT** import or call ``agent_working_group`` /
    ``MessageQueue``. Routing orchestrator narration through ``MessageQueue.send()``
    would ``mkdir`` a ``queues/orchestrator/`` directory, which the dashboard's
    ``_detect_agents`` surfaces as a phantom 4th agent. Direct append keeps the
    orchestrator a non-participant at the filesystem layer.
  * Agent-to-agent messages (``instruction``/``answer``/``question``/``blocker``)
    still go through ``MessageQueue.send()`` in the orchestrator — NOT here.
  * The log line format is byte-compatible with ``MessageQueue.send()``'s own
    append (verified against ``agent_working_group/queue.py``): compact JSON,
    ``ensure_ascii=False``, key order ``{id,kind,from,to,body,refs,priority,
    createdAt,createdAtMs}``, one object per line.

The append is guarded by ``fcntl.flock`` so concurrent writers (e.g. the
orchestrator's narration interleaved with anything else appending to the same
file) never interleave a partial line.
"""
from __future__ import annotations

import fcntl
import json
import time
import uuid
from pathlib import Path
from typing import Any

# AWG message-kind priorities (mirrors agent_working_group.queue.PRIORITIES).
# Kept as a local literal — importing AWG here is forbidden by design.
_PRIORITIES: dict[str, int] = {
    "blocker": 99,
    "question": 70,
    "answer": 60,
    "instruction": 50,
    "status": 30,
    "note": 10,
}

LOG_SUBDIR = "log"
LOG_FILENAME = "messages.jsonl"


def _now_ms() -> int:
    """Epoch milliseconds — matches ``agent_working_group.queue.now_ms()``."""
    return int(time.time() * 1000)


def _utc_iso(ms: int) -> str:
    """ISO-8601 UTC — matches ``agent_working_group.queue.utc_iso()``."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ms / 1000))


def log_message(
    session_path: str | Path,
    from_agent: str,
    to_agent: str,
    body: str,
    kind: str = "status",
) -> dict[str, Any]:
    """Append one AWG-format JSON line to ``<session_path>/log/messages.jsonl``.

    Returns the message dict that was written. The parent ``log/`` directory is
    created defensively so the writer works even before the orchestrator's
    ``setup()`` has run (and so unit tests can exercise it in isolation).

    The append is atomic w.r.t. other ``flock``-aware writers.
    """
    if kind not in _PRIORITIES:
        raise ValueError(
            f"unknown kind {kind!r}; valid: {sorted(_PRIORITIES)}"
        )

    created_ms = _now_ms()
    message: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "from": from_agent,
        "to": to_agent,
        "body": body,
        "refs": {},
        "priority": _PRIORITIES[kind],
        "createdAt": _utc_iso(created_ms),
        "createdAtMs": created_ms,
    }

    log_dir = Path(session_path) / LOG_SUBDIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILENAME

    line = json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
    with log_file.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(line)
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    return message


class SessionLog:
    """Convenience wrapper bound to one session directory.

    All writes go through :func:`log_message` (direct append). This class never
    touches ``MessageQueue`` and never creates a ``queues/`` directory.
    """

    def __init__(self, session_path: str | Path):
        self.session_path = Path(session_path)

    def narrate(self, stage_no: int, body: str) -> dict[str, Any]:
        """Emit a stage-progress ``status`` line as the orchestrator.

        ``body`` must be the orchestrator's Canonical Narration Corpus entry for
        ``stage_no`` (the corpus lives in ``core/orchestrator.py``; this module
        does not own it). Detection on the dashboard side keys on the free-text
        keywords inside ``body`` — see plan §7.
        """
        return log_message(
            self.session_path,
            from_agent="orchestrator",
            to_agent="all",
            body=body,
            kind="status",
        )

    def broadcast(self, body: str) -> dict[str, Any]:
        """Emit a generic orchestrator ``status`` broadcast (no stage semantics)."""
        return log_message(
            self.session_path,
            from_agent="orchestrator",
            to_agent="all",
            body=body,
            kind="status",
        )
