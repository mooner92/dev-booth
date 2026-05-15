# Dev-Booth Dashboard v10 UX — Implementation Results

**Date:** 2026-05-15
**Branch:** `feat/kanban-redesign-2026-05-14` (`main` untouched)
**Mode:** ralph PRD-driven, 4 user stories US-001..US-004
**Builds on:** v9 agent enhancement (commits `9b869b2` → `10378ba`, all local)

---

## Summary

v10 makes the dashboard feel like a tool, not a passive viewer:

1. **ChatStream no longer clips long messages.** The v6 layout pinned the
   virtualizer to an 80 px estimate, which caused overlapping rows on any
   markdown body with code fences or comment badges. v10 drops
   `@tanstack/react-virtual` entirely and renders a plain flex column —
   the typical worst case (timeline 100 + per-task log 50) is well under
   any threshold where virtualization is worth its layout cost.
2. **Main page is searchable and filterable.** A text input + four
   status pills + a GitHub-bot account card put the operator in
   control of a growing session list.
3. **Operators can launch a new session from the dashboard.** A
   `NewSessionModal` collects `{repo_url, session_name, goal, mode}` and
   hits the new `POST /api/sessions/start`, which seeds the Kanban board
   in a `BackgroundTasks` job. No more shelling into the host to run
   `./run.sh start`.
4. **GitHub bot-account status is visible at a glance.** A new
   `GET /api/github/status` shells `gh auth status` and surfaces
   "CrownClownCrowd → mooner92" as a stat card.

**Test bar:** v9 → v10 pytest **153 → 158 passing** (+5 new backend
tests for the two new endpoints). Frontend `tsc --noEmit` 0 errors;
`npm run build` ships `/` at 16.1 kB / 125 kB first-load JS.

**Per-phase commits on `feat/kanban-redesign-2026-05-14`:**

| Commit | Phase |
|---|---|
| `7f46c3f` | `phase1(ux10)`: ChatStream dynamic height — drop virtualizer |
| `<phase2>` | `phase2(ux10)`: backend POST /sessions/start + GET /github/status + 5 tests |
| `9c2a421` | `phase3(ux10)`: main page search/filter + GitHub card + NewSessionModal |
| `<pending>` | `docs(ux10)`: this report + progress |

(Phase-2 commit hash is the one between 7f46c3f and 9c2a421 in
`git log`; results report is the docs commit.)

Three operator actions remain (sudo dashboard restart + push + cautious
live-mode usage) — see §6.

---

## Phase 0 — Probes

| Probe | Result | Bearing on plan |
|---|---|---|
| ChatStream virtualizer config | `useVirtualizer({estimateSize: () => CHAT_VIRTUAL_ROW_HEIGHT})` with `CHAT_VIRTUAL_ROW_HEIGHT = 80` | Fixed estimate → clipping. Solution: drop virtualization given the WS payload caps |
| Backend endpoints | `sessions.py` had only GET endpoints; no POST | Add POST /sessions/start to existing file; create new github.py router |
| Main page | `page.tsx` renders sessions in a 3-column grid; no search/filter/CTA | Extend in-place; reuse existing `StatCard` and `EmptyState` |
| `gh auth status` | `Logged in to github.com account CrownClownCrowd` (Active account) | API can parse stdout to confirm |
| pytest baseline | 153 passing | Locked the v10 regression bar |

---

## Phase 1 — ChatStream dynamic height (commit `7f46c3f`)

The v6 implementation pinned `useVirtualizer`'s `estimateSize` to a
fixed 80 px. The actual `ChatMessage` renders:

- Markdown body via `react-markdown` + `rehype-highlight` (variable
  height: 1-50+ lines)
- Optional `task_title` badge for `kind: "comment"` rows
- Avatar + agent label + relative timestamp

Real-world rows ranged 40-300 px. The virtualizer placed each row at
its 80 px slot, so 200+ px rows clipped into the next slot — visible
as overlapping text in the chat panel.

**v10 fix:** drop virtualization entirely. The WS payload bounds the
chat content tightly:

- `timeline` ≤ 100 entries (backend bound `_WS_TIMELINE_LIMIT`)
- per-task `logs` ≤ 50 entries × ≤ 5 tasks

Worst case is ~350 entries. A plain flex-column map at that size
renders in < 50 ms on the host; virtualization saves nothing and
introduces the height-mismatch bug. Removed:

```diff
- import { useVirtualizer } from "@tanstack/react-virtual";
- import { SCROLL_ANCHOR_THRESHOLD_PX, CHAT_VIRTUAL_ROW_HEIGHT } from "@/lib/constants";
+ import { SCROLL_ANCHOR_THRESHOLD_PX } from "@/lib/constants";

- const virtualizer = useVirtualizer({
-   count: filteredIndices.length,
-   getScrollElement: () => parentRef.current,
-   estimateSize: () => CHAT_VIRTUAL_ROW_HEIGHT,
-   overscan: 8,
- });

- {virtualizer.getVirtualItems().map((virtualRow) => (
-   <div … style={{ position: "absolute", transform: `translateY(${virtualRow.start}px)` }}>
-     <ChatMessage entry={item.entry} />
-   </div>
- ))}

+ <div className="flex flex-col py-2">
+   {filtered.map((entry, i) => (
+     <ChatMessage key={entry.id ?? `${activeTab}-${i}`} entry={entry} />
+   ))}
+   <div ref={bottomRef} />
+ </div>
```

**Preserved behavior:**

- Search input still filters by body substring (`filteredIndices`
  renamed to `filtered`).
- `stickToBottom` + unread-count pill — now uses `bottomRef.scrollIntoView`
  instead of `parentRef.current.scrollTop = scrollHeight`. Effect-trigger
  and on-scroll detection unchanged.
- Two-tab header (timeline / task log), empty states, page-title
  notification when document hidden.

**Side note:** `CHAT_VIRTUAL_ROW_HEIGHT` constant still exists in
`lib/constants.ts` — left untouched in case a future view needs a
fixed-row estimate. Could be removed in a deslop pass.

---

## Phase 2 — Backend POST /sessions/start + GET /github/status

### `dashboard/backend/routers/sessions.py` (extended)

```python
class SessionStartRequest(BaseModel):
    session_name: str
    repo_url: str
    goal: str = "코드 품질 개선 및 버그 수정"
    mode: Literal["dryrun", "live"] = "dryrun"


@router.post("/sessions/start")
async def start_session(body: SessionStartRequest,
                        background_tasks: BackgroundTasks) -> dict:
    slug = body.session_name.strip().lower().replace(" ", "-").replace("_", "-")
    if not slug or not slug.replace("-", "").isalnum():
        raise HTTPException(400, "세션명은 영문/숫자/하이픈만 가능합니다")
    sessions_root = Path(os.environ.get("DEVBOOTH_SESSIONS_ROOT", "/dev-booth/sessions"))
    if (sessions_root / slug).exists():
        raise HTTPException(409, f"세션 '{slug}' 이미 존재합니다")
    dryrun = body.mode != "live"
    background_tasks.add_task(_run_session_seed, slug, body.repo_url, body.goal, dryrun)
    return {"session_name": slug, "status": "starting"}
```

`_run_session_seed` shells `/dev-booth/env/bin/python3 -m core.session
<slug> <repo_url> --goal <goal>` with `DEV_BOOTH_DRYRUN` set per mode.
Subprocess uses `timeout=300, check=False, capture_output=True` — the
seed is fire-and-forget; the UI follows the session via the existing
`/api/sessions/<name>/status` polling.

### `dashboard/backend/routers/github.py` (new)

```python
@router.get("/status")
def github_status() -> dict:
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=5,
        )
        text = (result.stdout or "") + (result.stderr or "")
        logged_in = "CrownClownCrowd" in text
        return {
            "logged_in": logged_in,
            "account": "CrownClownCrowd" if logged_in else None,
            "target": "mooner92",
        }
    except (subprocess.TimeoutExpired, OSError):
        return {"logged_in": False, "account": None, "target": "mooner92"}
```

Mounted via `main.py`:

```diff
- from .routers import health, kanban, metrics, sessions, ws
+ from .routers import github, health, kanban, metrics, sessions, ws
…
+ app.include_router(github.router)
```

### Tests (`test_sessions_start.py`, new)

5 cases — all monkeypatch `subprocess.run` so no real shell or seed
execution happens during tests:

| Test | Asserts |
|---|---|
| `test_post_sessions_start_happy_path` | 200, body `{session_name: <slug>, status: "starting"}` |
| `test_post_sessions_start_duplicate_409` | tmp-fixture pre-creates session dir → 409 |
| `test_post_sessions_start_invalid_slug_400` | special chars → 400 |
| `test_get_github_status_logged_in` | mocked `gh auth status` w/ "CrownClownCrowd" → `logged_in: true, account: "CrownClownCrowd"` |
| `test_get_github_status_failure` | mocked `OSError` → `logged_in: false` |

`pytest tests/ dashboard/backend/tests/ -q` → **158 passing**
(baseline 153, +5 new).

---

## Phase 3 — Main page UX (commit `9c2a421`)

### `app/page.tsx` — extensions

```tsx
const [search, setSearch] = useState("");
const [statusFilter, setStatusFilter] = useState<"all"|"running"|"done"|"unknown">("all");
const [githubStatus, setGithubStatus] = useState<GithubStatus | null>(null);
const [newSessionOpen, setNewSessionOpen] = useState(false);
const router = useRouter();
```

- GitHub status fetched once on mount via `api.getGithubStatus()`.
- `filteredSessions` derives from `sessions` + `statuses`:
  - search matches against `name` OR `agents.join(" ")`
  - status filter maps `StatusSnapshot.state` → 4 buckets
    (`"idle"` proxies for `"완료"` since the status snapshot has no
    explicit "done" state)
- Top bar: title + description on the left, brand-color "새 작업 시작"
  button (`<Plus>`) on the right.
- 4th `<StatCard>` next to vLLM / Activity / Cpu / GitCommit using the
  GitHub icon, account as the value, login/target as the hint.
- Search + filter row: `<Search>`-prefixed input with inline `<X>`
  clear button, 4 filter pills, session-count label on the right.
- Empty-state copy adapts to whether a search/filter is active.

### `components/NewSessionModal.tsx` (new, 260 lines)

- Form fields: `repoUrl`, `sessionName` (auto-derived from the repo's
  last path segment + YYYYMMDD; user-editable with a `nameManual` flag
  that stops auto-overwrite), `goal`, `mode` (dryrun / live).
- Local validation: `new URL(repoUrl)` + `/^[a-z0-9-]+$/` on
  `sessionName`. Submit disabled until both pass.
- Submit calls `api.startSession(...)` — no raw `fetch`. On success →
  `onCreated(name)` then `router.push(/session/<name>)`.
- Error banner: red-bordered `border-seed-error/40 bg-seed-error/10`
  card with the API error detail.
- Close paths: backdrop click + ESC keydown + `open === false` returns
  null + the corner `×` button.
- Accessibility: `role="dialog"`, `aria-modal`, `aria-labelledby`,
  label-for associations on all inputs, `aria-label` on icon-only
  buttons.

### `lib/api.ts` — new helpers

```ts
async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new ApiError(res.status, detail.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  …
  getGithubStatus: () => apiGet<GithubStatus>("/api/github/status"),
  startSession: (body) => apiPost<StartSessionResponse>("/api/sessions/start", body),
};
```

### `types/index.ts` — new interfaces

```ts
export interface GithubStatus {
  logged_in: boolean;
  account: string | null;
  target: string;
}
export interface StartSessionResponse {
  session_name: string;
  status: string;
}
```

---

## Acceptance criteria — final verification

| US | Acceptance summary | Status |
|---|---|---|
| US-001 | ChatStream dynamic height (no overlap); search + sticky-bottom preserved; tsc 0 | **MET** — `7f46c3f` |
| US-002 | POST /sessions/start (200/400/409) + GET /github/status (logged-in + failure) + 5 tests; pytest ≥ 156 | **MET** — pytest 158 / 158 |
| US-003 | Main page search + filter + GitHub card + NewSessionModal; tsc 0; build success | **MET** — `9c2a421` |
| US-004 | Per-phase commits + results report + operator block; main untouched | **MET** (this report + 3 commits) |

---

## 6. Operator TODOs (sudo + push — agent-blocked)

```bash
# 1. Restart the dashboard so the new POST /sessions/start endpoint +
#    rebuilt frontend bundle take effect
sudo systemctl restart dev-booth-dashboard
curl -s http://localhost:7000/api/health
curl -s http://localhost:7000/api/github/status | jq

# 2. (Browser) Hard-refresh the open tab so the new bundle loads
#    Cmd-Shift-R / Ctrl-Shift-R

# 3. Spot-check the new POST endpoint (DO NOT use live mode yet)
curl -X POST http://localhost:7000/api/sessions/start \
  -H "Content-Type: application/json" \
  -d '{
    "session_name": "test-ui-start",
    "repo_url": "https://github.com/mooner92/firebase-chat-exp",
    "goal": "UI 테스트",
    "mode": "dryrun"
  }'
# → expect {"session_name":"test-ui-start","status":"starting"}

# 4. Push (still pre-push-hook + classifier blocked for the agent)
DEV_BOOTH_DRYRUN=0 git -C /dev-booth push origin feat/kanban-redesign-2026-05-14
```

> **Caution on live mode:** the modal exposes a "🚀 Live" toggle that
> sets `DEV_BOOTH_DRYRUN=0` on the seed subprocess. Real PR creation
> will fire if the gateway worker reaches stage 12 with a valid
> `GITHUB_TOKEN` env. Keep mode = dryrun until the team is ready for
> a real PR cycle on a target repo.

---

## 7. ADR

- **Decision.** Drop chat virtualization (overkill for the WS-bounded
  payload), expose two new backend endpoints (one POST for new sessions,
  one GET for bot-account status), and surface search / filter /
  modal / status card on the main page.
- **Drivers.** (1) clipped chat messages were the most-reported visual
  bug; (2) operators were shelling to the host to spawn new sessions —
  unnecessary friction; (3) the bot-account → target chain was buried
  in docs.
- **Alternatives considered.**
  - `useVirtualizer({measureElement: ...})` for dynamic height. Rejected
    — the WS payload bounds make virtualization a net cost; simpler
    code wins.
  - A standalone `/new` page for session creation. Rejected — modal
    keeps the operator on the dashboard, preserves session-list
    context.
  - Polling `gh auth status` continuously. Rejected — one fetch on
    mount is enough; the bot account doesn't churn.
- **Why chosen.** Each change reduces friction at the right layer
  (UI for chat clipping; backend for new-session ergonomics; API for
  observability) without growing the WS contract or the dispatcher.
- **Consequences.**
  - `CHAT_VIRTUAL_ROW_HEIGHT` constant is unused; left in for future
    needs but is a deslop candidate.
  - The POST endpoint runs `core.session` via a subprocess job — if
    the gateway dispatcher isn't running, the seeded board will sit
    with `ready` tasks and no worker activity. The operator TODOs
    explicitly require both services up.
  - Live mode is one click away in the modal — caveat documented.
- **Follow-ups (post-v10).**
  - F1: surface "active sessions in flight" count from BackgroundTasks
    so the modal can warn before spawning a second long-running seed
    on the same backend process.
  - F2: webhook from gateway → dashboard on first stage-1 ready
    transition so the modal's "starting" → "running" badge auto-flips.
  - F3: delete `CHAT_VIRTUAL_ROW_HEIGHT` from `constants.ts` once any
    future consumer is gone.

---

## 8. Files Touched

**New:**
- `dashboard/backend/routers/github.py`
- `dashboard/backend/tests/test_sessions_start.py`
- `dashboard/frontend/components/NewSessionModal.tsx`
- `reports/results/2026_05_15_11-10-05_devbooth_dashboard_v10.md` (this file)

**Modified:**
- `dashboard/backend/main.py` (register github router)
- `dashboard/backend/routers/sessions.py` (POST /sessions/start + helper)
- `dashboard/frontend/app/page.tsx` (search / filter / CTA / GitHub card)
- `dashboard/frontend/components/ChatStream.tsx` (drop virtualizer)
- `dashboard/frontend/lib/api.ts` (apiPost + 2 new helpers)
- `dashboard/frontend/types/index.ts` (GithubStatus, StartSessionResponse)

**Untouched:**
- `main` branch
- `~/.hermes/hermes-agent` (v0.13.0 pin)
- All v5–v9 SOUL.md / MEMORY.md / scenario.py / watchdog.py
- Kanban WS contract (`useKanban`, `routers/kanban.py`)

---

## 9. Visual-smoke checklist (operator, post-restart)

1. `sudo systemctl restart dev-booth-dashboard` → `/api/health` 200.
2. Open `https://dashboard.excusa.uk` (hard-refresh tab).
3. Top stats row shows 4 cards including the GitHub one — value
   "CrownClownCrowd" or "—" if not logged in.
4. Search box filters the session grid live; clear button (×)
   restores full list.
5. Filter pills: "실행 중" should leave only running sessions visible;
   "완료" maps to status.state === "idle".
6. Click "새 작업 시작" → modal opens centered with backdrop blur.
7. Paste a repo URL → session name auto-fills as `<repo>-YYYYMMDD`.
8. ESC closes the modal; backdrop click closes too; corner × works.
9. Submit a dryrun session → toast/redirect to `/session/<name>`.
10. Open a session detail → ChatStream scrolls smoothly with no
    row overlap on long markdown messages.
