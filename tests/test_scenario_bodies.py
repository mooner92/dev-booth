"""v6 body skeleton enforcement — every stage body must:

- carry the file-reading rule (`head -n` / `tail -n`) so 5-turn budget holds,
- contain a kanban_complete() example with non-empty metadata,
- (review-gated stages + implementation stages) also contain a kanban_block() example,
- format cleanly with the ctx core/session.py builds (no KeyError),
- stay under 2 000 chars (~500 tokens) before the optional skills tail.

The v6 (micro-task) gate replaces the v5 12-stage-skeleton gate.
"""
from __future__ import annotations

import re

import pytest

from core.scenario import STAGE_DAG, SKILL_USE_CASES, format_task, ALLOWED_ASSIGNEES


CTX = {
    "repo":             "firebase-chat-exp",
    "repo_url":         "https://github.com/mooner92/firebase-chat-exp",
    "goal":             "코드 품질 개선 및 버그 수정",
    "session":          "demo",
    "session_path":     "/dev-booth/sessions/demo",
    "n":                1,
    "task_description": "initial implementation",
}


@pytest.mark.parametrize("stage", STAGE_DAG, ids=lambda s: f"stage-{s.stage}")
def test_body_renders_without_keyerror(stage):
    rendered = format_task(stage, **CTX)
    assert isinstance(rendered["body"], str) and len(rendered["body"]) > 200
    unresolved = re.findall(r"(?<!\{)\{[a-zA-Z_][a-zA-Z0-9_]*\}(?!\})", rendered["body"])
    assert not unresolved, f"stage {stage.stage} body has unresolved placeholders: {unresolved}"


@pytest.mark.parametrize("stage", STAGE_DAG, ids=lambda s: f"stage-{s.stage}")
def test_body_has_file_reading_rule(stage):
    """v6 contract: every body must teach the worker the head/tail rule."""
    body = format_task(stage, **CTX)["body"]
    assert "head -n" in body or "tail -n" in body, (
        f"stage {stage.stage} missing 'head -n' / 'tail -n' file-reading rule"
    )


@pytest.mark.parametrize("stage", STAGE_DAG, ids=lambda s: f"stage-{s.stage}")
def test_body_has_completion_block(stage):
    body = format_task(stage, **CTX)["body"]
    assert "kanban_complete(" in body, f"stage {stage.stage} missing kanban_complete( call"
    assert "metadata=" in body, f"stage {stage.stage} kanban_complete missing metadata kwarg"
    assert "## 완료" in body, f"stage {stage.stage} missing '## 완료' header"


@pytest.mark.parametrize("stage", STAGE_DAG, ids=lambda s: f"stage-{s.stage}")
def test_body_template_size_budget(stage):
    """v6 invariant: raw template stays ≤2000 chars (~500 tokens) so a 5-turn
    agent budget can absorb it without crowding out the actual work."""
    assert len(stage.body_template) <= 2000, (
        f"stage {stage.stage} body_template is {len(stage.body_template)}B > 2000B budget"
    )


@pytest.mark.parametrize(
    "stage",
    [s for s in STAGE_DAG if s.is_review_gate or s.tag == "implementation"],
    ids=lambda s: f"stage-{s.stage}",
)
def test_review_and_implementation_have_block_pathway(stage):
    """Review-gated stages and implementation stages MUST tell the worker how
    to block, or they fall into protocol_violation when the work fails."""
    body = format_task(stage, **CTX)["body"]
    assert "kanban_block(" in body, f"stage {stage.stage} missing kanban_block( pathway"
    assert "## 막힐 때" in body, f"stage {stage.stage} missing '## 막힐 때' header"


def test_all_assignees_valid():
    for s in STAGE_DAG:
        assert s.assignee in ALLOWED_ASSIGNEES, (
            f"stage {s.stage} assignee {s.assignee!r} not in {sorted(ALLOWED_ASSIGNEES)}"
        )


def test_dag_is_21_stages():
    """v6: the micro-task work is shaped against the 21-stage scenario."""
    stages = sorted(s.stage for s in STAGE_DAG)
    assert stages == list(range(1, 22)), f"DAG must be 1..21, got {stages}"


def test_every_stage_skills_known():
    for s in STAGE_DAG:
        for skill in s.skills:
            assert skill in SKILL_USE_CASES, (
                f"stage {s.stage}: '{skill}' missing from SKILL_USE_CASES"
            )


@pytest.mark.parametrize("stage", [s for s in STAGE_DAG if s.skills], ids=lambda s: f"stage-{s.stage}")
def test_body_has_skills_section_when_assigned(stage):
    body = format_task(stage, **CTX)["body"]
    assert "## 활용 가능한 스킬" in body, f"stage {stage.stage} missing skills section"
    for skill in stage.skills:
        assert skill in body, f"stage {stage.stage} skills section missing '{skill}'"


def test_body_omits_skills_section_when_empty():
    from core.scenario import StageTask
    synthetic = StageTask(
        stage=99, title="x", assignee="conductor",
        workspace="worktree", tag="orchestration",
        body_template="## 작업\nnoop\n\n## 완료\nkanban_complete(summary='x', metadata={{}})\nhead -n 10\n",
        skills=[],
    )
    body = format_task(synthetic, **CTX)["body"]
    assert "## 활용 가능한 스킬" not in body
