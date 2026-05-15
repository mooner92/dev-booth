"""Tests for core/watchdog.py — Phase 4 of stabilization v5.

The watchdog is a diagnostic backstop: when a task is `running` but the latest
attempt ended without a lifecycle call (and Hermes' own auto-block hasn't yet
fired), transition the task to `blocked` so it stops looking stuck.
"""
from __future__ import annotations

from unittest.mock import patch

from core.watchdog import (
    _is_protocol_violation,
    _latest_run,
    reap_protocol_violations,
)


def test_latest_run_picks_highest_attempt():
    runs = [
        {"attempt": 1, "outcome": "crashed"},
        {"attempt": 2, "outcome": "running"},
    ]
    assert _latest_run(runs)["attempt"] == 2
    assert _latest_run([]) is None


def test_is_protocol_violation_positive():
    """status=running + latest run ended + outcome neither completed nor blocked."""
    task = {"status": "running"}
    latest = {"attempt": 1, "outcome": "crashed"}
    assert _is_protocol_violation(task, latest) is True


def test_is_protocol_violation_skips_in_flight():
    """An attempt is still running -- do not reap."""
    task = {"status": "running"}
    latest = {"attempt": 2, "outcome": "running"}
    assert _is_protocol_violation(task, latest) is False


def test_is_protocol_violation_skips_completed():
    task = {"status": "running"}
    latest = {"attempt": 3, "outcome": "completed"}
    assert _is_protocol_violation(task, latest) is False


def test_is_protocol_violation_skips_blocked():
    task = {"status": "running"}
    latest = {"attempt": 1, "outcome": "blocked"}
    assert _is_protocol_violation(task, latest) is False


def test_is_protocol_violation_skips_non_running_task():
    """Task already in a terminal state shouldn't be touched."""
    task = {"status": "done"}
    latest = {"attempt": 1, "outcome": "completed"}
    assert _is_protocol_violation(task, latest) is False


# ---------------------------------------------------------------- integration


class _FakeReader:
    """Standin for KanbanReader so the test never touches sqlite/subprocess."""

    def __init__(self, tasks, runs_by_task):
        self.exists = True
        self.db_path = "/tmp/test-board/kanban.db"
        self._tasks = tasks
        self._runs = runs_by_task

    def list_tasks(self, status=None):
        return [t for t in self._tasks if status is None or t.get("status") == status]

    def get_runs(self, task_id):
        return self._runs.get(task_id, [])


def test_reap_blocks_stuck_running_task():
    tasks = [
        {"id": "t_a", "status": "running", "title": "A"},
        {"id": "t_b", "status": "running", "title": "B"},
        {"id": "t_c", "status": "done", "title": "C"},
    ]
    runs = {
        "t_a": [{"attempt": 1, "outcome": "crashed"}],          # stuck → reap
        "t_b": [{"attempt": 1, "outcome": "crashed"},
                {"attempt": 2, "outcome": "running"}],          # retrying → skip
        "t_c": [{"attempt": 1, "outcome": "completed"}],
    }
    reader = _FakeReader(tasks, runs)

    with patch("core.watchdog._block_task") as mock_block:
        reaped = reap_protocol_violations("test-board", reader=reader)

    assert reaped == ["t_a"]
    mock_block.assert_called_once()
    call_kwargs = mock_block.call_args
    assert call_kwargs.args[1] == "t_a"
    assert "protocol_violation" in call_kwargs.args[2]


def test_reap_is_idempotent_when_no_targets():
    """After a successful first run, subsequent calls reap nothing."""
    tasks = [{"id": "t_a", "status": "blocked", "title": "A (already blocked)"}]
    reader = _FakeReader(tasks, {"t_a": [{"attempt": 1, "outcome": "crashed"}]})
    with patch("core.watchdog._block_task") as mock_block:
        reaped = reap_protocol_violations("test-board", reader=reader)
    assert reaped == []
    mock_block.assert_not_called()


def test_reap_dry_run_does_not_block():
    tasks = [{"id": "t_a", "status": "running", "title": "A"}]
    reader = _FakeReader(tasks, {"t_a": [{"attempt": 1, "outcome": "crashed"}]})
    with patch("core.watchdog._block_task") as mock_block:
        reaped = reap_protocol_violations("test-board", dry_run=True, reader=reader)
    assert reaped == ["t_a"]
    mock_block.assert_not_called()


def test_reap_missing_board_returns_empty():
    class _GhostReader:
        exists = False
        db_path = "/nonexistent"
    assert reap_protocol_violations("ghost", reader=_GhostReader()) == []
