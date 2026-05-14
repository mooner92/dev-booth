# Dev-Booth Multi-Agent System Completion — Work Plan v3 (FINAL)

**Status:** PENDING APPROVAL
**Mode:** ralplan consensus, deliberate. Converged at iteration 3 of max 5.
**Consensus:** Architect → SOUND. Critic → APPROVE. (3 minor corrections folded in below: NEW-1, NEW-3, O9.)
**Date:** 2026-05-14

This plan completes the Dev-Booth multi-agent runtime. It is self-contained — an executor can work from it alone. Every reviewer finding across 3 iterations (v1: 3 blocking factual errors; v2: N1–N5; v3: NEW-1/NEW-3/O9) is resolved and the resolutions are recorded in §11.

---

## 0. RALPLAN-DR Summary

### Principles (P1–P5)

- **P1 — Two status surfaces, one canonical signal.** The dashboard derives state ONLY from `<session>/log/messages.jsonl` + `<session>/queues/`. `status.json` is a user-mandated operator artifact, written from the same orchestrator state machine, NEVER read by the dashboard.
- **P2 — Real Hermes agents, profile-selected** via the `HERMES_PROFILE` env var. No mock LLM, no `core/llm.py`.
- **P3 — Orchestrator is a mediator, NOT a participant — enforced at the filesystem layer.** The orchestrator's progress narration is written via **direct append** to `<session>/log/messages.jsonl` in AWG line format — **never** via `MessageQueue.send()` — so **no `queues/orchestrator/` directory is ever created**. `_detect_agents` / `queue_depths` / `any_running` only ever see `openclaw`, `hermes-a`, `hermes-b`. Agent-to-agent messages still flow through `MessageQueue.send()`.
- **P4 — Safety enforced by structure, not prompts.** Turn caps, timeouts, mode gating, idempotency are config/code. `SOUL.md` is persona text, NEVER counted as a control.
- **P5 — Reconcile to verified reality.** Every claim was checked against live source. We do not extend AWG internals.

### Top 3 Decision Drivers

1. **DD-A — Verified invocation surface.** `hermes -z "<prompt>" --yolo` with `HERMES_PROFILE` is the only confirmed-working stateless invocation. `--continue` is NOT composable with `-z` (verified: `-z`/`--oneshot` bypasses the chat code path; `run_oneshot()` has no session/continue/resume parameter). All 3 agents are stateless per turn; the orchestrator supplies 100% of context.
2. **DD-B — AWG API is fixed, not extensible within scope.** `MessageQueue.send()` rebuilds `refs` from fixed keyword args; arbitrary `refs` dicts are silently dropped. The only surviving cross-process signal is `kind`, `from`/`to`, and the `body` string. Detection relies on `kind:"status"` + body keyword regex only.
3. **DD-C — Detection keys on free-text keywords, not decorative markers.** `detect_stage` matches ONLY the semantic keyword table in `STAGES`. The `[STAGE n/12: stage_id]` marker is human decoration, invisible to detection. Narration bodies MUST carry the exact canonical keyword for their stage.

### Viable Options

- **Option A (CHOSEN) — Discrete stateless `hermes -z` subprocess per turn, file-queue coordination.**
  `HERMES_PROFILE=<profile> /home/mooner92/.local/bin/hermes -z "<prompt>" --yolo`, one subprocess per agent turn, for **all 3 agents**. The orchestrator owns the AWG `MessageQueue`, supplies full context every prompt, recovers from a crashed turn by re-running it.
  *Why A is still distinct from B after dropping `--continue`:* Option B's fragility is **IPC-based** — long-lived chat processes over sockets/pipes, where a dropped pipe corrupts an entire multi-turn session with no clean restart point. Option A's coordination substrate is the **durable file queue**, and each turn is a **discrete short-lived subprocess** — a crash loses at most one turn, recovered by re-dispatching one queue file. Statelessness does not change that A's failure unit is one turn while B's is one whole session.
- **Option B (REJECTED)** — long-lived `hermes` chat processes + pipes. IPC fragility, loss of per-turn crash recovery. The `--continue` incompatibility does not rehabilitate B — B was never about statefulness, it was about the coordination substrate.
- **Option C (DEFERRED)** — `hermes acp`/`mcp` protocol for native agent memory. Deferred pending investigation (FU-3); unverified protocol surface, out of scope for completing the 6 deliverables now.

---

## 1. Context

The Dev-Booth dashboard (FastAPI, package root `dashboard.backend`) is already built and reads sessions from `SESSIONS_ROOT`. The agent runtime is incomplete. This plan completes the 6 user deliverables: (1) `core/logger.py`, (2) 3 Hermes profiles + a `SOUL.md` each, (3) rewrite `core/orchestrator.py`, (4) rewrite `run.sh`, (5) real E2E against `https://github.com/mooner92/firebase-chat-exp`, (6) verify real-time dashboard logs.

**Verified environment facts (P5):**
- venv python `/dev-booth/env/bin/python3.11`; awg `/dev-booth/env/bin/awg` (importable as `agent_working_group` only from the venv).
- **hermes binary `/home/mooner92/.local/bin/hermes`** (a wrapper that scrubs `PYTHONPATH`/`PYTHONHOME` and execs `/home/mooner92/.hermes/hermes-agent/venv/bin/hermes` — the env scrub is desirable for subprocess isolation). NOTE: there is NO `hermes` under `/dev-booth/env/bin/`.
- `.env` is loaded by `core/orchestrator.py` from **`/dev-booth/config/.env`** (NOT `/dev-booth/.env`).
- `dashboard/backend/services/stage_mapper.py` `STAGES` is the source of truth for stage keywords (12 stages, Korean+English lists, NFC-normalized regex). The `[STAGE n/12]` prefix is invisible to `detect_stage`.
- `dashboard/backend/tests/conftest.py` puts `REPO_ROOT` (= `/dev-booth`) on `sys.path` and imports via `from dashboard.backend...`. New observability/cross-seam tests MUST live under that dir to inherit it.
- `StageTracker.observe()` is called for EVERY log entry with no `kind` filter — `kind:"status"` messages ARE picked up by the body regex.
- `StageTracker` resolves conflicts with a 60-second window (`config.STAGE_CONFLICT_WINDOW_S = 60.0`): highest-stage-wins inside; latest-wins outside. The heartbeat must be time-bounded (~45s) to exploit this.
- `MessageQueue.send()` builds the message dict `{id, kind, from, to, body, refs, priority, createdAt, createdAtMs}` and appends it to `<root>/log/messages.jsonl`; valid `kind` values are `blocker(99)/question(70)/answer(60)/instruction(50)/status(30)/note(10)`.
- `MessageQueue.initialize(agents)` creates `log/`, `tmp/locks/`, touches `messages.jsonl`, and creates `queues/<agent>/{inbox,processing,processed,dead}/` ONLY for the agents passed.

---

## 2. Decision Drivers Resolved (DD1–DD6)

### DD1 — Agent invocation
All 3 agents are invoked **statelessly, one subprocess per turn**:
`HERMES_PROFILE=<profile> /home/mooner92/.local/bin/hermes -z "<prompt>" --yolo`.
There is **no `--continue`** anywhere — `-z`/`--oneshot` bypasses the chat code path; `run_oneshot()` has no session/continue/resume parameter. The orchestrator supplies ALL context for ALL THREE agents in every prompt. Agent-side persistent memory moves to FU-2.

### DD2 — Message kinds and the orchestrator's progress channel
- **Agent-to-agent messages** go through `MessageQueue.send()` with kinds: `instruction` (50), `answer` (60), `question` (70), `blocker` (99). These are the only messages that create/use `queues/<agent>/` directories.
- **Orchestrator progress narration** is `kind:"status"` (priority 30), `from:"orchestrator"`, `to:"orchestrator"` (self-addressed) or `to:"all"`. It is **NOT sent via `MessageQueue.send()`** — it is **directly appended** to `<session>/log/messages.jsonl` (see DD4, helper 8f, Phase 3).
- **`refs` is `{}`** on orchestrator narration. `MessageQueue.send()` rebuilds `refs` from fixed keyword args and silently drops arbitrary dicts — there is no `{stage,stage_id,kind:"progress"}` passthrough. Detection depends on `kind:"status"` + body keyword regex, not `refs`. The `[STAGE n/12: stage_id]` token is **decorative**.
- `core/logger.py` is the thin direct-append writer; it does NOT wrap `MessageQueue.send()`.

### DD3 — `status.json`
User deliverable, written by `_write_status()` at every stage transition, never read by the dashboard. Schema: `session, status, current_step, current_agent, repo_url, repo_name, branch, started_at, last_commit{hash,message}, test_results{passed,failed}`.

### DD4 — Orchestrator as sole AWG client
- Runs under `/dev-booth/env/bin/python3.11`, imports `MessageQueue` directly, is the **only** AWG client.
- `MessageQueue` initialized at the **session root** (`<session>/`), NOT `<session>/awg`. Manages `<session>/queues/<agent>/{inbox,processing,processed,dead}/` for the 3 real agents only.
- Per-turn loop: `send` → `receive` → `hermes` subprocess → `ack` on success / `nack` on failure.
- `setup()` calls `requeue_stale()` to recover strands left in `processing/` (PM-2 — `test-awg` ships with one).
- The orchestrator's own progress narration **never touches `MessageQueue.send()`** — direct-append only. This is why no `queues/orchestrator/` directory is ever created.

### DD5 — Structured status channel + collision-safe narration
- **What survives cross-process:** `kind:"status"`, `from`/`to`, and the `body` string — sufficient because `_build_status` / `StageTracker.observe` regex the **body**. There is NO custom-`refs` mechanism.
- **The `[STAGE n/12: stage_id]` marker is human-readable decoration, NOT the detection mechanism.** `detect_stage('[STAGE 3/12: plan_drafted]')` returns `None`; it returns `(3,'plan_drafted')` only when the **free-text** portion contains a stage-3 keyword.
- **Interpretation A:** the orchestrator's narration generator is **RESPONSIBLE** for collision-avoidance at emit time — it draws every body from the fixed **Canonical Narration Corpus** (§7). The **cross-seam test is the GUARD that proves this, not the mechanism**.
- **Window survival / heartbeat:** see helper 8f.

### DD6 — Safety, all structural/config
Turn cap `agent.max_turns: 40` in each profile's `config.yaml` (verified-real honored key — live `~/.hermes/config.yaml` has `agent.max_turns: 90`). Per-turn subprocess wall-clock timeout `900s`. Session cap `5400s`. Mode gating `dryrun` (default) / `live`: in `dryrun`, `git push` → `--dry-run`, `gh pr create` → logged-only synthetic descriptor. Idempotent fork/clone/branch (8d). `SIGINT` handler. `MAX_REVISE_ROUNDS = 3`, mark-failed-continue (8e). `SOUL.md` is NEVER counted as a control.

---

## 3. Helper Contracts

### 8a — `build_prompt` (all 3 agents, single full-context path)
All three agents use the **same full-context path**. No `--continue` "delta-only" branch. Each turn's prompt:
1. persona preamble (~500 chars, from the profile, NOT the SOUL.md control surface)
2. stage objective (~1000 chars)
3. context artifact(s) — the single most-recent relevant artifact, truncated **head+tail**: first 2000 chars + `\n...[truncated]...\n` + last 2000 chars; `BODY_CAP = 4000` chars/artifact, up to 3 artifacts
4. output contract (~1000 chars)

**Truncation budget & ceiling:** worst-case prompt ≈ 500 + 1000 + (3 × 4000) + 1000 = **~14500 chars ≈ ~4000 tokens**. `PROMPT_HARD_CEILING = 50000` chars — `assert len(prompt) < 50000` before dispatch; on breach drop the oldest artifact, log a warning, re-assemble. `MAX_MODEL_LEN = 65536` tokens — ~14500 chars is comfortably under for every one of the 3 agents at every stage (turns run sequentially, so only one prompt is live at a time).

### 8b — `run_tests`
`package.json` with a `"test"` script → `npm test` (600s timeout); else `pytest.ini`/`pyproject.toml`/`tests/` present → `pytest` (600s); else `{passed:0, failed:0, raw:"no runner"}`.

### 8c — `gh` dryrun contract
`dryrun`: `gh pr create` writes `<session>/pr_draft.json` = `{number:0, url:"DRYRUN://no-pr", title, body, head, base}` and returns it; stages 10–12 read it. `live`: real `gh pr create --json number,url` writes the same file.

### 8d — Idempotency
- **fork:** `gh repo view BOT_OWNER/<repo>` exit 0 → skip, else `gh repo fork`.
- **clone:** if `<session>/project/.git` exists → `git fetch` + `git checkout main` + `git reset --hard origin/main`, else fresh `git clone`.
- **branch:** `git checkout -B <branch>`.

### 8e — `MAX_REVISE_ROUNDS` exhaustion = mark-failed-continue
On the 3rd failed revise round: emit a `status` blocker narration, record the task `failed` in `status.json` `test_results`, proceed to the next task. No crash, no infinite loop.

### 8f — Heartbeat / window-survival narration
**Purpose:** keep the dashboard's `StageTracker` reporting the correct current stage during long silent stretches within a stage.
**Rationale:** `StageTracker` resolves conflicts with a **60-second window** — highest-stage-wins inside it, latest-wins outside it. If no stage marker is appended for a long time, an old lower-stage hit could become "latest" and a late-arriving message could regress the displayed stage. Re-emitting the current-stage marker on a time bound keeps a fresh hit inside the rolling window.
**Contract:**
- Primary trigger — **time-bound:** if `> ~45s` (`HEARTBEAT_INTERVAL_S = 45`) elapsed since the last log append, re-emit the current stage's canonical-corpus body. 45s < the 60s conflict window, so a fresh hit always lands before the window expires.
- Secondary trigger — message-count: also re-emit every `STAGE_HEARTBEAT_EVERY = 15` agent messages (belt-and-suspenders, not the primary mechanism).
- Body content: the exact Canonical Narration Corpus entry for the current stage (§7).
- Routing: via the **direct-append path** (`core/logger.py`), NEVER `MessageQueue.send()`.

---

## 4. Pre-Mortem (Deliberate Mode — 6 scenarios)

| # | Failure scenario | Mitigation |
|---|---|---|
| **PM-1** | Dual-state-machine divergence — `status.json` and the log/queue surface disagree. | Both written from the *same* `_write_status()` + narration calls in the same stage-transition code path. `status.json` is never read back, so it cannot feed divergence into the dashboard. `test_log_is_canonical.py` asserts the dashboard reads only the log. |
| **PM-2** | `processing/` strand deadlock — a message stuck in `processing/` never re-dispatched (real: `test-awg` ships with one). | `setup()` calls `requeue_stale()` moving stale `processing/` files back to `inbox/`. `test_strand_recovery.py` proves it. |
| **PM-3** | Prompt growth across all 3 stateless agents — since all three are stateless and the orchestrator supplies full context every turn, prompt size could grow unbounded as artifacts accumulate, exceeding `MAX_MODEL_LEN` at later stages. | Re-priced (8a): `BODY_CAP=4000` chars, max 3 artifacts/prompt, head+tail truncation, `PROMPT_HARD_CEILING=50000` chars asserted before every dispatch with oldest-artifact-drop on breach. Worst-case prompt ≈14500 chars ≈4000 tokens — comfortably under `MAX_MODEL_LEN=65536` for every one of the 3 agents at every stage. `test_orchestrator_unit` covers the ceiling-breach drop path. |
| **PM-4** | Stale model / wrong vLLM endpoint — agents silently run against the wrong model. | `core/preflight.py` `check_vllm` asserts `curl <base_url>/models` == `EXPECTED_MODEL`; also asserts `awg` importable, `gh auth`, `hermes profile list` shows the 3 profiles. |
| **PM-5** | Agent escapes isolation — real `git push`/PR in dryrun, or an infinite turn loop. | Mode gating (dryrun default): `git push --dry-run`, `gh pr create` logged-only. `agent.max_turns:40`, per-turn 900s timeout, session 5400s cap, `MAX_REVISE_ROUNDS=3`, `SIGINT` handler, idempotent fork/clone/branch. Integration tests run dryrun only; `e2e_live.sh` operator-gated behind `--i-understand-this-is-live`. |
| **PM-6** | `improvements.md` unparseable — Hermes-A produces a plan the task parser can't read. | `test_task_parser` covers malformed input; parser failure records the task `failed` and emits a `blocker` narration rather than crashing (same path as 8e). |

(6 ≥ 5 required — satisfied. PM-7 from v2, "`--continue` session-id collision", was deleted: dropping `--continue` invalidates it.)

---

## 5. Test Plan (Deliberate Mode)

**Two test locations — stated explicitly:**
- **Orchestrator tests** → `/dev-booth/tests/` — run with `/dev-booth/env/bin/python3.11 -m pytest /dev-booth/tests/`. Import `core.*`, run under the venv.
- **Dashboard observability + cross-seam tests** → `/dev-booth/dashboard/backend/tests/` — inherit the **existing** `conftest.py` (puts `/dev-booth` on `sys.path`, `from dashboard.backend...` convention). Run with the existing dashboard test invocation. **Do NOT introduce a competing rootdir or a second conftest convention.**

**Unit (`/dev-booth/tests/`):** `test_config.py`, `test_logger.py` (appends valid AWG-format JSON lines; never creates a `queues/` dir), `test_stage_narration.py` (local sanity check that each corpus body contains its keyword), `test_task_parser.py`, `test_orchestrator_unit.py` (mocked `hermes`/`git`/`gh`: stage transitions, nack-on-failure, `build_prompt` ceiling-breach drop, `MAX_REVISE_ROUNDS` exhaustion), `test_idempotency.py`.

**Integration (`/dev-booth/tests/`):** `test_queue_roundtrip.py` (real venv `MessageQueue` send→receive→ack), `test_strand_recovery.py` (place file in `processing/` → `requeue_stale()` → assert back in `inbox/`), `test_no_orchestrator_queue.py` (run a dryrun session; assert `<session>/queues/` contains exactly `openclaw/`, `hermes-a/`, `hermes-b/` and NO `orchestrator/` dir), `test_hermes_smoke.py` `@slow` (real `HERMES_PROFILE=hermes-a hermes -z`), `test_orchestrator_stages_mocked.py` (full 1→12 mocked).

**Cross-seam (`/dev-booth/dashboard/backend/tests/`):** `test_stage_narration_crossseam.py` **(THE GATE)** — imports `from dashboard.backend.services.stage_mapper import detect_stage`; for **each of the 12 Canonical Narration Corpus entries** asserts `detect_stage(body) == (stage_no, stage_id)` **exactly** (same number AND stage_id, no higher-stage leakage). **CI-blocking.**

**Observability (`/dev-booth/dashboard/backend/tests/`):** `test_dashboard_sees_session.py` (FastAPI `TestClient`; fixture session with corpus markers for stages 1→5; `GET /sessions/<name>` asserts `current_stage==5` & `current_stage_id=="implementation"`), `test_log_is_canonical.py` (orchestrator writes to exactly `<session>/log/messages.jsonl`; `status.json` NOT under any dashboard-read path).

**E2E (`/dev-booth/tests/e2e/` — shell scripts):** `e2e_dryrun.sh` (`run.sh start e2e-dryrun https://github.com/mooner92/firebase-chat-exp --mode dryrun`; asserts exit 0, `messages.jsonl` exists, `TestClient` shows ≥1 stage transition, `status.json` exists, `pr_draft.json` `url=="DRYRUN://no-pr"`, all `processing/` empty — **honest bar: stages 1–8 real, 9–12 simulated**); `e2e_live.sh` (operator-only, gated behind `--i-understand-this-is-live`); `verify_dashboard.sh` (starts dashboard on port 7000, runs a dryrun, curls `GET /sessions/<name>`, confirms `current_stage` advances over time).

---

## 6. Phases

> All Python is run with `/dev-booth/env/bin/python3.11`. `awg` is `/dev-booth/env/bin/awg`. `hermes` is `/home/mooner92/.local/bin/hermes`. The orchestrator imports `MessageQueue` directly; it never shells to `awg`.

### Phase 0 — Preflight & `.env` reconciliation

**`.env` KEY DISPOSITION MATRIX.** The `.env` file is at **`/dev-booth/config/.env`** (verified — `core/orchestrator.py` calls `load_dotenv('/dev-booth/config/.env')`).

| Key | Disposition | Reason |
|---|---|---|
| `GITHUB_TOKEN` | **KEEP** | Rewritten orchestrator's `gh` helper needs it. |
| `GITHUB_UPSTREAM_OWNER` | **KEEP** | Orchestrator fork source. |
| `GITHUB_BOT_OWNER` | **KEEP** | Orchestrator fork target / idempotency check. |
| `DEV_BOOTH_PATH` | **KEEP** | Session root path; confirm it agrees with the dashboard's `DEVBOOTH_SESSIONS_ROOT` (see O9). |
| GPU / `MAX_MODEL_LEN` keys | **KEEP** | Still relevant to the vLLM runtime. |
| `DEVBOOTH_SESSIONS_ROOT`, `PROMETHEUS_URL` | **KEEP** (if present) | Read by `dashboard/backend/config.py`. |
| `VLLM_BASE_URL` | **DELETE** | Stale — only dead `core/llm.py` read it. The hermes `default` profile `config.yaml` is authoritative (`base_url http://localhost:8003/v1`, `Qwen2.5-Coder-14B-Instruct`). |
| `AGENT_MODEL` | **DELETE** | Stale — only dead `core/llm.py` read it. |
| `OPENCLAW_TOKEN`, `HERMES_A_TOKEN`, `HERMES_B_TOKEN` | **DELETE** | Dead once `bots/` is archived in Phase 1. |
| `DISCORD_GUILD_ID` | **DELETE** | Dead once `bots/` is archived. |
| `NOTION_TOKEN`, `NOTION_DATABASE_ID` | **DELETE** | `core/notion_logger.py` deleted in Phase 1; rewritten orchestrator does not use Notion. |

**Rollback note:** all `.env` edits are git-revertible. If Phase 4 reveals a key was still needed, `git revert`/`git checkout` the `.env` change.

**Create `core/config.py`** with constants — `SESSIONS_ROOT`, `VENV_PYTHON="/dev-booth/env/bin/python3.11"`, `AWG_BIN="/dev-booth/env/bin/awg"`, `HERMES_BIN="/home/mooner92/.local/bin/hermes"`, `AGENTS` (3 profile names), `ORCHESTRATOR_ID="orchestrator"`, `HERMES_MAX_TURNS=40`, `HERMES_TURN_TIMEOUT_S=900`, `SESSION_TIMEOUT_S=5400`, `MAX_REVISE_ROUNDS=3`, `BODY_CAP=4000`, `PROMPT_HARD_CEILING=50000`, `STAGE_HEARTBEAT_EVERY=15`, `HEARTBEAT_INTERVAL_S=45`, `MAX_MODEL_LEN=65536`, `GITHUB_TOKEN`/`UPSTREAM_OWNER`/`BOT_OWNER`, `EXPECTED_MODEL="/data/vllm/models/Qwen2.5-Coder-14B-Instruct"`, `RESULTS_DIR="/dev-booth/reports/results"`.

**Create `core/preflight.py`** — `check_vllm()` asserts `curl <base_url>/models` == `EXPECTED_MODEL` (model identity, not just liveness); asserts `awg` exists + importable under venv python, `gh auth status` ok, `hermes profile list` shows the 3 profiles.

**Acceptance:** `/dev-booth/env/bin/python3.11 -c "import core.config"` exits 0; `/dev-booth/env/bin/python3.11 -m core.preflight` exits 0 against the live vLLM endpoint; `grep -E 'VLLM_BASE_URL|AGENT_MODEL|NOTION_|OPENCLAW_TOKEN|HERMES_[AB]_TOKEN|DISCORD_GUILD_ID' /dev-booth/config/.env` returns nothing.

### Phase 1 — Remove dead code
Delete `core/agent.py`, `core/llm.py`, `core/notion_logger.py`. Archive `bots/` → `archive/bots/`. `grep -rn 'core.llm\|core.agent\|core.notion_logger\|from bots' /dev-booth/core /dev-booth/dashboard` confirms no dead imports.
**Acceptance:** the grep returns nothing; the `import core.orchestrator` check is re-verified at the end of Phase 4.

### Phase 2 — Hermes profiles + SOUL.md
`hermes profile create <name> --clone --clone-from default` for `openclaw`, `hermes-a`, `hermes-b`. Set `agent.max_turns: 40` in each profile's `config.yaml`. Author a `SOUL.md` per agent with a guaranteed probe token: `오케스트레이터` (openclaw), `아키텍트` (hermes-a), `개발자` (hermes-b). Keep version-controlled copies in `core/souls/`.
**Acceptance:** `hermes profile list` shows all 3; each `config.yaml` has `agent.max_turns: 40`; the probe-token greps on `core/souls/*` succeed; `HERMES_PROFILE=hermes-a /home/mooner92/.local/bin/hermes -z "ping" --yolo` exits 0.

### Phase 3 — `core/logger.py`
`SessionLog` with:
- `narrate(stage, stage_id, body)` — appends one AWG-format JSON line to `<session>/log/messages.jsonl`: `{id, kind:"status", from:"orchestrator", to:"orchestrator", body, refs:{}, priority:30, createdAt, createdAtMs}`, `body` = the §7 corpus entry for `stage`.
- `broadcast(body)` — same but `to:"all"`.

**Critical:** `core/logger.py` writes by **direct file append** in exact AWG line format. It NEVER imports or calls `MessageQueue.send()`. It NEVER creates a `queues/` directory. **It MUST `mkdir(parents=True, exist_ok=True)` the `<session>/log/` directory defensively before its first append** (so the direct-append path never races a missing directory, and `test_logger` can run the logger in isolation without a prior `setup()` call).
**Acceptance:** `test_logger.py` passes; after exercising `SessionLog` the session dir has valid `log/messages.jsonl` and **no `queues/orchestrator/`** directory.

### Phase 4 — Rewrite `core/orchestrator.py`
`DevBoothSession`:
- `__init__` — paths/names; `MessageQueue` rooted at `<session>/` (NOT `<session>/awg`); `self.project = <session>/project`.
- `setup()` — idempotent fork/clone/branch (8d); init `MessageQueue` at session root, `initialize(("openclaw","hermes-a","hermes-b"))`; `requeue_stale()`; install `SIGINT` handler; instantiate `SessionLog`; write initial `status.json`.
- `run_agent_turn()` — `send`→`receive`→`HERMES_PROFILE=<profile> /home/mooner92/.local/bin/hermes -z "<prompt>" --yolo` subprocess (`cwd=self.project`, `timeout=900`) → `ack` on success / `nack` on failure.
- `build_prompt()` — helper 8a (full-context for all 3 agents, head+tail truncation, `PROMPT_HARD_CEILING` assert).
- git/gh helpers — dryrun-aware (8c/8d).
- `run_tests()` — helper 8b.
- `_write_status()` — DD3 schema, every stage transition.
- `stage_01`…`stage_12` — each emits its §7 corpus marker via `SessionLog.narrate()` at stage start + heartbeat (8f); stages 1–8 do real subprocess work in both modes, stages 9–12 in dryrun are narration + `pr_draft.json` simulation only.
- `run()` — deterministic state machine, enforces `SESSION_TIMEOUT_S` and `MAX_REVISE_ROUNDS`.
- Entry: `python -m core.orchestrator <session> <repo> [--mode dryrun|live]`, default `dryrun`.

**Acceptance:** `test_orchestrator_unit.py`, `test_orchestrator_stages_mocked.py`, `test_idempotency.py`, `test_task_parser.py`, `test_queue_roundtrip.py`, `test_strand_recovery.py`, `test_no_orchestrator_queue.py` pass; `/dev-booth/env/bin/python3.11 -c "import core.orchestrator"` exits 0.

### Phase 5 — Rewrite `run.sh`
Subcommands: `start <session> <repo> [--mode ...]` (activates venv, launches `python -m core.orchestrator ...`, records PID); `stop` (verifies no orchestrator PID AND no orphaned hermes subprocess via `pgrep -f`); `status` (prints `status.json` summary); `logs` (tails `<session>/log/messages.jsonl`). `set -euo pipefail`. No references to `bots/`.
**Acceptance:** `bash -n run.sh` exits 0; `run.sh start` launches a dryrun reaching stage ≥1; `run.sh stop` leaves zero orchestrator/hermes processes (`pgrep -f` confirms); `run.sh status` prints the current stage.

### Phase 6 — Tests + E2E + dashboard verification
Write all unit/integration tests into `/dev-booth/tests/`; cross-seam + observability tests into `/dev-booth/dashboard/backend/tests/`. **Fill and verify the §7 Canonical Narration Corpus:** re-read `/dev-booth/dashboard/backend/services/stage_mapper.py` `STAGES`, confirm each of the 12 corpus entries contains that stage's exact keyword and no higher-stage keyword, then run `test_stage_narration_crossseam.py` until all 12 assertions pass — this test is the gate. Run `e2e_dryrun.sh` against `https://github.com/mooner92/firebase-chat-exp`. Run `verify_dashboard.sh`.
**Acceptance:** `/dev-booth/env/bin/python3.11 -m pytest /dev-booth/tests/` all pass (`@slow` on demand); dashboard test suite (existing invocation) — cross-seam + observability tests pass; `e2e_dryrun.sh` exits 0 with all assertions met; `verify_dashboard.sh` shows `current_stage` advancing.

---

## 7. Canonical Narration Corpus

The orchestrator's narration generator (8f, `core/logger.py`) draws every status body from this fixed corpus. Each entry MUST (a) contain the **exact canonical keyword** for its stage from `stage_mapper.STAGES`, and (b) contain **NO keyword from any higher stage**.

> **Executor instruction:** the draft `body` strings below were verified by the Architect against the current `/dev-booth/dashboard/backend/services/stage_mapper.py` — all 12 map to their intended stage with no higher-stage collision. Still **re-read that file** before finalizing in case `STAGES` has changed, and treat `test_stage_narration_crossseam.py` as the CI-blocking gate.

| Stage | stage_id | Draft body (must pass `detect_stage`) |
|---|---|---|
| 1 | `repo_clone` | `[STAGE 1/12: repo_clone] git clone of the target repository complete.` |
| 2 | `initial_scan` | `[STAGE 2/12: initial_scan] initial scan of the codebase underway.` |
| 3 | `plan_drafted` | `[STAGE 3/12: plan_drafted] drafting the implementation plan now (draft plan in progress).` |
| 4 | `plan_approved` | `[STAGE 4/12: plan_approved] the implementation plan approved by the orchestrator.` |
| 5 | `implementation` | `[STAGE 5/12: implementation] implementing the approved changes.` |
| 6 | `self_review` | `[STAGE 6/12: self_review] self review of the changes in progress.` |
| 7 | `tests_running` | `[STAGE 7/12: tests_running] running tests against the working tree.` |
| 8 | `tests_passed` | `[STAGE 8/12: tests_passed] all tests passed.` |
| 9 | `pr_drafted` | `[STAGE 9/12: pr_drafted] pr drafted and ready for review.` |
| 10 | `pr_review` | `[STAGE 10/12: pr_review] pr review requested from the reviewer.` |
| 11 | `pr_approved` | `[STAGE 11/12: pr_approved] pr approved by the reviewer.` |
| 12 | `pr_merged` | `[STAGE 12/12: pr_merged] pr merged into main.` |

**Collision-avoidance caution** (`detect_stage` returns the HIGHEST matching stage):
- Stage-3 body must not contain `plan approved`/`approved the plan` (stage 4).
- Stage-7 body must not contain `tests passed`/`0 failures` (stage 8).
- Stage-9 body must not contain `pr review` (10), `pr approved` (11), or `merged` (12). Note `gh pr create` is itself a stage-9 keyword — fine to use, but do not also write "review" or "merge". (The bare word "review" alone is NOT a stage-10 match — stage 10 keys on the phrase `pr review`/`review requested`.)
- Stage-1 body uses `git clone` — verify no stage-2+ keyword.
- The `[STAGE n/12: stage_id]` prefix is **decorative** and invisible to `detect_stage`; detection depends solely on the free-text keyword.

---

## 8. ADR-006 (FINAL)

**Decision:** Complete Dev-Booth as **Option A** — discrete, **stateless** `hermes -z` subprocess per turn for **all 3 agents**, coordinated through file-based AWG message queues, with the orchestrator as a non-participant mediator that writes its own progress narration by **direct append** to `<session>/log/messages.jsonl`.

**Decision Drivers:** DD-A — `--continue` is not composable with `-z` (verified); statelessness is forced, not chosen. DD-B — `MessageQueue.send()` has a fixed `refs` signature; no custom-`refs` channel is possible within scope. DD-C — `stage_mapper.detect_stage` keys only on free-text keywords; narration must carry canonical keywords.

**Alternatives considered:** Option B (long-lived chat + pipes) — rejected for IPC fragility and loss of per-turn crash recovery; dropping `--continue` did not rehabilitate it (B's failure unit is a whole session, A's is one turn). Option C (`hermes acp`/`mcp` native memory) — deferred (FU-3); unverified protocol surface, out of scope.

**Why chosen:** A is the only option with a verified-working invocation, a durable file-queue coordination substrate, per-turn crash recovery, and no dependency on extending AWG internals or an unverified protocol.

**Consequences:** All 3 agents are stateless; the orchestrator carries 100% of context every turn (8a, bounded by `BODY_CAP`/`PROMPT_HARD_CEILING`). The cross-process status signal is reduced to `kind:"status"` + `from`/`to` + body keyword regex — no `refs` passthrough; sufficient because `StageTracker.observe` regexes the body for every entry. The orchestrator's narration is direct-appended, never `MessageQueue.send()` — so no `queues/orchestrator/` directory exists and the dashboard never sees a phantom 4th agent (honors P3 at the filesystem layer). Narration bodies must come from the Canonical Narration Corpus; the cross-seam test is a CI-blocking gate. The heartbeat is time-bounded (~45s) to stay inside `StageTracker`'s 60s conflict window. Two writers append to the same `messages.jsonl` (orchestrator narration + `MessageQueue.send()` for agent messages), but the orchestrator is single-threaded and the sole process invoking both — POSIX `O_APPEND` of sub-`PIPE_BUF` JSON lines is atomic, and the dashboard's `LogTailer` already skips partial lines — no concurrency hazard.

**Follow-ups:** FU-2 — agent-side persistent memory: revisit once Option A is stable (would require `hermes` chat-mode sessions or an external memory store the orchestrator threads into prompts). FU-3 — investigate `hermes acp`/`mcp` (Option C). **(Not planned)** — extending AWG's `MessageQueue.send()` to accept arbitrary `refs` is out of P5 scope and not planned.

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Canonical corpus entry maps to the wrong stage (keyword collision). | `test_stage_narration_crossseam.py` is a CI-blocking gate asserting exact `(stage_no, stage_id)` for all 12; must be green before Phase 6 closes. |
| `detect_stage` returns highest-matching stage → a body accidentally contains a higher-stage keyword. | Per-entry collision-avoidance caution in §7; cross-seam test catches it. |
| Orchestrator narration accidentally routed via `MessageQueue.send()` → phantom `queues/orchestrator/`. | `core/logger.py` has no `MessageQueue` import; `test_no_orchestrator_queue.py` asserts `queues/` has exactly the 3 agent dirs after a dryrun. |
| Heartbeat too slow → stage regression in the dashboard. | Time-bound trigger at ~45s, strictly under `StageTracker`'s 60s conflict window; secondary count-based trigger every 15 messages. |
| Prompt growth across 3 stateless agents exceeds `MAX_MODEL_LEN`. | `BODY_CAP=4000`, max 3 artifacts, head+tail truncation, `PROMPT_HARD_CEILING=50000` asserted pre-dispatch with oldest-drop; worst case ≈4000 tokens ≪ 65536. |
| `.env` key deleted that was still needed. | Disposition matrix decided per-key from verified consumers; all changes git-revertible (rollback note in Phase 0). |
| Strand left in `processing/` (`test-awg` ships one). | `setup()` → `requeue_stale()`; `test_strand_recovery.py` proves it. |
| New observability tests collide with the existing dashboard test rootdir. | New tests placed under `/dev-booth/dashboard/backend/tests/` to inherit the existing `conftest.py`; orchestrator tests isolated in `/dev-booth/tests/`. |
| Wrong vLLM model silently used. | `core/preflight.py` `check_vllm` asserts model identity before any run. |
| Real `git push` / PR during a test. | Mode gating (dryrun default); `e2e_live.sh` operator-gated. |
| Agent infinite loop / runaway. | `agent.max_turns:40`, 900s per-turn timeout, 5400s session cap, `MAX_REVISE_ROUNDS=3`, `SIGINT` handler. |

---

## 10. Open Questions / Operator TODOs

(O1 and O7 were resolved during planning and removed.)

- **O2** — `bots/` archive location: `archive/bots/` assumed; confirm no tooling references the old path.
- **O3** — Stage 11 commit/push split: should "commit" and "push" be one stage action or two distinct narration events?
- **O4** — Stages 3 & 4 parallelism: deferred — currently sequential; revisit if turn budget is tight.
- **O5** — Live-run supervision: who watches `e2e_live.sh`, and what is the abort signal?
- **O6** — `GITHUB_TOKEN` scopes: confirm the token has `repo` + `workflow` for fork + PR.
- **O8** — Hermes profile `SOUL.md` install path: confirm where `hermes` expects per-profile soul files vs. the `core/souls/` version-controlled copies.
- **O9** — `.env` location of record: the orchestrator loads `/dev-booth/config/.env`; confirm the dashboard's `config.py` reads the same file (or document the two-file reality), and reconcile `DEV_BOOTH_PATH` vs `DEVBOOTH_SESSIONS_ROOT`. Phase 0 text uses `/dev-booth/config/.env` as the confirmed path.

---

## 11. Reviewer Findings — Resolution Record

**v1 (Architect):** FE-1 `hermes --profile` doesn't exist → fixed in v2 (`HERMES_PROFILE` env var). FE-2 `--max-turns` not composable with `-z` → fixed (`agent.max_turns:40` in profile config). FE-3 O1 resolvable now → fixed (hermes `default` profile config.yaml authoritative; stale `.env` keys deleted). FE-4 stage_mapper structural keyword issue → fixed via DD5 + canonical corpus + cross-seam test.

**v1 (Critic):** all 14 findings resolved by v3 (P1 two-surface, P3 mechanism-in-principle, cross-seam test, ≥5 adversarial pre-mortem, strand recovery, runnable AC, SOUL.md not a control, helper contracts 8a–8e, awg PATH, preflight model identity, Option C deferred, A′ folded then dropped, O7 resolved, observability tests defined).

**v2 (Architect):** N1 `--continue` not composable with `-z` → fixed (all 3 agents stateless, `--continue` dropped entirely). N3 `send()` drops arbitrary `refs` → fixed (`refs:{}`, detection via `kind`+body regex). N4 `orchestrator` queue-dir leak → fixed (direct log append, never `send()`; `test_no_orchestrator_queue`). N5 test import paths → fixed (tests under `dashboard/backend/tests/`, inherit conftest). FE-4b heartbeat rationale → fixed (time-bounded ~45s, correct 60s-conflict-window rationale).

**v2 (Critic):** C1–C9 resolved (P3 mechanism-in-principle, `--continue` clause deleted, pre-mortem re-priced, helper 8a single path, canonical corpus + decorative-marker clarification, `.env` disposition matrix, test-location reconciliation, heartbeat helper 8f, Interpretation A).

**v3 (Architect):** SOUND. NEW-1 `HERMES_BIN` path → folded in (`/home/mooner92/.local/bin/hermes`). NEW-3 logger `mkdir` → folded in (Phase 3 defensive `mkdir`). Two-writer concurrency → confirmed non-issue.

**v3 (Critic):** APPROVE. MINOR `.env` path → folded in as O9 + Phase 0 confirmed path + `DEV_BOOTH_PATH` in KEEP column.

---

## Approval

This plan is **PENDING APPROVAL**. On approval, recommended execution path:
- **`/oh-my-claudecode:team`** — parallel coordinated execution (Phases 0–2 have independent sub-tasks), or
- **`/oh-my-claudecode:ralph`** — sequential execution with per-phase verification.

Phases must run in order (0→6); within Phase 2 the three profiles can be created in parallel. Do not begin Phase 4 until Phase 3's `core/logger.py` and its `test_logger.py` are green.
