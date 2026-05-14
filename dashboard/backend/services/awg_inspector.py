"""AWG queue inspector.

Pattern copied (not imported) from
``/dev-booth/agent-working-group/dashboard/server/services/awg_reader.py``
per plan A14. The local copy is adjusted to the four-state schema
(``inbox/processing/processed/dead``) and reads queues at the per-session
location: ``<session_root>/queues/<agent>/<state>/*.json``.

We deliberately keep this trivial — counting JSON files in directories. The
upstream code did more (mtime caching), which we may add later if profiling
shows it's needed.
"""
from __future__ import annotations

from pathlib import Path

from .. import config
from .models import QueueDepth


def count_queue_files(session_root: Path, agent: str, state: str) -> int:
    """Count ``*.json`` files in ``<session_root>/queues/<agent>/<state>/``.

    Returns 0 if the directory doesn't exist (this is normal for empty
    sessions / undiscovered agents).
    """
    queue_dir = session_root / config.QUEUE_SUBDIR / agent / state
    if not queue_dir.is_dir():
        return 0
    count = 0
    for entry in queue_dir.iterdir():
        if entry.is_file() and entry.name.endswith(".json"):
            count += 1
    return count


def queue_depths(session_root: Path, agents: tuple[str, ...] | None = None) -> dict[str, QueueDepth]:
    """Compute depths for every known queue state, per agent.

    If ``agents`` is omitted, we scan the queue root for present agent dirs and
    fall back to ``KNOWN_AGENTS``.
    """
    queue_root = session_root / config.QUEUE_SUBDIR
    if agents is None:
        if queue_root.is_dir():
            scanned = tuple(sorted(p.name for p in queue_root.iterdir() if p.is_dir()))
            agents = scanned or config.KNOWN_AGENTS
        else:
            agents = config.KNOWN_AGENTS

    out: dict[str, QueueDepth] = {}
    for agent in agents:
        out[agent] = QueueDepth(
            inbox=count_queue_files(session_root, agent, "inbox"),
            processing=count_queue_files(session_root, agent, "processing"),
            processed=count_queue_files(session_root, agent, "processed"),
            dead=count_queue_files(session_root, agent, "dead"),
        )
    return out
