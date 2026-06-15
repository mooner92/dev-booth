"""Phase 3 — core/session.py: board setup + 12-stage DAG seeding (mocked CLI)."""
from __future__ import annotations

import json
from unittest import mock

import pytest

from core import session as session_mod
from core.session import DevBoothSession


@pytest.fixture
def sess(tmp_path, monkeypatch):
    monkeypatch.setattr(session_mod, "SESSIONS_ROOT", tmp_path)
    return DevBoothSession("test-sess", "https://github.com/mooner92/firebase-chat-exp", "버그 수정")


# ----------------------------------------------------------------- __init__
def test_init_derives_board_slug_and_repo_name(sess):
    assert sess.board_slug == "test-sess"
    assert sess.repo_name == "firebase-chat-exp"
    assert sess.session_path.name == "test-sess"


def test_board_slug_normalizes_underscores_and_spaces(tmp_path, monkeypatch):
    monkeypatch.setattr(session_mod, "SESSIONS_ROOT", tmp_path)
    s = DevBoothSession("My_Cool Session", "https://github.com/x/y.git", "g")
    assert s.board_slug == "my-cool-session"
    assert s.repo_name == "y"


# -------------------------------------------------------------------- setup
def test_setup_creates_dirs_and_board(sess):
    calls = []

    def fake_kanban(*args):
        calls.append(args)
        return ""

    with mock.patch.object(sess, "_kanban", side_effect=fake_kanban), \
         mock.patch.object(sess, "_kanban_json", return_value=[]), \
         mock.patch.object(sess, "_ensure_clone"):  # network op — mocked in unit tests
        sess.setup()

    assert sess.session_path.is_dir()
    assert (sess.session_path / "log").is_dir()
    assert (sess.session_path / "status.json").is_file()
    # board create called with the slug positionally (NOT --board)
    assert any(c[:2] == ("boards", "create") and "test-sess" in c for c in calls)


def test_setup_skips_board_create_if_exists(sess):
    calls = []
    with mock.patch.object(sess, "_kanban", side_effect=lambda *a: calls.append(a) or ""), \
         mock.patch.object(sess, "_kanban_json", return_value=[{"slug": "test-sess"}]), \
         mock.patch.object(sess, "_ensure_clone"):
        sess.setup()
    assert not any(c[:2] == ("boards", "create") for c in calls)


def test_setup_calls_ensure_clone_before_seed(sess):
    """The deterministic clone must run during setup (model-independent guarantee)."""
    order = []
    with mock.patch.object(sess, "_kanban", side_effect=lambda *a: ""), \
         mock.patch.object(sess, "_kanban_json", return_value=[]), \
         mock.patch.object(sess, "_ensure_clone", side_effect=lambda: order.append("clone")), \
         mock.patch.object(sess, "seed", side_effect=lambda: order.append("seed")):
        sess.setup()
    assert order == ["clone", "seed"]  # clone BEFORE any stage is seeded


# -------------------------------------------------------------- _ensure_clone
def test_ensure_clone_skips_when_already_present(sess):
    (sess.session_path / "project" / ".git").mkdir(parents=True)
    with mock.patch.object(session_mod.subprocess, "run") as run:
        sess._ensure_clone()
    run.assert_not_called()  # idempotent no-op — never shells out


def test_ensure_clone_clones_fork_and_checks_out_develop(sess):
    project = sess.session_path / "project"

    def fake_run(cmd, *a, **k):
        # gh repo view (fork exists) -> rc 0; gh repo clone -> create .git; git checkout -> rc 0
        if cmd[:3] == ["gh", "repo", "clone"]:
            (project / ".git").mkdir(parents=True, exist_ok=True)
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch.object(session_mod.subprocess, "run", side_effect=fake_run) as run:
        sess._ensure_clone()
    cmds = [c.args[0] for c in run.call_args_list]
    assert ["gh", "repo", "view", "CrownClownCrowd/firebase-chat-exp"] in cmds
    assert any(c[:3] == ["gh", "repo", "clone"] and "CrownClownCrowd/firebase-chat-exp" in c for c in cmds)
    assert any(c[:3] == ["git", "-C", str(project)] and c[3:] == ["checkout", "-B", "develop"] for c in cmds)


def test_ensure_clone_falls_back_to_upstream_when_fork_absent(sess):
    project = sess.session_path / "project"

    def fake_run(cmd, *a, **k):
        if cmd[:3] == ["gh", "repo", "view"]:
            return mock.Mock(returncode=1, stdout="", stderr="not found")  # fork absent
        if cmd[:3] == ["gh", "repo", "clone"]:
            (project / ".git").mkdir(parents=True, exist_ok=True)
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch.object(session_mod.subprocess, "run", side_effect=fake_run) as run:
        sess._ensure_clone()
    cmds = [c.args[0] for c in run.call_args_list]
    # upstream owner is mooner92 (from the repo_url) — clone falls back to it
    assert any(c[:3] == ["gh", "repo", "clone"] and "mooner92/firebase-chat-exp" in c for c in cmds)


def test_ensure_clone_is_nonfatal_on_clone_failure(sess):
    """A failed clone must NOT raise — the hardened stage-1 agent path is the backstop."""
    with mock.patch.object(session_mod.subprocess, "run",
                           return_value=mock.Mock(returncode=1, stdout="", stderr="boom")):
        sess._ensure_clone()  # must not raise
    assert not (sess.session_path / "project" / ".git").is_dir()


# --------------------------------------------------------------------- seed
def test_seed_creates_all_stage_tasks_with_parent_links(sess):
    """v6: seed creates one Kanban task per stage in STAGE_DAG (21 stages)."""
    from core.scenario import STAGE_DAG
    expected_len = len(STAGE_DAG)

    sess.session_path.mkdir(parents=True, exist_ok=True)
    (sess.session_path / "log").mkdir(exist_ok=True)
    seen_args = []
    counter = {"n": 0}

    def fake_kanban_json(*args):
        seen_args.append(args)
        counter["n"] += 1
        return {"id": f"t_{counter['n']:02d}"}

    with mock.patch.object(sess, "_kanban_json", side_effect=fake_kanban_json), \
         mock.patch.object(sess, "_kanban", return_value=""):
        stage_map = sess.seed()

    assert len(stage_map) == expected_len
    for args in seen_args:
        assert args[0] == "--board" and args[1] == "test-sess" and args[2] == "create", args
        assert "--idempotency-key" in args
        assert "--workspace" in args and "worktree" in args
    stage2_args = seen_args[1]
    assert "--parent" in stage2_args and "t_01" in stage2_args
    written = json.loads((sess.session_path / "stage_task_map.json").read_text())
    assert len(written) == expected_len


def test_seed_raises_on_unknown_assignee(sess, monkeypatch):
    from core import scenario
    bad = scenario.StageTask(stage=1, title="x", assignee="ghost", workspace="worktree",
                             tag="orchestration", body_template="b")
    monkeypatch.setattr(scenario, "STAGE_DAG", [bad])
    monkeypatch.setattr(session_mod, "STAGE_DAG", [bad])
    sess.session_path.mkdir(parents=True, exist_ok=True)
    with mock.patch.object(sess, "_kanban_json", return_value={"id": "t"}):
        with pytest.raises(ValueError, match="unknown assignee"):
            sess.seed()


# ------------------------------------------------------------- _write_status
def test_write_status_schema(sess):
    sess.session_path.mkdir(parents=True, exist_ok=True)
    sess._write_status(step=3, agent="architect", status="active", board_slug="test-sess")
    status = json.loads((sess.session_path / "status.json").read_text(encoding="utf-8"))
    for key in ("session", "status", "current_step", "current_agent", "repo_url",
                "repo_name", "board_slug", "started_at"):
        assert key in status
    assert status["current_step"] == 3
    assert status["current_agent"] == "architect"
