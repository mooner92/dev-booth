# Dev-Booth — CrownClownCrowd-only git management

**Date:** 2026-05-18 03:21:13
**Branch:** `feat/kanban-redesign-2026-05-14`
**Trigger:** Conductor session `20260518_021733_59dfcd` failed `gh repo fork` after running `gh auth login` interactively (300s timeout). User asked to drop mooner92 from git management entirely.

---

## Root cause of the conductor failure

| Layer | State | Implication |
|-------|-------|-------------|
| `gh auth status` | Logged in as **CrownClownCrowd**, scope `admin:org + repo` | gh CLI was fine |
| `gh repo fork --org CrownClownCrowd` (the actual failing command) | Active account IS CrownClownCrowd → self-fork is refused | The `--org` flag was wrong |
| `gh repo view CrownClownCrowd/GlobalTeamProject` | Returns OK — fork already exists from prior run | Re-fork is a no-op error |
| `git config --global user.email` | `mooner92@kakao.com` | Local commits authored as mooner92 regardless of which token pushes them |
| Interactive `gh auth login` in a hermes worker subprocess | 300s timeout (no TTY for the device-code menu) | Workers can never run `gh auth login` — auth must be pre-staged |

The PRD addresses all four with non-interactive, idempotent fixes.

---

## Changes

| File | Change |
|------|--------|
| `git config --global user.name` | → `CrownClownCrowd` |
| `git config --global user.email` | → `283567286+CrownClownCrowd@users.noreply.github.com` (GitHub noreply, attribution on web shows CrownClownCrowd) |
| `core/session.py` | `DevBoothSession.__init__` now derives `self.repo_owner` from `repo_url.split('/')[-2]`; `seed()` ctx exposes `repo_owner` to scenario templates. Stale "12-stage DAG" docstrings updated to v6/generic. |
| `core/scenario.py` stage 1 | Fork is now idempotent: `gh repo view CrownClownCrowd/{repo} >/dev/null 2>&1 \|\| gh repo fork {repo_url} --clone=false`. No `--org` flag. Body 1058B (≤ 2000B v6 invariant). |
| `core/scenario.py` stage 21 | `gh pr create --repo mooner92/{repo}` → `gh pr create --repo {repo_owner}/{repo}` so upstream is derived from URL, not hardcoded. Body 819B. |
| `core/souls/conductor.SOUL.md` line 68 | "원본 소유자: mooner92" → "원본 소유자(upstream)는 매 세션 `repo_url`에서 추출 (`{repo_owner}`)" |
| `core/memories/conductor.MEMORY.md` lines 12-15 | Same fix + explicit `git --global` identity line + idempotent fork pattern hint. Stale dryrun reference dropped. |
| `~/.hermes/profiles/conductor/SOUL.md` | Synced from core/souls (byte-identical, confirmed via `diff`) |
| `tests/test_scenario_bodies.py` + `tests/test_scenario.py` | Added `repo_owner` to test CTX so stage 21's new placeholder resolves |

---

## Live verification

```
$ git config --global user.name
CrownClownCrowd
$ git config --global user.email
283567286+CrownClownCrowd@users.noreply.github.com

$ gh auth status
github.com
  ✓ Logged in to github.com account CrownClownCrowd
  - Active account: true
  - Token scopes: admin:org, audit_log, codespace, repo, user, workflow

$ gh api user --jq '.id'
283567286     ← matches noreply email prefix, so commits attribute as CrownClownCrowd on web

$ gh repo view CrownClownCrowd/GlobalTeamProject --json name,owner.login
{"name":"GlobalTeamProject","owner":{"login":"CrownClownCrowd"}}   ← idempotent guard needed
```

### DAG smoke (formatted body checks)

```
Stage 1 idempotent fork present: True
Stage 1 body length:             769 B (template) / 1058 B (rendered)
Stage 21 mooner92 absent:        True
Stage 21 --repo {owner}/{repo}:  True  →  "--repo kwanghun/GlobalTeamProject"
Stage 21 body length:            702 B (template) / 819 B (rendered)
Total stages:                    21
```

### Regression

```
$ pytest tests/ dashboard/backend/tests/ -q
.................................................................................
.................................................................................
.................................................................................
..........................                                               [100%]
242 passed in 1.01s
```

### Live commit attribution

```
$ git -C /tmp/scratch-test commit --allow-empty -m smoke
Author: CrownClownCrowd <283567286+CrownClownCrowd@users.noreply.github.com>
```

---

## What's NOT changed (intentional)

- `core/dryrun/*` shell shims — they read `DEV_BOOTH_DRYRUN` directly from the worker env; the env var is now set to `0` in `.env` so they pass through to real `gh`/`git`. Removing the shims is a separate cleanup.
- `core/scenario.py` worker-instruction blurbs that still reference `(DEV_BOOTH_DRYRUN=1 이면 push --dry-run)` — preserved as safety notes for workers; the actual guard is the shim layer.
- `dashboard/README.md` mention of "Runtime / Build 사용자 분리 (`devbooth` / `mooner92`)" — that's about OS users running the dashboard service, not git identity. Out of scope.

---

## Operator follow-up

1. `sudo systemctl restart dev-booth-dashboard` — picks up the new `repo_owner` ctx in seed (dashboard's session start endpoint feeds into `core.session`).
2. No `gh auth login` needed — the bot account token is already stored in `~/.config/gh/hosts.yml` (`Logged in to github.com account CrownClownCrowd`).
3. Any new session you start now will fork into CrownClownCrowd, write commits as CrownClownCrowd, and target the upstream owner derived from the source URL.
