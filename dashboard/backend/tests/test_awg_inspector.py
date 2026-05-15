from __future__ import annotations

from dashboard.backend.services import awg_inspector


def test_count_queue_files_empty(make_session, tmp_sessions_root):
    root = make_session("empty")
    assert awg_inspector.count_queue_files(root, "architect", "inbox") == 0


def test_count_queue_files_with_messages(make_session, tmp_sessions_root):
    root = make_session("busy", queue_files={
        ("architect", "inbox"): 3,
        ("architect", "processing"): 1,
        ("conductor", "dead"): 2,
    })
    assert awg_inspector.count_queue_files(root, "architect", "inbox") == 3
    assert awg_inspector.count_queue_files(root, "architect", "processing") == 1
    assert awg_inspector.count_queue_files(root, "conductor", "dead") == 2
    assert awg_inspector.count_queue_files(root, "conductor", "inbox") == 0


def test_queue_depths_all_agents(make_session, tmp_sessions_root):
    root = make_session("multi", queue_files={
        ("architect", "inbox"): 1,
        ("executor", "processing"): 2,
        ("conductor", "processed"): 5,
    })
    depths = awg_inspector.queue_depths(root)
    assert depths["architect"].inbox == 1
    assert depths["executor"].processing == 2
    assert depths["conductor"].processed == 5
    assert depths["conductor"].inbox == 0
