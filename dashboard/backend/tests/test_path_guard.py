"""Path traversal defense tests (A11, C12)."""
from __future__ import annotations

from pathlib import Path

import pytest

from dashboard.backend.services.path_guard import (
    PathGuardError,
    safe_join,
    safe_session_path,
)


def test_safe_join_normal(tmp_path: Path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "file.txt").write_text("ok")
    resolved = safe_join(tmp_path, "sub/file.txt")
    assert resolved == (tmp_path / "sub" / "file.txt").resolve()


def test_safe_join_traversal_blocked(tmp_path: Path):
    # ..-style traversal must fail even if the path resolves to something outside root
    with pytest.raises(PathGuardError):
        safe_join(tmp_path, "../etc/passwd")


def test_safe_join_absolute_blocked(tmp_path: Path):
    with pytest.raises(PathGuardError):
        safe_join(tmp_path, "/etc/passwd")


def test_safe_join_url_encoded_decoded_path(tmp_path: Path):
    # Framework decodes %2F to / before reaching us — but we still must catch the resulting traversal.
    with pytest.raises(PathGuardError):
        safe_join(tmp_path, "../../etc/passwd")


def test_symlink_ancestor_outside_root(tmp_path: Path):
    # session root structure: sessions/<name>/some/dir/file.txt
    # Place a symlink "outside" pointing to /tmp, then under it have file.txt
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("nope")

    sessions = tmp_path / "sessions"
    sessions.mkdir()
    session = sessions / "test"
    session.mkdir()
    bad_link = session / "evil"
    bad_link.symlink_to(outside)

    with pytest.raises(PathGuardError):
        safe_session_path(sessions, "test", "evil/secret.txt")


def test_invalid_session_name(tmp_path: Path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    with pytest.raises(PathGuardError):
        safe_session_path(sessions, "../etc", "")
    with pytest.raises(PathGuardError):
        safe_session_path(sessions, "..", "")
    with pytest.raises(PathGuardError):
        safe_session_path(sessions, "a/b", "")


def test_session_path_404(tmp_path: Path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    with pytest.raises(PathGuardError) as exc:
        safe_session_path(sessions, "missing", "")
    assert exc.value.status_code == 404
