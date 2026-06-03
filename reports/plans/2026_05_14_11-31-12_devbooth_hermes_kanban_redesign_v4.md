# Dev-Booth → Hermes-Kanban Re-Platforming Plan — v4 (FINAL)

**Status:** PENDING APPROVAL
**Target Hermes version:** v0.13.0 (pinned)
**Date:** 2026-05-14
**Mode:** ralplan consensus, deliberate. Converged at iteration 3.
**Consensus:** Architect → SOUND (ready to finalize). Critic → APPROVE. (Final N-1/N-2 wording patch folded in below.)

This plan re-platforms Dev-Booth's coordination layer onto Hermes Kanban. It is the executor-facing artifact. Every reviewer finding across 3 iterations — v1-draft's ~15 factual errors, v2's Architect 7 + Critic 12, v3's Architect 5 + Critic 4, v4's N-1/N-2 — is resolved; the resolution record is §12.

---

## 1. Context

Dev-Booth today runs a hand-rolled **v1 coordination layer**: a stateless `hermes -z` per-turn execution loop, a file-queue (`messages.jsonl`) mediated by `MessageQueue`, plus hand-rolled strand recovery and reply draining. This v1 stack hand-rolls claiming, retry, handoff, blocking, and dispatch — exactly the concerns Hermes Kanban provides natively in v0.13.0, and exactly the brittle part of the current system.

v1 works and is tested (shipped at commit `25d5684` on `main`). Its **domain layer** is valuable and carries forward unchanged: the 12-stage DAG, the `STAGE_NARRATION` canonical corpus, the cross-seam narration gate (CI-blocking 12/12 test), the dryrun config, and the assignee mapping. The concrete pain is narrow and located entirely in the execution/coordination mechanism.

This plan **re-platforms the coordination EXECUTION layer onto Hermes Kanban while keeping the domain layer.** It is a targeted re-platforming of the coordination mechanism, **NOT a from-scratch rebuild.**

**Scope honesty:** This plan re-platforms coordination/execution onto Kanban — claiming, retry, handoff, blocking, and dispatch all genuinely come from Hermes now. **Autonomous decomposition (openclaw fanning out child tasks via `kanban_create`) is integration-tested but deliberately OFF the critical path.** The e2e / Milestone-A scenario DAG is **statically pre-decomposed** — stages 6 & 8 children are authored in `scenario.py`. The "Kanban redesign" framing does not hide that the e2e is still a static DAG seeded into a Kanban queue; autonomous decomposition is validated only by `test_decomposition.py` and is not the headline deliverable.

---

## 2. RALPLAN-DR Summary

### Principles
- **P1 — Use Hermes primitives, don't reimplement.** Acknowledged boundaries: `core/kanban/board.py` and `core/kanban/doctor.py` are labeled P1 tension points, each carrying a one-line "P1 tension: justified because…". Both shrink to thin wrappers if Phase 0.12 finds native primitives. `doctor.py` is pre-scoped as a thin wrapper over `hermes kanban diag`/`stats` (both verified to exist).
- **P2 — Empirical verification before irreversible action.** Phase 0 is a standalone evidence spike on a throwaway branch against a sandbox `HOME=` copy.
- **P3 — Reuse Dev-Booth investment.** Surgical extraction of the DAG / `STAGE_NARRATION` corpus / narration gate / dryrun config / assignee mapping from `orchestrator.py`; reuse survives-unchanged tests.
- **P4 — No silent coupling to Hermes internals.** `SOUL.md` restates the 3 lifecycle-critical rules rather than relying purely on `KANBAN_GUIDANCE` auto-injection; raw-SQL reads resolved by Phase 0.12b — CLI `--json` is the default sanctioned read contract, direct SQLite is the documented fallback only. The dryrun gate is mechanical (token-scrub + git hook), not model-trust.
- **P5 — Reversibility.** v1 stays live on `main` throughout; Phase 0 runs on a throwaway spike branch; `config.py` is additive-only through Phase 6; the dashboard swap lives on its own branch merged post-e2e-gate.

### Decision Drivers
- **D1 — No sudo by default / operator-gated.** Anything requiring system-level install is operator-gated and deferred to Milestone C.
- **D2 — RESOLVED.** Gateway runs headless (verified against source: `gateway/run.py:3636` "Gateway will continue running for cron job execution" with no messaging platforms; the dispatcher is a standalone asyncio task gated only on `dispatch_in_gateway` config, not on platform presence).
- **D3 — Dashboard sunk cost vs duplication.** The public `dashboard.excusa.uk` surface may itself be a v1 artifact (open question for the requester — `OQ-DASH`; gates Milestone B scope).

### Decisions
- **Decision A (dashboard): A3-lite chosen** — a thin read-only `kanban_reader.py` (CLI `--json` preferred, direct SQLite fallback) + minimal frontend re-skin + re-derive only the needs-rewrite-bucket tests. **Collapses to A1** (point the Cloudflare Tunnel at `hermes dashboard` on `:9119`, backend rewrite vanishes) if the requester declares `dashboard.excusa.uk` a non-requirement.
- **Decision B (gateway hosting): B1-dev / B2-prod.** B1 = `hermes gateway run` foreground (dev iteration). B2 = `hermes gateway install` (operator-gated for `--system --run-as-user`, durable hosting). **B3 = `hermes kanban daemon` standalone — DEMOTED to deprecated-emergency-only** (works in v0.13.0 but the unit header says DEPRECATED and `daemon` is hidden from `--help`, "for one more release cycle").

### Mode
**DELIBERATE** — high-risk re-platforming of a live coordination system; includes a Phase 0 verification gate, a 5-scenario pre-mortem, and an expanded test plan (unit / integration / e2e / observability).

---

## 3. Milestones

- **Milestone A = Phases 0–4 + 6.** Kanban coordination working; e2e dryrun green against the qualified per-task-type terminal-state map (§9). Independently shippable — **this is THE deliverable.**
- **Milestone B = Phase 5.** Dashboard. Gated on the requester answering whether `dashboard.excusa.uk` is a product requirement (`OQ-DASH`); collapses to A1 if not.
- **Milestone C = Phase 7.** Operator hardening + destructive cleanup.

---

## 4. Phase 0 — Verification Gate

Runs on a throwaway spike branch `spike/kanban-recon-2026-05-14`. **All probes run against a sandbox `HOME=` copy** so no irreversible action touches the operator's real `~/.hermes`. Phase 0 is a GATE — Phases 1–7 are conditional on its evidence.

- **0.0** vLLM `:8003` reachable + serving Qwen2.5-Coder-14B (precondition; **hard-fail the gate if unreachable**).
- **0.1** `hermes kanban init` + `hermes kanban boards create dev-booth`; confirm DB at `~/.hermes/kanban/boards/dev-booth/kanban.db` + `workspaces/` + `logs/` siblings.
- **0.2** probe task `--assignee openclaw --workspace worktree`; confirm task row + `workspace_kind` / `workspace_path` columns.
- **0.3** `hermes gateway run` foreground with NO messaging platforms; confirm headless ("continue running for cron job execution") — expected pass (D2 resolved).
- **0.4** confirm the dispatcher asyncio task starts under `dispatch_in_gateway:true` with no platform present + picks up a queued `dev-booth`-board task.
- **0.5** confirm a dispatcher-spawned worker GETS `kanban_create` + `kanban_link` and does NOT get `kanban_list` / `kanban_unblock`.
- **0.6** confirm the dispatcher appends `--skills kanban-worker` + injects `HERMES_KANBAN_TASK` / `DB` / `BOARD` / `WORKSPACES_ROOT` / `WORKSPACE` (+ `HERMES_TENANT`).
- **0.7** confirm unknown-assignee → silent no-spawn (`skipped_nonspawnable` bucket). *(Owner of Pre-Mortem P2 mitigation.)*
- **0.8** runtime dump of a `task_runs` / `tasks` timestamp to settle seconds-vs-milliseconds epoch unit (R10).
- **0.9** confirm `kanban_block(reason="review-required: ...")` terminates a task in `blocked` (not `done`) — **the e2e design (§9) depends on this.**
- **0.10** dump a real dispatcher-spawned worker's assembled system prompt; assert `KANBAN_GUIDANCE` (Lifecycle 1-6 + "Orchestrator mode" + "Do NOT" sections) is present (baseline for the Phase 3 `SOUL.md` acceptance check).
- **0.11** confirm `hermes dashboard` serves `plugins/kanban/dashboard/` on `:9119` (informs A3-lite vs A1 collapse).
- **0.12** full `hermes --help` + `hermes kanban --help` verb dump. Record:
  - **(a)** native board health/status/doctor primitive — **expected YES** (`hermes kanban diag` / `stats` exist; `doctor.py` is pre-scoped as a thin wrapper over them).
  - **(b)** is the SQLite schema a documented public read contract, or is CLI `--json` the only sanctioned read path? — **default assumption: CLI `--json` is the sanctioned contract; direct SQLite is the documented fallback only if `--json` proves insufficient.** Branches `board.py` / `kanban_reader.py` design.
- **0.13** probe the dryrun-gate mechanism:
  1. confirm a worker-created `worktree` workspace inherits `$GIT_COMMON_DIR/hooks` from the seed/clone repo's `.git/hooks` (so a `pre-push` hook installed once in the shared repo applies to all worker worktrees) — verify via `git rev-parse --git-common-dir` from inside a worker-created worktree resolving to the shared repo, with the hook present + executable;
  2. confirm that when the gateway is launched via Dev-Booth's launch script (which prepends a wrapper dir to PATH), a dispatcher-spawned worker's inherited `PATH` contains that wrapper dir — verify by dumping the worker's `PATH` env var;
  3. confirm that under `DEV_BOOTH_DRYRUN`, a dispatcher-spawned worker's env does NOT contain `GITHUB_TOKEN` / `GH_TOKEN` (the token-scrub leg of the gate — §8 N-2).

**Phase 0 acceptance:** all of 0.0–0.13 recorded with evidence on the spike branch; OQ1–5 answered; if 0.3 / 0.4 unexpectedly fail, reconsider B3; otherwise discard the spike branch and cut `feat/kanban-redesign-2026-05-14` off `main`.

---

## 5. Phase 1 — Branch + Surgical Extraction

Cut `feat/kanban-redesign-2026-05-14` off `main`. `git mv` the v1 execution-loop files (`hermes -z` per-turn loop, `MessageQueue` mediation, strand recovery, reply draining) → `archive/v1-stateless-orchestrator/`.

**Surgically extract** the domain layer from `orchestrator.py` → `core/kanban/seed.py`: the 12-stage DAG, the `STAGE_NARRATION` canonical corpus, the cross-seam narration gate / CI-blocking 12/12 test, the dryrun config, the assignee mapping — all as REUSED tested code.

Scaffold `core/kanban/`: `seed.py`, `scenario.py`, `board.py`, `kanban_reader.py`, `doctor.py`.

During Phase 1 inspection, confirm exact per-file test counts for the §9 dashboard-test classification table.

**Acceptance:** the extracted narration gate test runs green against `seed.py`.

---

## 6. Phase 2 — Board + Profiles + Hosting

Create the real named `dev-booth` board on the operator's `~/.hermes`. Build `core/kanban/board.py` access helpers shaped per Phase 0.12b (CLI `--json` default; **P1 tension labeled + justified**: "P1 tension: justified because Dev-Booth needs a typed access seam over the CLI `--json` contract; shrinks to a thin wrapper, never reimplements board state"). Confirm / adjust the 3 profiles (`openclaw` / `hermes-a` / `hermes-b`). Decision B — B1 (`hermes gateway run`) for dev, B2 documented for prod. `seed.py` idempotency-key scheme = `devbooth-<board>-<stage-id>`.

**Acceptance:** `dev-booth` board exists; a manually seeded probe task dispatches and a worker spawns against it.

---

## 7. Phase 3 — SOUL.md Rewrite (short)

Rewrite `SOUL.md` short and **explicitly restate the 3 lifecycle-critical rules** rather than relying purely on `KANBAN_GUIDANCE` auto-injection (closes the P4 invisible-coupling concern). Do NOT duplicate the full `KANBAN_GUIDANCE` text.

1. **Complete-with-handoff** — finish via `kanban_complete --result/--summary/--metadata`.
2. **Block-don't-guess-when-review-needed** — for code changes needing review, `kanban_comment` the metadata then `kanban_block(reason="review-required: ...")`; do NOT `kanban_complete`.
3. **Decompose-don't-execute** — in orchestrator mode, fan out child tasks; don't execute the work yourself.

**Acceptance:** dump a real worker's assembled system prompt; assert the lifecycle section is present.

---

## 8. Phase 4 — Scenario Seeding + Mechanical Dryrun Gate

`core/kanban/scenario.py` seeds the DAG via `hermes kanban create --board dev-booth ... --parent ... --assignee ...`.

**Static pre-decomposition** — stages 6 & 8 children are authored, seeded, and counted in `scenario.py` as part of a known `(12+N)`-task DAG (state the real N once fixed). Autonomous runtime `kanban_create` becomes integration-test-only (`test_decomposition.py`) and is **EXPLICITLY EXCLUDED from the e2e path.**

### Mechanical dryrun gate — three layers, clearly ranked

The dryrun guarantee is **mechanical, not model-trust.** Three layers:

1. **PRIMARY — `pre-push` hook in the shared seed/clone repo's `.git/hooks`.** This is the true backstop: it fires on **every** `git push` regardless of how `git` is invoked (bare command, absolute path, Python `subprocess` with a custom PATH, `GitPython`/`pygit2` — all still shell out to `git` for the network op and hit the hook). A `worktree` workspace is created by the worker skill itself mid-run (`git worktree add`), so Dev-Booth cannot pre-install a hook into the worktree directory — but git worktrees share the parent repo's hooks via `$GIT_COMMON_DIR/hooks`, so a hook installed **once** into the shared repo is inherited by every worker-created worktree (verified in Phase 0.13).
2. **DEFENSE-IN-DEPTH + the only gate for `gh` — `git`/`gh` wrapper dir prepended to the DISPATCHER's PATH.** Dev-Booth's launch script exports `PATH=<wrapper-dir>:$PATH` before launching `hermes gateway run`. Workers are spawned with `env = dict(os.environ)` (`kanban_db.py:3932`) — they inherit the dispatcher's PATH verbatim (there is no per-workspace PATH entry; the dispatcher's env is the only lever). The wrapper intercepts PATH-resolved `git push` (redundant with layer 1) and PATH-resolved `gh pr create` / `gh pr` (the spam-PR half of R3).
3. **CLOSES THE `gh`/DIRECT-API BYPASS — scrub `GITHUB_TOKEN` / `GH_TOKEN` from the worker env under `DEV_BOOTH_DRYRUN`.** The `pre-push` hook does not catch `gh pr create` (`gh` talks to the GitHub API over HTTPS, no `git push`), and a worker with the `code_execution` tool could call the GitHub API directly via Python `requests` with the token in its inherited env — bypassing both layers above. The mechanically-complete fix: under `DEV_BOOTH_DRYRUN`, Dev-Booth's launch script does NOT export `GITHUB_TOKEN` / `GH_TOKEN` into the dispatcher's env, so dispatcher-spawned workers (inheriting `env = dict(os.environ)`) have no credential to push or open a PR by **any** path — `gh`, raw API, or otherwise. This is the dispatcher-env lever the plan already controls; it makes the P3 "mechanical not model-trust" claim actually true and strengthens P4. Workers needing read-only GitHub API access in dryrun would require a separately-provisioned scoped read-only token (out of scope; an operator decision if ever needed).

`seed.py --reset` board lifecycle teardown (archive or `boards rm` + recreate `dev-booth`).

`core/config.py` changes are **ADDITIVE-ONLY through Phase 6** (add `DEV_BOOTH_DRYRUN` default-true + new Kanban keys; **no destructive AWG-ref removal until Phase 7**) AND an archived copy goes to `archive/v1-stateless-orchestrator/config.py`.

**Acceptance:** seeding produces the exact known `(12+N)` task count; `--reset` returns the board to empty; the `pre-push` hook provably blocks a `git push` from inside a worker-created worktree; under `DEV_BOOTH_DRYRUN` the worker env provably lacks `GITHUB_TOKEN`/`GH_TOKEN`.

---

## 9. Phase 5 — Dashboard (Milestone B, conditional)

On its own branch, merged post-e2e-gate. **A3-lite** — `core/kanban/kanban_reader.py` thin READ-ONLY layer (CLI `--json` default; P1 tension labeled + justified); minimal frontend re-skin; re-derive ONLY the needs-rewrite-bucket tests from the §10 table. Collapses to **A1** if `dashboard.excusa.uk` is declared a non-requirement (`OQ-DASH`).

---

## 10. Phase 6 — Test Plan (Milestone A completion)

### `tests/` (62 functions) — per-file classification

| File | Functions | Bucket |
|---|---|---|
| `test_orchestrator_*` | 16 | obsolete |
| `test_strand_recovery` | 3 | obsolete |
| `test_queue_roundtrip` | 4 | obsolete |
| `test_idempotency` | 5 | obsolete |
| `test_no_orchestrator_queue` | 2 | obsolete |
| `test_logger` | 8 | obsolete |
| `test_task_parser` | 6 | needs-rewrite — re-derive against `seed.py` DAG |
| `test_preflight` | 9 | needs-rewrite — re-derive against `doctor.py` |
| `test_config` | 9 | survives-unchanged — `config.py` kept additive-only |

**Totals:** obsolete 38, needs-rewrite 15, survives-unchanged 9 = **62**.

### `dashboard/backend/tests/` (47 functions) — per-file classification

**Bucket definitions:** *obsolete* = tests of `messages.jsonl`/file-queue readers (the v1 data layer is gone); *survives-unchanged* = generic log/path/session infra not coupled to the v1 data layer; *needs-rewrite* = data-layer-coupled tests assuming v1's queue/orchestrator data shape — re-derived against `kanban_reader.py` in Phase 5.

| File | Bucket | Rationale |
|---|---|---|
| `test_awg_inspector` | obsolete | AWG file-queue reader is gone |
| `test_log_parser` | obsolete | v1 `messages.jsonl` tail is gone |
| `test_log_tailer` | obsolete | v1 `messages.jsonl` tail is gone |
| `test_path_guard` | survives-unchanged | generic path safety, not coupled to the v1 data layer |
| `test_session_layout` | needs-rewrite | session model changes from filesystem-sessions to Kanban boards |
| `test_session_registry` | needs-rewrite | session model changes from filesystem-sessions to Kanban boards |
| `test_stage_mapper` | needs-rewrite | stage mapping moves to the Kanban scenario / terminal-state model |
| router tests | needs-rewrite | endpoints now serve `kanban_reader.py` data |
| ws tests | needs-rewrite | endpoints now serve `kanban_reader.py` data |

The executor confirms exact per-file counts during Phase 1 inspection; the table sums to **47**. Only the **needs-rewrite** bucket is re-derived, and only in Phase 5.

### Unit
- `seed.py` DAG integrity + the reused narration gate (CI-blocking 12/12).
- `scenario.py` static decomposition well-formed (stage 6/8 children have acceptance criteria, correct assignee, correct `--parent` link, non-empty summary).
- `doctor.py` / `board.py` helpers.
- `kanban_reader.py` read helpers (if Milestone B retained).

### Integration
- `test_decomposition.py` — autonomous runtime `kanban_create` fan-out tested IN ISOLATION; **explicitly excluded from the e2e path.**
- dispatcher pickup of a seeded `dev-booth` task + worker spawn with correct env injection.
- `seed.py --reset` round-trip.
- `test_unknown_assignee.py` — codifies Pre-Mortem P2.
- the mechanical dryrun gate provably blocks a real `git push` (via the `pre-push` hook) under `DEV_BOOTH_DRYRUN`, and the worker env provably lacks the GitHub token under dryrun.

### E2E
`test_full_scenario_dryrun.py` — seed the known `(12+N)`-task DAG on `dev-booth`, run the gateway dispatcher under `DEV_BOOTH_DRYRUN`.

**Asserts a per-task-type terminal-state map:** non-review stages → `done`; code-review / PR review-gated stages → `blocked` (the DESIGNED handoff per `KANBAN_GUIDANCE`, **NOT a failure**). **e2e success = "every task reached its EXPECTED terminal state"** — NOT "every task → `done`".

**Why `blocked` is terminal here (verified against Hermes v0.13.0 source):** `complete_task` (`kanban_db.py:2361`) only transitions `running|ready → done` — it REJECTS `blocked`. `recompute_ready` (`kanban_db.py:1829`) only promotes `todo → ready` — it never re-readies a `blocked` task; `kanban_link` dependency resolution does NOT rescue a blocked task. The ONLY `blocked → ready` transition is `unblock_task` (`kanban_db.py:2639`), exposed via (a) the `kanban_unblock` tool — **double-gated against dispatcher-spawned workers**; (b) the `hermes kanban unblock` CLI — works only for a process with a real shell + `hermes` on PATH and NO `HERMES_KANBAN_TASK`. Therefore a dispatcher-spawned reviewer worker CANNOT drive blocked tasks to `done`; the v3 "seed a reviewer task" mechanism is impossible and is **deleted entirely.**

**OPTIONAL full-loop variant:** the test harness ITSELF — running as the test driver, NOT as a dispatched worker, with NO `HERMES_KANBAN_TASK` in its env — shells `hermes kanban unblock <id>` to drive review tasks past `blocked`, OR runs an orchestrator-profile agent with the `kanban` toolset. The `done`-transition full loop is covered ONLY by this optional operator-run variant.

Each run begins with `seed.py --reset`. **This is a 20–40 min nightly-class test** (60s dispatch tick × 12+ sequential stages × model inference), **NOT a fast CI gate** — the fast CI gate is the unit + integration tier.

**R7 max_turns audit criterion:** "no worker task hit `gave_up` / max_turns truncation in the e2e dryrun; if any did, bump that profile's `max_turns` above 40 and re-run."

### Observability
- `task_events` / `task_runs` handoff inspection (handoff lands on `task_runs.summary` / `metadata`).
- **Stuck-task detector** and **runtime board validator** are **CLI / library tools, NOT dashboard views** — so Milestone A is genuinely shippable without Phase 5. No observability piece is dashboard-only.
  - Stuck-task detector: flags a task in `ready` past a threshold with no `task_events` progress.
  - Runtime board validator: checks every task for required fields + valid `--parent` links + valid assignee (ties to Pre-Mortem P5).

### Phase 6 acceptance (Milestone A complete)
- unit + integration tiers green in CI;
- e2e dryrun green against the per-task-type terminal-state map (`blocked` is an expected terminal state, not a failure; "e2e green" does NOT silently imply every task reaches `done`);
- `--reset` repeatability confirmed;
- mechanical dryrun gate confirmed (all three layers);
- observability CLI tools functional.

---

## 11. Phase 7 — Operator Hardening + Destructive Cleanup (Milestone C, conditional)

Destructive cleanup is DEFERRED to here:
- remove AWG references from `core/config.py` (lines 35, 45);
- delete the `agent-working-group/` directory;
- B2 production hosting hardening (`hermes gateway install --system --run-as-user`, operator-gated, sudo);
- operator runbook (board teardown / reset, dispatcher restart, Hermes-version drift checks);
- address OT1–5.

---

## 12. Migration Table

| v1 artifact | Disposition |
|---|---|
| `orchestrator.py` | Surgical extraction — domain layer (DAG, `STAGE_NARRATION` corpus, narration gate, dryrun config, assignee mapping) → `core/kanban/seed.py` (REUSED); execution loop → `archive/v1-stateless-orchestrator/` |
| `preflight.py` | Replaced by `core/kanban/doctor.py` (thin wrapper over `hermes kanban diag`/`stats`); `test_preflight` (9) → needs-rewrite |
| `logger.py` (141 lines) | ARCHIVED definitive — it's the v1 direct-append writer; the dashboard backend does not import it (confirmed); `test_logger` (8) → obsolete |
| `souls/` | Archived as reference + rewritten short (Phase 3) |
| `core/config.py` (99 lines, 2 AWG refs at lines 35, 45) | Additive-only through Phase 6 + archived copy → `archive/v1-stateless-orchestrator/config.py`; destructive AWG-ref removal in Phase 7 |
| `tests/` (62) | Per the `tests/` classification table (§10) |
| `dashboard/backend/tests/` (47) | Per the dashboard classification table (§10) |
| `agent-working-group/` (gitignored) | Superseded by Kanban; deleted in Phase 7 |
| Branching | New branch `feat/kanban-redesign-2026-05-14` off `main`, preceded by throwaway `spike/kanban-recon-2026-05-14` for Phase 0 |

---

## 13. Pre-Mortem (5 scenarios)

- **P1 — Gateway is not actually headless.** Probability LOW (D2 RESOLVED, verified). Mitigation: Phase 0.3 / 0.4 empirical confirm + B3 deprecated-emergency path as fallback.
- **P2 — Unknown-profile task sits in `ready` forever.** Mitigation: seed-time assignee validation against the 3 known profiles. Concrete owners: Phase 0.7 probe confirms the silent-no-spawn behavior; `test_unknown_assignee.py` integration test codifies it; the stuck-task detector (Phase 6 observability CLI tool) flags it at runtime; seed-time assignee validation in `seed.py` rejects it before it ever queues.
- **P3 — Agents push bad commits / open spam PRs.** Mitigation: the three-layer mechanical dryrun gate (§8) — PRIMARY: shared-repo `pre-push` hook catches every `git push` regardless of invocation path; DEFENSE-IN-DEPTH + sole `gh` gate: `git`/`gh` wrapper on the dispatcher PATH; CLOSES THE BYPASS: `GITHUB_TOKEN`/`GH_TOKEN` scrubbed from the worker env under `DEV_BOOTH_DRYRUN` so no credential exists for `gh` or a raw-API push by any path. NOT model-trust. `DEV_BOOTH_DRYRUN` default-true.
- **P4 — Hermes update drift.** Mitigation: pin / record Hermes v0.13.0; Phase 7 drift-check; P1/P4 boundary acknowledgements keep coupling visible.
- **P5 — Autonomous decomposition produced a malformed board.** Mitigation: the static pre-decomposition shrinks the blast radius (autonomous `kanban_create` is integration-test-only, off the e2e path); a runtime board validator (CLI tool) checks every task; the stuck-task detector catches downstream stalls.

---

## 14. Risks (R1–R11)

| ID | Risk | Mitigation |
|---|---|---|
| R1 | Gateway not headless | LOW (D2 resolved); Phase 0.3/0.4 empirical confirm; B3 emergency path |
| R2 | Unknown-profile silent no-spawn | Seed-time validation + `test_unknown_assignee.py` + stuck-task detector |
| R3 | Bad push / spam PR | Three-layer mechanical gate (§8): shared-repo `pre-push` hook (primary), dispatcher-PATH `git`/`gh` wrapper (defense-in-depth + sole `gh` gate), `GITHUB_TOKEN`/`GH_TOKEN` scrubbed from worker env under dryrun (closes the `gh`/direct-API bypass); `DEV_BOOTH_DRYRUN` default-true |
| R4 | Hermes update drift | Pin v0.13.0 + Phase 7 drift-check + P1/P4 boundary acknowledgements |
| R5 | Dashboard rewrite breaks tunnel | A3-lite on its own branch post-e2e + A1 fallback |
| R6 | Git stages use scratch not worktree | `--workspace worktree` enforced in `seed.py` + Phase 0.2 verify |
| R7 | Worker `max_turns:40` too low | Measurable audit — no `gave_up`/truncation in e2e else bump + rerun |
| R8 | Dispatcher dies in foreground | B1 dev-only, B2 systemd for prod |
| R9 | `SOUL.md` duplicates `KANBAN_GUIDANCE` | Restate only the 3 lifecycle rules; do not duplicate the full guidance text |
| R10 | Timestamp seconds vs milliseconds | Phase 0.8 runtime dump |
| R11 | Static decomposition drifts from real scenario needs | Children version-controlled in `scenario.py`; `test_decomposition.py` keeps the autonomous path exercised. Detection trigger: `test_scenario.py` DAG-wellformedness check + integration-test dispatch coverage; drift surfaces as an unmatched-dependency or orphan-task failure |

---

## 15. ADR-001 — Re-platform the Coordination EXECUTION Layer onto Hermes Kanban, Keep the Domain Layer

**Decision.** Re-platform the coordination execution layer onto Hermes Kanban; keep the domain layer. A targeted re-platforming of the coordination mechanism, NOT a from-scratch rebuild.

**Drivers.** D1 (no sudo by default / operator-gated), D2 (gateway runs headless — RESOLVED, verified against source), D3 (dashboard sunk cost vs duplication).

**Alternatives considered.**
- *Keep v1 as-is.* v1 works and is tested; its domain logic (DAG, narration corpus, dryrun config, survives-classification tests) carries forward unchanged regardless of this decision. The concrete pain v1 causes today is narrow — its file-queue + stateless-`-z` execution loop hand-rolls claiming / retry / handoff, exactly what Hermes Kanban does natively and exactly the brittle part. The re-platforming targets that brittle seam and nothing else.
- *A1 dashboard fallback* (point the Cloudflare Tunnel at `hermes dashboard` :9119) — retained as the collapse target for Decision A if `dashboard.excusa.uk` is a non-requirement.
- *B3 standalone `hermes kanban daemon`* — demoted to deprecated-emergency-only (works in v0.13.0 but the unit header says DEPRECATED and `daemon` is hidden from `--help`).

**Why chosen.** The execution/coordination layer is the brittle, hand-rolled part; Hermes Kanban provides claiming, retry, handoff, blocking, and dispatch natively and is verified to run headless. Keeping the domain layer preserves the tested investment (P3) while removing the maintenance liability.

**Consequences.**
- Claiming, retry, handoff, blocking, and dispatch all genuinely come from Hermes now.
- **Autonomous decomposition (openclaw fanning out child tasks via `kanban_create`) is validated only by the `test_decomposition.py` integration test and is deliberately NOT on the e2e / Milestone-A critical path; the e2e DAG is statically pre-decomposed (stages 6 & 8 children authored in `scenario.py`).** This plan re-platforms coordination/execution onto Kanban — but autonomous decomposition is integration-tested and off the critical path, not the headline deliverable.
- e2e success is defined against a per-task-type terminal-state map, not "every task → `done`", because `blocked` is a designed terminal state for review-gated stages and is unreachable-to-`done` by any dispatcher-spawned worker.
- The dryrun guarantee is mechanical (shared-repo `pre-push` hook + dispatcher-PATH wrapper + token-scrub under dryrun), not model-trust — strengthening P4.
- `core/kanban/board.py` and `core/kanban/doctor.py` are acknowledged P1 tension points (thin wrappers over CLI `--json` and `hermes kanban diag`/`stats` respectively).
- New dependency on a long-lived gateway/dispatcher daemon; coupling to Hermes v0.13.0 specifics — managed via version pinning + the Phase 7 drift-check.

**Follow-ups.** `OQ-DASH` gates Milestone B scope; Phase 7 operator hardening + destructive cleanup; Hermes-version drift checks (P4 / R4).

---

## 16. Open Questions

- **OQ1–OQ5** — Phase-0-blocking; mostly expected-to-pass now that D2 is resolved. Answered as part of Phase 0 acceptance.
- **OQ6 — RESOLVED** → A3-lite (collapses to A1 if `dashboard.excusa.uk` is a non-requirement).
- **OQ7 — RESOLVED** → named `dev-booth` board (isolation of an autonomous-git-action system from the operator's shared `~/.hermes/kanban.db`).
- **OQ8 — RESOLVED** → new branch `feat/kanban-redesign-2026-05-14` off `main`; Phase 0 spike on its own throwaway `spike/kanban-recon-2026-05-14` branch first.
- **OQ-DASH (for the requester — NOT resolved):** Is the public `dashboard.excusa.uk` surface an actual product requirement, or a v1 artifact? — gates Milestone B's scope (A3-lite vs collapse to A1).
- **OT1–OT5** — operator tasks, addressed in Phase 7 (systemd install, the operator-supervised non-dryrun real-PR run, Cloudflare Tunnel reconfig if A1, `agent-working-group/` deletion, Hermes-version pin discipline).
- **B3-deprecation note** — `hermes kanban daemon` is DEPRECATED in v0.13.0 ("for one more release cycle"); track for drift.

---

## 17. Reviewer Findings — Resolution Record

**v1-draft (recon):** ~15 factual errors found against live Hermes v0.13.0 (`tools:`→`toolsets:`, no `--tag` routing, `gateway start &` wrong, redundant hand-written systemd unit, default-board DB path, 2-table→6-table schema, `--workspace` kind, ignored `kanban-worker`/`kanban-orchestrator` skills, ignored `KANBAN_GUIDANCE` auto-injection, ignored the shipped dashboard plugin, headless-gateway unverified, `kanban daemon` deprecated, no migration plan for the just-shipped v1) — all corrected in v2.

**v2 (Architect, 7 changes):** Phase 0 as standalone spike; surgical extraction not wholesale archival; SOUL.md restates 3 rules; dashboard own branch + A3→A3-lite; e2e blocked-vs-done terminal-state design; named board; B3 verified-but-deprecated — all folded into v3.

**v2 (Critic, 12 changes C-1..C-12):** 47-not-58 + per-file classification; deterministic-DAG via static pre-decomposition; 62-test classification; config.py additive-only + archived copy; Phase 0.12 verb dump; board.py/doctor.py P1 labels; Pre-Mortem P5; mechanical dryrun gate; board lifecycle/reset; milestone boundaries; default-board scrub; deferred items concretized — all folded into v3.

**v3 (Architect, 5 changes A-1..A-5):** e2e reviewer-task mechanism impossible → assert `blocked` as terminal; dryrun gate mis-specified → dispatcher-PATH wrapper + shared-repo hook + Phase 0.13; ADR states autonomous decomposition off critical path; observability tools are CLI not dashboard views; Phase 0.12b defaults to CLI `--json` + doctor.py thin wrapper — all folded into v4.

**v3 (Critic, 4 changes V4-CR-1..4):** 47-test classification inline; Milestone A / e2e terminal-state qualification; R11 detection trigger; Pre-Mortem P2 owner cross-reference — all folded into v4.

**v4 (Architect, N-1/N-2):** N-1 label the shared-repo `pre-push` hook as the PRIMARY gate, PATH wrapper as defense-in-depth + sole `gh` gate; N-2 scrub `GITHUB_TOKEN`/`GH_TOKEN` from the worker env under `DEV_BOOTH_DRYRUN` to close the `gh`/direct-API PR-spam bypass — folded into §8 (three-layer gate), Pre-Mortem P3, R3, Phase 0.13, and ADR-001 Consequences. **v4 (Critic): APPROVE.**

---

## 18. Approval

This plan is **PENDING APPROVAL**. On approval, recommended execution path:
- **`/oh-my-claudecode:ralph`** — sequential execution with the Phase 0 verification gate as a hard stop. Phase 0 runs first on the throwaway spike branch; Phases 1–7 are conditional on Phase 0's recorded evidence.
- Milestone A (Phases 0–4 + 6) is the real deliverable and is independently shippable. Milestone B (Phase 5, dashboard) is gated on the requester answering **OQ-DASH**. Milestone C (Phase 7) is operator-gated (sudo, real-GitHub actions).

Before execution begins, the requester should answer **OQ-DASH** (is `dashboard.excusa.uk` a product requirement?) so Milestone B's scope is fixed.
