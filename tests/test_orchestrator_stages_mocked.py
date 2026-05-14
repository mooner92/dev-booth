"""US-005 — full 12-stage run() with mocked hermes / git / gh.

Proves the deterministic state machine walks stages 1->12, writes every
Canonical Narration Corpus marker to the log, transitions status.json to
``completed``, and never creates a ``queues/orchestrator/`` directory.
"""
from __future__ import annotations

import json
import subprocess
from unittest import mock

import pytest

from core import config
from core.orchestrator import AgentResult, DevBoothSession, STAGE_NARRATION


def _completed(rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _fake_subprocess_run(cmd, *a, **kw):
    """Stand in for git / gh — every invocation 'succeeds'."""
    if cmd[:2] == ["git", "ls-files"]:
        return _completed(0, stdout="src/index.js\npackage.json\nREADME.md")
    if cmd[:2] == ["git", "rev-parse"]:
        return _completed(0, stdout="deadbeefcafe")
    if cmd[:2] == ["git", "diff"]:
        return _completed(0, stdout=" src/index.js | 4 ++--\n 1 file changed")
    # git clone, git checkout, git add, git commit, git push, gh ... -> ok
    return _completed(0, stdout="")


def _fake_run_agent(self, profile, prompt, timeout=None):
    """Canned agent output.

    When the orchestrator asks openclaw to write improvements (the prompt names
    the TASK-NNN format), return a parseable task list; otherwise return generic
    text containing the stage-6 review-approval keyword so the dev loop closes.
    """
    if "TASK-NNN" in prompt or "improvements_v0.0.1.md" in prompt:
        return AgentResult(
            text="- [TASK-001] @hermes-b: 입력 검증을 추가한다\n",
            returncode=0,
        )
    return AgentResult(text="작업을 완료했습니다. 리뷰 승인.", returncode=0)


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SESSIONS_ROOT", tmp_path)
    # signal handlers only install from the main thread; mock to stay portable
    monkeypatch.setattr("signal.signal", lambda *a, **kw: None)
    return DevBoothSession(
        "stages-test", "https://github.com/acme/widget", goal="버그 수정", mode="dryrun"
    )


def test_full_run_walks_all_12_stages(session):
    with mock.patch.object(DevBoothSession, "_run_agent", _fake_run_agent), \
         mock.patch("subprocess.run", side_effect=_fake_subprocess_run):
        rc = session.run()

    assert rc == 0, "dryrun full run should exit 0"

    # status.json reached the terminal state
    status = json.loads(session.status_file.read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert status["current_step"] == 12
    assert status["session"] == "stages-test"
    assert status["mode"] == "dryrun"

    # every Canonical Narration Corpus body landed in the log as an
    # orchestrator status line
    log_lines = [
        json.loads(ln)
        for ln in (session.root / "log" / "messages.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    orch_bodies = [m["body"] for m in log_lines if m["from"] == "orchestrator"]
    for stage_no, (_sid, body) in STAGE_NARRATION.items():
        assert body in orch_bodies, f"stage {stage_no} narration missing from log"

    # pr_draft.json written with the dryrun synthetic descriptor
    pr_draft = json.loads(session.pr_draft_file.read_text(encoding="utf-8"))
    assert pr_draft["url"] == "DRYRUN://no-pr"


def test_full_run_never_creates_orchestrator_queue(session):
    with mock.patch.object(DevBoothSession, "_run_agent", _fake_run_agent), \
         mock.patch("subprocess.run", side_effect=_fake_subprocess_run):
        session.run()

    queue_dirs = {p.name for p in (session.root / "queues").iterdir() if p.is_dir()}
    assert queue_dirs == {"openclaw", "hermes-a", "hermes-b"}, (
        f"queues/ must contain exactly the 3 real agents, got {queue_dirs}"
    )
    assert not (session.root / "queues" / "orchestrator").exists()


def test_full_run_leaves_no_processing_strands(session):
    with mock.patch.object(DevBoothSession, "_run_agent", _fake_run_agent), \
         mock.patch("subprocess.run", side_effect=_fake_subprocess_run):
        session.run()

    for agent in config.AGENTS:
        processing = session.root / "queues" / agent / "processing"
        leftover = list(processing.glob("*.json"))
        assert leftover == [], f"{agent} left a strand in processing/: {leftover}"


def test_full_run_leaves_all_inboxes_drained(session):
    """P1: a completed session must derive as 'idle' — no inbox/processing depth."""
    with mock.patch.object(DevBoothSession, "_run_agent", _fake_run_agent), \
         mock.patch("subprocess.run", side_effect=_fake_subprocess_run):
        session.run()

    for agent in config.AGENTS:
        inbox = session.root / "queues" / agent / "inbox"
        leftover = list(inbox.glob("*.json"))
        assert leftover == [], f"{agent} left replies in inbox/: {leftover}"


def test_full_run_writes_session_artifacts(session):
    with mock.patch.object(DevBoothSession, "_run_agent", _fake_run_agent), \
         mock.patch("subprocess.run", side_effect=_fake_subprocess_run):
        session.run()

    for name in (
        "analysis_hermes_a.md", "analysis_hermes_b.md",
        "summary_v1.0.0.md", "improvements_v0.0.1.md",
    ):
        assert (session.root / name).is_file(), f"missing session artifact: {name}"
