from __future__ import annotations

from dashboard.backend.services import session_layout


def test_resolve_queues_only(tmp_sessions_root, make_session):
    make_session("alpha", messages=[], queue_files={("hermes-a", "inbox"): 2})
    layout = session_layout.resolve("alpha", tmp_sessions_root)
    assert layout.name == "alpha"
    assert layout.has_log is True
    assert layout.has_queues is True
    assert "hermes-a" in layout.agents


def test_resolve_empty_session(tmp_sessions_root):
    (tmp_sessions_root / "empty").mkdir()
    layout = session_layout.resolve("empty", tmp_sessions_root)
    assert layout.has_log is False
    assert layout.has_queues is False


def test_list_sessions(tmp_sessions_root, make_session):
    make_session("alpha")
    make_session("beta")
    (tmp_sessions_root / ".hidden").mkdir()  # should be ignored
    names = session_layout.list_session_names(tmp_sessions_root)
    assert names == ["alpha", "beta"]


def test_resolve_rejects_escape(tmp_sessions_root):
    import pytest
    with pytest.raises(ValueError):
        session_layout.resolve("../escape", tmp_sessions_root)
