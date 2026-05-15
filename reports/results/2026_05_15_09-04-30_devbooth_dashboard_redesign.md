# Dev-Booth Dashboard Redesign v8 — Implementation Results

**Date:** 2026-05-15
**Branch:** `feat/kanban-redesign-2026-05-14` (`main` untouched)
**Mode:** ralph PRD-driven, 3 user stories US-001..US-003
**Builds on:** v7 skill activation (commits `c72c27b` → `91ed31e`, all local).

---

## Summary

v8 reorients the Dev-Booth session detail page around the **Kanban board
as the primary navigation surface**. The v6/v7 layout buried the kanban
in a narrow right-side panel beneath GPU charts; v8 makes it a
240 px-wide left sidebar — a flat chronological task list with status
glyphs, a click-to-pin-log interaction, and a compact GPU summary
pinned at the bottom. The right pane becomes a focused chat workspace
with a thin progress bar at the top.

Two parallel sub-agents implemented the change in 30 minutes — a
**designer** (Sonnet) for the layout / KanbanBoard / SessionDetailClient
rewrite, and an **executor** (Sonnet) for the ChatMessage body-processing
pass. No file overlap, no merge friction.

**Test bar:** v7 pytest 153 unchanged (no backend touched). Frontend
`tsc --noEmit` → **0 errors**. `npm run build` → **success** (5 pages
prerendered, /session/[name] route 114 KB, 87.3 KB shared bundle).

**Per-phase commits on `feat/kanban-redesign-2026-05-14`:**

| Commit | Phase |
|---|---|
| `c31974a` | `phase1+2(redesign)`: kanban-first 2-column layout |
| `0ae45d1` | `phase4(redesign)`: ChatMessage body processing |
| `<pending>` | `docs(redesign)`: this report + progress |

Two operator actions remain (sudo dashboard restart + push) — see §6.

---

## Layout before → after

### Before (v6/v7) — 3-column

```
┌───────────┬─────────────────────────────┬──────────────┐
│ FileTree  │  Chat (timeline / log tab)  │  Kanban      │
│ 280 px    │  flex-1                     │  + Monitoring│
│           │                             │  320 px      │
└───────────┴─────────────────────────────┴──────────────┘
```

Issues:
- Kanban crammed into 320 px right column, beneath GPU charts.
- File tree consumed 280 px the operator rarely needs.
- Task status spread across 5+ accordion columns — hard to scan.

### After (v8) — 2-column

```
┌──────────────┬──────────────────────────────────────────┐
│  Session     │  현재 단계 · WS 연결됨 · 검색 (⌘F)        │ ← top status row
│  ← 목록      ├──────────────────────────────────────────┤
│  /sessions/x │  67%  ███████████░░░░░░ (progress bar)   │
├──────────────┼──────────────────────────────────────────┤
│  Kanban      │  [팀 타임라인]  [태스크 로그 — TASK-3]    │ ← v6 tabs preserved
│              │                                           │
│ ✓ fork       │  CD Conductor  initial project scan       │
│ ✓ scan       │   Initial scan complete. React/Firebase…  │
│ ●animated    │                                           │
│ ▶ ready      │  AR Architect  code structure             │
│ ⬜ todo      │   Let's move on to reviewing Home.js…     │
│   (sorted    │                                           │
│   by         │  EX Executor   dependency analysis        │
│   created_at)│   The correct clone_path is…             │
│              │                                           │
│ ──────────── │                                           │
│ GPU          │                                           │
│ 사용률 78%   │                                           │
│ 메모리 41 GB │                                           │
│ 온도 78°C    │                                           │
└──────────────┴──────────────────────────────────────────┘
   240 px            flex-1
```

The kanban is **always visible**, the operator scans status at a glance,
clicks any row to pin its log in the chat panel, and watches GPU
pressure without leaving the page.

---

## Phase 0 — Pre-flight probes

- Frontend tsc baseline (post-v7) — 0 errors.
- GPU data source identified: `api.getMetricsPreset(preset)` for
  `gpu_utilization` / `gpu_memory_used` / `gpu_temperature` — the same
  surface MonitoringPane uses on a 5 s tick. Reuse the pattern.
- No `--sidebar` CSS token in tailwind config — use `bg-card` and
  `border-border` from the existing Seed Design system.
- AppHeader is shared across pages — drop the import from this page
  only; the file stays untouched.
- StageBar is used in `SessionCard.tsx` — drop from this page only.
- The "page.tsx" wrapper at `/session/[name]/page.tsx` only renders
  `<SessionDetailClient />` — no further changes needed.

---

## Phase 1+2 — Layout redesign (commit `c31974a`)

### `components/KanbanBoard.tsx` — full rewrite

The old `KanbanBoard` rendered N status-grouped columns
(triage/todo/ready/running/blocked/done/archived), each its own scroll
container with `max-h-[calc(100vh-220px)]`. v6 fixed the nested-scroll
bug by removing those caps; v8 finishes the job by collapsing the whole
thing into **one chronological list** sorted by `created_at`.

**New API contract (same outer signature as v6):**

```tsx
export function KanbanBoard({
  boardSlug,
  selectedTaskId,
  onTaskSelect,
}: {
  boardSlug: string;
  selectedTaskId?: string;
  onTaskSelect?: (id: string) => void;
}) { … }
```

**Internal structure:**

- `<div className="flex h-full min-h-0 flex-col bg-card">`
  - Header (shrink-0): "Kanban" label · WS dot · `완료 N / 전체 M`
  - Body (min-h-0, flex-1, overflow-y-auto): `sorted.map(t => <TaskRow … />)`
  - `<GpuSummary />` footer (shrink-0)

**`StatusIcon`:**

| Status | Glyph |
|---|---|
| `done` | `<span className="text-emerald-500">✓</span>` |
| `running` | animated ping + brand-color dot (Tailwind `animate-ping` + solid base) |
| `blocked` | `<span className="text-amber-500">⊘</span>` |
| `ready` | `<span className="text-blue-500">▶</span>` |
| `todo` / `triage` / `archived` | empty 2 × 2 px square outline |

**`TaskRow`:**

- `<button>` (full-width left-aligned).
- 2px StatusIcon column, 1-line title (truncated, `title=task.title`
  tooltip), 1.5 × 1.5 px agent-color dot right-aligned.
- Done titles: `line-through text-muted-foreground`.
- Running: `font-medium text-foreground`.
- Blocked: `text-amber-600 dark:text-amber-400`.
- Selected (`task.id === selectedTaskId`): `bg-muted` + `border-l-2 border-brand`.
- Hover: `bg-muted`.

**`trimTaskTitle()` helper** — exported so `SessionDetailClient` can
reuse it for the top-bar `currentStageName`:

```ts
function trimTaskTitle(title: string): string {
  return title.replace(/^\[[^\]]+\]\s*/, "");
}
```

`[firebase-chat-exp] fork & clone` → `fork & clone`.

**`GpuSummary` footer:**

```tsx
const [util, mem, temp] = await Promise.all([
  api.getMetricsPreset("gpu_utilization"),
  api.getMetricsPreset("gpu_memory_used"),
  api.getMetricsPreset("gpu_temperature"),
].map(p => p.catch(() => null)));
```

- Polls every 5 s via `useEffect` + `setInterval`.
- Reads the single most-recent point from each preset's series.
- Thresholds: util > 80 % = red, ≤ 80 % = emerald; temp > 80 °C = red,
  ≤ 80 °C = foreground default.
- Hidden when all three return null (Prometheus down) — no stale
  zero-state.

### `components/SessionDetailClient.tsx` — 3-col → 2-col

The diff:

| Removed | Replaced with |
|---|---|
| `<AppHeader />` | (none — top-level header subsumed into in-page bar) |
| Status pill row + `<StageBar>` row | Single 2-row top bar (stage name + WS + search button; progress bar) |
| `<div className="grid lg:grid-cols-[280px_1fr_320px]">` | `<div className="flex h-screen">` + 240 px left aside + flex-1 main |
| Left aside with `FileTreePane` | Left aside with session-header + `KanbanBoard` |
| Right aside with `KanbanBoard` + `MonitoringPane` + scroll wrapper | (right aside removed entirely) |
| `tree` state + `api.getFiles(name)` prefetch | (removed — file tree gone) |

**New derived state** (`useMemo` over `tasks`):

```ts
const progressPercent = useMemo(() => {
  if (tasks.length === 0) return 0;
  const done = tasks.filter(t => t.status === "done").length;
  return Math.round((done / tasks.length) * 100);
}, [tasks]);

const currentStageName = useMemo(() => {
  const running = tasks.find(t => t.status === "running");
  if (running) return trimTaskTitle(running.title);
  const blocked = tasks.find(t => t.status === "blocked");
  if (blocked) return `차단됨: ${trimTaskTitle(blocked.title)}`;
  const ready = tasks.find(t => t.status === "ready");
  if (ready) return `준비: ${trimTaskTitle(ready.title)}`;
  return "대기 중";
}, [tasks]);
```

**`min-h-0` cascade preserved** — three places on the flex-children of
the right `<main>` so the chat scroll container resolves to a bounded
height. (The v6 lesson: flex children default to `min-height: auto` and
need explicit `min-h-0` to shrink below content height.)

**`MonacoModal` kept** but no longer wired to a file tree. Modal can
still be triggered programmatically if a future feature wants to surface
the file viewer from a kanban task. Removing it entirely is a later
cleanup item (logged F1).

---

## Phase 4 — ChatMessage body processing (commit `0ae45d1`)

The v6 chat tab finally pipes Hermes worker logs into ChatStream, but
the raw bodies arrive with two stylistic problems:

1. **Unicode escapes** — `마치 때` instead of `마치 때`.
   The dispatcher JSON-encodes log lines before storing.
2. **Framing tags** — `<tool_response>`, `<output>` XML-style wrappers
   the model emits around tool calls.

**`processBody(raw: string | null | undefined): string`** added at the
top of `ChatMessage.tsx`:

```ts
function processBody(raw) {
  if (!raw) return "";
  let s = raw;
  if (s.includes("\\u")) {
    try {
      const decoded = JSON.parse(`"${s.replace(/"/g, '\\"').replace(/\n/g, "\\n").replace(/\r/g, "\\r").replace(/\t/g, "\\t")}"`);
      if (typeof decoded === "string") s = decoded;
    } catch { /* keep raw */ }
  }
  s = s.replace(/<\/?tool_response>/g, "").replace(/<\/?output>/g, "");
  return s.replace(/^\s+|\s+$/g, "");
}
```

The component now:

```tsx
const isComment = entry.kind === "comment";
const rawBody = entry.body ?? "";
const isToolCall =
  entry.kind === "tool" ||
  rawBody.startsWith("kanban_") ||
  rawBody.includes("preparing ");
const body = processBody(rawBody);

// row backdrop
className={cn(
  "flex items-start gap-3 px-4 py-2.5",
  isComment && "bg-muted/30",
  isToolCall && !isComment && "bg-muted/40",
)}
```

`<ReactMarkdown>` now renders `{body}` (the processed string) instead
of `entry.body`. Markdown rendering still works because `processBody`
returns plain text/markdown — no HTML escaping.

The v6 `task_title` badge path is untouched; the comment styling rule
wins when both `isComment` and `isToolCall` are true (defensive — should
rarely overlap in practice).

---

## Acceptance criteria — final verification

| US | Acceptance summary | Status |
|---|---|---|
| US-001 | KanbanBoard sidebar + GPU summary + SessionDetailClient 2-col + progress bar + FileTreePane removed; tsc+build clean | **MET** — `c31974a`; tsc 0; build 5 pages |
| US-002 | ChatMessage processBody (unicode + tag strip) + tool-call backdrop | **MET** — `0ae45d1`; tsc 0 |
| US-003 | Per-phase commits, results report, operator block | **MET** — this report + 3 commits + §6 |

---

## 6. Operator TODOs (sudo + push — agent-blocked)

```bash
# 1. Rebuild the static export so the dashboard service serves the new bundle
cd /dev-booth/dashboard/frontend && npm run build

# 2. Restart the dashboard service (loads the rebuilt out/ via DASHBOARD_STATIC_DIR)
sudo systemctl restart dev-booth-dashboard
curl -s http://localhost:7000/api/health

# 3. (Optional) Hard-refresh the browser tab so the new bundle loads in any
#    open session view: Cmd-Shift-R / Ctrl-Shift-R.

# 4. Push (still pre-push-hook + classifier blocked for the agent)
DEV_BOOTH_DRYRUN=0 git -C /dev-booth push origin feat/kanban-redesign-2026-05-14
```

> Note on "PM2 restart" in the task description: there is no PM2 in
> this deployment. The dashboard is managed by the systemd service
> `dev-booth-dashboard.service` (FastAPI + Next.js static export).
> Step 2 is the equivalent.

---

## 7. Visual-smoke checklist (operator, post-restart)

1. Open `https://dashboard.excusa.uk` → click any session card.
2. Left sidebar is 240 px, shows session name + back button + path.
3. Kanban list scrolls inside the sidebar (one scrollbar) — task rows
   sorted by created_at, status glyphs visible, running rows show the
   animated ping dot.
4. GPU summary at bottom shows util / mem / temp; numbers update every
   ~5 s.
5. Click any task row → chat panel switches to its log (existing v6
   tab logic; the "태스크 로그" tab activates).
6. Top of right pane shows current stage + progress bar (done/total %).
7. Hot-refresh test: scroll the chat to top, watch a new log line
   arrive — the chat scrolls (the v6 `min-h-0` cascade preserved).
8. Tool-call rows (those starting with `kanban_*`) have a subtle darker
   background than text rows.
9. Comment rows still keep the v6 `task_title` badge and the lighter
   `bg-muted/30` backdrop.
10. Unicode no longer rendered as `\uXXXX` — Korean text reads as
    Korean.

If anything fails: capture the diff with a screenshot and re-open the
v8 PR or escalate to F1 (file-tree restore as collapsible side-tray).

---

## 8. ADR

- **Decision.** Adopt a 2-column kanban-first layout. The sidebar is
  flat-chronological (not status-grouped), the progress bar is
  top-of-pane, GPU summary is sidebar-footer. Drop the file tree
  entirely; keep MonacoModal for future programmatic file open.
- **Drivers.**
  - Operator's primary debugging surface is the kanban + chat —
    everything else was secondary.
  - The v6 layout's nested-column scrolling made the kanban awkward to
    scan.
  - GPU pressure is glance-only data — a 3-row footer beats charts when
    you're focused on agent activity.
- **Alternatives considered.**
  - Keep file tree as a collapsible drawer (option B). Rejected for
    simplicity — file viewing was rare in operator workflows and
    `MonacoModal` is still reachable.
  - Per-status accordion columns inside the sidebar. Rejected — the v6
    multi-column layout was the source of the scroll bug we already
    fixed by flattening.
  - Real GPU charts in the sidebar. Rejected — charts compete with the
    task list for vertical real estate; sparkline-summary is cheap.
- **Why chosen.** Glance-density. The kanban + GPU at left and chat at
  right matches how the operator thinks: "what's the system doing? what
  did each agent say?" One scroll per panel; no nesting.
- **Consequences.**
  - File tree gone — F1 (post-v8) restores it as a slide-over if
    operator feedback requires.
  - MonitoringPane is now unused; the file stays for now (out of v8
    cleanup scope, F2).
  - The right aside that previously hosted KanbanBoard + Monitoring is
    gone — its space goes to the chat.
- **Follow-ups (post-v8).**
  - F1: file-tree slide-over (operator-triggered).
  - F2: remove `MonitoringPane.tsx` + `MiniChart.tsx` if v8 ships
    without rollback for two sessions.
  - F3: per-stage column-collapse if a status group exceeds 30 cards
    (logged from v6).
  - F4: GPU sparkline next to the numbers (compact, no chart pane).

---

## 9. Files Touched (v8)

**Modified (Phase 1+2, commit `c31974a`):**
- `dashboard/frontend/components/KanbanBoard.tsx` — full rewrite (sidebar
  TaskRow + StatusIcon + GpuSummary + `trimTaskTitle` export)
- `dashboard/frontend/components/SessionDetailClient.tsx` — 3→2 col, top
  progress bar, drop FileTreePane / MonitoringPane / AppHeader / StageBar
  from this page

**Modified (Phase 4, commit `0ae45d1`):**
- `dashboard/frontend/components/ChatMessage.tsx` — `processBody`,
  `isToolCall`, tool-call backdrop

**New (this commit):**
- `reports/results/2026_05_15_09-04-30_devbooth_dashboard_redesign.md` (this file)

**Untouched:**
- All backend files
- `useKanban.ts`, `ChatStream.tsx`, `types/index.ts`
- `core/scenario.py`, `core/session.py`, `core/souls/*`,
  `core/watchdog.py`
- `main` branch
- `~/.hermes/hermes-agent` (v0.13.0 pin)

---

## 10. Risk matrix (post-implementation)

| # | Risk | Status |
|---|---|---|
| R1 — sub-`lg` viewport hides the kanban entirely | Acceptable — same behavior as v6 (asides are `hidden lg:flex`); mobile redesign is F5 (post-v8) |
| R2 — Removed FileTreePane breaks deep-link users | Mitigated — no router refs to /session/<n>/files/...; MonacoModal still reachable for future programmatic use |
| R3 — GpuSummary polling adds 3 × api.getMetricsPreset / 5 s = 36 req/min from every open browser tab | Bounded — same pattern as the existing MonitoringPane (the v8 just relocates the data). Net traffic identical |
| R4 — processBody's JSON.parse on a maliciously crafted body throws → caught by try/catch; raw body shown | Acceptable — text fidelity beats crash; the catch keeps the original string |
| R5 — `progressPercent` reads `tasks.length === 0` as 0% but a brand-new board legitimately is "0/0" | Cosmetic — the bar renders empty (width: 0%) until tasks arrive; matches user expectation |
| R6 — `trimTaskTitle` exported from KanbanBoard creates a cross-file dep with SessionDetailClient | Mild — same module is already imported for `<KanbanBoard>`; one extra named import. Could move to `lib/utils.ts` if it grows |
| R7 — The v6 jsonl fallback still uses `chatEntries` in SessionDetailClient | Preserved — verified by the sub-agent; jsonl path stays alive for pre-Kanban sessions |
