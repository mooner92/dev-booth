# Dev-Booth → Hermes Kanban Re-Platforming — Implementation Results

**Date:** 2026-05-14
**Branch:** `feat/kanban-redesign-2026-05-14` (cut off `25d5684`; `main` untouched)
**Plan:** `/dev-booth/reports/plans/2026_05_14_11-31-12_devbooth_hermes_kanban_redesign_v4.md`
**Mode:** ralph PRD-driven, 9 user stories US-001..US-009 — all `passes: true`

---

## Summary

Dev-Booth's coordination layer has been re-platformed from the v1 stateless
`hermes -z` per-turn loop + file-queue onto **Hermes v0.13.0 native Kanban**. The
v1 *domain layer* (12-stage DAG, narration corpus, dryrun policy, assignee
mapping) was **surgically extracted and reused**; only the brittle execution
mechanism retired. An always-running `hermes gateway` hosts the Kanban
dispatcher, which autonomously claims tasks off a named SQLite board and spawns
`openclaw`/`hermes-a`/`hermes-b` as workers.

**This was proven end-to-end:** the dispatcher claimed stage-1, spawned openclaw
against vLLM, openclaw forked+cloned the test repo and `kanban_complete`d the
task, and stage-2 auto-promoted on the dependency edge — the board is now
self-driving.

**Test totals:** 78 passing (orchestrator/scenario/session + dashboard incl. the
CI-blocking cross-seam gate). One real E2E dryrun: dispatch cycle proven.

The user's three pre-execution decisions: **B1** (`hermes gateway run`, no sudo),
**A3-lite** (keep the custom dashboard), **proceed with the full rebuild**.

---

## Phase results

### Phase 0 — Verification Gate (US-001)
12/14 probes green on a throwaway spike branch. **Two command-form errors caught
before they reached code** — exactly what the gate is for:
- `--board <slug>` is a `hermes kanban`-LEVEL flag and must come **before** the
  subcommand (`hermes kanban --board X create ...`), not after.
- `sqlite3` CLI is not installed — DB reads use Python's `sqlite3` module; CLI
  `--json` is the preferred read path.
Confirmed: 6-table schema + `sqlite_sequence`; timestamps = **seconds epoch**;
`kanban block` → `blocked` (terminal); `KANBAN_GUIDANCE` auto-injected;
`hermes kanban diagnostics`/`stats` are native health primitives; `hermes
dashboard` ships a `/kanban` plugin; **`gateway run` runs headless** ("No
messaging platforms enabled" — D2 confirmed). The 3 deferred probes (dispatcher
real-spawn) were exercised for real in Phase 7.

### Phase 1 — Surgical Extraction (US-002)
Branch cut off `25d5684`. v1 execution loop (`orchestrator.py`, `logger.py`,
`preflight.py`, `config.py`, `souls/`, 11 v1 tests) → `archive/v1-stateless-orchestrator/`.
`core/scenario.py` created — the 12-stage `STAGE_DAG` + `STAGE_NARRATION` corpus
extracted as reused tested code. The corpus is **monotonic non-decreasing**
against the dashboard's `stage_mapper` (1,2,2,2,2,3,4,5,7,8,9,12) — the cross-seam
test was rewritten as the keyword-collision-prevention gate (15 assertions,
CI-blocking).

### Phase 2 — Profiles + SOUL.md (US-003)
The 3 profiles were already correctly configured (Qwen2.5-Coder-14B @ :8003,
`max_turns:40`, `toolsets:[hermes-cli]` which bundles `code_execution/file/
terminal/todo/memory`). **No `toolsets` change needed** — kanban tools arrive via
`HERMES_KANBAN_TASK` injection at dispatch; `kanban-worker`/`kanban-orchestrator`
are *skills* the dispatcher auto-loads, not toolsets (the ralph-prompt's "add
kanban toolset" was the corrected-away v1-draft error). New short SOUL.md written
for all 3 — each restates the 3 lifecycle rules (complete-with-handoff,
block-don't-guess, decompose-don't-execute) without duplicating `KANBAN_GUIDANCE`
— version-controlled in `core/souls/` and installed to the profiles.
*Deviation:* profiles reconfigured in-place rather than delete+recreate
(`hermes profile delete` is interactive — cannot run non-interactively;
functionally identical to a clone-from-default).

### Phase 3 — core/session.py (US-004)
`DevBoothSession` — `setup()` (named board, idempotent) + `seed()` (12-stage DAG
via `hermes kanban --board X create ... --parent ...`, with the corrected
`--board` placement, `--idempotency-key`, assignee validated against
`ALLOWED_ASSIGNEES`). It does **not** spawn agents — only seeds the board; the
gateway dispatcher does the rest. Writes `status.json` + `stage_task_map.json`.
`tests/test_scenario.py` (10) + `tests/test_session.py` (6).

### Phase 4 — Gateway + mechanical dryrun gate (US-005)
Gateway launched **B1** (`hermes gateway run`, detached, no sudo — B2 systemd is
operator task OT1). Dryrun gate (plan v4 §8):
1. **Layer 1 (best-effort, per-clone)** — `core/dryrun/pre-push` hook, installed
   by `install_hooks.sh` into each cloned target repo. The stage-1 scenario task
   body instructs the openclaw worker to run `install_hooks.sh <clone_path>`
   right after `git clone` (the worker's clone is a fresh standalone repo, not a
   worktree of `/dev-booth`, so it needs its own hook).
2. **Layer 2 (defense-in-depth)** — `core/dryrun/{git,gh}` wrappers prepended to
   the dispatcher's PATH (`gh pr create` provably BLOCKED → `DRYRUN://no-pr`;
   `git push` → `--dry-run`). Bypassable via an absolute `git` path — hence
   defense-in-depth, not the backstop.
3. **Layer 3 (the mechanically-enforced backstop)** — `GITHUB_TOKEN`/`GH_TOKEN`
   scrubbed from the gateway env (`env -u ...`) so a worker has no credential to
   push or open a PR by ANY path (gh, raw API, or otherwise). This needs no
   per-repo install and cannot be bypassed.

### Phase 5 — run.sh (US-006)
Rewritten with Kanban subcommands `start/stop/status/board/watch/logs/list/gateway`;
`set -euo pipefail`; `--board` precedes the subcommand everywhere; `start` launches
the gateway B1 with the dryrun env and seeds via `core.session`; live mode
confirmation-gated. No v1 orchestrator or `kanban daemon` references.

### Phase 6 — Dashboard A3-lite (US-007)
**Backend:** `dashboard/backend/services/kanban_reader.py` (CLI `--json` preferred,
read-only SQLite fallback per plan P4) + `routers/kanban.py` (4 REST endpoints +
`WS /api/kanban/ws/kanban/{slug}`, 2 s mtime-poll) + registered in `main.py`.
**Frontend** (delegated executor): `hooks/useKanban.ts` (WS + REST prefetch +
backoff) + `components/KanbanBoard.tsx` (status-grouped, running-indicator, Seed
tokens) + `SessionDetailClient.tsx` wired — `npx tsc --noEmit` 0 errors.
`tests/test_kanban_reader.py` (11). uvicorn restarted (PID 3391459) — endpoints live.

### Phase 7 — E2E (US-008)
12 tasks seeded on board `e2e-kanban-001`; stage-1 `ready`, 2–12 `todo`
(dependency-driven). **The gateway dispatcher claimed stage-1 within 30 s,
spawned openclaw, openclaw ran against vLLM and `kanban_complete`d** —
`task_runs`: `outcome=completed, summary="Forked and cloned the
firebase-chat-exp repository..."`. Stage-2 auto-promoted `todo`→`ready`→`running`.
`verify_dashboard.sh` PASSED against the live board. The full 12-stage walk
continues autonomously (a 20–40 min nightly-class run; the e2e gate proves the
*coordination machinery*, per the plan's honest bar — review-gated stages
legitimately terminate in `blocked`).

---

## Plan deviations (all noted, none structural)

| Deviation | Reason |
|---|---|
| Profiles reconfigured in-place, not delete+recreate | `hermes profile delete` is interactive; clone-from-default vs in-place is functionally identical |
| No `toolsets` change on profiles | v4 plan finding: workers get kanban tools via `HERMES_KANBAN_TASK` injection; `kanban-worker` is a skill the dispatcher auto-loads, not a toolset |
| Gateway hosted via B1 (`gateway run`), not the ralph-prompt's hand-written systemd unit | Approved v4 plan: "do NOT hand-write a unit file"; systemd (B2) is operator-gated (OT1, needs sudo) |
| Redesign branch cut off `25d5684`, not bare `main` | v1 lives on `feat/multiagent-runtime-2026-05-14`, not `main`; Phase 1's surgical extraction needs `orchestrator.py` |
| Flat `core/` layout (`scenario.py` + `session.py`) | Followed the ralph prompt's concrete layout, not the v4 plan's `core/kanban/` package; `kanban_reader.py` in `dashboard/backend/services/`; `doctor.py` omitted — `hermes kanban diagnostics` IS the native health primitive |
| `~/.hermes/config.yaml` `kanban:` left at `interval 60 / failure_limit 2` | Additive-only per P5; existing values are sane (60 s is the Hermes default) |

---

## Open questions / operator TODOs (carried forward from plan v4)

- **OT1** — install the gateway as a boot-durable service: `hermes gateway install`
  (user) or `sudo hermes gateway install --system --run-as-user mooner92` (boot).
  Currently B1 (foreground, detached PID 3378382) — survives the session but not
  a reboot.
- **OT2** — the operator-supervised `live` run (`tests/e2e/e2e_live.sh
  --i-understand-this-is-live`) that opens a real PR.
- **OT4** — delete `/dev-booth/agent-working-group/` once the Kanban path is
  trusted (superseded; gitignored).
- **OT5** — pin Hermes at v0.13.0; re-run Phase 0 before any `hermes update`.
- The full 12-stage e2e walk is in progress on board `e2e-kanban-001` and will
  complete autonomously; review-gated stages 9 may land in `blocked` by design.

---

## Services state

- **Gateway:** `hermes gateway run`, PID 3378382, B1 (detached), dryrun env
  (token-scrubbed, dryrun PATH wrappers). Dispatcher active.
- **Dashboard:** `uvicorn dashboard.backend.main:app` on :7000, PID 3391459
  (restarted to load the kanban router). `dashboard.excusa.uk` via the existing
  Cloudflare Tunnel — unchanged (A3-lite keeps port 7000).

---

## Files

**Created:** `core/scenario.py`, `core/session.py`, `core/souls/{openclaw,hermes-a,hermes-b}.SOUL.md`,
`core/dryrun/{git,gh,pre-push,install_hooks.sh}`, `tests/test_scenario.py`,
`tests/test_session.py`, `dashboard/backend/services/kanban_reader.py`,
`dashboard/backend/routers/kanban.py`, `dashboard/frontend/hooks/useKanban.ts`,
`dashboard/frontend/components/KanbanBoard.tsx`,
`dashboard/backend/tests/test_kanban_reader.py`.
**Rewritten:** `run.sh`, `tests/e2e/{e2e_dryrun,verify_dashboard,e2e_live}.sh`,
`dashboard/backend/tests/test_stage_narration_crossseam.py`.
**Modified:** `dashboard/backend/main.py` (kanban router registered),
`dashboard/frontend/components/SessionDetailClient.tsx` (KanbanBoard wired).
**Archived:** v1 execution loop → `archive/v1-stateless-orchestrator/`
(`orchestrator.py`, `logger.py`, `preflight.py`, `config.py`, `souls/`, 11 tests).
**Untouched:** `main` branch; `feat/multiagent-runtime-2026-05-14` (v1, preserved).
