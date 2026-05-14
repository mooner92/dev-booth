from __future__ import annotations

from dashboard.backend.services import awg_inspector


def test_count_queue_files_empty(make_session, tmp_sessions_root):
    root = make_session("empty")
    assert awg_inspector.count_queue_files(root, "hermes-a", "inbox") == 0


def test_count_queue_files_with_messages(make_session, tmp_sessions_root):
    root = make_session("busy", queue_files={
        ("hermes-a", "inbox"): 3,
        ("hermes-a", "processing"): 1,
        ("openclaw", "dead"): 2,
    })
    assert awg_inspector.count_queue_files(root, "hermes-a", "inbox") == 3
    assert awg_inspector.count_queue_files(root, "hermes-a", "processing") == 1
    assert awg_inspector.count_queue_files(root, "openclaw", "dead") == 2
    assert awg_inspector.count_queue_files(root, "openclaw", "inbox") == 0


def test_queue_depths_all_agents(make_session, tmp_sessions_root):
    root = make_session("multi", queue_files={
        ("hermes-a", "inbox"): 1,
        ("hermes-b", "processing"): 2,
        ("openclaw", "processed"): 5,
    })
    depths = awg_inspector.queue_depths(root)
    assert depths["hermes-a"].inbox == 1
    assert depths["hermes-b"].processing == 2
    assert depths["openclaw"].processed == 5
    assert depths["openclaw"].inbox == 0
