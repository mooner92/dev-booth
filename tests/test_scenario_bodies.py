"""v5 body skeleton enforcement — every stage body must:

- carry the absolute artifact paths the worker reads/writes,
- contain a kanban_complete() example with non-empty metadata,
- (review-gated stages) also contain a kanban_block() example,
- format cleanly with the ctx core/session.py builds (no KeyError).

This is the regression gate against Problem 1 (protocol_violation) +
Problem 2 (path confusion) + Problem 3 (template-leak) — every regression
that surfaces in production after v5 should add a row here, not weaken the
existing assertions.
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
    """format_task() resolves every {placeholder} the body contains."""
    rendered = format_task(stage, **CTX)
    assert isinstance(rendered["body"], str) and len(rendered["body"]) > 200
    # No unresolved braces remain after .format() (escaped {{}} render as {})
    # — we only check for the unescaped form `{xxx}` that would indicate a
    # missed key.
    unresolved = re.findall(r"(?<!\{)\{[a-zA-Z_][a-zA-Z0-9_]*\}(?!\})", rendered["body"])
    assert not unresolved, f"stage {stage.stage} body has unresolved placeholders: {unresolved}"


@pytest.mark.parametrize("stage", STAGE_DAG, ids=lambda s: f"stage-{s.stage}")
def test_body_has_environment_section(stage):
    """Every body must carry the '## 환경 정보' section with absolute paths."""
    body = format_task(stage, **CTX)["body"]
    assert "## 환경 정보" in body, f"stage {stage.stage} missing '## 환경 정보' section"


@pytest.mark.parametrize("stage", STAGE_DAG, ids=lambda s: f"stage-{s.stage}")
def test_body_has_completion_block(stage):
    """Every body must show the exact kanban_complete() shape with metadata."""
    body = format_task(stage, **CTX)["body"]
    assert "kanban_complete(" in body, f"stage {stage.stage} missing kanban_complete( call"
    # The closing rule heading is the marker for the v5 skeleton. Review-gated
    # stages (e.g. stage 9) split it into pass/fail variants — accept either by
    # matching the '## ⚠️ 완료 시' prefix.
    assert "## ⚠️ 완료 시" in body, (
        f"stage {stage.stage} missing '## ⚠️ 완료 시 …' completion header"
    )
    assert "metadata=" in body, f"stage {stage.stage} kanban_complete missing metadata kwarg"


@pytest.mark.parametrize("stage", [s for s in STAGE_DAG if s.assignee == "architect" or s.stage == 8],
                         ids=lambda s: f"stage-{s.stage}")
def test_review_or_implementation_has_block_pathway(stage):
    """Review stages (architect) + the implementation stage MUST tell the worker
    how to block. Otherwise it has no escape hatch and falls into protocol_violation."""
    body = format_task(stage, **CTX)["body"]
    assert "kanban_block(" in body, f"stage {stage.stage} missing kanban_block( pathway"
    assert "## 막힐 때" in body, f"stage {stage.stage} missing '## 막힐 때' header"


def test_all_assignees_valid():
    """The dispatcher silently drops unknown assignees — guard the canonical set."""
    for s in STAGE_DAG:
        assert s.assignee in ALLOWED_ASSIGNEES, (
            f"stage {s.stage} assignee {s.assignee!r} not in {sorted(ALLOWED_ASSIGNEES)}"
        )


def test_dag_has_twelve_stages():
    """Sanity: the v5 work is shaped against the 12-stage scenario."""
    stages = sorted(s.stage for s in STAGE_DAG)
    assert stages == list(range(1, 13)), f"DAG must be 1..12, got {stages}"


def test_every_stage_skills_known():
    """Every skill name used in any stage has an entry in SKILL_USE_CASES."""
    for s in STAGE_DAG:
        for skill in s.skills:
            assert skill in SKILL_USE_CASES, (
                f"stage {s.stage}: '{skill}' missing from SKILL_USE_CASES"
            )


@pytest.mark.parametrize("stage", [s for s in STAGE_DAG if s.skills], ids=lambda s: f"stage-{s.stage}")
def test_body_has_skills_section_when_assigned(stage):
    """Every stage with non-empty skills renders the section + every named skill."""
    body = format_task(stage, **CTX)["body"]
    assert "## 활용 가능한 스킬" in body, f"stage {stage.stage} missing skills section"
    for skill in stage.skills:
        assert skill in body, f"stage {stage.stage} skills section missing '{skill}'"


def test_body_omits_skills_section_when_empty():
    """A synthetic stage with skills=[] does NOT render the section header (no blank heading)."""
    from core.scenario import StageTask
    synthetic = StageTask(
        stage=99, title="x", assignee="conductor",
        workspace="worktree", tag="orchestration",
        body_template="## 작업\nnoop\n\n## 환경 정보\n- none\n",
        skills=[],
    )
    body = format_task(synthetic, **CTX)["body"]
    assert "## 활용 가능한 스킬" not in body
