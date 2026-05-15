# Dev-Booth Dashboard UX — Chat Visibility + Team Timeline (v6 plan)

> **Status:** `pending approval` — produced by `/ralplan` (consensus planning).
> Execution paths after approval: `team` (parallel, recommended — Phase 1 backend / Phase 2 frontend / Phase 3 SOUL are independent) or `ralph` (sequential).
> Do **not** start code changes until the operator authorizes execution.

**Date:** 2026-05-15
**Author:** /ralplan (Planner → Architect → Critic synthesis)
**Builds on:** v5 stabilization
(`reports/results/2026_05_15_05-43-21_devbooth_stabilization_v5.md`,
commits `08dd7a7` → `abdb1ba`).
**Base branch:** `feat/kanban-redesign-2026-05-14` (`main` untouched; OQ-1 default).
**Scope label:** UX/observability — adds a new endpoint + WS field + a chat
tab, fixes two flex-scroll bugs, and asks agents to narrate themselves more.
No DAG, no profile-config, no scenario changes.

---

## 0. RALPLAN-DR Summary

### Principles (decision frame)

1. **Operator visibility is a product feature.** Two agents passing
   metadata via `kanban_complete` is correct execution but is invisible to
   the operator. The dashboard's job is to surface the team's *conversation*,
   not just its task states.
2. **One scroll container per panel.** Nested `overflow-y-auto` per Kanban
   column is the bug, not the fix; collapse to a single scroll on each panel.
3. **Backend keeps doing the projection.** v5 set the rule: agent identity,
   timestamps, log-entry shape are server-side. v6 follows it for the new
   timeline endpoint — frontend receives ready-to-render `LogEntry[]`.
4. **Additive only.** New endpoint, new WS field, new tab. v5's
   `kanban_update` payload schema stays backward-compatible; the new
   `timeline` field is optional and unknown to existing consumers it's a
   no-op for them.
5. **No agent behavior changes via code.** SOUL.md is the only knob; the
   dispatcher and `core/scenario.py` body templates are untouched.

### Decision drivers (top 3)

1. **Team conversation must be visible at a glance.** The default chat tab
   is the operator's debugging surface today — it's empty because
   `kanban_comment()` flows nowhere. Until this is wired, the v5 dashboard
   chat shows only one task's transcript, not the team handoff signal.
2. **Scroll must work on every panel without page-level overflow.** Two
   separate bugs: ChatStream not scrolling, KanbanBoard's per-column cap
   not triggering. Both are flex-min-height issues — same root cause.
3. **No regression on v5.** 135 pytest pass + 0 tsc errors is the bar.
   The new WS field must be opt-in for legacy clients.

### Viable options

#### A. Backend timeline query path

| Option | Mechanism | Pros | Cons | Verdict |
|---|---|---|---|---|
| **A1. CLI fanout (user-supplied skeleton)** | `for task in tasks: get_comments(task.id)` — N subprocesses per call | Reuses `get_comments`; no schema knowledge | N=tasks subprocesses on every WS-mtime tick (~every 2 s when active); slow when N>10 | **Reject** — performance hazard |
| **A2. Direct SQLite join (RO)** | One `SELECT … FROM task_comments JOIN tasks USING (task_id)` against `kanban.db?mode=ro` | One subprocess-free DB read; reuses the kanban_reader's existing RO connect helper; consistent with the SQLite fallback path on stats/comments | Requires the `task_comments` schema (already used by `_sqlite_comments`); locked to v0.13.0's table layout | **Adopt** — same pattern as `get_board_stats` |
| **A3. Hermes CLI `--all` flag** | If a CLI flag exposed all comments at once | Cleanest | Not available on v0.13.0 (verified by `hermes kanban --help` in v5 P0.4) | Reject (not present) |

**Decision: A2.** Aligns with the project's "CLI preferred, SQLite RO fallback" pattern — `get_board_stats` already does SQLite-direct because the CLI subcommand lacks `--json`. Same justification here.

#### B. Frontend tab implementation

| Option | Mechanism | Pros | Cons | Verdict |
|---|---|---|---|---|
| **B1. Tabs in `ChatStream`** (user skeleton) | One component, one virtualizer, switch entry source on tab change | Shared search bar; single ref; smallest diff | Prop sprawl (5 → 6+ props); virtualizer scroll position resets on tab change | **Adopt with refinement** |
| **B2. Split into `TimelineStream` + `LogStream`** | Two stateless components consumed by `ChatStream` shell | Cleaner per-tab logic; each can have its own auto-scroll memory | More files; duplicated virtualizer | Reject (more code for marginal gain) |
| **B3. Side-by-side panes** | Render both timeline + log in the chat column | No tab switching | Halves vertical space; team timeline becomes cramped | Reject |

**Decision: B1, refined** — keep one virtualizer; pass `activeEntries = activeTab === "timeline" ? timeline : entries` directly to the existing scroll container. Don't extract `VirtualLogList` (it adds churn for zero benefit when the only thing changing is the entries array).

#### C. Flex-scroll fix scope

| Option | Mechanism | Verdict |
|---|---|---|
| **C1. Add `min-h-0` defensively to flex/grid containers along the chat + kanban paths** | One-line tailwind change per container | **Adopt** — universal flex-scroll fix; matches React/Tailwind convention |
| **C2. Switch to JS-measured fixed heights** | `useResizeObserver` to compute pixel heights | Reject — over-engineered; CSS handles it |

**Decision: C1.** Add `min-h-0` (`min-height: 0`) to the grid container, the section wrapping ChatStream, and the aside flex-col, AND remove the per-column `max-h-[calc(100vh-220px)]` from `KanbanBoard.Column` (the parent's own `overflow-y-auto` is the scroll).

### Invalidations (why not the others)

- **A1 (CLI fanout)** would let us reuse `get_comments`, but at the cost of
  spawning N subprocesses per WS tick. On firebase-001 (31 tasks today)
  that's ~31 `hermes kanban` invocations every ~2 seconds when any task
  updates — completely unacceptable.
- **B2 / B3** are pure code cost for no UX gain.
- **C2** is JS-Measured layout instead of CSS — a smell in a Tailwind/Next.js
  codebase that already uses pure-CSS scroll containers everywhere else.

---

## 1. Background — Current State (post-v5)

### What's broken (operator-reported)

| # | Symptom | Root cause | Confirmed where |
|---|---|---|---|
| 1 | ChatStream doesn't scroll | The chain `main(flex h-screen) → div(grid flex-1 overflow-hidden) → section(overflow-hidden) → ChatStream(flex h-full flex-col) → div(flex-1 overflow-y-auto)` is missing `min-h-0` on the flex/grid ancestors. Without it, child flex items refuse to shrink below their intrinsic content height, so `flex-1 overflow-y-auto` never gets a bounded height and instead pushes the parent to grow. | `SessionDetailClient.tsx:184-190` |
| 2 | KanbanBoard's right panel doesn't scroll | Same root cause + `Column.tsx:155` puts `overflow-y-auto max-h-[calc(100vh-220px)]` on *each* per-status column instead of the outer panel. With 5+ statuses each capped at the viewport-height-minus-220, the layout has up to 5 nested scrollers, and the panel itself grows beyond its `aside`'s available height because the `aside.flex-col` flex line has no `min-h-0`. | `KanbanBoard.tsx:155`, `SessionDetailClient.tsx:191-198` |
| 3 | Chat shows only the selected task's "monologue" | By design in v5 — `SessionDetailClient.tsx:78-80` feeds `ChatStream.entries` from `logsByTask[selectedTaskId]`. There's no team-level surface. | `SessionDetailClient.tsx:78-80` |
| 4 | No team conversation surface | The backend exposes `/tasks/<id>/comments` (per-task) but no aggregate-across-board endpoint. WS payload carries `comments` for the whole board (≤150 entries) but `useKanban` stores them into a `comments` state that nothing consumes. | `routers/kanban.py:45-50`, `useKanban.ts:155` (consumed nowhere downstream) |

### What's already in place (we build on, not duplicate)

- `kanban_reader.get_comments(task_id)` (SQLite RO path) — works.
- WS `kanban_update` payload already carries `tasks`, `comments` (≤150),
  `logs` (≤5 × ≤50).
- `useKanban.ts` already merges WS pushes into per-task `logsByTask`.
- `ChatMessage.tsx` already renders `LogEntry` (agent avatar, body markdown,
  relative timestamp). It does NOT currently style `kind: "comment"` —
  v6 adds that.

### What we will **not** touch

- Profile configs (`max_turns`, `context_length`, model).
- `core/scenario.py` body templates / `STAGE_DAG`.
- The Kanban WS poll cadence (2 s mtime tick).
- `dashboard/backend/main.py` (no router or middleware change).
- `KanbanBoard.tsx`'s second `useKanban(boardSlug)` call (architect's v5
  optimality note — the double-WS connection refactor is out of v6 scope,
  logged as F-future).

---

## 2. Root-Cause Analysis (verifying the user's diagnosis)

### Problem 1 + 2 (scroll fail) — one root cause

The fix isn't "add overflow-y-auto somewhere"; it's the **flex-min-height
gotcha**: flex/grid children default to `min-height: auto` (i.e.
`min-content`), which means a child with `flex-1 overflow-y-auto` *cannot
shrink below its intrinsic min-content height*. Result: instead of the
child scrolling, the parent gets pushed taller than the viewport. Tailwind
encodes the fix as `min-h-0` (`min-height: 0`).

The chain that needs `min-h-0`:

```
<main className="flex h-screen flex-col">                              ← OK (h-screen hard cap)
  <AppHeader />
  <div ...status bar...> </div>
  <div className="grid flex-1 overflow-hidden lg:grid-cols-...">       ← (a) NEEDS min-h-0
    <aside className="hidden ... lg:block"> ... </aside>
    <section className="overflow-hidden">                              ← (b) NEEDS min-h-0
      <ChatStream> {/* flex h-full flex-col */} </ChatStream>
    </section>
    <aside className="hidden ... lg:flex lg:flex-col">                 ← (c) NEEDS min-h-0
      <div className="flex-1 overflow-y-auto border-b">                ← OK once parent (c) is min-h-0
        <KanbanBoard />
      </div>
      <div className="shrink-0"> <MonitoringPane /> </div>
    </aside>
  </div>
</main>
```

Inside `KanbanBoard.tsx:155`, drop the per-column `overflow-y-auto
max-h-[calc(100vh-220px)]` — the outer aside's
`flex-1 overflow-y-auto` is the only scroll. The board renders a single
long stack; one scrollbar.

### Problem 3 + 4 (team surface) — one missing endpoint

`kanban_comment()` calls land in `task_comments` table. The board-wide
view requires aggregating across tasks. Today:
- REST: `GET /api/kanban/boards/<slug>/tasks/<id>/comments` (per task)
- WS: `comments` payload carries up to 150 across the whole board
  *(useKanban stores it, nothing consumes it)*

Two ways to surface the team timeline:

1. **Use the WS `comments` already there** — wire `useKanban.comments`
   into the new tab via a server-side projection step in `_collect_comments`
   (already projects across tasks).
2. **Add a `/timeline` REST + WS `timeline` field with the server-side
   projection** — more explicit, ready-to-render LogEntry shape.

Both work. v6 picks #2 because:
- The `comments` field today is the *raw* SQL row shape (`{id, task_id,
  author, body, created_at}`) — not LogEntry. Wiring it directly into
  ChatStream needs a client-side projection step anyway.
- The new tab also benefits from `task_title` (so each comment can show
  "from task: [stage 3] code structure analysis") — that join is best
  done server-side once, not client-side per render.

---

## 3. Phase 0 — Pre-flight Probes (record `/tmp/v6-phase0.md`)

| ID | Probe | Why it gates |
|---|---|---|
| P0.1 | `npx tsc --noEmit` on a clean checkout | Locks the 0-error bar for v6 |
| P0.2 | `pytest tests/ dashboard/backend/tests/ -q` baseline | Locks ≥ 135 passing for v6 |
| P0.3 | Inspect `task_comments` schema: `sqlite3 ~/.hermes/kanban/boards/firebase-001/kanban.db ".schema task_comments"` | Confirms the columns the SQLite-direct join will use |
| P0.4 | Count `task_comments` on firebase-001: `SELECT COUNT(*) FROM task_comments` | Establishes whether agents are emitting any comments today (we suspect ~0) |
| P0.5 | `curl http://localhost:7000/api/kanban/boards/firebase-001/tasks` 200 + non-empty | Backend service up |
| P0.6 | DevTools manual visual: reproduce both scroll bugs on the live dashboard (firebase-001 session detail) | Reproduces the bug we're fixing — bar for "fixed" is screenshot diff |
| P0.7 | Inspect `dashboard/backend/main.py` to confirm CORS / static-export config is untouched | Defense against accidental route layering |

**Phase 0 exit:** all probes recorded; if P0.3 reveals an unexpected
schema, the SQLite-direct query for Phase 1 is adjusted before code lands.

---

## 4. Phase 1 — Backend (kanban_reader + router + WS)

### 4.1 `services/kanban_reader.py` — new method

```python
def get_all_comments(self, limit: int = 200) -> list[dict[str, Any]]:
    """Aggregate every comment on the board, newest-last, joined with
    task title + assignee. Returns ready-to-project rows. SQLite-direct
    (single query) so a WS-driven refresh stays cheap regardless of how
    many tasks the board has — see plan §0 Option A2."""
    if not self.exists:
        return []
    with self._connect() as c:
        rows = c.execute(
            """
            SELECT c.id, c.task_id, c.author, c.body, c.created_at,
                   t.title AS task_title, t.assignee AS task_assignee
              FROM task_comments AS c
              LEFT JOIN tasks AS t ON t.id = c.task_id
             ORDER BY c.created_at ASC
            """
        ).fetchall()
    return [dict(r) for r in rows[-limit:]]
```

- **Why `LEFT JOIN`** not `INNER`: if a comment exists for a task that
  was archived/deleted, we still surface the comment with `task_title =
  None`. Robust to edge data.
- **Why SQLite-direct, not CLI fanout**: see decision A2.
- The `_TASK_FIELDS` tuple does NOT change — that's the projection for
  task rows, not comment rows.

### 4.2 `routers/kanban.py` — new endpoint + WS field

```python
# new endpoint
@router.get("/boards/{board_slug}/timeline")
def get_timeline(board_slug: str, limit: int = 200) -> dict:
    reader = KanbanReader(board_slug)
    if not reader.exists:
        raise HTTPException(status_code=404, detail=f"board {board_slug!r} not found")
    return {"entries": [
        _comment_to_log_entry(row) for row in reader.get_all_comments(limit=limit)
    ]}

# server-side projection — LogEntry shape, consistent with /log
def _comment_to_log_entry(row: dict) -> dict:
    """task_comments row → LogEntry. Agent identity = comment.author
    (which is the worker's profile name at write time — the same scheme
    Kanban uses for kanban_comment()). task_title is a free join from §4.1."""
    cid = row.get("id")
    ts  = row.get("created_at")  # seconds-epoch per Phase-0 v4 evidence
    return {
        "id":          f"comment-{cid}",
        "from":        row.get("author") or "system",
        "to":          "all",
        "kind":        "comment",
        "body":        row.get("body") or "",
        "task_id":     row.get("task_id"),
        "task_title":  row.get("task_title"),
        "createdAt":   _epoch_to_iso(ts),
        "createdAtMs": (ts or 0) * 1000,
    }

def _epoch_to_iso(ts):
    if ts is None: return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
```

And in `kanban_ws()`:

```python
timeline = await asyncio.to_thread(_collect_timeline, reader)
await websocket.send_json({
    "type":     "kanban_update",
    "tasks":    tasks,
    "comments": comments,
    "logs":     logs,
    "timeline": timeline,        # NEW — ready-to-render LogEntry[]
})

def _collect_timeline(reader: KanbanReader, limit: int = 100) -> list[dict]:
    return [_comment_to_log_entry(r) for r in reader.get_all_comments(limit=limit)]
```

- **Bound on WS payload**: 100 entries (vs 200 for REST) — smaller per push
  is fine because we only fire on mtime change; subscribers cumulate
  client-side anyway.
- **Backward compat**: existing v5 frontend (older bundles cached in
  browser tab) just ignores the `timeline` field — no breakage.

### 4.3 Tests (`dashboard/backend/tests/test_kanban_reader.py`)

Three new test rows:

```python
def test_get_all_comments_joins_task_title(boards_root):
    """SQLite-direct: every comment row carries task_title from a LEFT JOIN."""
    rows = KanbanReader("demo-board").get_all_comments()
    assert all("task_title" in r for r in rows)
    assert any(r["task_title"] == "initial scan" for r in rows)
    # ordered by created_at ASC, capped to `limit`
    timestamps = [r["created_at"] for r in rows]
    assert timestamps == sorted(timestamps)

def test_get_all_comments_limit(boards_root):
    rows = KanbanReader("demo-board").get_all_comments(limit=1)
    assert len(rows) == 1

def test_route_timeline_projects_to_log_entry(client):
    r = client.get("/api/kanban/boards/demo-board/timeline").json()
    assert r["entries"][0]["kind"] == "comment"
    assert r["entries"][0]["from"] == "conductor"   # author from fixture
    assert r["entries"][0]["to"] == "all"
    assert "task_title" in r["entries"][0]
    assert "createdAtMs" in r["entries"][0]

def test_route_timeline_unknown_board_404(client):
    assert client.get("/api/kanban/boards/ghost/timeline").status_code == 404
```

The existing fixture (`_make_board`) already seeds 2 comments on `t_02` —
we extend it with one more on `t_01` to exercise the join with multiple
distinct task titles.

---

## 5. Phase 2 — Frontend (types + hook + ChatStream + KanbanBoard + SessionDetailClient)

### 5.1 `types/index.ts` — extend LogEntry

```ts
export interface LogEntry {
  id?: string | null;
  /** v5 kanban logs: 'tool' | 'text'.
   *  v6 team timeline:  'comment'.
   *  legacy logs may carry other strings — kind is permissive. */
  kind?: "tool" | "text" | "comment" | string | null;
  from?: string | null;
  to?: string | null;
  body?: string | null;
  /** v6: comment → originating task identity for the tab label / badge */
  task_id?: string | null;
  task_title?: string | null;
  refs?: Record<string, unknown> | null;
  priority?: number | null;
  createdAt?: string | null;
  createdAtMs?: number | null;
}

/** v6: extends KanbanWSUpdate */
export interface KanbanWSUpdate {
  type: "kanban_update";
  tasks?: import("@/hooks/useKanban").KanbanTask[];
  comments?: import("@/hooks/useKanban").KanbanComment[];
  logs?: Record<string, LogEntry[]>;
  timeline?: LogEntry[];      // NEW — server already projects to LogEntry
}
```

- `kind` was already permissive (`| string`) → adding `"comment"` is
  source-compatible.
- New optional `task_id`, `task_title` properties → existing consumers
  ignore.

### 5.2 `useKanban.ts` — surface `timeline`

Diff in `UseKanbanResult`, hook state, REST prefetch, WS handler:

```ts
export interface UseKanbanResult {
  tasks: KanbanTask[];
  comments: KanbanComment[];
  stats: KanbanStats | null;
  /** @deprecated use connectionState */
  connected: boolean;
  connectionState: KanbanConnectionState;
  logsByTask: Record<string, LogEntry[]>;
  timeline: LogEntry[];         // NEW
}

// inside the hook
const [timeline, setTimeline] = useState<LogEntry[]>([]);

// REST prefetch — add a 4th fetch (no need to gate on selectedTaskId)
apiFetch<{ entries: LogEntry[] }>(
  `/api/kanban/boards/${encodeURIComponent(boardSlug)}/timeline`,
).then((r) => !cancelled && setTimeline(r.entries))
 .catch((err) => console.warn("[useKanban] timeline prefetch failed:", err));

// WS handler — adjacent to logs handling
if (msg.timeline) setTimeline(msg.timeline);  // server already projects

// return
return { tasks, comments, stats, connected: …, connectionState, logsByTask, timeline };
```

- **No client-side projection.** Server returns LogEntry shape; client
  just `setTimeline(msg.timeline)`. Aligns with v5's
  "backend projects, frontend renders" rule (Principle 3).
- WS snapshot overwrites (consistent with `logs` handling pattern).

### 5.3 `ChatStream.tsx` — add tabs (refined B1)

Change the prop signature to accept three named streams + selected-task
context, and add a tab header above the virtualized list:

```ts
export function ChatStream({
  entries,             // task-log entries (existing)
  timeline,            // team timeline entries (v6)
  selectedTaskId,
  selectedTaskTitle,
  searchOpen,
  onCloseSearch,
}: {
  entries: LogEntry[];
  timeline: LogEntry[];
  selectedTaskId?: string;
  selectedTaskTitle?: string;
  searchOpen: boolean;
  onCloseSearch: () => void;
}) {
  const [activeTab, setActiveTab] = useState<"timeline" | "log">("timeline");
  const activeEntries = activeTab === "timeline" ? timeline : entries;
  // … existing virtualizer/state logic against activeEntries …
```

- **Tab header**: 2 buttons (`팀 타임라인` / `태스크 로그`) with border-b
  highlight; `cn()` helper from `lib/utils`; brand color for active state.
- **Empty states**: when timeline tab + zero entries → instructional
  message; when log tab + no `selectedTaskId` → "오른쪽 칸반에서 태스크
  클릭" message.
- **Default tab**: `timeline` (per user spec). If `selectedTaskId`
  changes from null → string, do *not* auto-switch tab; the operator
  explicitly clicked, but switching away from the team view would feel
  surprising. (Document this in MANUAL.)
- **Virtualizer**: same instance for both tabs — when `activeEntries`
  array changes (tab switch), `useVirtualizer` recomputes from index 0.
  Scroll position resets to 0; the existing `stickToBottom` effect then
  kicks the new tab to the bottom on next render. **Acceptable.**
- **Search bar**: stays at the top of the stream regardless of tab —
  searches whichever tab is active.

#### Architect tension: tab vs. unified stream

A reviewer might argue: "Don't add a tab; merge timeline + log into one
sorted-by-time stream." Rejected because:
- Mixing kind=tool/text (per-turn worker activity) with kind=comment
  (team handoff signal) destroys signal-to-noise. The log is a verbose
  worker monologue (50+ lines per turn); the timeline is the
  digest. Merging them buries the digest.
- Operators have explicitly asked for the digest as a first-class view.

### 5.4 `ChatMessage.tsx` — render `kind: "comment"`

Tiny additive change:

```tsx
const isComment = entry.kind === "comment";
// container className gains conditional bg
className={cn(
  "flex items-start gap-3 px-4 py-2.5",
  isComment && "bg-muted/30",   // gentle backdrop for team signals
)}
// after the author row, when isComment AND entry.task_title is set
{isComment && entry.task_title && (
  <span className="ml-2 rounded bg-card border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">
    {entry.task_title}
  </span>
)}
```

No mention-highlighting (`@architect`) in v6 — the markdown renderer
already keeps them readable. Future enhancement (logged as F1).

### 5.5 `KanbanBoard.tsx` — single-scroller refactor

```diff
- function Column({ status, tasks, ... }) {
-   ...
-   <div className="overflow-y-auto max-h-[calc(100vh-220px)] space-y-2 pr-0.5 scrollbar-thin ...">
+ function Column({ status, tasks, ... }) {
+   ...
+   <div className="space-y-2 pr-0.5">
      {tasks.map((task) => (...))}
    </div>
  }
```

Outer `<KanbanBoard>` already renders `<div className="flex flex-col
gap-4 p-4">`; the *parent* aside in `SessionDetailClient` provides the
single `overflow-y-auto`. One scrollbar, not five.

### 5.6 `SessionDetailClient.tsx` — flex-min-height fix + new props

Three small surgical changes:

```diff
- <div className="grid flex-1 overflow-hidden lg:grid-cols-[280px_1fr_320px]">
+ <div className="grid flex-1 min-h-0 overflow-hidden lg:grid-cols-[280px_1fr_320px]">

- <section className="overflow-hidden">
+ <section className="overflow-hidden min-h-0">

- <aside className="hidden border-l border-border bg-card lg:flex lg:flex-col">
+ <aside className="hidden border-l border-border bg-card lg:flex lg:flex-col min-h-0">

- const { tasks, logsByTask } = useKanban(boardSlug, selectedTaskId ?? undefined);
+ const { tasks, logsByTask, timeline } = useKanban(boardSlug, selectedTaskId ?? undefined);

  // resolve selectedTaskTitle for the tab label
+ const selectedTaskTitle = selectedTaskId
+   ? tasks.find((t) => t.id === selectedTaskId)?.title
+   : undefined;

- <ChatStream entries={chatEntries} searchOpen={searchOpen} onCloseSearch={...} />
+ <ChatStream
+   entries={selectedTaskId ? (logsByTask[selectedTaskId] ?? []) : []}
+   timeline={timeline}
+   selectedTaskId={selectedTaskId ?? undefined}
+   selectedTaskTitle={selectedTaskTitle}
+   searchOpen={searchOpen}
+   onCloseSearch={() => setSearchOpen(false)}
+ />
```

Removed the v5 `chatEntries` derived const (timeline tab is the default
for empty selection, log tab is the explicit choice; the v1
`messages.jsonl` fallback path moves into the *log tab's empty state*
or is dropped — see below).

#### v1 fallback decision

v5 kept `jsonlEntries` as fallback for pre-Kanban sessions. v6 has three
options:

| Option | Pros | Cons |
|---|---|---|
| **Drop entirely** | Smallest diff; v1 sessions don't exist in production | Breaks any archived session viewer |
| **Keep, render in log tab when timeline + logsByTask both empty** | Backward compat | Confusing: jsonl appears under "태스크 로그" without a task selected |
| **Keep, render in a third tab "JSONL (legacy)"** | Explicit; discoverable | Three tabs for an edge case |

**Choose: keep, render in log tab when no task selected AND timeline is
empty.** Same v5 behavior, just with the tab switch wrapper. Document
the decision tree in MANUAL.

---

## 6. Phase 3 — SOUL.md — Team Narration

For each of `~/.hermes/profiles/{conductor,architect,executor}/SOUL.md`
*and* `core/souls/<p>.SOUL.md` (single source of truth), insert a new
section **right after** the v5 `## ⚠️ 최우선 규칙` block and **before**
the role-specific prose:

```markdown
## 팀 공지 규칙 (대시보드 가시성)

팀이 무엇을 하고 있는지 운영자가 한눈에 보려면, **상태 전환 순간**에만
`kanban_comment()` 로 한 줄 공지를 남깁니다 (일상 작업 단위마다 X — noise 방지).

- 작업 시작:  `kanban_comment("▶ <태스크명> 시작")`
- 작업 완료:  `kanban_comment("✅ <태스크명> 완료 → 다음: <단계명>")`
- 막힘:       `kanban_comment("⚠️ <태스크명> 차단됨 — <한 줄 이유>")`
- 질문:       `kanban_comment("@<상대 프로필>: <한 줄 질문>")`

이 한 줄들이 대시보드 "팀 타임라인" 탭에 시간순으로 떠서, 운영자가
세 에이전트가 어떻게 협업하고 있는지 본다는 점 — 한 줄로 충분합니다.
```

**Conductor SOUL.md only** gets one extra bullet at the end of the same
section:

```markdown
- 단계 전환: `kanban_comment("📋 단계 <N> [<단계명>] 시작 — 담당: <에이전트명>")`
```

#### Architect/Critic note: comment frequency

The user-supplied skeleton phrased this as "use on start/complete/block."
The plan tightens it to **state transitions only** (noise prevention):

- Without this constraint: every turn of a 15-turn task could call
  `kanban_comment()` → 45 comments per task × 12 tasks = 540 comments per
  session. WS payload + ChatStream rendering both pay the cost.
- With the constraint: 2–4 comments per task → 24–48 per session.
  Manageable.

**Operator follow-up:** after one E2E session on the v6 build, count
comments per task. If average > 5, the SOUL.md guidance is too loose;
tighten or move the rule from "suggestion" to "limit: ≤ N
kanban_comment per task."

#### Activation requires gateway restart

SOUL.md changes don't apply until the gateway restarts (the worker reads
SOUL at spawn). v6 must surface this to the operator (see TODO §10.3).

---

## 7. Tests / Verification

### 7.1 Backend regression

```bash
cd /dev-booth && env/bin/python3.11 -m pytest tests/ dashboard/backend/tests/ -q
# Bar: ≥ 139 passing (v5 baseline 135 + 4 new timeline tests)
```

### 7.2 Frontend regression

```bash
cd /dev-booth/dashboard/frontend
npx tsc --noEmit                            # 0 errors
npm run build                               # success
```

### 7.3 Live API smoke

```bash
curl -s http://localhost:7000/api/health
curl -s http://localhost:7000/api/kanban/boards/firebase-001/timeline | python3 -m json.tool | head -30
# expect {entries:[{id:"comment-…", kind:"comment", from:"…", task_title:"…"}, …]}
```

### 7.4 Manual visual smoke (the scroll fix bar)

| Bug | Test | Bar |
|---|---|---|
| ChatStream doesn't scroll | Open firebase-001 session detail; chat panel filled with 50+ entries; ensure the chat panel itself shows a scrollbar and the page (`<body>`) has no overflow. | ✅ if chat scrolls in-place; page body doesn't grow |
| Kanban panel doesn't scroll | Same page; right panel has many tasks; ensure the right aside shows a single scrollbar and individual columns do not nest scrollers. | ✅ if one scrollbar on aside; column inner has no `overflow-y-auto`-driven internal scroll |
| Tabs work | Click "팀 타임라인" / "태스크 로그" headers; verify content swaps; verify clicking a task auto-selects + populates the log tab. | ✅ if tab switching + selection both work |

Smoke is manual (no Playwright/Cypress in this repo today — adding it is
F3, out of v6 scope).

### 7.5 End-to-end agent narration

After the gateway is restarted (operator TODO §10.3), seed a small test
board and verify that after stage 1 completes, the timeline contains at
least one `kanban_comment` from `conductor`:

```bash
DEV_BOOTH_DRYRUN=1 ./run.sh start v6-smoke https://github.com/mooner92/firebase-chat-exp "smoke"
# wait ~5 min for stage 1 to complete
curl -s http://localhost:7000/api/kanban/boards/v6-smoke/timeline | jq '.entries[].body' | head
# expect at least one "✅" or "▶" line
```

If zero comments emerge: the SOUL.md guidance is too soft or the model
doesn't honor it. Tighten to "MUST emit at minimum one comment per
task" (architect's fallback recommendation).

---

## 8. Risk Matrix

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | `min-h-0` cascade breaks an unrelated panel (FileTreePane, MonitoringPane) | Low | Med | Add `min-h-0` only to the 3 specific containers in §5.6; manual smoke verifies file tree + monitoring scroll unchanged |
| R2 | Per-column scrollers removed → very-long-running boards (50+ tasks in one status) make the aside scroll huge | Low | Low | Aside already has `overflow-y-auto`; one big scroll is correct UX (Discord/Slack do the same). If a status has > 50 cards, consider collapsing — F2 |
| R3 | `get_all_comments` SQLite query slow if `task_comments` grows large | Low (current count ~0; will grow) | Low | `LIMIT` clause caps; add an index hint comment in code: `CREATE INDEX IF NOT EXISTS idx_task_comments_created_at ON task_comments(created_at)` is a future optimization but not in v6 (we don't own the schema) |
| R4 | SOUL.md guidance causes comment spam (one per turn) | Med | Med | Frame the rule as "state transitions only"; operator follow-up after first session |
| R5 | Comment author string drift: kanban_comment uses profile name (conductor/architect/executor) but the *current_agent* in the dashboard could be a legacy openclaw/hermes-a/hermes-b in archived sessions | Low | Low | The frontend's AGENT_COLORS/AGENT_LABELS table (v5 rename) handles only the new names; for legacy author values, the system color fallback applies — acceptable for archived sessions |
| R6 | WS `timeline` payload growth (≤ 100 entries × ~200 bytes/each ≈ 20 KB per push) | Med | Low | Cap is configurable; if push size ever becomes a metric concern, reduce to 50 |
| R7 | Tab switching loses scroll position (virtualizer reset) | Med | Low | Acceptable; not a blocker. F4 (per-tab scroll memory) is post-v6 |
| R8 | Operator unaware that SOUL.md changes need gateway restart | Med | Med | Add to MANUAL §6 (operator TODO §10.3 below makes it explicit) |

---

## 9. Test Plan (per phase)

### Phase 0 (probes)
- [ ] `/tmp/v6-phase0.md` exists with 7 entries.
- [ ] `task_comments` schema captured (P0.3).
- [ ] firebase-001 comment count captured (P0.4).
- [ ] Both scroll bugs reproduced on the live dashboard (P0.6).

### Phase 1 (backend)
- [ ] `kanban_reader.get_all_comments` exists, SQLite-direct (one query).
- [ ] `_comment_to_log_entry` is a pure projection — no I/O.
- [ ] `GET /api/kanban/boards/<slug>/timeline` returns 200 with `entries:[…]` on
  existing board, 404 on missing.
- [ ] WS `kanban_update` payload contains `timeline: LogEntry[]` (≤ 100).
- [ ] 4 new tests pass; total ≥ 139 passing.

### Phase 2 (frontend)
- [ ] `types/index.ts` adds `"comment"` to `LogEntry.kind` union;
  `task_id`/`task_title` optional fields present.
- [ ] `useKanban` returns `timeline: LogEntry[]`; WS handler sets it
  from `msg.timeline` directly (no client projection).
- [ ] `ChatStream` accepts `entries` + `timeline` + `selectedTaskId` +
  `selectedTaskTitle` props; tab header renders; `activeEntries`
  switches.
- [ ] `ChatMessage` styles `kind: "comment"` distinctively (muted
  background + optional task_title badge).
- [ ] `KanbanBoard.Column` no longer carries
  `overflow-y-auto max-h-[…]`.
- [ ] `SessionDetailClient` adds `min-h-0` to 3 containers; passes new
  props to `ChatStream`.
- [ ] `npx tsc --noEmit` → 0 errors. `npm run build` → success.

### Phase 3 (SOUL.md)
- [ ] All 3 `core/souls/<p>.SOUL.md` carry the new `## 팀 공지 규칙` section
  between the ⚠️ block and the role prose.
- [ ] All 3 `~/.hermes/profiles/<p>/SOUL.md` mirrors updated (single source of truth maintained).
- [ ] `head -30` confirms the section is present.

### Phase 4 (close-out)
- [ ] Per-phase commits: `phase1`, `phase2`, `phase3`, `docs`.
- [ ] Results report at
  `reports/results/YYYY_MM_DD_HH-MM-SS_devbooth_dashboard_ux.md`.
- [ ] Operator block surfaced (dashboard restart, gateway restart for
  SOUL.md activation).
- [ ] Manual visual smoke per §7.4 passes (operator confirms).

---

## 10. Operator TODOs (sudo / gateway / verification — not agent-runnable)

### 10.1. Restart the dashboard (sudo)

After Phase 2 builds, the live uvicorn must reload the new
`/timeline` route and serve the rebuilt static export:

```bash
sudo systemctl restart dev-booth-dashboard
curl -s http://localhost:7000/api/health
curl -s http://localhost:7000/api/kanban/boards/firebase-001/timeline | jq '.entries | length'
```

### 10.2. Push (still pre-push-hook-blocked in agent env)

Same as v5 — the pre-push dryrun hook rejects agent pushes.

```bash
DEV_BOOTH_DRYRUN=0 git -C /dev-booth push origin feat/kanban-redesign-2026-05-14
```

### 10.3. Restart the gateway to activate the new SOUL.md (sudo)

```bash
sudo systemctl restart hermes-gateway
# verify
hermes gateway status
# spawn a one-shot probe to confirm SOUL.md is picked up
HERMES_PROFILE=conductor hermes -z "팀 공지 규칙을 한 줄로 인용해줘" --yolo | head
```

If the gateway is NOT yet a systemd service (v4 OT1 is still open), use
the v4 fallback: `pkill -f "hermes gateway run" && ./run.sh gateway`.

### 10.4. (Optional) After first session, audit comment frequency

```bash
sqlite3 ~/.hermes/kanban/boards/<v6-session>/kanban.db \
  "SELECT t.title, COUNT(c.id) FROM tasks t LEFT JOIN task_comments c ON c.task_id=t.id GROUP BY t.id ORDER BY 2 DESC;"
```

If any task has > 5 comments, tighten SOUL.md (R4 follow-up).

---

## 11. ADR — Architecture Decision Record

- **Decision.** Add a dedicated team-timeline endpoint + WS field +
  default chat tab; fix the flex-scroll bug with `min-h-0` + collapse
  per-column Kanban scrollers; instruct agents (via SOUL.md) to emit a
  short comment on state transitions only.
- **Drivers.** Operator visibility on team handoffs (Driver 1); two
  separate scroll bugs sharing one CSS root cause (Driver 2); no
  regression on v5's 135-test bar (Driver 3).
- **Alternatives considered.**
  - CLI fanout for the timeline query (A1) — rejected, perf hazard.
  - Split ChatStream into separate components per tab (B2) — rejected,
    code cost without UX gain.
  - Drop v1 JSONL fallback — rejected (kept under "no task + empty
    timeline" empty state for compat).
- **Why chosen.** SQLite-direct join is the cheapest path that matches
  the project's existing read pattern. Tab UI matches Discord/Slack
  channel-vs-thread mental model — familiar without explanation.
- **Consequences.**
  - One new endpoint, one new WS field, one new chat tab, one CSS
    cascade fix.
  - Agents become chatter — measured impact, dialable via SOUL.md
    re-edit if too noisy.
  - SOUL.md changes require gateway restart (sudo).
- **Follow-ups (post-v6).**
  - F1: mention-highlighting (`@architect:` → underline + link to
    profile filter).
  - F2: per-status column collapse if > 30 cards.
  - F3: Playwright e2e for the scroll/tab smoke (test infra gap).
  - F4: per-tab scroll memory (virtualizer state preservation).
  - F5: address the v5-leftover double-WS connection in KanbanBoard
    (architect optimality note carried forward).

---

## 12. Open Questions for the Operator

| OQ | Question | Default |
|---|---|---|
| OQ-1 | Should the timeline tab default to selecting the most-recent task's log when the operator clicks a task? Or stay on timeline until the operator explicitly switches? | Stay on timeline; operator switches manually (less surprising) |
| OQ-2 | What's an acceptable comment-per-task cap before we re-tighten SOUL.md? | 5 |
| OQ-3 | Do we keep the v1 `messages.jsonl` fallback path, or drop it entirely? | Keep (under "no task selected" empty state of the log tab) |
| OQ-4 | Should comment timestamps render in absolute (`HH:MM`) or relative (`5분 전`) form? | Relative (matches v5 ChatMessage default) |

---

## 13. Files Touched (planning estimate)

| File | Change | Risk |
|---|---|---|
| `dashboard/backend/services/kanban_reader.py` | + `get_all_comments` | Low |
| `dashboard/backend/routers/kanban.py` | + `/timeline` route, `_comment_to_log_entry`, `_epoch_to_iso`, WS payload + `_collect_timeline` | Low |
| `dashboard/backend/tests/test_kanban_reader.py` | + 4 tests, extended fixture (1 extra comment row on `t_01`) | Low |
| `dashboard/frontend/types/index.ts` | extend `LogEntry.kind` union + 2 optional fields; `KanbanWSUpdate` adds `timeline?` | Low |
| `dashboard/frontend/hooks/useKanban.ts` | + `timeline` state, REST prefetch, WS handler, return shape | Low |
| `dashboard/frontend/components/ChatStream.tsx` | + tab header, `activeEntries`, empty states, prop shape change | Med |
| `dashboard/frontend/components/ChatMessage.tsx` | + `kind: "comment"` styling + task_title badge | Low |
| `dashboard/frontend/components/KanbanBoard.tsx` | remove per-column `overflow-y-auto max-h-[…]` from `Column` | Low |
| `dashboard/frontend/components/SessionDetailClient.tsx` | + `min-h-0` on 3 containers; + `selectedTaskTitle` resolution; pass new props to ChatStream | Med |
| `core/souls/conductor.SOUL.md` | + `## 팀 공지 규칙` section (with stage transition bullet) | Low |
| `core/souls/architect.SOUL.md` | + `## 팀 공지 규칙` section | Low |
| `core/souls/executor.SOUL.md` | + `## 팀 공지 규칙` section | Low |
| `~/.hermes/profiles/{conductor,architect,executor}/SOUL.md` | mirror of the 3 above (live profiles) | Low |
| `reports/plans/2026_05_15_06-44-20_devbooth_dashboard_ux.md` | this file | n/a |
| `reports/results/<date>_devbooth_dashboard_ux.md` | end-of-exec | n/a |

**Commit policy** (feature-unit, mirrors v5 / user-stated preference):

| Phase | Commit |
|---|---|
| Phase 0 probes | (fold into Phase 1 — probes are transient `/tmp` notes here) |
| Phase 1 backend | `phase1(ux): add /timeline endpoint + WS payload + tests` |
| Phase 2 frontend | `phase2(ux): tabbed ChatStream + min-h-0 cascade + single-scroller Kanban` |
| Phase 3 SOUL.md | `phase3(ux): teach agents the 팀 공지 규칙 (state-transition comments only)` |
| Phase 4 docs | `docs: dashboard UX v6 plan + results` |

---

## 14. How to Execute This Plan After Approval

This plan is `pending approval`. Recommended path:

- **`Skill("oh-my-claudecode:team")`** — Phases 1 (backend), 2 (frontend),
  and 3 (SOUL.md) have near-zero file overlap. Three sub-agents run in
  parallel, the team controller merges.
- **`Skill("oh-my-claudecode:ralph")`** — sequential alternative if you
  prefer story-by-story verification.

The two non-blocking architect follow-ups carried forward from v5
(double-WS in `KanbanBoard`, missing `workspace_hint` ctx key) remain
out of scope.

---

*End of v6 dashboard UX plan.*
