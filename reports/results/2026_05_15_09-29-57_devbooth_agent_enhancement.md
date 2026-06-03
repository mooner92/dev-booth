# Dev-Booth Hermes Agent Enhancement v9 — Results

**Date:** 2026-05-15
**Branch:** `feat/kanban-redesign-2026-05-14` (`main` untouched)
**Mode:** ralph PRD-driven, 5 user stories US-001..US-005
**Builds on:** v8 dashboard redesign (commits `c31974a` → `dfbdae8` → `3193161`, all local)

---

## Summary

v9 outfits the three Hermes worker profiles (conductor / architect /
executor) with three operator-side upgrades that all dial up agent
self-sufficiency without changing the Hermes Agent codebase
(v0.13.0 pin per OT5):

1. **RTK terminal-rewrite plugin** — `rtk-rewrite` (rtk-hermes 1.2.3,
   pip-installed) is now correctly enabled in `~/.hermes/config.yaml`
   after deduplicating three colliding `plugins:` blocks left over
   from prior edits. Hermes' entry-point discovery
   (group `hermes_agent.plugins`) confirms the plugin is registered:
   `[('rtk-rewrite', 'rtk_hermes')]`.
2. **MEMORY.md per profile** — each agent now starts every task with
   its role-specific operational memo (server env, paths, Kanban
   rules, context-saving tips). All three files are well under the
   2200-byte Hermes cap (1297 / 1392 / 1472 bytes).
3. **3 custom Dev-Booth skills** — `devbooth-session-start`,
   `devbooth-task-complete`, `devbooth-context-save`. All three appear
   in `hermes skills list` as `local/local/enabled`, and the SOUL.md
   files of every profile now ship a `## Dev-Booth 전용 스킬 (항상 사용)`
   section pointing the agent at them.

**Test bar:** v8 → v9 pytest unchanged at **153 passing**
(no Python code touched — all v9 work is in config files, markdown, and
profile-side `~/.hermes/`).

**Per-phase commits on `feat/kanban-redesign-2026-05-14`:**

| Commit | Phase |
|---|---|
| `<pending>` | `phase2(agent)`: MEMORY.md per profile + repo mirrors |
| `<pending>` | `phase3(agent)`: 3 custom Dev-Booth skills + repo mirrors |
| `<pending>` | `phase4(agent)`: SOUL.md Dev-Booth 전용 스킬 section |
| `<pending>` | `docs(agent)`: v9 results report + progress |

Phase 1 produced no repo-tracked artifact (it edits
`~/.hermes/config.yaml`, which lives outside the repo) — it is
documented here + the pre-edit backup is at
`/tmp/v9-backup/hermes-config.yaml`.

Three operator actions remain (sudo gateway restart + firebase-003
unblock + push) — see §6.

---

## Phase 0 — Probes (`/tmp/phase0-agent-enhancement.md`)

| Probe | Result | Bearing on plan |
|---|---|---|
| P0.1 RTK binary | `/home/mooner92/.local/bin/rtk` 0.40.0 | Available; `rtk init hermes` does NOT exist (flag rejected) |
| P0.2 rtk-hermes pip package | 1.2.3 installed in the Hermes venv | Entry-point distribution exposed at `[hermes_agent.plugins].rtk-rewrite=rtk_hermes` |
| P0.3 config.yaml `plugins:` block | **3 duplicate top-level `plugins:` blocks** at lines 536/540/544 — YAML parser undefined behavior | Dedup is the Phase-1 work |
| P0.4 `hermes plugins list` | Lists only bundled plugins (disk-cleanup / google_meet / spotify / teams_pipeline) — pip-entry-point plugins NOT surfaced | CLI quirk on v0.13.0; pip plugins still load at runtime via `_scan_entry_points` |
| P0.5 `rtk init hermes` | Not supported on RTK 0.40.0 (flag rejected) | Skip plan §1.1; pip path is the right one |
| P0.6 `~/.hermes/plugins/` | Empty (no `<name>/` subdirs) | Pip-installed plugin doesn't materialize there — expected |
| P0.7 MEMORY.md / USER.md | **None of the 3 profiles** had MEMORY.md | Greenfield install |
| P0.8 `~/.hermes/skills/devbooth-*` | None | Greenfield install |
| P0.9 firebase-003 stats | 8 todo / 1 blocked / 3 done / 0 running | Unblock = operator action after gateway restart |
| P0.10 Hermes entry-point loader | Loader code (`hermes_cli/plugins.py:170`) confirms `ENTRY_POINTS_GROUP = "hermes_agent.plugins"` matches what rtk-hermes registers — wiring is correct | Phase 1 is config-only, no plugin install |

---

## Phase 1 — RTK plugin registration (config dedupe)

**Pre-edit state:** `~/.hermes/config.yaml` had three identical
`plugins:` blocks at lines 536, 540, 544:

```yaml
plugins:
  enabled:
    - rtk-rewrite

plugins:
  enabled:
    - rtk-rewrite

plugins:
  enabled:
    - rtk-rewrite
```

YAML duplicate top-level keys are undefined behavior — most parsers
keep only the last block, some raise. Either way, this is a config
smell that suggests prior automated edits appended without
deduplication.

**Fix:** a Python pass through the file removed duplicate 3-line
`plugins: / enabled: / - rtk-rewrite` blocks, keeping the first one
at line 536. Pre-edit backup at `/tmp/v9-backup/hermes-config.yaml`.

```yaml
# post-edit, line 536-538
plugins:
  enabled:
    - rtk-rewrite
```

**Verification:**

```bash
$ grep -nE "^plugins:" ~/.hermes/config.yaml
536:plugins:

$ /home/mooner92/.hermes/hermes-agent/venv/bin/python3 -c "
  import importlib.metadata as md
  print(list(md.entry_points(group='hermes_agent.plugins')))
  "
[EntryPoint(name='rtk-rewrite', value='rtk_hermes', group='hermes_agent.plugins')]

$ hermes plugins list | grep -i rtk
(empty — see Note below)
```

**Note on `hermes plugins list`:** Pip-entry-point plugins are *not*
surfaced in this CLI command on v0.13.0; it lists only `bundled` and
filesystem `~/.hermes/plugins/<name>/` plugins. The agent process still
loads pip plugins at startup via `PluginManager._scan_entry_points()`
when `plugins.enabled` includes the entry-point name — which it now
does. **Operator can confirm activation after gateway restart** by
checking gateway logs for an `rtk-rewrite` loaded line, or by
monitoring whether terminal-tool outputs in `hermes kanban log` look
RTK-compressed.

**Activation = operator action:** `sudo systemctl restart hermes-gateway`
(§6.1 below).

---

## Phase 2 — MEMORY.md per profile (commit `<pending>`)

Three role-specific memos installed at
`~/.hermes/profiles/<role>/MEMORY.md` and mirrored to
`/dev-booth/core/memories/<role>.MEMORY.md` (single source of truth in
the repo).

| Role | Bytes | Cap | Content focus |
|---|---|---|---|
| conductor | **1297** | 2200 | server env (data05lx, vLLM @ 8003), session/clone paths, GitHub Bot conventions, Kanban rules, RTK-context-saving |
| architect | **1392** | 2200 | analysis output path, role split (analysis vs review), `kanban_show` first-step, head-100-first context-saving |
| executor | **1472** | 2200 | implementation TDD, test-result handoff format, npm/pip install-output-tail tip |

Each MEMORY.md is auto-injected at every task spawn (Hermes built-in).
This makes the v5 plan's per-stage body templates lighter: bodies can
assume the agent already knows the server / Kanban basics and focus on
the *task-specific* directives.

---

## Phase 3 — Custom Dev-Booth skills (commit `<pending>`)

Three new skills shipped both to the version-controlled origin at
`/dev-booth/core/skills/<name>/SKILL.md` and the live skill registry
at `~/.hermes/skills/<name>/SKILL.md`.

| Skill | Trigger | Purpose |
|---|---|---|
| `devbooth-session-start` | "작업 시작", "kanban task 시작" | 4-step start procedure: `kanban_show()` parent metadata → 팀 공지 → `$HERMES_KANBAN_WORKSPACE` check → context-saving rules |
| `devbooth-task-complete` | "작업 완료", "kanban_complete", "LGTM" | self-check + `kanban_complete()` metadata templates per task type (analysis / implementation / review) |
| `devbooth-context-save` | "기억해줘", "memory" | MEMORY.md update procedure (≤ 2200-byte cap + signal-vs-noise filter) |

All three carry frontmatter (`name`, `description`, `version`,
`author`, `metadata.hermes.tags`, `related_skills`) matching the
Hermes skill schema. `hermes skills list` post-install:

```
│ devbooth-context-save   │  │ local │ local │ enabled │
│ devbooth-session-start  │  │ local │ local │ enabled │
│ devbooth-task-complete  │  │ local │ local │ enabled │
```

All three flagged `enabled` — Hermes will surface their `description`
in the agent's skill summary so the model can decide to load on demand.

---

## Phase 4 — SOUL.md `Dev-Booth 전용 스킬` section (commit `<pending>`)

Each of the three profiles' SOUL.md gains a new section at the tail:

```markdown
## Dev-Booth 전용 스킬 (항상 사용)

- `devbooth-session-start` — 모든 태스크 시작 시 로드. 워크스페이스 확인 + 부모 metadata + 팀 공지 절차.
- `devbooth-task-complete` — `kanban_complete()` 호출 직전 체크리스트와 태스크 타입별 metadata 형식.
- `devbooth-context-save` — 세션 너머로 가져갈 발견사항을 MEMORY.md 에 저장하는 절차 (2200자 cap).
```

**Existing sections preserved** (verified by grep):

| File | Section order | Final lines |
|---|---|---|
| conductor.SOUL.md | ⚠️ 최우선 (L1) → 팀 공지 규칙 (L21) → 스킬 카탈로그 (L65) → **Dev-Booth 전용 스킬 (L83)** | 95 |
| architect.SOUL.md | ⚠️ 최우선 (L1) → 팀 공지 규칙 (L21) → 스킬 카탈로그 (L57) → **Dev-Booth 전용 스킬 (L70)** | 82 |
| executor.SOUL.md | ⚠️ 최우선 (L1) → 팀 공지 규칙 (L21) → 스킬 카탈로그 (L61) → **Dev-Booth 전용 스킬 (L73)** | 85 |

Live `~/.hermes/profiles/<p>/SOUL.md` mirrors all match.

---

## Phase 5 — firebase-003 (operator action)

The board has 1 blocked task + 8 todo. Per plan §5 this is an operator
action after Phase 1-4 are deployed:

```bash
# Confirm what's blocked
hermes kanban --board firebase-003 list | grep blocked

# Read why
hermes kanban --board firebase-003 log <blocked_task_id> --tail 8192 | tail -20

# Restart gateway so workers reload SOUL.md + load rtk-rewrite + read MEMORY.md
sudo systemctl restart hermes-gateway
sleep 15

# Unblock
hermes kanban --board firebase-003 unblock <blocked_task_id>

# Watch
hermes kanban --board firebase-003 watch
```

If the same task re-blocks with `protocol_violation`, the v5 watchdog
(`core/watchdog.py`) will surface it via cron / manual run — escalate to
F1 (upstream dispatcher patch) if recurrent.

---

## Phase 6 — Verify

| Bar | Result |
|---|---|
| `pytest tests/ dashboard/backend/tests/` | **153 passing** (no regression) |
| `STAGE_DAG` length | 12 (unchanged) |
| `ALLOWED_ASSIGNEES` | `{architect, conductor, executor}` (unchanged) |
| `hermes skills list` shows 3 devbooth-* | YES (all `local/local/enabled`) |
| MEMORY.md byte cap (≤ 2200) | all 3 well under (1297 / 1392 / 1472) |
| `~/.hermes/config.yaml` single `plugins:` block | YES (line 536, was 3) |
| Hermes entry-point discovery for `rtk-rewrite` | YES (Python verified) |
| Frontend `tsc --noEmit` | (not run — no FE change in v9) |

---

## 6. Operator TODOs (sudo + push — agent-blocked)

```bash
# 1. Restart the gateway so workers reload SOUL.md / MEMORY.md / activate rtk-rewrite
sudo systemctl restart hermes-gateway
hermes gateway status

# 2. Confirm rtk-rewrite activation (look for plugin-load line in gateway logs)
sudo journalctl -u hermes-gateway -n 100 | grep -iE "rtk|rewrite|plugin"
# OR: spawn a one-shot probe and watch for compressed terminal output
HERMES_PROFILE=executor hermes -z "git -C /dev-booth status" --yolo 2>&1 | head -30

# 3. Spot-check that workers see the new MEMORY.md and skills
HERMES_PROFILE=conductor hermes -z "당신의 운영 메모를 한 줄로 인용해줘" --yolo | head
HERMES_PROFILE=architect hermes -z "devbooth-session-start 스킬을 한 줄 설명해줘" --yolo | head

# 4. Unblock firebase-003 (after Phase 5 instructions above)
hermes kanban --board firebase-003 list | grep blocked
hermes kanban --board firebase-003 unblock <task_id>

# 5. (Optional) Restart the dashboard service if you want backend churn (none in v9)
#    sudo systemctl restart dev-booth-dashboard

# 6. Push all local commits (still pre-push-hook + classifier blocked for the agent)
DEV_BOOTH_DRYRUN=0 git -C /dev-booth push origin feat/kanban-redesign-2026-05-14
```

> **Note on "PM2 restart"** in the task description: there is no PM2 in
> this deployment. The dashboard runs as the systemd service
> `dev-booth-dashboard.service`; the gateway runs as
> `hermes-gateway.service` (if the v4 OT1 install completed) or as B1
> via `/dev-booth/run.sh gateway`.

---

## 7. ADR

- **Decision.** Three operator-side enhancements that all dial up
  agent self-sufficiency without touching the pinned Hermes Agent
  codebase: RTK plugin (terminal output compression), MEMORY.md
  (per-role operational memos), and 3 custom Dev-Booth skills
  (lifecycle + memory).
- **Drivers.** (1) Cut per-task context usage so the v5 28K envelope
  has more headroom for actual work, (2) stop re-injecting the same
  server/Kanban basics in every task body, (3) give the model a
  semantic name (`devbooth-session-start`) it can load on demand,
  not a wall of inline prose.
- **Alternatives considered.**
  - `hermes-rtkit` (git-clone fallback from the plan's §1.2) —
    rejected after Phase 0 confirmed `rtk-hermes` was already
    pip-installed with the correct entry-point. Dedup was the only
    real fix.
  - SOUL.md inline of all 3 skills' procedures — rejected as too
    expensive on the system prompt budget; the skill mechanism is
    cheaper because it's load-on-demand.
- **Why chosen.** Cheapest path that respects OT5 (no upstream
  changes). The plan §1.2 git-clone fallback was unnecessary once
  Phase 0 showed the existing pip plugin is correctly wired.
- **Consequences.**
  - SOUL.md grows ~14 lines per profile (the new section) — well
    under the system-prompt budget.
  - MEMORY.md re-injects ~1.4 KB per task — the gain is per-task
    body shrinkage (the v5 body templates can rely on the memo).
  - Plugin loading needs a gateway restart — operator action.
- **Follow-ups (post-v9).**
  - F1: dispatcher-level skill injection (upstream Hermes patch
    after the pin is bumped).
  - F2: extend MEMORY.md with session-specific findings via the new
    `devbooth-context-save` skill (operator-driven so far).
  - F3: a unit test that re-validates SKILL_USE_CASES keys against
    `hermes skills list` (catches name drift on Hermes updates).
  - F4: surface "active plugins" in the dashboard top bar.

---

## 8. Files Touched

**New (committed):**
- `core/memories/conductor.MEMORY.md`
- `core/memories/architect.MEMORY.md`
- `core/memories/executor.MEMORY.md`
- `core/skills/devbooth-session-start/SKILL.md`
- `core/skills/devbooth-task-complete/SKILL.md`
- `core/skills/devbooth-context-save/SKILL.md`
- `reports/results/2026_05_15_09-29-57_devbooth_agent_enhancement.md` (this file)

**Modified (committed):**
- `core/souls/conductor.SOUL.md` — appended Dev-Booth 전용 스킬 section
- `core/souls/architect.SOUL.md` — same
- `core/souls/executor.SOUL.md` — same

**Modified (live, outside repo):**
- `~/.hermes/config.yaml` — deduplicated 3 plugins: blocks → 1 (backup at /tmp/v9-backup/)
- `~/.hermes/profiles/<role>/MEMORY.md` — new file (mirror of core/memories)
- `~/.hermes/profiles/<role>/SOUL.md` — appended Dev-Booth 전용 스킬 section
- `~/.hermes/skills/devbooth-*/SKILL.md` — new (mirror of core/skills)

**Untouched:**
- `main` branch
- `~/.hermes/hermes-agent/` (v0.13.0 pin per OT5)
- All Python code (`core/scenario.py`, `core/session.py`, `core/watchdog.py`)
- Dashboard backend + frontend
- Tests

---

## 9. Visual-smoke checklist (operator, post-restart)

1. `sudo systemctl restart hermes-gateway && hermes gateway status` →
   `active (running)`.
2. `sudo journalctl -u hermes-gateway -n 100 | grep -iE "plugin|rtk"` →
   shows a `Loading plugin: rtk-rewrite` or equivalent line.
3. `HERMES_PROFILE=conductor hermes -z "..." --yolo` → the assistant
   references its operational memo content (server, Bot account,
   Kanban rules) without being told.
4. `hermes kanban --board firebase-003 unblock <task_id>` after the
   above — the worker should reach `kanban_complete` within
   `max_turns × ~30s` (≈ 8 min) on its next attempt.
5. Dashboard team-timeline tab (`dashboard.excusa.uk`) should start
   showing more `▶/✅/⚠️` agent comments (v6 팀 공지 규칙 + the new
   `devbooth-session-start` skill both reinforce this).
