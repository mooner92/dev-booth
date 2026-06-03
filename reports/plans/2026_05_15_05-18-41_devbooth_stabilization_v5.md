# Dev-Booth Stabilization v5 — Plan

> **Status:** `pending approval` — produced by `/ralplan` (consensus planning).
> Execution paths after approval: `team` (parallel, recommended) or `ralph` (sequential).
> Do **not** start code changes until the operator authorizes execution.

**Date:** 2026-05-15
**Author:** /ralplan (Planner → Architect → Critic synthesis)
**Builds on:** v4 results report (`2026_05_14_23-58-41_devbooth_kanban_replatform.md`)
+ post-v4 docs/rename commits (`3ff83c1` / `d1f4a3a` / `4dbb10e`, not yet pushed)
**Base branch:** `feat/kanban-redesign-2026-05-14` (cut off `25d5684`; `main` untouched)
**Scope label:** stabilization (no architectural shift; tightens what v4 shipped)

---

## 0. RALPLAN-DR Summary

### Principles (decision frame)

1. **Mechanical guarantees beat prompt compliance.** When the model can fail
   silently (no `kanban_complete()` call), prefer a system-level backstop over a
   stronger prompt. Prompts are a soft layer; pair them with one hard layer.
2. **Make paths explicit; never ask the model to discover them.** Every task
   body must carry the absolute paths the worker will read/write — no
   "find the worktree" heuristics.
3. **One source of truth per concern.** `core/scenario.py` owns DAG + bodies;
   `core/session.py` owns ctx assembly; `kanban_reader.py` owns the dashboard
   read path. Don't duplicate state.
4. **Verify the failure mode before "fixing" it.** Phase 0 probes confirm the
   token budget, the existence of `hermes kanban log`, the actual cause of
   each `protocol_violation` — *before* we change config.
5. **Backward-compat:** all 78 existing tests stay green. v5 adds tests; it
   does not delete or weaken any.

### Decision drivers (top 3)

1. **Protocol-violation rate** must drop to near-zero on a clean E2E run
   (firebase-002 dryrun, stages 1–3). Today this is the dominant failure mode
   — every other improvement is wasted if the agents keep hitting the wall.
2. **Token budget headroom** must be provable. vLLM's effective ceiling is the
   served `--max-model-len`; we need numbers, not vibes (Phase 0 P0.3).
3. **Operator observability.** The dashboard chat is currently empty — the
   only way to debug a stuck task is the CLI. Wiring run-time logs into the
   chat is the lever that makes the rest of the work debuggable.

### Viable options for the `kanban_complete()`-not-called failure

| Option | Description | Pros | Cons | Verdict |
|---|---|---|---|---|
| **A. Prompt-only** (v5 ralph prompt's default) | SOUL.md ⚠️ rule + body "completion section" + explicit example. | Cheap; in-scope; no upstream changes. | Soft layer — model can still skip; can't catch context-exhaustion exits. | Adopt as Layer 1. |
| **B. Mechanical post-run probe** | A small watchdog: after each dispatcher run, if task `status==running` and a fresh `task_runs.outcome` is not `completed`/`blocked`, auto-`kanban block reason="protocol_violation: agent exit without lifecycle call"`. | Catches every silent failure; surfaces it as `blocked` (retryable) instead of `running` (stuck). | Needs care to not race the dispatcher; small new module. | Adopt as Layer 2. **Recommended addition over v5 ralph prompt.** |
| **C. Per-turn budgeting / sliding window** | Hard-cap context with truncation, drop oldest turns. | Decouples max_turns from token blow-up. | Touches Hermes Agent internals (out of repo); risky. | **Reject** — out of scope; defer. |

Adopting **A + B** gives a strict upgrade over the v5 ralph prompt: A handles
"model forgot", B handles "model crashed / context overflowed".

### Viable options for the chat integration

| Option | Description | Verdict |
|---|---|---|
| **X. Mirror `kanban log` → `messages.jsonl`** | Dispatcher writes log lines into the existing per-session JSONL. | **Reject** — requires upstream dispatcher hook we don't own. |
| **Y. Pull-based reader (dashboard)** | `kanban_reader.py` shells out to `hermes kanban log <task_id>` (subject to Phase 0 P0.4 verification of that subcommand) and projects into the dashboard's `LogEntry` shape. | **Adopt** — matches the existing read-only A3-lite design; no dispatcher coupling. |
| **Z. Comments-only** | Use only `task_comments` (already wired) and accept no per-turn agent chatter. | **Reject as primary**, but **keep as fallback** if P0.4 finds `hermes kanban log` does not exist. |

### Invalidations (why not the others)

- **C (sliding window)** would be the most robust general fix but lives in the
  Hermes Agent codebase (`~/.hermes/hermes-agent`), which is upstream and
  versioned separately (we pinned v0.13.0 per OT5). Touching it would invalidate
  the pin. **Defer to upstream issue.**
- **X (JSONL mirror)** is upstream-coupled too. The dashboard already mtime-polls
  `kanban.db`; adding a second write path for the same data creates a
  consistency hazard.
- **Z (comments-only)** is fallback-only; we want the agent's actual stdout/tool
  calls visible, not just the `kanban_comment` thread.

---

## 1. Background — Current State

### v4 status (what exists today)

- Coordination platform: **Hermes Kanban** (SQLite, named board per session;
  no `hermes kanban daemon` — deprecated).
- DAG: `core/scenario.py` — 12 stages, `--parent` dependency edges,
  `STAGE_NARRATION` keyword-mapped to dashboard `stage_mapper`.
- Worker spawn: `hermes gateway` dispatcher claims `ready` tasks and spawns
  one of the three Hermes profiles — `conductor` / `architect` / `executor`
  (renamed in the unpushed v4-docs commit). Workers are NOT spawned by Dev-Booth.
- Dryrun: 3 layers — pre-push hook (per clone) + `git`/`gh` PATH wrappers +
  `GITHUB_TOKEN` scrub from gateway env. **Layer 3 is the mechanical backstop.**
- Dashboard: `kanban_reader.py` (CLI `--json` preferred, SQLite RO fallback) +
  `routers/kanban.py` (4 REST + 1 WS, 2 s mtime-poll). Frontend `KanbanBoard.tsx` +
  `useKanban.ts`. Live at `dashboard.excusa.uk`.

### What's broken (observed on firebase-001)

| Symptom | Evidence | Hypothesized cause |
|---|---|---|
| Tasks ending in `protocol_violation` (specifically `t_19363249`, `t_be0966f7`) | Workers exit without `kanban_complete()` or `kanban_block()`; task stays `running` until the dispatcher reaps it | Mix of (i) `max_turns: 40` ⇒ context overflow ⇒ Hermes truncated/killed before the closing tool call; (ii) model just skipped the call |
| Workers can't find the files they're supposed to read/write | Bodies say "결과를 `/dev-booth/sessions/{session}/analysis_architect.md`에 저장" but workers run in `~/.worktrees/<task_id>/` and the path resolution is ambiguous | Bodies don't carry the **workspace absolute path** the dispatcher actually mounted; agents guess |
| `improvements_v0.0.1.md` saved with template strings (not real plan content) | Stage-6 conductor output looks like the unrendered template | Conductor wrote the body verbatim instead of synthesizing — root cause is either skipped read of parent metadata, or context-pressure-driven shortcut |
| Dashboard chat is empty; no per-turn agent activity visible | `sessions/<session>/log/messages.jsonl` ≈ 0 bytes | Workers don't write to it — it was a v1 artifact; Kanban era never wired anything in |

### What v4 did **not** do (carry-overs into v5)

- Profile `max_turns` / `context_length` were left at upstream defaults (40 / 65 536).
- Stage bodies were ported verbatim from v1 (path comments only — no absolute
  paths, no completion checklist).
- The dashboard's chat panel was not wired to Kanban logs (it still expects
  the v1 `messages.jsonl` schema).

### Unpushed v4 work (relevant to base)

Three commits live locally only — `3ff83c1` (rename), `d1f4a3a` (systemd unit),
`4dbb10e` (docs). Operator must push them (or v5 must rebase) before v5 lands.
**Plan assumption:** v4 commits are pushed before v5 begins (else v5 commits
inherit the same `--no-verify` push problem).

---

## 2. Root-Cause Analysis (deeper than the ralph prompt)

### Problem 1 — `protocol_violation`

Two distinct failure modes share the same outcome. We treat them separately:

**1a) Silent context overflow.** Hermes Agent at `max_turns: 40` plus the
default `context_length: 65536` lets a conversation drift past the *actually
served* vLLM `--max-model-len`. When the serving layer's KV cache fills, the
chat call returns an error; if that error hits between a tool-result and the
next turn, the agent loop exits without calling `kanban_complete()`.

- **Falsifiable test:** Phase 0 P0.3 — `curl http://localhost:8003/v1/models`
  and print served `max_model_len`. Until verified, we treat "32 K" as a
  hypothesis. (Qwen2.5-Coder-32B can serve any window up to 128 K; vLLM may be
  launched with `--max-model-len` lower.)
- **Fix:** drop `max_turns` to 15 *and* set `context_length` 4 K below the
  actually-served ceiling.

**1b) Model skipped the call.** Even with budget left, the model decides "I'm
done" and stops generating tool calls. Pure prompt-compliance failure.

- **Falsifiable test:** Phase 0 P0.2 — read `t_19363249` / `t_be0966f7` run
  history. Does the run end mid-output (1a) or after a natural assistant turn
  (1b)?
- **Fix (Option A):** SOUL.md ⚠️ rule + body completion section. Helps but is
  soft.
- **Fix (Option B, the strict upgrade):** dispatcher-side post-run probe. If a
  task is `running` *and* its latest `task_runs` row has `outcome` ≠
  `completed`/`blocked` *and* the worker process has exited, auto-transition it
  to `blocked` with `reason="protocol_violation: agent exit without lifecycle call"`.
  This makes the failure mode terminal-and-retryable instead of indefinitely
  stuck.

### Problem 2 — file-path confusion

Workers run with `HERMES_KANBAN_WORKSPACE` env injected (`workspace_kind=worktree`
puts them in `~/.hermes/kanban/boards/<slug>/workspaces/<task_id>/` per the
Phase-0 evidence in the v4 result, NOT `~/.worktrees/` which the ralph prompt
incorrectly claims — **verify in P0.5**). They have no idea where
`/dev-booth/sessions/<session>/` is relative to that.

The fix has two parts:

- **Body templates:** put absolute paths in every body (read paths + write
  paths). Don't say "결과를 저장" without the full destination.
- **Ctx:** add `session_path` / `clone_root` / `workspace_hint` to
  `format_task`'s ctx so the template variables actually resolve.

### Problem 3 — `improvements_v0.0.1.md` was unrendered template

Two possible explanations, both plausible:

- Conductor read the parent task's *body* (which contains the template) and
  pasted that into the file instead of reading the parent's `summary` /
  `metadata` and synthesizing.
- Context pressure → conductor took a shortcut.

**Fix:** stage 6 body must explicitly say (a) READ the summary file written by
stage 5, (b) the output is a *new* document with structure X, (c) here are 1-2
shape examples. Plus: the stage 5 body must commit content to
`summary_v1.0.0.md` (not stuff it all into `kanban_complete.summary`).

### Problem 4 — dashboard chat is empty

Two layers:

- **Data:** there's no log feed to read from. The dashboard expects
  `messages.jsonl`. The dispatcher writes to `task_runs` / `task_logs` (TBD by
  P0.4) inside `kanban.db`, not into our JSONL.
- **UI:** `ChatStream.tsx` accepts a `LogEntry[]` — we need to shape the
  Kanban data into that type. The agent identity needs to come from
  `task.assignee` (reliable), not log-content heuristics (fragile).

---

## 3. Phase 0 — Verification Gate (probes BEFORE any code change)

**This phase is non-negotiable.** Several v5 fixes have a hidden assumption
(token budget; `hermes kanban log` exists; workspace path layout). We probe
each and record results in `/tmp/v5-phase0.md` **before** Phase 1.

| ID | Probe | Why it gates |
|---|---|---|
| P0.1 | `hermes kanban --board firebase-001 list --json` — confirm board exists / what state | If firebase-001 was deleted, redo on firebase-002 from scratch |
| P0.2 | For each `protocol_violation` task on firebase-001: `hermes kanban --board firebase-001 runs <id> --json` — was the run truncated (1a) or did the model finish a normal turn without `kanban_complete()` (1b)? | Determines whether Fix A alone is enough or Fix B is also needed |
| P0.3 | `curl -s http://localhost:8003/v1/models \| jq '.data[0].max_model_len'` (or `/v1/show` equivalent) — confirm the actually-served context window | The 28 000 number in the ralph prompt is *unverified*; if vLLM was launched with `--max-model-len 16384`, our budget math is wrong |
| P0.4 | `hermes kanban log --help` and `hermes kanban --board firebase-001 log <task_id>` — does the `log` subcommand exist on v0.13.0? | If it does not, the chat integration must fall back to `task_runs.transcript` (if any) or comments-only |
| P0.5 | After seeding one probe task, print the worker's `HERMES_KANBAN_WORKSPACE` from a one-shot agent (the env injection — confirm the actual path) | The ralph prompt says `~/.worktrees/`; the v4 phase-0 evidence said `~/.hermes/kanban/boards/<slug>/workspaces/`. We need the truth. |
| P0.6 | `ls -la ~/.hermes/profiles/conductor/config.yaml` + actually read `agent.max_turns`, `model.context_length`, served model name | Confirms baseline before we mutate |
| P0.7 | Estimate the assembled system prompt size: `hermes -z --print-system "noop"` or equivalent (if it exists) — else best-effort token count of SOUL.md + KANBAN_GUIDANCE | Validates the "8 K + 2 K" budget claim |
| P0.8 | Dashboard `/api/health` + `/api/kanban/boards` against the running uvicorn | Smoke test before any FE change |
| P0.9 | `pytest tests/ dashboard/backend/tests/ -q` baseline (capture pass count) | Locks in regression bar — must remain ≥ 78 throughout |

**Phase 0 exit criteria:** all 9 probes recorded; deviations (e.g.
`hermes kanban log` does not exist) trigger a plan amendment commit **before**
Phase 1.

---

## 4. Phase 1 — Profile Tuning

### 1.1 `max_turns` + `context_length`

For each profile in `~/.hermes/profiles/{conductor,architect,executor}/config.yaml`:

```yaml
agent:
  max_turns: 15            # was 40 (or 90 in shared default)
model:
  context_length: <CTX>    # value derived from P0.3:  served_max_model_len − 4096
```

- If P0.3 reports `max_model_len: 32768` → `CTX = 28000` (v5 ralph default).
- If P0.3 reports `16384` → `CTX = 12288` AND lower `max_turns` further (10),
  AND raise alarm: stage 8 / 9 may not fit at all.
- If P0.3 reports `≥ 65536` → keep `CTX = 28000` (conservative) unless we need
  more for stage 8.

**Backup before write.** For each profile:

```bash
cp -p ~/.hermes/profiles/<p>/config.yaml /tmp/v5-backup/<p>-config.yaml
```

so a single `cp /tmp/v5-backup/<p>-config.yaml ~/.hermes/profiles/<p>/config.yaml`
rolls back.

### 1.2 SOUL.md ⚠️ rule

Prepend the same block to all 3 SOUL.md files (and mirror to
`/dev-booth/core/souls/`, our version-controlled origin — see Principle 3):

```markdown
## ⚠️ 최우선 규칙 — 반드시 읽고 시작

당신은 Hermes Kanban 워커입니다. 모든 작업은 다음 둘 중 하나로 끝납니다:

  1. 작업 완료 → `kanban_complete(summary="...", metadata={...})`
  2. 작업 불가 → `kanban_block(reason="구체적 이유")`

이 두 호출 없이 대화가 끝나면 시스템은 protocol_violation 으로 기록하고
태스크는 stuck `running`이 됩니다.

작업이 끝났다고 판단한 즉시 추가 설명 없이 곧바로 `kanban_complete()`를 호출하세요.

예시:
    kanban_complete(
        summary="분석 완료. React 17, 테스트 없음, API 레이어 부재.",
        metadata={"file": "/dev-booth/sessions/<s>/analysis_architect.md", "issues_found": 3}
    )
```

**Rationale for top-of-file placement** (vs the more recency-biased tail
position): SOUL.md is concatenated as the *persona/role* layer; placing the
guarantee at the top binds the agent's identity to the rule from turn 1.
Architect would also accept tail placement; we choose top for testability —
`head -10` confirms presence (the v5 verification step).

### 1.3 No new toolsets / no new skills

Confirmed in v4: the dispatcher injects `HERMES_KANBAN_TASK/DB/BOARD/WORKSPACE`
which auto-loads the `kanban-worker` skill. We do **not** change `toolsets:` —
that's the v1-draft mistake the v4 phase 0 caught.

---

## 5. Phase 2 — `scenario.py` body templates

### 5.1 Shared template skeleton

Every stage's body follows this skeleton (enforced by a new helper
`_render_body(stage, ctx)` or by hand-rolled bodies — see §5.3):

```markdown
## 작업
<짧은 한 줄>

## 환경 정보 (꼭 사용)
- 작업 디렉터리(자동 주입): {workspace_hint}   ← HERMES_KANBAN_WORKSPACE
- 세션 디렉터리:           /dev-booth/sessions/{session}
- 부모 태스크 조회:        kanban_show()  로 metadata.clone_path / 직전 산출물 확인
- 클론 경로:               부모 metadata.clone_path  (stage 1 이 채움)

## 단계
1. ...
2. ...

## 완료 직전 체크리스트
□ 산출물 파일이 실제로 디스크에 쓰였는가? (touch 가 아닌 내용 포함)
□ 아래 호출을 곧바로 실행했는가? (다른 텍스트 없이)

## ⚠️ 완료 시 반드시 호출
kanban_complete(
    summary="<한 줄 요약>",
    metadata={{...구조화된 핸드오프...}}
)

## 막힐 때
kanban_block(reason="review-required: <구체적 이유>")
```

The duplicated rule (SOUL.md ⚠️ + body completion section) is intentional —
prompts are best-effort and redundancy is cheap.

### 5.2 Ctx additions (`core/session.py`)

```python
ctx = {
    "repo":         self.repo_name,
    "repo_url":     self.repo_url,
    "goal":         self.goal,
    "session":      self.session_name,
    "session_path": str(self.session_path),               # NEW
    "workspace_hint": "{HERMES_KANBAN_WORKSPACE}",        # NEW — literal; dispatcher injects at exec
    "n":            1,
    "task_description": "initial implementation",
}
```

The `workspace_hint` is a *literal* env-var reference that the agent (with a
shell tool) can `echo "$HERMES_KANBAN_WORKSPACE"` to resolve. We don't
substitute it at seed time because we don't know the worker's workspace at
seed time. (Architect concern: if the agent doesn't reach for the shell, it
won't resolve — accepted; the dispatcher injects the env var, and the body's
"환경 정보" line documents the variable.)

### 5.3 Per-stage diffs

The v5 ralph prompt enumerates bodies for stages 1–9 (10–12 left as
"동일한 패턴"). v5 the plan fills in **all 12**, because partial templating
is what produced Problem 3 in the first place.

> The full per-stage body specs are appended in **Appendix A** for length.

Key callouts:

- **Stage 1 (fork & clone) — path policy:** v5 ralph prompt clones to
  `/dev-booth/sessions/{session}/project`, *outside* the worker's worktree.
  This trades the auto-inherited pre-push hook (via `$GIT_COMMON_DIR/hooks`)
  for path predictability — accepted because stage 1 explicitly calls
  `install_hooks.sh <clone_path>` (per-clone Layer 1 stands), and Layer 3
  (token scrub) is unchanged. **Architect-flagged risk, mitigated by step 5.**
- **Stage 6 (improvements plan) — anti-template-leak:** the body MUST tell
  the conductor to *read* `summary_v1.0.0.md` first via the file tool and
  write a freshly-authored markdown, with at least 3 distinct TASKs. The
  closing checklist asks: "Is the file ≥ 200 bytes AND not just a copy of
  this body?" (the Layer 2 dispatcher probe — §6 — will also flag a file
  that didn't grow).
- **Stages 8 / 9 — turn budget worry:** with `max_turns: 15`, implement +
  test + review in one task may not fit. **Mitigation:**
  - Stage 8 explicitly instructs to `kanban_block(reason="needs-continuation: <where I stopped>")`
    if running low on turns; the operator unblocks (which re-queues with fresh budget).
  - Document this in the manual as the expected pattern.
  - **Open question:** is per-task `max_turns` overridable via task body or
    Kanban metadata? If yes, stage 8 should set a higher override. (Hermes
    v0.13.0 — verify in P0.6.)

### 5.4 No-regression invariant

The cross-seam test (`dashboard/backend/tests/test_stage_narration_crossseam.py`)
maps `STAGE_NARRATION` to dashboard `stage_mapper`. v5 body rewrites must NOT
change `STAGE_NARRATION` (only titles + body templates). Pytest catches drift.

---

## 6. Phase 3 — Dashboard Chat Integration

### 6.1 Backend — `kanban_reader.py`

Add `get_task_log(task_id)` and `get_runs(task_id)`:

```python
def get_runs(self, task_id: str) -> list[dict]:
    """Per-attempt outcomes from task_runs (always available; not version-coupled)."""
    out = self._run("--board", self.board_slug, "runs", task_id, "--json")
    if out is None: return []
    try: data = json.loads(out)
    except json.JSONDecodeError: return []
    return data if isinstance(data, list) else data.get("runs", [])

def get_task_log(self, task_id: str) -> list[dict]:
    """Raw per-turn transcript if v0.13.0 exposes it; else fall back to runs + comments."""
    out = self._run("--board", self.board_slug, "log", task_id, "--json")
    if out is not None:
        try:
            data = json.loads(out)
            return data if isinstance(data, list) else data.get("entries", [])
        except json.JSONDecodeError:
            pass
    return []   # fallback handled at router layer (compose runs + comments)
```

**Agent identity is derived from `task.assignee`** — NOT log-content regex.
The router composes a `LogEntry`:

```python
{
  "id":        f"run-{run.id}",
  "from":      task["assignee"],          # conductor | architect | executor
  "to":        None,
  "kind":      "tool" if entry_is_tool_call else "text",
  "body":      entry["text"],
  "createdAt": iso8601(entry["ts"]),
}
```

(`entry_is_tool_call` is best-effort: if `entry["kind"]` exists from
`hermes kanban log --json`, use it; else heuristic on `body` prefix
`kanban_*(`.)

### 6.2 Backend — new endpoint + WS payload

```python
# routers/kanban.py
@router.get("/boards/{board_slug}/tasks/{task_id}/log")
def get_task_log(board_slug: str, task_id: str) -> dict:
    reader = KanbanReader(board_slug)
    if not reader.exists: raise HTTPException(404, ...)
    return {"messages": reader.get_task_log(task_id)}
```

WebSocket payload extension (existing `kanban_update`):

```jsonc
{
  "type": "kanban_update",
  "tasks": [...],
  "comments": [...],
  "logs":    {<task_id>: [<LogEntry>, ...], ...}  // NEW; bounded
}
```

**Perf guardrail:** logs are pulled only for tasks whose `status` is
`running` OR whose `updated_at` is within the last 60 s. Cap: 5 tasks ×
50 newest entries per push. (Otherwise the dispatcher's normal cadence
causes a subprocess storm.)

### 6.3 Frontend

- **`useKanban.ts`** — extend the reducer to fold `logs` into per-task
  `messages: LogEntry[]`. Exponential-backoff reconnect (already partly
  present in `ws.ts`; reuse). Surface `connectionState` in the hook return
  so the UI can render a "reconnecting…" badge.
- **`ChatStream.tsx`** — already accepts `LogEntry[]`. Wire it to the
  active task's `messages` (from `useKanban`), not the empty
  `messages.jsonl` source.
- **`KanbanBoard.tsx`** — column scrolling: `overflow-y-auto` +
  `max-h-[calc(100vh-200px)]` per column (the ralph prompt's diff is correct).
- **`SessionDetailClient.tsx`** — replace whatever currently drives
  `ChatStream` for Kanban sessions with the `useKanban` log stream.
  Keep the old JSONL path behind a feature flag for v1 sessions
  (graceful fallback for any operator scrolling old data).

### 6.4 Tests

- `dashboard/backend/tests/test_kanban_reader.py` — extend with
  `test_get_task_log_cli` (mocked subprocess) and `test_get_runs`.
- `dashboard/backend/tests/test_kanban_router.py` (new) — endpoint smoke:
  200 on existing board, 404 on missing.
- Frontend: `KanbanBoard.tsx` snapshot includes scrollable columns.

---

## 7. Phase 4 — Mechanical `protocol_violation` Backstop (the v5-plan addition)

> This phase is what the v5 *ralph prompt* doesn't have. It is the Architect's
> insistence: prompts alone won't reach zero. Critic agrees: without B, the
> acceptance criterion "0 violations on stages 1–3" is fragile.

Add `core/devbooth/watchdog.py` (or `core/kanban/watchdog.py` to fit the
v4-plan layout) — a thin polling helper invoked by a cron / systemd
`OnCalendar=*:0/2` timer (operator setup, **out-of-scope sudo** — see §9):

```python
def reap_protocol_violations(board: str) -> list[str]:
    """Find tasks still 'running' whose latest task_runs row is closed (worker exited)
    without 'completed' or 'blocked' outcome; mark them blocked with a diagnostic reason.
    Idempotent."""
    reader = KanbanReader(board)
    tasks = reader.list_tasks(status="running")
    reaped = []
    for t in tasks:
        runs = reader.get_runs(t["id"])
        if not runs: continue
        latest = runs[-1]
        if latest.get("ended_at") and latest.get("outcome") not in ("completed", "blocked"):
            subprocess.run([HERMES_BIN, "kanban", "--board", board, "block", t["id"],
                            "--reason", f"protocol_violation: worker exited (outcome={latest.get('outcome')!r})"])
            reaped.append(t["id"])
    return reaped
```

- Idempotent (`hermes kanban block` on a `running` task → `blocked`; on a
  `blocked` task → no-op or noisy-no-op; either is acceptable).
- Bounded: only looks at `running` tasks; cost = 1 subprocess per running
  task per tick.
- Surfaces the failure in the dashboard immediately as `blocked` (with a
  human-readable reason), which the operator can `unblock` to retry.

**Run cadence:** every 2 minutes. (Aligned with the dispatcher's
`interval: 60` so we never preempt a turn but catch a dead one within ~3 min.)

**Out-of-scope nicety:** wire the same logic into the dispatcher itself
(upstream change). Logged as **OT3** for the Hermes Agent backlog.

---

## 8. Risk Matrix

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | `max_turns: 15` is too tight for stage 8 (implement) | Med | Med | Stage 8 body teaches "needs-continuation" block pattern; operator unblocks to grant new budget; documented in MANUAL |
| R2 | P0.3 reveals served context < 28 K | Low | High | Plan amendment: drop ctx to `served - 4 K`; if `< 16 K`, halt and ask operator to relaunch vLLM with bigger window |
| R3 | `hermes kanban log` subcommand doesn't exist on v0.13.0 | Med | Low | Fallback: compose chat from `runs` + `comments` (both confirmed-available) |
| R4 | `install_hooks.sh` is forgotten on a stage-1 retry — push not blocked at Layer 1 | Low | Low | Layer 3 (token scrub) still holds; document in MANUAL §6 retry checklist |
| R5 | Body template growth lifts per-turn token use, partially offsetting the `max_turns` cut | Med | Low | After Phase 2, measure: seed one task, capture worker's first turn token count. If > 1.2 × pre-v5 baseline, prune the "단계" sections |
| R6 | Watchdog races the dispatcher (block fires on a task that was about to `kanban_complete`) | Low | Med | Watchdog only acts when `task_runs.ended_at IS NOT NULL` (worker process is provably done); the dispatcher's own write of `kanban_complete` clears `outcome` before `ended_at` is final |
| R7 | Frontend chat wiring breaks v1 session backward compat | Low | Low | Feature flag on session id / fallback to `messages.jsonl` reader for older sessions |
| R8 | Deleting firebase-001 loses diagnostic evidence | Med | Med | **Do not delete** firebase-001 before P0.2 captures the run history; even after, archive `kanban.db` to `archive/firebase-001-pre-v5.db` |

---

## 9. Out of scope / operator-gated

| OT | Item | Reason |
|---|---|---|
| OT1 | `hermes-gateway.service` install (`sudo cp` + enable) | Already documented in v4 results; not re-introduced by v5 |
| OT2 | `dev-booth-dashboard.service` restart (after FE rebuild) | sudo |
| OT3 | Upstream Hermes Agent — sliding-window context, in-dispatcher protocol_violation handling | We pinned v0.13.0; touching upstream invalidates the pin |
| OT4 | Cron/timer for `watchdog.reap_protocol_violations` | systemd timer → sudo. v5 ships the function + a CLI entry point; operator wires the timer |
| OT5 | `git push` of the v4 unpushed commits (`3ff83c1`/`d1f4a3a`/`4dbb10e`) | Pre-push hook blocks; agent classifier blocks `--no-verify` / `DEV_BOOTH_DRYRUN=0`; operator pushes manually |

---

## 10. Test Plan

### 10.1 Unit / regression

```bash
cd /dev-booth && source env/bin/activate
pytest tests/ dashboard/backend/tests/ -v
# Bar: ≥ 78 passing (v4 baseline), plus the new tests added in §6.4 and §11.
```

### 10.2 Frontend

```bash
cd /dev-booth/dashboard/frontend
npx tsc --noEmit
npm run build
```

(Same gates as v4; FE changes must keep these clean.)

### 10.3 E2E — clean board (firebase-002)

Pre-flight:

```bash
hermes kanban boards list           # confirm firebase-001 archived, not deleted
hermes gateway status               # active, dryrun env (GITHUB_TOKEN unset, PATH wrappers)
curl -s http://localhost:8003/v1/models | jq    # vLLM up
```

Run:

```bash
DEV_BOOTH_DRYRUN=1 ./run.sh start firebase-002 \
    https://github.com/mooner92/firebase-chat-exp \
    "코드 품질 개선 및 버그 수정"

# Observe live
hermes kanban --board firebase-002 watch &
watch -n 60 "hermes kanban --board firebase-002 stats"
```

Bar (stage 1–3 within 30 min):

- `hermes kanban --board firebase-002 stats` shows 0 `running` tasks
  abandoned (i.e., status `running` for > `max_turns` × ~30 s ≈ 8 min).
- Tasks for stages 1 / 2 / 3 reach `done`.
- `/dev-booth/sessions/firebase-002/analysis_architect.md` exists and is
  ≥ 1 KB and contains actual analysis (not just the body template).
- Dashboard `https://dashboard.excusa.uk/session/firebase-002` shows
  per-task chat (logs) flowing.

If any task hit `blocked` with `protocol_violation` reason: Phase-4 watchdog
worked; that's a **pass** for v5 (the failure was caught, not silent).

### 10.4 Watchdog acceptance

Synthetic test:

```bash
# Seed a task, kill its worker mid-turn (simulating context overflow)
hermes kanban --board v5-synthetic init && \
hermes kanban --board v5-synthetic create "noop" --assignee conductor --workspace worktree --body "sleep 999" --json
# wait until dispatcher spawns it ...
pkill -9 -f "hermes -z .*v5-synthetic"     # simulate hard exit
# within 2 min watchdog should transition it to blocked
sleep 130 && hermes kanban --board v5-synthetic list --json | jq '.[]|.status'
# Expected: "blocked" with reason starting "protocol_violation: ..."
```

---

## 11. Acceptance Criteria (testable)

### Phase 0

- [ ] `/tmp/v5-phase0.md` exists with P0.1–P0.9 results.
- [ ] P0.3 records actual `max_model_len`; plan numbers for §1.1 adjusted if needed.
- [ ] P0.4 either confirms `hermes kanban log` works (use it) or falls back
      to runs+comments composition.

### Phase 1

- [ ] `grep -E 'max_turns:|context_length:' ~/.hermes/profiles/{conductor,architect,executor}/config.yaml`
      reports `max_turns: 15` and `context_length: <chosen>` for all 3.
- [ ] `head -10 ~/.hermes/profiles/<each>/SOUL.md` shows the `⚠️ 최우선 규칙` section.
- [ ] `/dev-booth/core/souls/*.SOUL.md` (version-controlled origin) matches.
- [ ] Backups exist at `/tmp/v5-backup/<each>-config.yaml`.

### Phase 2

- [ ] All 12 stages in `core/scenario.py` follow the §5.1 skeleton (sectioned
      `## 작업`, `## 환경 정보`, `## 단계`, `## 완료 직전 체크리스트`,
      `## ⚠️ 완료 시 반드시 호출` block).
- [ ] `ctx` in `core/session.py` includes `session_path`, `workspace_hint`,
      `n`, `task_description`; no `KeyError` on `format_task()`.
- [ ] Existing `test_scenario.py` + `test_session.py` pass; new
      `test_body_has_completion_block` (parametrized over all 12 stages)
      asserts the kanban_complete example is present.
- [ ] Cross-seam test (`test_stage_narration_crossseam`) still green.

### Phase 3

- [ ] `dashboard/backend/services/kanban_reader.py` exposes `get_task_log` +
      `get_runs`.
- [ ] `GET /api/kanban/boards/<slug>/tasks/<id>/log` returns 200 + `messages: [...]`.
- [ ] WS payload includes `logs` (≤ 5 tasks, ≤ 50 entries each).
- [ ] `KanbanBoard.tsx` columns scroll; visual check on `dashboard.excusa.uk`.
- [ ] `npx tsc --noEmit` and `npm run build` clean.

### Phase 4

- [ ] `core/.../watchdog.py:reap_protocol_violations` is unit-tested
      (mock subprocess; assert idempotent + correct block reason).
- [ ] Synthetic E2E (§10.4) shows transition to `blocked` within ~2 min.
- [ ] CLI entry `python -m core.watchdog --board <slug>` exists for the
      operator's timer to call.

### Phase 5 (close-out)

- [ ] Results report at
      `/dev-booth/reports/results/YYYY_MM_DD_HH-MM-SS_devbooth_stabilization_v5.md`.
- [ ] All v5 commits on `feat/kanban-redesign-2026-05-14` (or a new
      `feat/stabilization-v5` branch — decide at exec time); `main` untouched.
- [ ] Operator block (sudo) documented inline for `dev-booth-dashboard` restart
      + optional watchdog timer install.

---

## 12. ADR — Architecture Decision Record

- **Decision.** Stabilize protocol_violation, file-path confusion, plan
  rendering, and dashboard chat in a single v5 increment, layering a
  *mechanical* watchdog on top of the v5-ralph-prompt's prompt-only fixes.
- **Drivers.** 0 violations on stages 1–3 is the user's stated bar; the
  ralph prompt's prompt-only approach is necessary but not sufficient; the
  dashboard chat is the operator's debug surface.
- **Alternatives considered.**
  - Pure prompt-only (the v5 ralph prompt as written) — rejected as
    insufficient (R2 / R6).
  - Upstream Hermes Agent patch (sliding window, in-dispatcher reaping) —
    rejected as out-of-scope (OT3) but logged.
  - JSONL mirroring for chat — rejected (X above); pull-based reader fits
    A3-lite.
- **Why chosen.** Layered (prompts + mechanical) matches the project's
  existing dryrun design (3 layers, mechanical Layer-3 backstop). Reusing
  that pattern for protocol_violation makes the system's failure-mode story
  consistent and explainable.
- **Consequences.**
  - The operator inherits one optional cron/timer (OT4).
  - `max_turns: 15` will cause more block-then-unblock cycles in stages 8/9
    — a *documented* pattern, not a bug.
  - Dashboard becomes more useful as a debugging surface — operator
    observability scales with the system.
- **Follow-ups.**
  - **F1 (post-v5):** measure protocol_violation rate on 5 consecutive full
    runs; if > 5 %, escalate to OT3 (upstream patch).
  - **F2:** per-stage `max_turns` override (Hermes feature ask / local
    fork).
  - **F3:** archive policy for `firebase-*` boards once a run is post-mortem'd.

---

## 13. Open Questions for the Operator

| OQ | Question | Default-if-no-answer |
|---|---|---|
| OQ-1 | Branch strategy — keep all v5 work on `feat/kanban-redesign-2026-05-14` (long-lived) or cut `feat/stabilization-v5` from it? | Same branch (smaller blast radius for ops; v4 not yet on `main`) |
| OQ-2 | Delete or archive firebase-001? | **Archive** (`hermes kanban boards rm` is destructive; prefer `boards archive`); preserve `kanban.db` to `archive/firebase-001-pre-v5.db` |
| OQ-3 | Watchdog cadence — 2 min (responsive) vs 5 min (cheap)? | 2 min |
| OQ-4 | If P0.3 reports `max_model_len < 16384`, do we (a) ask the operator to relaunch vLLM, or (b) reduce v5 ambition (drop stage 8 / 9 from the bar)? | (a); document the relaunch command in the report |

---

## 14. Rollback

Each phase has a clean reverse:

- **Phase 1:** `cp /tmp/v5-backup/<p>-config.yaml ~/.hermes/profiles/<p>/config.yaml`
  for each profile; `git checkout HEAD -- core/souls/`. Then
  `hermes gateway` restart picks up old values.
- **Phase 2:** single git revert of the `scenario.py` + `session.py` commit.
- **Phase 3:** git revert of dashboard commits; `npm run build` once;
  `sudo systemctl restart dev-booth-dashboard` (operator).
- **Phase 4:** delete the watchdog module; remove the timer (if installed)
  — no other system surface touched.

---

## 15. Appendix A — Per-stage body specs (12 stages)

For each stage, the body MUST contain (in order):

1. `## 작업` — one-sentence directive.
2. `## 환경 정보` — concrete absolute paths + how to discover what isn't seeded.
3. `## 단계` — numbered, ≤ 6 items. **Each is shell-runnable or tool-callable.**
4. `## 완료 직전 체크리스트` — 2–3 boolean items the agent self-asserts.
5. `## ⚠️ 완료 시 반드시 호출` — `kanban_complete(...)` example with a
   non-empty `metadata` that includes the artifact path(s) the *next* stage
   will read.
6. (Stages 8 / 9 only) `## 막힐 때` — `kanban_block(reason="...")` example.

Stages and their core handoff metadata (the actual full bodies are in the
implementation diff and are too long to inline here — reference: the v5 ralph
prompt §2.1 stages 1–9 are correct as drafts; stages 10–12 below fill the
gap):

- **Stage 10 (commit approved changes):** read parent metadata
  `changed_files`, `cd /dev-booth/sessions/{session}/project`, `git add -A`,
  `git commit -m "feat: {task_description} [devbooth/{session}]"`; under
  dryrun the commit is local-only. Complete with
  `metadata={"commit_sha":"<sha>", "files":[...]}`.
- **Stage 11 (draft PR):** assemble `pr_body` from the summary +
  improvements file; under dryrun write
  `/dev-booth/sessions/{session}/pr_draft.json` with `{title, body, url: "DRYRUN://no-pr"}`.
  Complete with `metadata={"draft_file": "..."}`.
- **Stage 12 (submit PR):** under dryrun, copy `pr_draft.json` to
  `pr_final.json` (no `gh pr create`). Under live (operator-gated),
  `gh pr create --repo mooner92/{repo} ...`. Complete with
  `metadata={"pr_url": "<DRYRUN://no-pr or real URL>"}`.

The "metadata is the handoff" principle is the same in all 12: every stage's
`kanban_complete.metadata` is what the next stage's body says to read.

---

## 16. Appendix B — Files touched (planning estimate)

| File | Change | Risk |
|---|---|---|
| `~/.hermes/profiles/{conductor,architect,executor}/config.yaml` | yaml-write `max_turns`, `context_length` | Med (lives outside repo; backup mandatory) |
| `~/.hermes/profiles/{conductor,architect,executor}/SOUL.md` | prepend ⚠️ block | Low |
| `core/souls/{conductor,architect,executor}.SOUL.md` | mirror of above | Low |
| `core/scenario.py` | rewrite all 12 `body_template`s; no DAG / narration changes | Med |
| `core/session.py` | extend ctx | Low |
| `dashboard/backend/services/kanban_reader.py` | + `get_runs`, `get_task_log` | Low |
| `dashboard/backend/routers/kanban.py` | + `/log` endpoint, WS payload extension | Low |
| `dashboard/frontend/hooks/useKanban.ts` | logs in reducer + backoff | Low |
| `dashboard/frontend/components/{KanbanBoard,ChatStream,SessionDetailClient}.tsx` | wiring + scrolling | Low |
| `core/.../watchdog.py` (new) | reaper + CLI | Low |
| `tests/test_scenario.py` | parametrized "has completion block" test | Low |
| `dashboard/backend/tests/test_kanban_reader.py` | + log/runs tests | Low |
| `dashboard/backend/tests/test_kanban_router.py` (new) | endpoint smoke | Low |
| `reports/plans/2026_05_15_05-18-41_devbooth_stabilization_v5.md` | this file | n/a |
| `reports/results/<date>_devbooth_stabilization_v5.md` | end-of-exec | n/a |

**Commit policy (per the operator's last instruction):** ship as
**feature-unit commits** (one per phase), not a single bundle:

1. `phase0: record stabilization v5 verification probes`
2. `phase1: cap max_turns + context_length; prepend kanban lifecycle rule to souls`
3. `phase2: rewrite 12 scenario bodies with explicit paths + completion blocks`
4. `phase3: surface kanban log + runs in dashboard chat + scrollable columns`
5. `phase4: add protocol_violation watchdog + CLI entry`
6. `docs: stabilization v5 results report`

---

## 17. How to execute this plan after approval

This plan is `pending approval`. After the operator approves:

- **Recommended:** `Skill("oh-my-claudecode:team")` — Planner/Architect/Critic
  done; team launches Phase 0 → 4 with parallel sub-agents on independent
  files (backend / frontend / scenario / watchdog).
- **Alternative:** `Skill("oh-my-claudecode:ralph")` — sequential, story-by-story.

The team option is recommended because Phases 1–4 have ~zero file overlap
once Phase 0 is recorded.

---

*End of v5 stabilization plan.*
