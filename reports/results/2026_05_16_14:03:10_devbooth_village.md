# Dev-Booth Village — Pixel Office Agent Visualization (Ralph)

- Date: 2026-05-16 14:03:10 KST
- Branch: `feat/kanban-redesign-2026-05-14`
- Driver: `/oh-my-claudecode:ralph` (PRD-gated, single iteration)
- Session ID: `db06adb5-e50b-4d84-8f8e-f4f2170dda27`

## Goal

Add a new page `/village` to the existing dashboard that visualises the three
agents (conductor / architect / executor) as pixel-office characters whose
position and speech bubble reflect live Hermes Kanban state. The existing
dashboard at `dbdb.excusa.uk` stays untouched apart from a small "🏢 Village"
header link.

## Phase summary

| Phase     | Deliverable | Files | Verification |
|-----------|-------------|-------|--------------|
| Backend   | `village_status` service projecting Kanban → Village shape | `services/village_status.py` | unit tests + live curl |
| Backend   | REST + WS router under `/api/village` | `routers/village.py`, `main.py` | router introspection, live curl |
| Tests     | 9 new tests covering shape, mapping, and HTTP surface | `tests/test_village.py` | `pytest` 86/86 pass (77 baseline + 9 new) |
| Frontend  | Canvas pixel-office page with WS-driven updates | `app/village/page.tsx` | `tsc --noEmit` 0 errors, `next build` ✓ |
| Frontend  | Header "🏢 Village" link (additive) | `components/AppHeader.tsx` | static export ✓ |
| Build     | Static export emits `/out/village/index.html` | — | `out/village/index.html` exists, 3.23 kB page chunk |
| Smoke     | Live API on a temp port serves real boards | — | `/api/village/boards` → 4 boards, firebase-003 state OK |

## API shape

### `GET /api/village/boards`

```json
{ "boards": ["e2e-kanban-001", "firebase-001", "firebase-003", "globalteamproject-20260515"] }
```

### `GET /api/village/boards/{slug}/state`

```json
{
  "board":    "firebase-003",
  "progress": 32,
  "done":     7,
  "total":    22,
  "agents": {
    "conductor": { "state": "error", "task": "create feature branch",  "task_status": "blocked", "area": "breakroom", "emoji": "⚠️", "x": 400, "y": 150, "label": "Conductor" },
    "architect": { "state": "error", "task": "Security Enhancements",  "task_status": "blocked", "area": "breakroom", "emoji": "⚠️", "x": 200, "y": 300, "label": "Architect" },
    "executor":  { "state": "error", "task": "Performance Optimization","task_status": "blocked", "area": "breakroom", "emoji": "⚠️", "x": 600, "y": 300, "label": "Executor" }
  }
}
```

- Missing board → same shape with `total=0`, `progress=0`, all agents idle.
  Intentionally **HTTP 200**, not 404 — the page renders a quiet office instead
  of toasting an error.

### `WS /api/village/ws/{slug}`

Pushes `{ "type": "village_update", ...state }` whenever `~/.hermes/kanban/boards/<slug>/kanban.db` mtime changes (2 s poll).

## Kanban → Village mapping

| Kanban status | Village state | Office area |
|---------------|---------------|-------------|
| `running`     | `executing`   | desk        |
| `blocked`     | `error`       | breakroom   |
| `ready`       | `syncing`     | hallway     |
| `done`        | `idle`        | breakroom   |
| `todo`        | `idle`        | breakroom   |
| `triage`      | `idle`        | breakroom   |
| `archived`    | `idle`        | breakroom   |

Per-agent task picker preference: **running > blocked > most-recent done**.
`ready` is queued work — the picker leaves the agent idle to keep the page
honest about what's actually happening *now*. Slug prefix `[xxx] ` in titles is
stripped before display.

## File list

```
M dashboard/backend/main.py                         (router registration)
A dashboard/backend/routers/village.py              (38 LoC)
A dashboard/backend/services/village_status.py      (~140 LoC)
A dashboard/backend/tests/test_village.py           (9 tests)
A dashboard/frontend/app/village/page.tsx           (~330 LoC, client component)
M dashboard/frontend/components/AppHeader.tsx       (+5 LoC: Village link)
A .omc/state/sessions/db06adb5.../prd.json          (Ralph PRD)
A reports/results/2026_05_16_14:03:10_devbooth_village.md
```

## Evidence

- **Backend tests:** `env/bin/pytest dashboard/backend/tests/` → **86 passed in 0.85s** (was 77 before; +9 village tests, 0 regressions).
- **Type check:** `npx tsc --noEmit` → 0 errors.
- **Build:** `npm run build` → ✓; emits `/dev-booth/dashboard/frontend/out/village/index.html` (3.23 kB page, 97.3 kB First Load JS — well under the 250 kB project budget).
- **Live API:** temporary `uvicorn` on `:7099` served real boards including `firebase-003` (22 tasks, 7 done = 32 % progress), and `nonexistent-board` returned HTTP 200 with the empty shape.
- **Router introspection:** `from dashboard.backend.main import app` lists `/api/village/boards`, `/api/village/boards/{board_slug}/state`, `/api/village/ws/{board_slug}`.

## Operator TODO

The dashboard running on `:7000` is still serving the **previous** static build,
so `curl http://localhost:7000/api/village/boards` will 404 until restarted.
Run on the host (requires sudo):

```bash
sudo systemctl restart dev-booth-dashboard
```

After restart, verify:

```bash
curl -s http://localhost:7000/api/village/boards
# expect: {"boards":[...]}
```

…then open `https://dbdb.excusa.uk/village/` and pick a board.

## Constraints respected

- ✓ No edits to existing `/api/kanban`, `/api/sessions`, `/api/github` endpoints
- ✓ No edits to `app/page.tsx` layout, stats grid, or session list
- ✓ Header touched only to add the additive Village link
- ✓ No `main` branch changes (work stays on `feat/kanban-redesign-2026-05-14`)
- ✓ No `~/.hermes/hermes-agent` upstream patches
- ✓ Reuses `KanbanReader` (CLI-first, SQLite fallback) — no parallel DB layer
- ✓ Static export compatible — `output: "export"` build succeeds with `/out/village/index.html`
