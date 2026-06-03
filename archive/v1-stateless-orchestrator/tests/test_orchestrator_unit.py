"""US-005 — orchestrator unit behaviour (mocked subprocess / queue)."""
from __future__ import annotations

import json
import subprocess
from unittest import mock

import pytest

from core import config
from core.logger import SessionLog
from core.orchestrator import AgentResult, DevBoothSession


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SESSIONS_ROOT", tmp_path)
    s = DevBoothSession("unit-test", "https://github.com/acme/widget", mode="dryrun")
    s.root.mkdir(parents=True, exist_ok=True)
    s.artifacts.mkdir(parents=True, exist_ok=True)
    s.mq.initialize(config.AGENTS)
    s.slog = SessionLog(s.root)
    return s


# -------------------------------------------------------------- _build_prompt
def test_build_prompt_under_ceiling_contains_objective(session):
    prompt = session._build_prompt("hermes-a", "분석을 수행하세요", ["small artifact"])
    assert "분석을 수행하세요" in prompt
    assert len(prompt) < config.PROMPT_HARD_CEILING


def test_build_prompt_truncates_large_artifact(session):
    big = "X" * (config.BODY_CAP * 3)
    prompt = session._build_prompt("hermes-b", "objective", [big])
    assert "[truncated" in prompt
    # the artifact block must be capped near BODY_CAP, not the full 12k
    assert len(prompt) < config.BODY_CAP + 4000


def test_build_prompt_drops_oldest_artifact_on_ceiling_breach(session):
    # objective alone (~48k) is under the 50k ceiling; adding a 3k artifact tips
    # the assembled prompt over -> the orchestrator drops the oldest artifact.
    huge_objective = "O" * 48000
    artifact = "A" * 3000
    prompt = session._build_prompt("openclaw", huge_objective, [artifact])
    assert len(prompt) < config.PROMPT_HARD_CEILING
    assert artifact not in prompt  # the artifact was dropped


def test_build_prompt_raises_when_irreducible(session):
    # objective alone exceeds the ceiling and there is nothing left to drop
    with pytest.raises(AssertionError, match="hard ceiling"):
        session._build_prompt("openclaw", "Z" * (config.PROMPT_HARD_CEILING + 100), [])


# -------------------------------------------------------------- _run_agent
def test_run_agent_command_has_no_continue_and_sets_profile(session):
    captured = {}

    class _FakeProc:
        returncode = 0

        def communicate(self, timeout=None):
            return ("agent output", "")

    def fake_popen(cmd, env=None, cwd=None, **kw):
        captured["cmd"] = cmd
        captured["env"] = env
        return _FakeProc()

    with mock.patch("subprocess.Popen", side_effect=fake_popen):
        result = session._run_agent("hermes-a", "do the thing")

    assert result.ok
    assert result.text == "agent output"
    assert "-z" in captured["cmd"]
    assert "--yolo" in captured["cmd"]
    assert "--continue" not in captured["cmd"], "DD1: -z is stateless, no --continue"
    assert captured["cmd"][0] == config.HERMES_BIN
    assert captured["env"]["HERMES_PROFILE"] == "hermes-a"


def test_run_agent_timeout_returns_timed_out_result(session):
    class _HangingProc:
        """First communicate() call (with timeout) hangs; the post-kill drain returns."""

        returncode = None

        def __init__(self):
            self._killed = False

        def communicate(self, timeout=None):
            if not self._killed:
                raise subprocess.TimeoutExpired(cmd="hermes", timeout=timeout)
            return ("", "")  # post-kill drain returns normally, like real Popen

        def kill(self):
            self._killed = True

    with mock.patch("subprocess.Popen", return_value=_HangingProc()):
        result = session._run_agent("hermes-b", "slow task", timeout=1)

    assert result.timed_out is True
    assert result.ok is False


def _log_messages(session):
    log_file = session.root / "log" / "messages.jsonl"
    return [
        json.loads(ln)
        for ln in log_file.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]


# -------------------------------------------------------------- _agent_turn
def test_agent_turn_acks_on_success_and_sends_answer(session):
    ok = AgentResult(text="completed the analysis", returncode=0)
    with mock.patch.object(session, "_run_agent", return_value=ok):
        result = session._agent_turn(
            "hermes-a", "analyze", "do the analysis", artifact_name="a.md"
        )
    assert result.ok
    # processing/ is empty (acked) on hermes-a's side
    assert len(list((session.root / "queues" / "hermes-a" / "processing").glob("*.json"))) == 0
    # the answer landed in the LOG (dashboard chat view reads the log)...
    log = _log_messages(session)
    assert any(m["kind"] == "answer" and m["from"] == "hermes-a" for m in log)
    # ...and its inbox file was DRAINED — openclaw's inbox is empty, the answer
    # is in processed/ (P1: completed sessions must derive as idle)
    oc_inbox = session.root / "queues" / "openclaw" / "inbox"
    assert len(list(oc_inbox.glob("*.json"))) == 0, "answer must be drained from inbox"
    oc_processed = session.root / "queues" / "openclaw" / "processed"
    assert len(list(oc_processed.glob("*.json"))) == 1
    assert (session.artifacts / "a.md").read_text() == "completed the analysis"


def test_agent_turn_retries_on_failure_and_sends_blocker(session):
    bad = AgentResult(text="", returncode=2, timed_out=False)
    with mock.patch.object(session, "_run_agent", return_value=bad):
        result = session._agent_turn("hermes-b", "implement", "do impl")
    assert result.ok is False
    # failure path: the instruction is retry()'d (lifecycle records the retry)
    # then drained — it must NOT strand in hermes-b's inbox (that would keep the
    # dashboard stuck on 'running').
    hb_inbox = session.root / "queues" / "hermes-b" / "inbox"
    assert len(list(hb_inbox.glob("*.json"))) == 0, "retried instruction must be drained, not stranded"
    # the retry was real: the instruction landed in processed/ with retryCount bumped
    hb_processed = list((session.root / "queues" / "hermes-b" / "processed").glob("*.json"))
    assert len(hb_processed) == 1
    retried = json.loads(hb_processed[0].read_text())
    assert int(retried.get("refs", {}).get("retryCount", 0)) >= 1, "retry() must bump retryCount"
    # the blocker is in the LOG, and openclaw's inbox was drained
    log = _log_messages(session)
    assert any(m["kind"] == "blocker" for m in log)
    oc_inbox = session.root / "queues" / "openclaw" / "inbox"
    assert len(list(oc_inbox.glob("*.json"))) == 0, "blocker must be drained from inbox"


def test_drain_inbox_clears_replies(session):
    # seed openclaw's inbox with a couple of replies, then drain
    session.mq.send("hermes-a", "openclaw", "answer", "result one")
    session.mq.send("hermes-b", "openclaw", "answer", "result two")
    assert len(session.mq.peek("openclaw")) == 2
    drained = session._drain_inbox("openclaw")
    assert drained == 2
    assert session.mq.peek("openclaw") == []
    assert len(list((session.root / "queues" / "openclaw" / "inbox").glob("*.json"))) == 0


# -------------------------------------------------------------- narrate / status
def test_narrate_writes_corpus_body_and_advances_step(session):
    session.narrate(5)
    assert session.current_step == 5
    log_lines = (session.root / "log" / "messages.jsonl").read_text().splitlines()
    last = json.loads(log_lines[-1])
    assert last["from"] == "orchestrator"
    assert last["kind"] == "status"
    assert "implementing" in last["body"]  # stage-5 keyword


def test_write_status_has_dd3_schema(session):
    session.last_commit = {"hash": "abc123", "message": "fix"}
    session.test_results = {"passed": 3, "failed": 0}
    session._write_status(7, "hermes-b", state="active", branch="feature/x")
    status = json.loads(session.status_file.read_text(encoding="utf-8"))
    for key in (
        "session", "status", "current_step", "current_agent", "repo_url",
        "repo_name", "branch", "started_at", "last_commit", "test_results",
    ):
        assert key in status, f"status.json missing DD3 key: {key}"
    assert status["current_step"] == 7
    assert status["current_agent"] == "hermes-b"
    assert status["branch"] == "feature/x"
    assert status["last_commit"] == {"hash": "abc123", "message": "fix"}
    assert status["test_results"] == {"passed": 3, "failed": 0}
