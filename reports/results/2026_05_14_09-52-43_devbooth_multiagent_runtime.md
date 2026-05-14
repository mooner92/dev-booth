# Dev-Booth Multi-Agent Runtime — Implementation Results

**Date:** 2026-05-14
**Branch:** `feat/multiagent-runtime-2026-05-14` (off `main`; `main` untouched)
**Plan:** `/dev-booth/reports/plans/2026_05_14_07-44-41_devbooth_multiagent_completion_v3.md`
**Mode:** ralph PRD-driven, 9 user stories US-001..US-009 — all `passes: true`

---

## Summary

The Dev-Booth multi-agent runtime is complete. Three real Hermes agents
(OpenClaw orchestrator, Hermes-A analyst, Hermes-B developer) now run an
autonomous 12-stage scenario — fork → clone → analyze → plan → develop loop →
PR — coordinating through file-based AWG message queues, with every step
visible in the already-built dashboard.

A real end-to-end dryrun against `https://github.com/mooner92/firebase-chat-exp`
completed all 12 stages with real LLM agent turns, and the dashboard tracked it
live (`current_stage` advanced 3→5→11→12, finishing `idle`/`pr_merged`).

**Test totals:** 62 orchestrator tests + 58 dashboard tests = **120 passing**
(the dashboard's original 37 + 21 new). One real E2E dryrun: all assertions
passed.

---

## Deliverables

### Deliverable 1 — `core/logger.py` (US-004)
Direct-append session log writer. `log_message()` appends one AWG-format JSON
line `{id,kind,from,to,body,refs:{},priority,createdAt,createdAtMs}` to
`<session>/log/messages.jsonl`, `fcntl.flock`-guarded, defensive `log/` mkdir.
`SessionLog` wrapper exposes `narrate()` / `broadcast()`.
**Constraint enforced (P3/DD2):** the module never imports or calls
`MessageQueue` — AST-verified by `tests/test_logger.py`. Routing orchestrator
narration through `MessageQueue.send()` would `mkdir` a phantom
`queues/orchestrator/`; direct append keeps the orchestrator a non-participant
at the filesystem layer.
**Evidence:** `tests/test_logger.py` + `tests/test_no_orchestrator_queue.py` —
10 tests incl. a 12-thread × 20-message concurrency test.

### Deliverable 2 — 3 Hermes profiles + SOUL.md (US-003)
`hermes profile create openclaw|hermes-a|hermes-b --clone --clone-from default`.
Each profile's `config.yaml` set to `agent.max_turns: 40` (the FE-2 turn cap —
`--max-turns` is not composable with `-z`, so the cap lives in profile config),
inheriting `base_url http://localhost:8003/v1` + `Qwen2.5-Coder-14B-Instruct`.
Role-specific `SOUL.md` authored for each with a guaranteed probe token
(`오케스트레이터` / `아키텍트` / `개발자`); version-controlled copies in
`core/souls/`.
**Evidence:** `hermes profile list` shows all 3; real round-trip
`HERMES_PROFILE=openclaw hermes -z 'ping' --yolo` → `pong`, exit 0.

### Deliverable 3 — `core/orchestrator.py` rewrite (US-005)
`DevBoothSession` — a deterministic 12-stage state machine:
- **DD1:** every agent turn is a discrete stateless
  `HERMES_PROFILE=<p> hermes -z "<prompt>" --yolo` subprocess. No `--continue`
  anywhere (test-asserted) — the orchestrator supplies 100% of context.
- **DD2/DD4:** orchestrator narration goes via `core/logger.py` direct append;
  agent-to-agent messages (`instruction`/`answer`/`question`/`blocker`) go via
  `MessageQueue.send()`. `MessageQueue` is rooted at the session dir,
  `initialize()`'d with exactly the 3 real agents, `requeue_stale()`'d in
  `setup()` to recover `processing/` strands.
- **DD5/§7:** the `STAGE_NARRATION` Canonical Narration Corpus — 12 bodies, each
  carrying exactly its stage's keyword (CI-gated by the cross-seam test).
- **DD6:** dryrun default — `git push` → `--dry-run`, `gh pr create` →
  logged-only synthetic `pr_draft.json`. Per-turn 900s subprocess timeout,
  5400s session cap, SIGINT graceful abort, `MAX_REVISE_ROUNDS=3`
  mark-failed-continue.
- Helpers 8a–8f all implemented: `build_prompt` (head+tail truncation +
  `PROMPT_HARD_CEILING` drop), `run_tests` (npm/pytest auto-detect), `gh` dryrun
  contract, idempotent fork/clone/branch, revise-exhaustion handling, the
  time-bound stage heartbeat.
**Evidence:** 62 tests pass — `test_orchestrator_unit`, `_stages_mocked`,
`_idempotency`, `_task_parser`, `_queue_roundtrip`, `_strand_recovery`.

### Deliverable 4 — `run.sh` rewrite (US-006)
`set -euo pipefail`, subcommands `start|stop|status|logs|help`. `start` sources
the venv and launches `python -m core.orchestrator`, recording the PID; `stop`
sends SIGINT→SIGTERM and verifies no orphaned orchestrator/`hermes` subprocess
via `pgrep -f`. No `bots/` references.
**Evidence:** `bash -n run.sh` clean; all subcommands exercised.

### Deliverable 5 — Real E2E test (US-008)
`tests/e2e/{e2e_dryrun.sh,verify_dashboard.sh,e2e_live.sh}` written;
`e2e_live.sh` is gated behind `--i-understand-this-is-live` and was not run.
A real dryrun against `firebase-chat-exp` **completed all 12 stages** with real
Hermes agent turns (`status: completed`, step 12). Assertions passed:
`messages.jsonl` non-empty (51 orchestrator narration lines), `pr_draft.json`
`url == DRYRUN://no-pr`, `queues/` contains exactly `openclaw/hermes-a/hermes-b`
(no `orchestrator/` phantom), `processing/` and `inbox/` both empty.

### Deliverable 6 — Dashboard real-time verification (US-008)
During the E2E run the dashboard API at `:7000` showed the `e2e-dryrun` session
and `current_stage` advancing live — 3 transitions captured (3→5→11→12) — and
after completion the dashboard derived `state: idle`, `current_stage: 12`,
`current_stage_id: pr_merged`.

---

## Mid-run fix (P1 correctness)

The first E2E run completed all 12 stages but the dashboard reported `running`
on the *finished* session. Root cause: `_agent_turn` sent `answer`/`blocker`
replies to the sender's inbox but never drained them, so `_build_status`'s
`any_running` check (inbox+processing depth > 0) stayed true forever.

Fix: added `_drain_inbox()`; `_agent_turn` now drains the reply after sending
it. The reply has already served its purpose — `send()` appended it to
`messages.jsonl` for the dashboard chat view — so the leftover inbox file was an
unwanted side effect. This honors plan **P1** (the dashboard derives state
correctly). Verified: the re-run's `inbox/` ended empty and the dashboard
derived `idle`. Covered by 2 new tests (`test_drain_inbox_clears_replies`,
`test_full_run_leaves_all_inboxes_drained`).

---

## Plan deviation (P5 — reconcile to verified reality)

`core/config.py` sets `MAX_MODEL_LEN = 32768`, not the plan's `65536`. The live
vLLM on `:8003` reports `max_model_len: 32768`; the `.env`'s `MAX_MODEL_LEN=65536`
belongs to the *other* vLLM (`:8000`, Qwen3-Coder-Next) and is irrelevant here.
This is a constant-value correction with **no behaviour change** — the
worst-case assembled prompt is ~14,500 chars (~4,000 tokens), and the real guard
is `PROMPT_HARD_CEILING = 50,000` chars. Setting the constant to the verified
value is exactly what plan principle **P5** mandates.

---

## Open-question resolutions

| ID | Resolution |
|----|------------|
| **O2** | `bots/` was referenced only in `run.sh` (rewritten) + plan docs → safely moved to `archive/bots/`. |
| **O3** | User decision — commit and push are two separate narration events (`_submit_pr` emits both). |
| **O4** | User decision — stages 3 & 4 run sequentially this iteration (`_analyze` runs Hermes-A then Hermes-B). |
| **O5** | User decision — `e2e_live.sh` is operator-gated; the automated run is dryrun only. |
| **O6** | `GITHUB_TOKEN` confirmed to carry `repo` + `workflow` scopes. |
| **O8** | Hermes profiles live at `~/.hermes/profiles/<name>/`; `SOUL.md` at `<profile>/SOUL.md`. |
| **O9** | Two-file reality documented: the dashboard reads `os.environ` (`DEVBOOTH_SESSIONS_ROOT`, default `/dev-booth/sessions`); the orchestrator loads `/dev-booth/config/.env` (`DEV_BOOTH_PATH=/dev-booth/sessions`). Both resolve to `/dev-booth/sessions`. |

`.env` was reconciled per the plan's KEY DISPOSITION MATRIX — stale Discord /
Notion / `VLLM_BASE_URL` / `AGENT_MODEL` keys removed; `GITHUB_*`, `DEV_BOOTH_PATH`,
GPU keys retained. (`config/.env` is gitignored, so the reconcile is on-disk
only.)

---

## Known residual (documented, accepted — plan PM-1)

During the E2E run the dashboard briefly showed `current_stage: 11` while the
orchestrator's `status.json` was at step 5–6 — an agent's `answer` body happened
to contain a stage-11 keyword, and `detect_stage` is highest-stage-wins inside
the 60s window. This is the exact PM-1 residual the plan documents as accepted:
the orchestrator's authoritative `status.json` and the time-bound narration
heartbeat converge the dashboard correctly (final: `12`/`pr_merged`). The
cross-seam test guarantees the *orchestrator's own* narration never leaks; agent
free-text is outside that guarantee by design.

---

## Files

**Created:** `core/__init__.py`, `core/config.py`, `core/preflight.py`,
`core/logger.py`, `core/orchestrator.py` (rewrite), `core/souls/{openclaw,hermes-a,hermes-b}.SOUL.md`,
`tests/` (conftest + 11 test files + `tests/e2e/` 3 scripts),
`dashboard/backend/tests/{test_stage_narration_crossseam,test_dashboard_sees_session,test_log_is_canonical}.py`,
3 Hermes profiles under `~/.hermes/profiles/`.
**Rewritten:** `run.sh`.
**Deleted:** `core/agent.py`, `core/llm.py`, `core/notion_logger.py`, old `core/orchestrator.py`.
**Archived:** `bots/` → `archive/bots/`.
**Reconciled (on-disk, gitignored):** `/dev-booth/config/.env`.
**Untouched:** the entire `dashboard/` runtime (only 3 test files added).
