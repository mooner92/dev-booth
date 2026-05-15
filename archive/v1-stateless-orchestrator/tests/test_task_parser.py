"""US-005 — parse_tasks(): tolerant improvements.md -> Task list."""
from __future__ import annotations

from core.orchestrator import Task, parse_tasks


def test_well_formed():
    md = (
        "# Improvements\n"
        "- [TASK-001] @hermes-b: fix the null check in auth.js\n"
        "- [TASK-002] @hermes-a: refactor the routing module\n"
        "- [TASK-003] @hermes-b: add input validation\n"
    )
    tasks = parse_tasks(md)
    assert [t.task_id for t in tasks] == ["TASK-001", "TASK-002", "TASK-003"]
    assert tasks[0].assignee == "hermes-b"
    assert tasks[1].assignee == "hermes-a"
    assert tasks[0].description == "fix the null check in auth.js"
    assert all(t.status == "pending" for t in tasks)


def test_missing_assignee_defaults_to_hermes_b():
    md = "- [TASK-007]: do the thing\n[TASK-008] another thing\n"
    tasks = parse_tasks(md)
    assert len(tasks) == 2
    assert all(t.assignee == "hermes-b" for t in tasks)


def test_malformed_lines_skipped():
    md = (
        "just some prose\n"
        "## a heading\n"
        "- [TASK-001] @hermes-b: real task\n"
        "- not a task at all\n"
        "TASKX-9 bad id\n"
    )
    tasks = parse_tasks(md)
    assert len(tasks) == 1
    assert tasks[0].task_id == "TASK-001"


def test_empty_input_returns_empty_list():
    assert parse_tasks("") == []
    assert parse_tasks("no tasks here\njust text\n") == []


def test_case_insensitive_id_and_assignee():
    md = "- [task-042] @HERMES-A: mixed case\n"
    tasks = parse_tasks(md)
    assert len(tasks) == 1
    assert tasks[0].task_id == "TASK-042"
    assert tasks[0].assignee == "hermes-a"


def test_task_dataclass_defaults():
    t = Task("TASK-100", "hermes-b", "desc")
    assert t.status == "pending"
