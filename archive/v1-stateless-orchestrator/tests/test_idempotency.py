"""US-005 / helper 8d — idempotent fork / clone / branch."""
from __future__ import annotations

import subprocess
from unittest import mock

import pytest

from core import config
from core.orchestrator import DevBoothSession


def _completed(rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SESSIONS_ROOT", tmp_path)
    s = DevBoothSession("idem-test", "https://github.com/acme/widget", mode="dryrun")
    # SessionLog so broadcast()/narrate() work if reached
    from core.logger import SessionLog
    s.slog = SessionLog(s.root)
    return s


def test_fork_skipped_when_repo_already_exists(session):
    calls: list[tuple] = []

    def fake_gh(*args, **kw):
        calls.append(args)
        if args[:2] == ("repo", "view"):
            return _completed(rc=0)  # fork already exists
        return _completed(rc=0)

    with mock.patch.object(session, "_gh", side_effect=fake_gh), \
         mock.patch.object(session, "_git", return_value=_completed(rc=0)), \
         mock.patch.object(session, "_git_push", return_value=_completed(rc=0)), \
         mock.patch("subprocess.run", return_value=_completed(rc=0)):
        # pretend the clone already exists so we exercise the fetch path too
        (session.project / ".git").mkdir(parents=True)
        session._fork_and_clone()

    assert ("repo", "view", "CrownClownCrowd/widget") in calls
    assert not any(c[:2] == ("repo", "fork") for c in calls), "fork must be skipped"


def test_fork_runs_when_repo_missing(session):
    calls: list[tuple] = []

    def fake_gh(*args, **kw):
        calls.append(args)
        if args[:2] == ("repo", "view"):
            return _completed(rc=1)  # fork does NOT exist
        return _completed(rc=0)

    with mock.patch.object(session, "_gh", side_effect=fake_gh), \
         mock.patch.object(session, "_git", return_value=_completed(rc=0)), \
         mock.patch.object(session, "_git_push", return_value=_completed(rc=0)), \
         mock.patch("subprocess.run", return_value=_completed(rc=0)):
        (session.project / ".git").mkdir(parents=True)
        session._fork_and_clone()

    assert any(c[:2] == ("repo", "fork") for c in calls), "fork must run when missing"


def test_clone_skipped_when_git_dir_exists(session):
    git_clone_calls: list = []

    def fake_run(cmd, *a, **kw):
        if cmd[:2] == ["git", "clone"]:
            git_clone_calls.append(cmd)
        return _completed(rc=0, stdout="origin/main")

    with mock.patch.object(session, "_gh", return_value=_completed(rc=0)), \
         mock.patch.object(session, "_git", return_value=_completed(rc=0, stdout="origin/main")), \
         mock.patch.object(session, "_git_push", return_value=_completed(rc=0)), \
         mock.patch("subprocess.run", side_effect=fake_run):
        (session.project / ".git").mkdir(parents=True)  # clone already present
        session._fork_and_clone()

    assert git_clone_calls == [], "git clone must be skipped when .git exists"


def test_clone_runs_when_no_git_dir(session):
    git_clone_calls: list = []

    def fake_run(cmd, *a, **kw):
        if cmd[:2] == ["git", "clone"]:
            git_clone_calls.append(cmd)
        return _completed(rc=0)

    with mock.patch.object(session, "_gh", return_value=_completed(rc=1)), \
         mock.patch.object(session, "_git", return_value=_completed(rc=0)), \
         mock.patch.object(session, "_git_push", return_value=_completed(rc=0)), \
         mock.patch("subprocess.run", side_effect=fake_run):
        # project/.git does NOT exist
        session._fork_and_clone()

    assert len(git_clone_calls) == 1, "git clone must run when no .git dir"


def test_branch_uses_checkout_dash_capital_b(session):
    git_calls: list[tuple] = []

    def fake_git(*args, **kw):
        git_calls.append(args)
        return _completed(rc=0, stdout="origin/main")

    with mock.patch.object(session, "_gh", return_value=_completed(rc=0)), \
         mock.patch.object(session, "_git", side_effect=fake_git), \
         mock.patch.object(session, "_git_push", return_value=_completed(rc=0)), \
         mock.patch("subprocess.run", return_value=_completed(rc=0)):
        (session.project / ".git").mkdir(parents=True)
        session._fork_and_clone()

    assert ("checkout", "-B", "develop") in git_calls, "branch must be idempotent (checkout -B)"
