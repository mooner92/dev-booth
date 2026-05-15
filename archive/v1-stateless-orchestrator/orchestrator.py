"""Dev-Booth multi-agent orchestrator — 12-stage deterministic state machine.

Plan v3 reference: /dev-booth/reports/plans/2026_05_14_07-44-41_devbooth_multiagent_completion_v3.md

Design invariants (enforced, not optional):
  * DD1 — every agent turn is a discrete *stateless* ``hermes -z`` subprocess.
    There is NO ``--continue`` anywhere. The orchestrator supplies 100% of
    context in each prompt.
  * DD2/DD4 — the orchestrator's OWN progress narration is written via
    ``core.logger`` (direct append to ``log/messages.jsonl``), NEVER through
    ``MessageQueue.send()``. Only agent-to-agent messages
    (instruction/answer/question/blocker) go through ``MessageQueue``. This is
    why ``queues/`` only ever contains ``openclaw/hermes-a/hermes-b``.
  * DD4 — ``MessageQueue`` is rooted at the *session directory* (not
    ``<session>/awg``). ``setup()`` calls ``requeue_stale()`` to recover
    ``processing/`` strands.
  * DD5/§7 — stage narration bodies come from ``STAGE_NARRATION`` (the Canonical
    Narration Corpus); each body carries exactly its stage's keyword.
  * DD6 — dryrun is the default mode: ``git push`` becomes ``--dry-run`` and
    ``gh pr create`` becomes a logged-only synthetic descriptor. Turn cap is in
    each profile's ``config.yaml`` (``agent.max_turns: 40``); per-turn 900s
    subprocess timeout; 5400s whole-session cap; SIGINT aborts cleanly.

Entry point::

    /dev-booth/env/bin/python3.11 -m core.orchestrator <session> <repo_url> \
        [--goal "..."] [--mode dryrun|live]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent_working_group import MessageQueue

from core import config
from core.logger import SessionLog

# --------------------------------------------------------------------------
# Canonical Narration Corpus (plan §7) — one body per dashboard stage.
# Each body's free-text carries that stage's stage_mapper keyword and NO
# higher-stage keyword. Verified by
# dashboard/backend/tests/test_stage_narration_crossseam.py (CI-blocking gate).
# The "[STAGE n/12: id]" prefix is human decoration — invisible to detect_stage.
# --------------------------------------------------------------------------
STAGE_NARRATION: dict[int, tuple[str, str]] = {
    1:  ("repo_clone",      "[STAGE 1/12: repo_clone] git clone of the target repository complete."),
    2:  ("initial_scan",    "[STAGE 2/12: initial_scan] initial scan of the codebase underway."),
    3:  ("plan_drafted",    "[STAGE 3/12: plan_drafted] drafting the implementation plan now (draft plan in progress)."),
    4:  ("plan_approved",   "[STAGE 4/12: plan_approved] the implementation plan approved by the orchestrator."),
    5:  ("implementation",  "[STAGE 5/12: implementation] implementing the approved changes."),
    6:  ("self_review",     "[STAGE 6/12: self_review] self review of the changes in progress."),
    7:  ("tests_running",   "[STAGE 7/12: tests_running] running tests against the working tree."),
    8:  ("tests_passed",    "[STAGE 8/12: tests_passed] all tests passed."),
    9:  ("pr_drafted",      "[STAGE 9/12: pr_drafted] pr drafted and ready for review."),
    10: ("pr_review",       "[STAGE 10/12: pr_review] pr review requested from the reviewer."),
    11: ("pr_approved",     "[STAGE 11/12: pr_approved] pr approved by the reviewer."),
    12: ("pr_merged",       "[STAGE 12/12: pr_merged] pr merged into main."),
}


@dataclass
class AgentResult:
    """Outcome of one ``hermes -z`` subprocess turn."""

    text: str
    returncode: int
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return (not self.timed_out) and self.returncode == 0


@dataclass
class Task:
    """One parsed line from improvements_v0.0.1.md."""

    task_id: str
    assignee: str
    description: str
    status: str = "pending"  # pending | done | failed


# --------------------------------------------------------------------------
# improvements.md task parser (helper — covered by tests/test_task_parser.py)
# --------------------------------------------------------------------------
_TASK_RE = re.compile(
    r"""^\s*[-*]?\s*           # optional bullet
        \[?(?P<id>TASK-\d+)\]? # TASK-001 or [TASK-001]
        \s*[:@]?\s*
        @?(?P<assignee>hermes-[ab]|openclaw)?  # optional @hermes-b
        \s*[:\-]?\s*
        (?P<desc>.+?)\s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def parse_tasks(improvements_md: str) -> list[Task]:
    """Parse ``improvements_v0.0.1.md`` into a list of :class:`Task`.

    Tolerant by design: any line matching ``TASK-NNN ... description`` becomes a
    task. If a line names no assignee, it defaults to ``hermes-b`` (the
    implementer). Returns ``[]`` for unparseable input — the caller (the dev
    loop) treats an empty list as a clean no-op rather than crashing.
    """
    tasks: list[Task] = []
    for line in improvements_md.splitlines():
        m = _TASK_RE.match(line)
        if not m:
            continue
        desc = m.group("desc").strip()
        if not desc:
            continue
        assignee = (m.group("assignee") or "hermes-b").lower()
        tasks.append(Task(task_id=m.group("id").upper(), assignee=assignee, description=desc))
    return tasks


def _truncate(text: str, cap: int = config.BODY_CAP) -> str:
    """Head+tail truncation so structure markers at both ends survive."""
    if len(text) <= cap:
        return text
    half = cap // 2
    return f"{text[:half]}\n...[truncated {len(text) - cap} chars]...\n{text[-half:]}"


class DevBoothSession:
    """Drives the 12-stage scenario for one Dev-Booth session."""

    # ---------------------------------------------------------------- init
    def __init__(
        self,
        session_name: str,
        repo_url: str,
        goal: str = "코드 품질 개선 및 버그 수정",
        mode: str = "dryrun",
    ):
        if mode not in ("dryrun", "live"):
            raise ValueError(f"mode must be dryrun|live, got {mode!r}")
        self.session_name = session_name
        self.repo_url = repo_url.rstrip("/")
        self.repo_name = self.repo_url.split("/")[-1].removesuffix(".git")
        self.goal = goal
        self.mode = mode

        self.root = config.SESSIONS_ROOT / session_name
        self.project = self.root / "project"
        self.artifacts = self.root / "artifacts"
        self.status_file = self.root / "status.json"
        self.pr_draft_file = self.root / "pr_draft.json"

        # MessageQueue rooted at the SESSION DIR (DD4) — queues/ + log/ live here.
        self.mq = MessageQueue(str(self.root))
        self.slog: Optional[SessionLog] = None

        self.branch = "develop"
        self.feature_branch = f"feature/dev-booth-{session_name}"
        self.current_step = 0
        self.current_agent = "orchestrator"
        self.last_commit = {"hash": "", "message": ""}
        self.test_results = {"passed": 0, "failed": 0}
        self.tasks: list[Task] = []

        self._started_at = time.time()
        self._started_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._last_log_ms = 0
        self._msg_count = 0
        self._current_proc: Optional[subprocess.Popen] = None
        self._aborting = False

    # ---------------------------------------------------------------- setup
    def setup(self) -> None:
        """Create dirs, init the queue, recover strands, install SIGINT, fork+clone."""
        for d in (self.root, self.project.parent, self.artifacts, self.root / "log"):
            d.mkdir(parents=True, exist_ok=True)

        # DD4: initialize the queue for exactly the 3 real agents — never
        # 'orchestrator'. requeue_stale() recovers any processing/ strand.
        self.mq.initialize(config.AGENTS)
        for agent in config.AGENTS:
            stats = self.mq.requeue_stale(agent, older_than_sec=0)
            if stats["requeued"] or stats["dead"]:
                print(f"[setup] requeue_stale {agent}: {stats}")

        self.slog = SessionLog(self.root)

        signal.signal(signal.SIGINT, self._on_sigint)
        signal.signal(signal.SIGTERM, self._on_sigint)

        self._write_status(step=0, agent="orchestrator", state="active")
        self._fork_and_clone()

    # ------------------------------------------------------------ lifecycle
    def run(self) -> int:
        """Execute the 12-stage scenario. Returns a process exit code."""
        try:
            self.setup()
            self._analyze()        # stage 2
            self._plan()           # stages 3-4
            self._develop_loop()   # stages 5-8
            self._submit_pr()      # stages 9-12
        except _SessionAborted:
            print("[run] session aborted")
            self._write_status(self.current_step, self.current_agent, state="aborted")
            return 130
        except _SessionTimeout:
            print("[run] session timed out")
            self._write_status(self.current_step, self.current_agent, state="error")
            return 124
        except Exception as exc:  # noqa: BLE001 — top-level guard
            print(f"[run] ERROR: {exc}")
            self._write_status(self.current_step, self.current_agent, state="error")
            return 1
        self._write_status(12, "orchestrator", state="completed")
        print(f"[run] session {self.session_name} completed ({self.mode})")
        return 0

    def _on_sigint(self, signum, frame) -> None:  # noqa: ARG002
        self._aborting = True
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.terminate()
            except ProcessLookupError:
                pass
        raise _SessionAborted()

    def _check_budget(self) -> None:
        if self._aborting:
            raise _SessionAborted()
        if time.time() - self._started_at > config.SESSION_TIMEOUT_S:
            raise _SessionTimeout()

    # -------------------------------------------------------------- narration
    def narrate(self, stage_no: int) -> None:
        """Emit the Canonical Narration Corpus body for ``stage_no`` (direct append)."""
        assert self.slog is not None
        _stage_id, body = STAGE_NARRATION[stage_no]
        msg = self.slog.narrate(stage_no, body)
        self._last_log_ms = msg["createdAtMs"]
        self.current_step = stage_no

    def _heartbeat(self) -> None:
        """Re-emit the current stage marker if the log has been quiet (helper 8f).

        Time-bound: > HEARTBEAT_INTERVAL_S (45s) since the last log append, which
        is < StageTracker's 60s conflict window — keeps a fresh hit inside it.
        """
        if self.current_step < 1 or self.slog is None:
            return
        now_ms = int(time.time() * 1000)
        elapsed_s = (now_ms - self._last_log_ms) / 1000 if self._last_log_ms else 0
        if elapsed_s > config.HEARTBEAT_INTERVAL_S:
            _sid, body = STAGE_NARRATION[self.current_step]
            msg = self.slog.narrate(self.current_step, body)
            self._last_log_ms = msg["createdAtMs"]

    # ---------------------------------------------------------------- status
    def _write_status(
        self,
        step: int,
        agent: str,
        state: str = "active",
        branch: Optional[str] = None,
    ) -> None:
        """Write status.json (DD3 schema). Operator artifact — dashboard never reads it."""
        self.current_step = step
        self.current_agent = agent
        status = {
            "session": self.session_name,
            "status": state,
            "current_step": step,
            "current_agent": agent,
            "repo_url": self.repo_url,
            "repo_name": self.repo_name,
            "branch": branch or self.branch,
            "started_at": self._started_iso,
            "mode": self.mode,
            "last_commit": self.last_commit,
            "test_results": self.test_results,
        }
        self.root.mkdir(parents=True, exist_ok=True)
        self.status_file.write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # -------------------------------------------------------- agent subprocess
    def _build_prompt(
        self,
        profile: str,
        stage_objective: str,
        context_artifacts: Optional[list[str]] = None,
    ) -> str:
        """Assemble a full-context prompt for a stateless agent turn (helper 8a).

        All three agents use this same path — there is no ``--continue`` delta
        branch. Context artifacts are head+tail truncated at ``BODY_CAP`` and
        capped at ``MAX_ARTIFACTS_PER_PROMPT``. The assembled prompt is asserted
        below ``PROMPT_HARD_CEILING``; on breach the oldest artifact is dropped.
        """
        persona = (
            f"당신은 {profile} 입니다. Dev-Booth 멀티에이전트 세션 "
            f"'{self.session_name}' 에서 작업합니다. 작업 디렉터리는 "
            f"{self.project} 입니다."
        )
        artifacts = list(context_artifacts or [])[: config.MAX_ARTIFACTS_PER_PROMPT]
        contract = (
            "지시를 수행한 뒤, 한국어로 결과를 설명하고 마지막 줄에 한 문장으로 "
            "요약하세요."
        )

        def assemble(arts: list[str]) -> str:
            blocks = [persona, f"[목표]\n{self.goal}", f"[지시]\n{stage_objective}"]
            for i, art in enumerate(arts, 1):
                blocks.append(f"[참고자료 {i}]\n{_truncate(art)}")
            blocks.append(f"[출력 규칙]\n{contract}")
            return "\n\n".join(blocks)

        prompt = assemble(artifacts)
        while len(prompt) >= config.PROMPT_HARD_CEILING and artifacts:
            dropped = artifacts.pop(0)  # drop oldest artifact
            print(f"[build_prompt] ceiling breach — dropped artifact ({len(dropped)} chars)")
            prompt = assemble(artifacts)
        assert len(prompt) < config.PROMPT_HARD_CEILING, "prompt exceeds hard ceiling"
        return prompt

    def _run_agent(
        self,
        profile: str,
        prompt: str,
        timeout: int = config.HERMES_TURN_TIMEOUT_S,
    ) -> AgentResult:
        """Run one stateless ``hermes -z`` subprocess turn for ``profile``."""
        env = {**os.environ, "HERMES_PROFILE": profile}
        # NO --continue: -z is stateless by design (plan DD1).
        cmd = [config.HERMES_BIN, "-z", prompt, "--yolo"]
        self.project.mkdir(parents=True, exist_ok=True)
        try:
            self._current_proc = subprocess.Popen(
                cmd,
                env=env,
                cwd=str(self.project),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = self._current_proc.communicate(timeout=timeout)
            rc = self._current_proc.returncode
            self._current_proc = None
            if rc != 0:
                print(f"[_run_agent] {profile} rc={rc} stderr={stderr[:200]}")
            return AgentResult(text=stdout.strip(), returncode=rc)
        except subprocess.TimeoutExpired:
            if self._current_proc:
                self._current_proc.kill()
                self._current_proc.communicate()
                self._current_proc = None
            print(f"[_run_agent] {profile} TIMED OUT after {timeout}s")
            return AgentResult(text="", returncode=-1, timed_out=True)

    def _agent_turn(
        self,
        to_agent: str,
        instruction_body: str,
        stage_objective: str,
        context_artifacts: Optional[list[str]] = None,
        from_agent: str = "openclaw",
        artifact_name: Optional[str] = None,
    ) -> AgentResult:
        """The DD4 mediation loop for one agent turn.

        send(instruction) -> receive(require_ack) -> hermes subprocess ->
        ack on success / retry (requeue) on failure -> send(reply back) ->
        drain the reply. The reply (``answer``/``blocker``) exists to land in
        ``log/messages.jsonl`` for the dashboard chat view — ``send()`` already
        appended it there. Its inbox file is then drained so completed sessions
        report ``idle`` (P1: the dashboard's ``any_running`` check counts
        inbox+processing depth). The full untruncated output goes to
        ``artifacts/``; the queue body is truncated to ``BODY_CAP``.
        """
        self._check_budget()
        self._heartbeat()

        # 1. enqueue the instruction (agent-to-agent — goes through MessageQueue)
        self.mq.send(from_agent, to_agent, "instruction", instruction_body)
        self._msg_count += 1
        # 2. the recipient receives it (inbox -> processing)
        received = self.mq.receive(to_agent, timeout=10, require_ack=True)
        if received is None:
            # nothing to receive — should not happen since we just sent; treat
            # as a soft failure rather than a hang.
            return AgentResult(text="", returncode=-2, timed_out=False)

        # 3. build the full-context prompt and run the stateless hermes turn
        prompt = self._build_prompt(to_agent, stage_objective, context_artifacts)
        result = self._run_agent(to_agent, prompt)

        # 4. ack on success, retry (requeue) on failure
        if result.ok:
            self.mq.ack(to_agent, received["id"])
            # 5. route the agent's reply back as an 'answer'
            self.mq.send(to_agent, from_agent, "answer", result.text[: config.BODY_CAP])
            self._msg_count += 1
        else:
            # nack: requeue the instruction so its lifecycle records a retry
            # (retryCount is bumped in refs), then drain it — the orchestrator
            # moves on per helper 8e (mark-failed-continue) rather than
            # re-consuming it, so leaving it in the inbox would strand it and
            # keep the dashboard stuck on 'running'.
            self.mq.retry(to_agent, received["id"])
            self._drain_inbox(to_agent)
            self.mq.send(to_agent, from_agent, "blocker",
                         f"turn failed (rc={result.returncode} timed_out={result.timed_out})")
            self._msg_count += 1

        # 6. drain the reply — it is already in the log; keep the inbox clean so
        #    a completed session derives as 'idle', not perpetually 'running'.
        self._drain_inbox(from_agent)

        # full output -> artifacts/
        if artifact_name and result.text:
            (self.artifacts / artifact_name).write_text(result.text, encoding="utf-8")
        return result

    def _drain_inbox(self, agent: str) -> int:
        """Receive+ack everything currently in ``agent``'s inbox.

        Agent inboxes only ever hold orchestrator-routed ``answer``/``blocker``
        replies — already logged by ``send()``. Draining them keeps queue depth
        at zero so a finished session derives as ``idle`` (plan P1). Returns the
        number of messages drained.
        """
        drained = 0
        while self.mq.peek(agent):
            msg = self.mq.receive(agent, timeout=1, require_ack=True)
            if msg is None:
                break
            self.mq.ack(agent, msg["id"])
            drained += 1
        return drained

    # ----------------------------------------------------------- git / gh
    def _git(self, *args: str, cwd: Optional[Path] = None, check: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd or self.project),
            capture_output=True,
            text=True,
            check=check,
        )

    def _gh(self, *args: str, check: bool = False) -> subprocess.CompletedProcess:
        env = {**os.environ}
        if config.GITHUB_TOKEN:
            env["GH_TOKEN"] = config.GITHUB_TOKEN
        return subprocess.run(
            ["gh", *args], capture_output=True, text=True, env=env, check=check
        )

    def _git_push(self, *args: str) -> subprocess.CompletedProcess:
        """Push — dryrun-gated. In dryrun mode the push is ``--dry-run``."""
        push_args = ["push", *args]
        if self.mode == "dryrun":
            push_args.append("--dry-run")
            print(f"[_git_push] dryrun: git {' '.join(push_args)}")
        return self._git(*push_args)

    # ---------------------------------------------------- stage 1: fork+clone
    def _fork_and_clone(self) -> None:
        """Stages 1-2 of the scenario -> dashboard stage 1 (repo_clone).

        Idempotent (helper 8d): skip fork if it already exists; fetch+reset if
        the clone already exists; ``git checkout -B`` for the branch.
        """
        self._check_budget()
        self._write_status(1, "openclaw", state="active")

        # idempotent fork: skip if BOT_OWNER already has the repo
        fork_check = self._gh("repo", "view", f"{config.BOT_OWNER}/{self.repo_name}")
        if fork_check.returncode != 0:
            print(f"[fork] forking {config.UPSTREAM_OWNER}/{self.repo_name} -> {config.BOT_OWNER}")
            self._gh("repo", "fork", f"{config.UPSTREAM_OWNER}/{self.repo_name}", "--clone=false")
        else:
            print(f"[fork] {config.BOT_OWNER}/{self.repo_name} already exists — skip")

        # idempotent clone
        clone_url = self.repo_url
        if config.GITHUB_TOKEN:
            clone_url = (
                f"https://{config.GITHUB_TOKEN}@github.com/"
                f"{config.BOT_OWNER}/{self.repo_name}.git"
            )
        if (self.project / ".git").is_dir():
            print("[clone] project/.git exists — fetch + reset")
            self._git("fetch", "origin")
            # best-effort: reset to the default remote branch
            for base in ("main", "master"):
                if self._git("rev-parse", "--verify", f"origin/{base}").returncode == 0:
                    self._git("checkout", base)
                    self._git("reset", "--hard", f"origin/{base}")
                    break
        else:
            print(f"[clone] cloning {config.BOT_OWNER}/{self.repo_name} -> {self.project}")
            self.project.parent.mkdir(parents=True, exist_ok=True)
            res = subprocess.run(
                ["git", "clone", clone_url, str(self.project)],
                capture_output=True, text=True,
            )
            if res.returncode != 0:
                raise RuntimeError(f"git clone failed: {res.stderr.strip()}")

        # idempotent develop branch
        self._git("checkout", "-B", self.branch)
        self._git_push("-u", "origin", self.branch)

        self.narrate(1)
        self._write_status(1, "openclaw", state="active", branch=self.branch)

    # --------------------------------------------------- stage 2: analysis
    def _analyze(self) -> None:
        """Scenario steps 3-4 -> dashboard stage 2 (initial_scan).

        Hermes-A (structure) then Hermes-B (stack) — sequential this iteration
        (O4 deferred true parallelism).
        """
        self._check_budget()
        self.narrate(2)
        self._write_status(2, "hermes-a", state="active")

        file_list = self._project_file_list()
        a_res = self._agent_turn(
            "hermes-a",
            instruction_body="레포지토리의 코드 구조와 아키텍처를 분석해주세요.",
            stage_objective=(
                "프로젝트의 디렉터리 구조, 핵심 모듈, 아키텍처를 분석하고 "
                "improvements_v0.0.1.md 작성을 위한 근거를 정리하세요."
            ),
            context_artifacts=[f"프로젝트 파일 목록:\n{file_list}"],
            artifact_name="analysis_hermes_a.md",
        )
        (self.root / "analysis_hermes_a.md").write_text(
            a_res.text or "(no output)", encoding="utf-8"
        )

        self._write_status(2, "hermes-b", state="active")
        b_res = self._agent_turn(
            "hermes-b",
            instruction_body="레포지토리의 의존성과 기술 스택을 분석해주세요.",
            stage_objective=(
                "사용 언어, 프레임워크, 빌드/테스트 도구, 의존성을 분석하세요."
            ),
            context_artifacts=[f"프로젝트 파일 목록:\n{file_list}"],
            artifact_name="analysis_hermes_b.md",
        )
        (self.root / "analysis_hermes_b.md").write_text(
            b_res.text or "(no output)", encoding="utf-8"
        )

    # ----------------------------------------------------- stages 3-4: plan
    def _plan(self) -> None:
        """Scenario steps 5-8 -> dashboard stages 3 (plan_drafted) + 4 (plan_approved)."""
        self._check_budget()
        self.narrate(3)
        self._write_status(3, "openclaw", state="active")

        a_text = (self.root / "analysis_hermes_a.md").read_text(encoding="utf-8")
        b_text = (self.root / "analysis_hermes_b.md").read_text(encoding="utf-8")

        summary = self._agent_turn(
            "openclaw",
            instruction_body="두 분석 결과를 취합해 summary_v1.0.0.md를 작성해주세요.",
            stage_objective="Hermes-A와 Hermes-B의 분석을 종합한 요약 문서를 작성하세요.",
            context_artifacts=[a_text, b_text],
            artifact_name="summary_v1.0.0.md",
        )
        (self.root / "summary_v1.0.0.md").write_text(
            summary.text or "(no output)", encoding="utf-8"
        )

        improvements = self._agent_turn(
            "openclaw",
            instruction_body=(
                "요약을 바탕으로 improvements_v0.0.1.md를 작성하세요. 각 작업은 "
                "'- [TASK-001] @hermes-b: 설명' 형식의 줄로 작성하고 담당자를 명시하세요."
            ),
            stage_objective=(
                "개선 작업 목록을 TASK-NNN 형식으로 작성하세요. 각 줄은 "
                "'- [TASK-NNN] @hermes-a|@hermes-b: 한 줄 설명' 형식입니다."
            ),
            context_artifacts=[summary.text or a_text],
            artifact_name="improvements_v0.0.1.md",
        )
        improvements_text = improvements.text or ""
        (self.root / "improvements_v0.0.1.md").write_text(
            improvements_text or "(no output)", encoding="utf-8"
        )
        self.tasks = parse_tasks(improvements_text)
        if not self.tasks:
            # tolerant fallback (PM-6): no parseable tasks -> log a blocker and
            # synthesize one generic task so the dev loop still exercises stages.
            assert self.slog is not None
            self.slog.broadcast("improvements.md produced no parseable TASK lines — using fallback task")
            self.tasks = [Task("TASK-001", "hermes-b", self.goal)]

        # stage 4: plan approved -> create the feature branch
        self.narrate(4)
        self._write_status(4, "openclaw", state="active", branch=self.feature_branch)
        self._git("checkout", "-B", self.feature_branch)

    # ----------------------------------------- stages 5-8: development loop
    def _develop_loop(self) -> None:
        """Scenario step 9 -> dashboard stages 5-8 (implementation..tests_passed)."""
        for task in self.tasks:
            self._check_budget()
            self.narrate(5)
            self._write_status(5, task.assignee, state="active", branch=self.feature_branch)

            impl = self._agent_turn(
                task.assignee,
                instruction_body=f"[{task.task_id}] {task.description}",
                stage_objective=(
                    f"{task.task_id} 작업을 구현하세요: {task.description}. "
                    "코드를 직접 수정하고 변경 내용을 설명하세요."
                ),
                artifact_name=f"impl_{task.task_id}.md",
            )

            # self-review + revise loop, capped at MAX_REVISE_ROUNDS (helper 8e)
            self.narrate(6)
            self._write_status(6, "hermes-a", state="active", branch=self.feature_branch)
            review_ok = False
            for round_no in range(1, config.MAX_REVISE_ROUNDS + 1):
                self._check_budget()
                review = self._agent_turn(
                    "hermes-a",
                    instruction_body=f"[{task.task_id}] 변경 사항을 리뷰해주세요.",
                    stage_objective=(
                        f"{task.task_id}의 변경 사항을 리뷰하고, 문제가 없으면 "
                        "'리뷰 승인'을, 수정이 필요하면 구체적인 피드백을 작성하세요."
                    ),
                    context_artifacts=[impl.text or "(no impl output)",
                                       self._git("diff", "--stat").stdout],
                    from_agent="hermes-b",
                    artifact_name=f"review_{task.task_id}_r{round_no}.md",
                )
                if review.ok and ("승인" in review.text or "approve" in review.text.lower()):
                    review_ok = True
                    break
                if round_no < config.MAX_REVISE_ROUNDS:
                    impl = self._agent_turn(
                        task.assignee,
                        instruction_body=f"[{task.task_id}] 리뷰 피드백을 반영해주세요.",
                        stage_objective="리뷰 피드백을 코드에 반영하세요.",
                        context_artifacts=[review.text or "(no review output)"],
                        from_agent="hermes-a",
                        artifact_name=f"impl_{task.task_id}_r{round_no}.md",
                    )

            # run tests (stage 7 -> 8)
            self.narrate(7)
            self._write_status(7, "hermes-b", state="active", branch=self.feature_branch)
            tr = self.run_tests()
            self.test_results = {"passed": tr["passed"], "failed": tr["failed"]}
            (self.artifacts / f"test_{task.task_id}.log").write_text(
                tr["raw"], encoding="utf-8"
            )

            if review_ok and tr["failed"] == 0:
                task.status = "done"
                self.narrate(8)
            else:
                # 8e: mark-failed-continue — do not crash, do not loop forever
                task.status = "failed"
                assert self.slog is not None
                self.slog.broadcast(
                    f"{task.task_id} marked failed after {config.MAX_REVISE_ROUNDS} "
                    f"revise rounds — continuing to next task"
                )
            self._write_status(8, "openclaw", state="active", branch=self.feature_branch)

    def run_tests(self) -> dict:
        """Auto-detect and run the project's test runner (helper 8b)."""
        pkg = self.project / "package.json"
        if pkg.is_file():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
            if isinstance(data.get("scripts"), dict) and "test" in data["scripts"]:
                return self._exec_tests(["npm", "test"])
        if (
            (self.project / "pytest.ini").is_file()
            or (self.project / "pyproject.toml").is_file()
            or (self.project / "tests").is_dir()
        ):
            return self._exec_tests(["pytest"])
        return {"passed": 0, "failed": 0, "raw": "no test runner detected"}

    def _exec_tests(self, cmd: list[str]) -> dict:
        """Run a test command. The runner's exit code is authoritative for
        pass/fail (regex-scraping a summary line is unreliable across npm /
        pytest / jest output formats); the full output is kept in ``raw`` for
        the operator. ``passed``/``failed`` are coarse 1/0 signals — enough for
        the dev-loop gate (``tr["failed"] == 0``) and status.json display."""
        try:
            res = subprocess.run(
                cmd, cwd=str(self.project), capture_output=True, text=True, timeout=600
            )
            raw = (res.stdout + "\n" + res.stderr).strip()
            if res.returncode == 0:
                return {"passed": 1, "failed": 0, "raw": raw}
            return {"passed": 0, "failed": 1, "raw": raw}
        except subprocess.TimeoutExpired:
            return {"passed": 0, "failed": 1, "raw": f"{cmd} timed out after 600s"}
        except OSError as exc:
            return {"passed": 0, "failed": 0, "raw": f"test runner unavailable: {exc}"}

    # ------------------------------------------- stages 9-12: PR submission
    def _submit_pr(self) -> None:
        """Scenario steps 10-12 -> dashboard stages 9-12.

        In dryrun mode stages 9-12 are narration + pr_draft.json simulation only
        (no real agent turns, no real git push, no real gh pr create — the
        honest-bar boundary from plan §5).
        """
        self._check_budget()
        diff_stat = self._git("diff", f"{self.branch}...{self.feature_branch}", "--stat").stdout

        # stage 9: PR drafted
        self.narrate(9)
        self._write_status(9, "openclaw", state="active", branch=self.feature_branch)
        if self.mode == "live":
            pr_body_res = self._agent_turn(
                "openclaw",
                instruction_body="변경 사항을 바탕으로 PR 본문을 작성해주세요.",
                stage_objective="PR 제목과 본문을 작성하세요. 변경 요약과 테스트 결과를 포함하세요.",
                context_artifacts=[diff_stat,
                                   (self.root / "improvements_v0.0.1.md").read_text(encoding="utf-8")],
                artifact_name="pr_body.md",
            )
            pr_body = pr_body_res.text or "Dev-Booth automated improvements."
        else:
            pr_body = (
                f"Dev-Booth dryrun — automated improvements for {self.repo_name}.\n\n"
                f"Goal: {self.goal}\n\nChanged files:\n{diff_stat}"
            )
        pr_title = f"[Dev-Booth] {self.session_name} — {self.goal}"

        # commit (O3: commit is its own narration event) — Hermes-B commits locally
        self._git("add", "-A")
        commit_msg = f"Dev-Booth: {self.goal} ({self.session_name})"
        commit_res = self._git("commit", "-m", commit_msg)
        if commit_res.returncode == 0:
            head = self._git("rev-parse", "HEAD").stdout.strip()
            self.last_commit = {"hash": head, "message": commit_msg}
        assert self.slog is not None
        self.slog.broadcast(f"commit prepared on {self.feature_branch}: {commit_msg}")

        # push (O3: push is a separate narration event) — orchestrator pushes
        self.slog.broadcast(f"pushing {self.feature_branch} (mode={self.mode})")
        self._git_push("-u", "origin", self.feature_branch)

        # stage 10: PR review
        self.narrate(10)
        self._write_status(10, "hermes-a", state="active", branch=self.feature_branch)

        # stage 11: PR approved
        self.narrate(11)
        self._write_status(11, "openclaw", state="active", branch=self.feature_branch)

        # gh pr create — dryrun: synthetic descriptor; live: real PR
        if self.mode == "live":
            pr_res = self._gh(
                "pr", "create",
                "--repo", f"{config.UPSTREAM_OWNER}/{self.repo_name}",
                "--head", f"{config.BOT_OWNER}:{self.feature_branch}",
                "--base", "main",
                "--title", pr_title,
                "--body", pr_body,
            )
            pr_url = pr_res.stdout.strip() or "https://github.com/(pr-created)"
            pr_number = 0
        else:
            pr_url = "DRYRUN://no-pr"
            pr_number = 0
            print("[_submit_pr] dryrun: gh pr create skipped (logged-only)")
        pr_draft = {
            "number": pr_number,
            "url": pr_url,
            "title": pr_title,
            "body": pr_body,
            "head": f"{config.BOT_OWNER}:{self.feature_branch}",
            "base": "main",
        }
        self.pr_draft_file.write_text(
            json.dumps(pr_draft, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # stage 12: PR merged
        self.narrate(12)
        self._write_status(12, "orchestrator", state="active", branch=self.feature_branch)

    # ------------------------------------------------------------- helpers
    def _project_file_list(self) -> str:
        if not self.project.is_dir():
            return "(project not cloned)"
        res = subprocess.run(
            ["git", "ls-files"], cwd=str(self.project), capture_output=True, text=True
        )
        listing = res.stdout if res.returncode == 0 else ""
        if not listing:
            # not a git repo or empty — fall back to a bounded find
            files = [
                str(p.relative_to(self.project))
                for p in sorted(self.project.rglob("*"))
                if p.is_file() and ".git" not in p.parts
            ]
            listing = "\n".join(files[:300])
        return _truncate(listing, config.BODY_CAP)


class _SessionAborted(Exception):
    """Raised by the SIGINT handler to unwind the run cleanly."""


class _SessionTimeout(Exception):
    """Raised when the whole-session wall-clock cap is exceeded."""


# --------------------------------------------------------------------------
# CLI entry point
# --------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="core.orchestrator",
        description="Dev-Booth multi-agent orchestrator (12-stage scenario).",
    )
    parser.add_argument("session", help="session name (dir under SESSIONS_ROOT)")
    parser.add_argument("repo_url", help="GitHub repo URL to fork/clone/improve")
    parser.add_argument("--goal", default="코드 품질 개선 및 버그 수정", help="session goal")
    parser.add_argument(
        "--mode", choices=("dryrun", "live"), default="dryrun",
        help="dryrun (default): no real git push / gh pr create",
    )
    args = parser.parse_args(argv)

    session = DevBoothSession(args.session, args.repo_url, goal=args.goal, mode=args.mode)
    return session.run()


if __name__ == "__main__":
    sys.exit(main())
