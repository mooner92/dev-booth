"""Phase 1 — core/scenario.py: the static 12-stage DAG is well-formed."""
from __future__ import annotations

from core.scenario import (
    ALLOWED_ASSIGNEES,
    STAGE_DAG,
    STAGE_NARRATION,
    format_task,
    get_stage,
)

_VALID_WORKSPACES = ("worktree", "scratch")


def test_dag_has_twelve_stages_numbered_1_to_12():
    assert len(STAGE_DAG) == 12
    assert [s.stage for s in STAGE_DAG] == list(range(1, 13))


def test_narration_corpus_has_twelve_entries():
    assert sorted(STAGE_NARRATION.keys()) == list(range(1, 13))
    assert all(isinstance(v, str) and v.strip() for v in STAGE_NARRATION.values())


def test_every_assignee_is_a_real_profile():
    # the dispatcher silently never spawns unknown assignees — guard at the source
    for s in STAGE_DAG:
        assert s.assignee in ALLOWED_ASSIGNEES, (
            f"stage {s.stage} assignee {s.assignee!r} not in {sorted(ALLOWED_ASSIGNEES)}"
        )


def test_workspace_kinds_are_valid_and_git_stages_use_worktree():
    for s in STAGE_DAG:
        kind = s.workspace.split(":")[0]
        assert kind in (*_VALID_WORKSPACES, "dir"), f"stage {s.stage} bad workspace {s.workspace!r}"
        # every Dev-Booth stage touches a git repo → must be worktree (not scratch)
        assert s.workspace == "worktree", (
            f"stage {s.stage} should use --workspace worktree, got {s.workspace!r}"
        )


def test_dag_is_acyclic_parents_precede_children():
    for s in STAGE_DAG:
        for p in s.parent_stages:
            assert 1 <= p < s.stage, (
                f"stage {s.stage} has parent {p} that is not a strictly-earlier stage"
            )


def test_parent_links_reference_real_stages():
    valid = {s.stage for s in STAGE_DAG}
    for s in STAGE_DAG:
        for p in s.parent_stages:
            assert p in valid


def test_review_gate_flag_set_on_review_stage():
    review_stages = [s for s in STAGE_DAG if s.is_review_gate]
    assert len(review_stages) >= 1
    assert all(s.tag == "review" for s in review_stages)


def test_format_task_renders_without_keyerror():
    # a missing template var would raise KeyError here; that's the real check.
    # v5: session_path is part of the ctx core/session.py builds — bodies use
    # it for absolute artifact paths (Problem 2 fix).
    ctx = dict(repo="acme", repo_url="https://github.com/x/acme", goal="g",
               session="sess", session_path="/dev-booth/sessions/sess",
               n=1, task_description="impl")
    for s in STAGE_DAG:
        params = format_task(s, **ctx)
        # title only templates {repo} — must be fully resolved
        assert params["title"] and "{repo}" not in params["title"]
        assert params["assignee"] in ALLOWED_ASSIGNEES
        assert params["workspace"] == "worktree"
        # body must be non-empty and carry no unresolved tokens
        # (literal JSON braces from {{...}} are fine — they are intended output)
        body = params["body"]
        assert body
        for tok in ("{repo}", "{repo_url}", "{goal}", "{session}",
                    "{session_path}", "{n}", "{task_description}"):
            assert tok not in body, f"unresolved {tok} in stage {s.stage} body"


def test_get_stage():
    assert get_stage(1).stage == 1
    assert get_stage(12).stage == 12
    assert get_stage(99) is None
