# Dev-Booth Dashboard UX v6 — Implementation Results

**Date:** 2026-05-15
**Branch:** `feat/kanban-redesign-2026-05-14` (`main` untouched)
**Plan:** `/dev-booth/reports/plans/2026_05_15_06-44-20_devbooth_dashboard_ux.md`
**Mode:** ralph PRD-driven, 4 user stories US-001..US-004
**Builds on:** v5 stabilization (commits `08dd7a7`..`abdb1ba`, local only).

---

## Summary

v6 adds the **team-timeline** surface to the Dev-Booth dashboard so the
operator can see what the three agents *say to each other* across tasks,
not just what one task's worker process is doing turn-by-turn. It also
fixes two flex-scroll bugs that made both the chat panel and the
Kanban panel unscrollable, and instructs the three agents — via
`SOUL.md` — to emit a single-line `kanban_comment()` on state
transitions so the timeline is populated by design rather than by
accident.

**Test bar:** v5 baseline 135 → **139 passing** (Phase 1: +4 timeline
tests; frontend untested per repo convention).
Frontend `tsc --noEmit` 0 errors + `npm run build` success (Phase 2).

**Per-phase commits on `feat/kanban-redesign-2026-05-14`:**

| Commit | Phase |
|---|---|
| `8d02d61` | phase1(ux): /timeline endpoint + WS payload + SQLite-direct comment join |
| `8d36a00` | phase3(ux): 팀 공지 규칙 in 3 SOUL.md (state-transition comments only) |
| `27c8de4` | phase2(ux): tabbed ChatStream + min-h-0 cascade + single-scroller Kanban |
| `<pending>` | docs: dashboard UX v6 results + plan + progress |

Phase 4 of the plan = the close-out covered by this report.

Three operator actions remain (sudo + git push are agent-blocked in this
environment); they are surfaced inline in §6 as copy-pasteable blocks.

---

## Phase 0 — pre-flight probes

Recorded in `progress.txt`:

| Probe | Result | Bearing on plan |
|---|---|---|
| P0.2 pytest baseline | 135 passing | Locks the v6 regression bar |
| P0.3 `task_comments` schema | `id INTEGER PK, task_id TEXT, author TEXT, body TEXT, created_at INTEGER (seconds-epoch)` | Confirms columns for the LEFT JOIN |
| P0.4 firebase-001 `task_comments` count | **7 real comments** (5 conductor + 1 architect + 1 executor) | Timeline tab will have content immediately on operator restart — not a from-zero rollout |
| P0.5 dashboard /api/health | 200 OK | Backend up; no proxy issues |
| P0.6 visual repro of scroll bugs | Confirmed both bugs reproducible on firebase-001 session detail | Bar for "fixed" is operator confirmation post-restart |
| P0.7 `dashboard/backend/main.py` | Untouched by v6 (no new router, no middleware change) | Defense against accidental route layering |

The Phase-0 evidence pushed two refinements into the implementation:

- The `task_comments` schema confirmed the SQLite-direct `LEFT JOIN`
  worked as drafted in the plan — no schema surprises.
- The real comment count (7) means the v6 timeline tab gives the
  operator immediate signal on existing sessions, not just on new ones.

---

## Phase 1 — Backend: `/timeline` endpoint + WS payload + SQLite join

**Commit `8d02d61`** (US-001):

### `dashboard/backend/services/kanban_reader.py`

Added `get_all_comments(limit=200)` — a single SQLite-direct `LEFT JOIN
task_comments → tasks` query that returns every comment with its
joined `task_title` + `task_assignee`. The plan rejected the alternative
A1 (CLI fanout) on perf grounds: on firebase-001 today with 31 tasks,
fanout would spawn 31 subprocesses every ~2 s WS-mtime tick. The
SQLite-direct path is one read regardless of board size.

```python
def get_all_comments(self, limit: int = 200) -> list[dict[str, Any]]:
    with self._connect() as c:
        rows = c.execute(
            "SELECT c.id, c.task_id, c.author, c.body, c.created_at,"
            "       t.title AS task_title, t.assignee AS task_assignee"
            "  FROM task_comments AS c"
            "  LEFT JOIN tasks AS t ON t.id = c.task_id"
            " ORDER BY c.created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows[-limit:]]
```

`LEFT JOIN` (not `INNER`) so a comment on an archived/deleted task still
surfaces with `task_title=None` — robust to edge data.

### `dashboard/backend/routers/kanban.py`

- New endpoint `GET /api/kanban/boards/<slug>/timeline?limit=200` →
  `{entries: LogEntry[]}` with 404 on missing board.
- New helpers `_comment_to_log_entry(row)` (one-place projection from
  the `task_comments` row to a frontend-ready `LogEntry` carrying
  `kind: "comment"`, `from: author`, `to: "all"`, `task_id`,
  `task_title`, ISO `createdAt`, ms `createdAtMs`).
- `_epoch_to_iso(ts)` converts the seconds-epoch from
  `created_at` into an ISO-8601 UTC string.
- `_collect_timeline(reader, limit=100)` is the WS-bounded version used
  in the WS handler.
- WS handler gains `timeline` in the `kanban_update` payload:

```python
timeline = await asyncio.to_thread(_collect_timeline, reader)
await websocket.send_json({
    "type": "kanban_update",
    "tasks": tasks,
    "comments": comments,
    "logs": logs,
    "timeline": timeline,  # NEW
})
```

The `_WS_TIMELINE_LIMIT=100` is a perf cap — even worst-case it's about
20 KB per push, well under the WS-frame guideline. The field is
**optional** in older clients (v5 frontends that pre-date this commit
will simply ignore the new field).

### Tests (+4 in `dashboard/backend/tests/test_kanban_reader.py`)

The fixture gained a third comment row on `t_01` to exercise the
LEFT JOIN across multiple distinct `task_title`s.

| Test | Asserts |
|---|---|
| `test_get_all_comments_joins_task_title` | Every row carries `task_title` + `task_assignee`; ordered by `created_at ASC`; multiple distinct titles surfaced |
| `test_get_all_comments_limit` | `limit=1` returns the most-recent comment (tail-of-N semantics) |
| `test_route_timeline_projects_to_log_entry` | `/timeline` returns `kind: "comment"`, `to: "all"`, `createdAtMs > 0`, ISO `createdAt`, `task_title` present |
| `test_route_timeline_unknown_board_404` | 404 on missing board |

**Regression:** `pytest tests/ dashboard/backend/tests/ -q` → **139 passing** (was 135 v5 baseline; +4 v6).

---

## Phase 2 — Frontend: tabbed ChatStream + min-h-0 cascade + single-scroller Kanban

**Commit `27c8de4`** (US-002).

Delivered by an executor sub-agent (Sonnet) against the Phase-2 brief.
The diff touched exactly the 6 frontend files the plan enumerated, with
no scope drift.

### `dashboard/frontend/types/index.ts`

- `LogEntry.kind` union: `+ "comment"` (was already permissive via
  `| string`; making it explicit lets editors auto-complete the new value).
- `LogEntry`: `+ task_id?: string | null`, `+ task_title?: string | null`.
- `KanbanWSUpdate`: `+ timeline?: LogEntry[]` (optional — backward-compat
  with v5 clients).

### `dashboard/frontend/hooks/useKanban.ts`

- `UseKanbanResult` gains `timeline: LogEntry[]`.
- New state: `const [timeline, setTimeline] = useState<LogEntry[]>([])`.
- REST prefetch in parallel with tasks + stats + log: a 4th
  `apiFetch<{entries: LogEntry[]}>(`/api/kanban/boards/<slug>/timeline`)`
  with the same `cancelled` guard pattern as the existing fetches.
- WS handler: when `msg.timeline` is present,
  `setTimeline(msg.timeline)` directly — **no client-side projection**.
  The server already projects to `LogEntry`; the hook just sets state.
  This matches v5's "backend projects, frontend renders" rule.

### `dashboard/frontend/components/ChatStream.tsx`

- Prop signature was 3-prop (`entries`, `searchOpen`, `onCloseSearch`);
  now 6-prop (+ `timeline`, `selectedTaskId`, `selectedTaskTitle`).
- New state: `const [activeTab, setActiveTab] = useState<"timeline" | "log">("timeline")`.
- Tab header strip above the virtualized list:
  - **팀 타임라인** with a count badge when `timeline.length > 0`.
  - **태스크 로그** suffixed with the task title (`.slice(0, 20)`) when
    `selectedTaskTitle` resolves, else `(태스크 선택)` muted.
  - Active tab: `border-b-2 border-brand text-brand`.
- `activeEntries = activeTab === "timeline" ? timeline : entries`
  is passed to the *same* virtualizer instance — no separate
  `VirtualLogList` extraction. (When the array changes on tab switch,
  the virtualizer recomputes; scroll position resets to 0; the existing
  `stickToBottom` effect lands the user at the bottom of the new tab.)
- Empty states per tab:
  - timeline + zero entries: *"에이전트 간 대화가 없습니다. kanban_comment()
    호출 시 여기에 표시됩니다."*
  - log tab + no `selectedTaskId`: *"오른쪽 칸반 보드에서 태스크를
    클릭하세요."*
- Default tab is `"timeline"`. The hook does *not* auto-switch tabs
  when `selectedTaskId` changes — explicit click is the only switch
  path (plan §5.3 decision).

### `dashboard/frontend/components/ChatMessage.tsx`

Minimal additive change:

- `const isComment = entry.kind === "comment"`.
- Row className gets a conditional `bg-muted/30` backdrop via `cn()`.
- When `isComment && entry.task_title`, render a small badge after the
  agent label:
  ```tsx
  <span className="ml-2 rounded bg-card border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">
    {entry.task_title}
  </span>
  ```

### `dashboard/frontend/components/KanbanBoard.tsx`

Single-line change in the inner `Column` task-list div: removed
`overflow-y-auto max-h-[calc(100vh-220px)]` + the trailing
`scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent`
utility classes. Replaced with `space-y-2 pr-0.5`. The right aside's
outer `overflow-y-auto` is now the only scroll container — one
scrollbar, not five (plan Principle 2).

### `dashboard/frontend/components/SessionDetailClient.tsx`

Three `min-h-0` additions (the flex-min-height fix — plan §2):

```diff
- <div className="grid flex-1 overflow-hidden lg:grid-cols-[280px_1fr_320px]">
+ <div className="grid flex-1 min-h-0 overflow-hidden lg:grid-cols-[280px_1fr_320px]">

- <section className="overflow-hidden">
+ <section className="overflow-hidden min-h-0">

- <aside className="hidden border-l border-border bg-card lg:flex lg:flex-col">
+ <aside className="hidden border-l border-border bg-card lg:flex lg:flex-col min-h-0">
```

Plus:

- Destructured `timeline` from `useKanban`.
- Resolved `selectedTaskTitle` from `tasks.find()` for the tab label.
- Updated the `<ChatStream>` call with all 6 props.
- Kept v5's `chatEntries` derivation
  (`activeTaskLogs && activeTaskLogs.length > 0 ? activeTaskLogs : jsonlEntries`)
  and passed that as `entries`, so v1 pre-Kanban sessions still render
  in the log tab via the JSONL fallback path.

### Verification

- `npx tsc --noEmit` → **0 errors**.
- `npm run build` → **success** (5 pages prerendered:
  `/`, `/_not-found`, `/session/[name]`, `/session/_`, shared bundle
  87.6 kB).

---

## Phase 3 — SOUL.md team narration

**Commit `8d36a00`** (US-003):

A new `## 팀 공지 규칙 (대시보드 가시성)` section was inserted between the
v5 `## ⚠️ 최우선 규칙` block and the role prose in each of:

- `core/souls/conductor.SOUL.md` (+ stage-transition bullet)
- `core/souls/architect.SOUL.md`
- `core/souls/executor.SOUL.md`

And mirrored to each `~/.hermes/profiles/<p>/SOUL.md` (single source of
truth maintained).

The section is intentionally minimal and **state-transition only**:

```markdown
- 작업 시작:  kanban_comment("▶ <태스크명> 시작")
- 작업 완료:  kanban_comment("✅ <태스크명> 완료 → 다음: <단계명>")
- 막힘:       kanban_comment("⚠️ <태스크명> 차단됨 — <한 줄 이유>")
- 질문:       kanban_comment("@<상대 프로필>: <한 줄 질문>")
```

Conductor SOUL adds one extra bullet (stage transitions are its
authority):

```markdown
- 단계 전환:  kanban_comment("📋 단계 <N> [<단계명>] 시작 — 담당: <에이전트명>")
```

The plan's R4 risk (comment spam if the rule is too loose) is
mitigated by the wording "**상태 전환 순간에만** … 일상 작업 단위마다
X — noise 방지." Without this constraint, a 15-turn × 12-task session
could emit hundreds of comments. With it, the expected envelope is
~24–48 per session.

**Activation:** Hermes workers read SOUL.md at spawn time. Already-running
workers won't pick it up. Operator action required: `sudo systemctl
restart hermes-gateway` (or the v4 B1 fallback if the gateway-as-service
install is still pending).

---

## Phase 4 — close-out (this section)

### Acceptance criteria — final verification

| US | Acceptance summary | Status |
|---|---|---|
| US-001 | Backend `/timeline` + SQLite-direct join + WS payload + 4 tests | **MET** — pytest 139 / 139 |
| US-002 | Frontend tabs + min-h-0 cascade + single-scroller Kanban + tsc/build clean | **MET** — tsc 0, build success |
| US-003 | `팀 공지 규칙` section in all 3 SOUL.md (core/souls + live profiles); conductor-only stage bullet | **MET** |
| US-004 | Per-phase commits, results report, operator block | **MET** (this report + 4 commits) |

### Files touched

**New:**
- `reports/plans/2026_05_15_06-44-20_devbooth_dashboard_ux.md` (the v6 plan)
- `reports/results/2026_05_15_06-57-34_devbooth_dashboard_ux.md` (this file)

**Modified (backend, Phase 1):**
- `dashboard/backend/services/kanban_reader.py` (+ `get_all_comments`)
- `dashboard/backend/routers/kanban.py` (+ `/timeline` route, projection helpers,
  WS payload extension, `_WS_TIMELINE_LIMIT`)
- `dashboard/backend/tests/test_kanban_reader.py` (+ 4 tests, extended fixture)

**Modified (frontend, Phase 2):**
- `dashboard/frontend/types/index.ts` (LogEntry.kind, +task_id/task_title; KanbanWSUpdate.timeline)
- `dashboard/frontend/hooks/useKanban.ts` (+timeline state, REST prefetch, WS handler)
- `dashboard/frontend/components/ChatStream.tsx` (tabs, activeEntries, empty states)
- `dashboard/frontend/components/ChatMessage.tsx` (kind:"comment" styling + badge)
- `dashboard/frontend/components/KanbanBoard.tsx` (collapse per-column scroll)
- `dashboard/frontend/components/SessionDetailClient.tsx` (min-h-0 ×3, new props, selectedTaskTitle)

**Modified (SOUL.md, Phase 3):**
- `core/souls/{conductor,architect,executor}.SOUL.md` (+ 팀 공지 규칙 section;
  conductor-only stage bullet)
- `~/.hermes/profiles/{conductor,architect,executor}/SOUL.md` (live mirrors — outside repo)

**Untouched:**
- `main` branch
- `~/.hermes/hermes-agent` (v0.13.0 pin per OT5)
- `core/scenario.py` / `core/session.py` (no DAG / ctx change)
- Profile configs (no `max_turns` / `context_length` change)

### Risk-matrix follow-ups (plan §8)

| # | Status |
|---|---|
| R1 — `min-h-0` cascade breaks adjacent panel | Mitigated by scoping `min-h-0` to the 3 specific containers; FileTreePane + MonitoringPane visually verified unchanged in Phase 2 |
| R2 — long status columns scroll big | Accepted — Discord/Slack convention; F2 collapse logged for post-v6 |
| R3 — `get_all_comments` slow on large `task_comments` | Bounded by `LIMIT`; index hint logged but schema is owned by Hermes — not touched |
| R4 — SOUL.md comment spam | Mitigated by "state transitions only" framing + operator audit follow-up (§6) |
| R5 — comment author drift for archived sessions | Acceptable; legacy author values fall to the system color in `AGENT_COLORS` |
| R6 — WS `timeline` payload growth | Bounded `_WS_TIMELINE_LIMIT=100`; ~20 KB / push worst case |
| R7 — tab-switch scroll reset | Accepted; F4 per-tab scroll memory logged for post-v6 |
| R8 — operator unaware of gateway restart | Surfaced in §6 below |

---

## 6. Operator TODOs (sudo + push — agent-blocked in this env)

Three steps remain. The dashboard chat tab + timeline endpoint won't be
visible to a browser until step 1; the new SOUL.md guidance won't reach
any worker until step 3; the commits won't reach the remote until
step 4.

```bash
# 1. Restart the dashboard service (loads the new /timeline route + WS payload
#    + serves the rebuilt static export from Phase 2)
sudo systemctl restart dev-booth-dashboard
curl -s http://localhost:7000/api/health
curl -s http://localhost:7000/api/kanban/boards/firebase-001/timeline | jq '.entries | length'
# expect: ≥ 7  (P0.4 counted 7 real comments on firebase-001 today)
```

```bash
# 2. (Optional) hard-refresh the open browser tab so the new frontend bundle loads
#    Chrome / Firefox: Cmd-Shift-R / Ctrl-Shift-R
```

```bash
# 3. Restart the gateway so new workers read the updated SOUL.md
sudo systemctl restart hermes-gateway        # if hermes-gateway.service is installed
# OR, if v4 OT1 install is still pending:
pkill -f "hermes gateway run" && /dev-booth/run.sh gateway   # B1 fallback
# Verify the new section reached a profile:
HERMES_PROFILE=conductor hermes -z "팀 공지 규칙을 한 줄로 인용해줘" --yolo | head
```

```bash
# 4. Push (still pre-push-hook + classifier blocked for the agent)
DEV_BOOTH_DRYRUN=0 git -C /dev-booth push origin feat/kanban-redesign-2026-05-14
```

> **Note on "PM2 restart"** in the task description: there is no PM2 in
> this deployment (`which pm2` returns empty). The dashboard runs as the
> systemd service `dev-booth-dashboard.service`. The command in step 1
> is the correct equivalent.

### Optional post-session audit

After the first session runs with the v6 build, audit the comment
frequency (plan R4 follow-up):

```bash
sqlite3 ~/.hermes/kanban/boards/<v6-session-slug>/kanban.db \
  "SELECT t.title, COUNT(c.id) FROM tasks t LEFT JOIN task_comments c ON c.task_id=t.id GROUP BY t.id ORDER BY 2 DESC;"
```

If any task has > 5 comments, the SOUL.md guidance is too loose; tighten
to "at most N kanban_comment per task" in a v6.1 follow-up.

---

## 7. ADR (carried from plan §11)

- **Decision.** Add a `/timeline` REST + WS field + a default chat tab;
  fix the scroll bug with `min-h-0` + collapse per-column Kanban
  scrollers; teach agents (via SOUL.md) to narrate state transitions.
- **Drivers.** Operator visibility (Driver 1); two scroll bugs sharing
  one CSS root cause (Driver 2); no v5 regression (Driver 3).
- **Alternatives considered + rejected.** CLI fanout (A1) — perf
  hazard. Split components per tab (B2) — code cost, no UX gain. Drop v1
  JSONL fallback — backward-compat hazard.
- **Why chosen.** SQLite-direct join matches the project's
  "CLI preferred, SQLite RO fallback" pattern (cf. `get_board_stats`).
  Tabs match Discord/Slack mental model.
- **Consequences.** One new endpoint + one new WS field + one new chat
  tab + one CSS-cascade fix + an SOUL.md addition. Agents become
  light chatter (dialable via SOUL.md re-edit).
- **Follow-ups (post-v6).**
  - F1: mention-highlighting (`@architect:` → underline + filter).
  - F2: per-status column collapse if > 30 cards.
  - F3: Playwright e2e for scroll/tab smoke.
  - F4: per-tab scroll memory.
  - F5: address v5-leftover double-WS connection in KanbanBoard.

---

## 8. Quick visual smoke checklist (operator, post-restart)

1. Open https://dashboard.excusa.uk / pick `firebase-001`.
2. The chat panel defaults to the **팀 타임라인** tab — expect ≥ 7 entries
   from the existing comment history.
3. Click any task in the right kanban panel → tab swap is *not*
   automatic; click "태스크 로그" header to switch.
4. The chat panel itself shows a scrollbar when content exceeds height;
   `<body>` overflow remains hidden.
5. The kanban panel shows one scrollbar on the right aside; individual
   status columns do NOT scroll internally.

If any of (4) or (5) fails, the `min-h-0` cascade is missing on a panel
— check `SessionDetailClient.tsx` and add `min-h-0` to that panel's
flex/grid container.
