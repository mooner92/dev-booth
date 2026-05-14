"""Session directory layout adapter (ADR-005).

The dashboard reads only the ``queues/`` form (per ADR-005). The legacy ``awg/``
form is ignored. The log file lives at ``<session>/log/messages.jsonl``.

Anything that needs to know "where does X live in a session directory" goes
through this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .. import config


@dataclass(frozen=True)
class SessionLayout:
    name: str
    root: Path
    log_path: Path
    queue_root: Path
    agents: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_log(self) -> bool:
        return self.log_path.exists()

    @property
    def has_queues(self) -> bool:
        return self.queue_root.is_dir()


def _detect_agents(queue_root: Path) -> tuple[str, ...]:
    if not queue_root.is_dir():
        return ()
    detected = sorted(p.name for p in queue_root.iterdir() if p.is_dir())
    if detected:
        return tuple(detected)
    return config.KNOWN_AGENTS


def resolve(name: str, sessions_root: Path | None = None) -> SessionLayout:
    root = (sessions_root or config.SESSIONS_ROOT).resolve()
    session_root = (root / name).resolve()
    if not session_root.is_relative_to(root):
        raise ValueError(f"session name {name!r} escapes sessions root")
    log_path = session_root / config.LOG_SUBDIR / config.LOG_FILENAME
    queue_root = session_root / config.QUEUE_SUBDIR
    agents = _detect_agents(queue_root)
    return SessionLayout(
        name=name,
        root=session_root,
        log_path=log_path,
        queue_root=queue_root,
        agents=agents,
    )


def list_session_names(sessions_root: Path | None = None) -> list[str]:
    root = (sessions_root or config.SESSIONS_ROOT).resolve()
    if not root.is_dir():
        return []
    names: list[str] = []
    for entry in root.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            names.append(entry.name)
    return sorted(names)


def iter_layouts(sessions_root: Path | None = None) -> Iterable[SessionLayout]:
    for name in list_session_names(sessions_root):
        yield resolve(name, sessions_root)
