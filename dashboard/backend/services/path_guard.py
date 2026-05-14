"""Path traversal defense per plan A11.

Three layered checks:
    1. ``Path.resolve()`` — collapses ``..`` and follows symlinks.
    2. ``is_relative_to(root)`` — final target must stay inside root.
    3. ``walk_up_check`` — every ancestor up to root must NOT be a symlink
       pointing outside root. This catches the case where an attacker drops
       a symlinked subdirectory inside a session directory.

The threat model includes a malicious or misconfigured orchestrator placing a
symlink in a session directory that resolves into ``/etc`` (or any path outside
``SESSIONS_ROOT``).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException


class PathGuardError(HTTPException):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(status_code=status_code, detail=detail)


def walk_up_check(target: Path, root: Path) -> None:
    """Reject if any directory between ``target`` and ``root`` is a symlink
    pointing outside ``root``.
    """
    root_resolved = root.resolve()
    cur = target
    while True:
        if cur.is_symlink():
            link_target = cur.resolve()
            if not link_target.is_relative_to(root_resolved):
                raise PathGuardError("symlink escapes session root")
        if cur == root_resolved or cur.parent == cur:
            break
        cur = cur.parent


def safe_join(root: Path, rel: str) -> Path:
    """Resolve ``root / rel`` and verify it stays inside ``root``.

    ``rel`` is treated as a relative path; absolute paths are rejected.
    URL-encoded forms like ``..%2F`` are decoded by the framework before
    reaching here, so we operate on the decoded representation.
    """
    if rel.startswith("/"):
        raise PathGuardError("absolute path not allowed")
    root_resolved = root.resolve()
    candidate = (root_resolved / rel).resolve()
    if not candidate.is_relative_to(root_resolved):
        raise PathGuardError("path traversal blocked")
    walk_up_check(candidate, root_resolved)
    return candidate


def safe_session_path(sessions_root: Path, session: str, rel: str = "") -> Path:
    """Resolve a path inside one session directory."""
    if "/" in session or session in ("", ".", ".."):
        raise PathGuardError("invalid session name")
    session_root = (sessions_root.resolve() / session).resolve()
    if not session_root.is_relative_to(sessions_root.resolve()):
        raise PathGuardError("invalid session name")
    if not session_root.exists():
        raise PathGuardError("session not found", status_code=404)
    if not rel:
        walk_up_check(session_root, sessions_root.resolve())
        return session_root
    return safe_join(session_root, rel)
