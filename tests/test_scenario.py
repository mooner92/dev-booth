"""Phase 1 — core/scenario.py: the static 21-stage micro DAG is well-formed (v6)."""
from __future__ import annotations

from core.scenario import (
    ALLOWED_ASSIGNEES,
    STAGE_DAG,
    STAGE_NARRATION,
    format_task,
    get_stage,
)

_VALID_WORKSPACES = ("worktree", "scratch")
_EXPECTED_LEN = 21


def test_dag_is_21_stages_numbered_1_to_21():
    assert len(STAGE_DAG) == _EXPECTED_LEN
    assert [s.stage for s in STAGE_DAG] == list(range(1, _EXPECTED_LEN + 1))


def test_narration_corpus_covers_all_stages():
    assert sorted(STAGE_NARRATION.keys()) == list(range(1, _EXPECTED_LEN + 1))
    assert all(isinstance(v, str) and v.strip() for v in STAGE_NARRATION.values())


def test_every_assignee_is_a_real_profile():
    for s in STAGE_DAG:
        assert s.assignee in ALLOWED_ASSIGNEES, (
            f"stage {s.stage} assignee {s.assignee!r} not in {sorted(ALLOWED_ASSIGNEES)}"
        )


def test_workspace_kinds_are_valid_and_git_stages_use_worktree():
    for s in STAGE_DAG:
        kind = s.workspace.split(":")[0]
        assert kind in (*_VALID_WORKSPACES, "dir"), f"stage {s.stage} bad workspace {s.workspace!r}"
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
    ctx = dict(repo="acme", repo_url="https://github.com/x/acme", goal="g",
               session="sess", session_path="/dev-booth/sessions/sess",
               n=1, task_description="impl")
    for s in STAGE_DAG:
        params = format_task(s, **ctx)
        assert params["title"] and "{repo}" not in params["title"]
        assert params["assignee"] in ALLOWED_ASSIGNEES
        assert params["workspace"] == "worktree"
        body = params["body"]
        assert body
        for tok in ("{repo}", "{repo_url}", "{goal}", "{session}",
                    "{session_path}", "{n}", "{task_description}"):
            assert tok not in body, f"unresolved {tok} in stage {s.stage} body"


def test_get_stage():
    assert get_stage(1).stage == 1
    assert get_stage(_EXPECTED_LEN).stage == _EXPECTED_LEN
    assert get_stage(99) is None


def test_stage_1_and_last_are_conductor():
    assert STAGE_DAG[0].assignee == "conductor"
    assert STAGE_DAG[-1].assignee == "conductor"


def test_analysis_stages_assigned_only_to_architect_or_executor():
    analysis = [s for s in STAGE_DAG if s.tag == "analysis"]
    assert len(analysis) >= 5, f"expected ≥5 analysis stages, got {len(analysis)}"
    for s in analysis:
        assert s.assignee in {"architect", "executor"}, (
            f"analysis stage {s.stage} assigned to {s.assignee!r} (conductor is reserved for orchestration)"
        )


def test_two_task_iterations_with_review_gates():
    """v6: TASK-1 impl/test/review + TASK-2 impl/test/review = 6 stages."""
    task1 = [s for s in STAGE_DAG if "TASK-1" in s.title]
    task2 = [s for s in STAGE_DAG if "TASK-2" in s.title]
    assert len(task1) == 3 and len(task2) == 3
    assert any(s.is_review_gate for s in task1)
    assert any(s.is_review_gate for s in task2)
    # TASK-1 review must gate TASK-2 implementation
    task1_review = next(s for s in task1 if s.is_review_gate)
    task2_impl = next(s for s in task2 if s.tag == "implementation" and "구현" in s.title)
    assert task1_review.stage in task2_impl.parent_stages, (
        f"TASK-2 impl (stage {task2_impl.stage}) must depend on TASK-1 review "
        f"(stage {task1_review.stage}); current parents = {task2_impl.parent_stages}"
    )
