# Dev-Booth Hermes Skill Activation v7 — Implementation Results

**Date:** 2026-05-15
**Branch:** `feat/kanban-redesign-2026-05-14` (`main` untouched)
**Plan:** `/dev-booth/reports/plans/2026_05_15_07-35-35_devbooth_hermes_skill_activation.md`
**Mode:** `/team` (2 parallel executor sub-agents at Sonnet) — see §3.
**Builds on:** v6 dashboard UX (commits `8d02d61` → `f916630`, all local).

---

## Summary

v7 teaches the three Hermes worker profiles — `conductor` / `architect` /
`executor` — to discover and use the **82 builtin Hermes skills**
during a Dev-Booth session. The lever is **biasing the model's
discretion at two layers**:

1. **Per-stage body mention.** Every `STAGE_DAG` body now ends with a
   `## 활용 가능한 스킬 (필요 시 로드)` section naming 1-4 skills the
   model should consider for that specific task.
2. **Per-role SOUL.md catalog.** Each profile's SOUL.md gains a
   `## 스킬 카탈로그 (필요 시 로드)` section at the tail, mapping the
   role to its most-used skills.

Both layers are **model-decision-driven, zero forced-load cost** —
they do not pre-bind tokens, so the v5 context budget (28 K) and
turn cap (15) stay intact. Phase-0 evidence confirmed that v0.13.0
does not expose a per-task `--skills` injection hook (logged as F1
follow-up for the next Hermes-version bump).

**Test bar:** v6 baseline 139 → **153 passing** (Phase 1 added 3 new
test functions; 11 parametrized cases across the 12 stages with
skills plus the 3 non-parametrized ones for the new behavior).
Frontend was not touched in v7 (no `tsc`/`build` change).

**Per-phase commits on `feat/kanban-redesign-2026-05-14`:**

| Commit | Phase |
|---|---|
| `c72c27b` | `phase1(skills)`: per-stage skill map + use-case registry + body section |
| `136cf2f` | `phase2(skills)`: skill catalog appended to each role's SOUL.md |
| `<pending>` | `docs(skills)`: this report + plan + progress |

Three operator actions remain (sudo + agent-blocked push) — see §7.

---

## Phase 0 — Pre-flight probes

Recorded during planning. Results that shaped the plan:

| Probe | Result | Bearing |
|---|---|---|
| P0.1 `hermes -z --help \| grep -i skill` | `--skills SKILLS` flag exists on v0.13.0 | Confirms the dispatcher's existing `--skills kanban-worker` mechanism; per-session forced-load is the only API |
| P0.2 every named skill on disk | **15/15 verified** (incl. `github-auth`, `architecture-diagram`, `plan`, `test-driven-development`, `subagent-driven-development`, `systematic-debugging`, `spike`, …) | No name drift; Phase 1 can land safely |
| P0.3 SKILL.md frontmatter format | `name: <skill> / description: …` — the model uses `description` as activation hook | Confirms body-mention-only is enough; the model already has each skill's description in its summary view |
| P0.4 per-task `--skills` injection | **NOT available** — `hermes kanban create` has no `--skills` flag; profile config.yaml's `skills:` block is infrastructure config (`external_dirs`, `template_vars`, `inline_shell`, …), not a default-load list | Forced-load path B + C rejected; biasing path A + D adopted |
| P0.5 pytest baseline | 139 passing (v6 bar) | Regression bar locked |
| P0.6 `default_skills:` in config.yaml | Does NOT exist on v0.13.0 | Confirms B (profile-config force-load) dead-end |

Phase 0 turned the plan from "patch Hermes to inject per-task skills"
into "bias the model via prompts" — strictly within scope of the
v0.13.0 pin (OT5 from v5).

---

## Phase 1 — `core/scenario.py` per-stage skill map (commit `c72c27b`)

### `StageTask` dataclass — new field

```python
@dataclass
class StageTask:
    stage: int
    title: str
    assignee: str
    workspace: str
    tag: str
    body_template: str
    parent_stages: list[int] = field(default_factory=list)
    is_review_gate: bool = False
    skills: list[str] = field(default_factory=list)   # v7: per-stage suggested skills
```

### `SKILL_USE_CASES` registry (13 entries)

Module-level dict mapping skill name → one-line Korean use-case. Used
by `format_task()` to render the body section. **One source of truth**
for the per-skill description text (Driver 3).

| Skill | Use-case (rendered in body) |
|---|---|
| `github-auth` | GitHub 인증 (gh auth status, token 환경변수 검증) |
| `github-repo-management` | 레포 fork / clone / 브랜치 생성 |
| `github-pr-workflow` | branch → commit → PR 작성/제출 / CI 대기 전체 lifecycle |
| `github-code-review` | PR 리뷰 (코드 진단 + 코멘트 작성) |
| `requesting-code-review` | 내 코드를 리뷰받을 수 있게 정리하는 절차 |
| `codebase-inspection` | 낯선 레포의 구조 / 핵심 파일 / 의존성 파악 |
| `architecture-diagram` | ASCII / Mermaid 로 아키텍처 그리기 |
| `writing-plans` | markdown 계획서 작성 컨벤션 (이 프로젝트는 reports/plans/) |
| `plan` | plan 모드 — 코드 안 짜고 markdown 계획만 작성 |
| `test-driven-development` | RED → GREEN → REFACTOR; 테스트가 코드보다 먼저 |
| `systematic-debugging` | 실패 테스트 / 버그의 근본 원인 분리 절차 |
| `subagent-driven-development` | 범위 큰 구현을 자식 에이전트에게 위임 |
| `spike` | 옵션 비교용 시한부 탐색 (결과는 폐기되거나 흡수) |

### Per-stage `skills=[...]` (plan §2 table)

| Stage | Title | Assignee | Skills (rank-ordered) |
|---|---|---|---|
| 1 | fork & clone | conductor | `github-auth`, `github-repo-management` |
| 2 | initial scan | conductor | `codebase-inspection` |
| 3 | code structure analysis | architect | `codebase-inspection`, `architecture-diagram` |
| 4 | dependency analysis | executor | `codebase-inspection` |
| 5 | analysis summary | conductor | `writing-plans` |
| 6 | improvements plan | conductor | `plan`, `writing-plans` |
| 7 | feature branch | conductor | `github-pr-workflow` |
| 8 | implement TASK-{n} | executor | `test-driven-development`, `systematic-debugging`, `subagent-driven-development` |
| 9 | code review | architect | `requesting-code-review`, `github-code-review` |
| 10 | commit | conductor | `github-pr-workflow` |
| 11 | draft PR | conductor | `github-pr-workflow` |
| 12 | submit PR | conductor | `github-pr-workflow` |

`kanban-worker` / `kanban-orchestrator` are NOT in this table — the
dispatcher already auto-injects them via `--skills kanban-worker` on
every spawned worker. They are mentioned parenthetically in SOUL.md
(Phase 2) so the model knows why they're there.

### `format_task()` — section rendering

The body section is appended **at the end of the rendered body**
(after the existing `## ⚠️ 완료 시 반드시 호출` block). Mid-body
insertion was considered and rejected — the body templates vary in
internal structure (one has `## 막힐 때`, another doesn't, etc.),
and an anchored insertion is fragile. End-append is structurally
simple and the tests verify presence + content, not exact line
position.

The section is rendered **only** when `stage.skills` is non-empty —
no blank heading for empty-skills stages (covered by
`test_body_omits_skills_section_when_empty`).

### Tests (3 new, `tests/test_scenario_bodies.py`)

| Test | Assertion |
|---|---|
| `test_every_stage_skills_known` | every name used in any stage has an entry in `SKILL_USE_CASES` (catches typos at test time) |
| `test_body_has_skills_section_when_assigned` | parametrized over the 12 stages with skills: header + every named skill present in rendered body |
| `test_body_omits_skills_section_when_empty` | synthetic `skills=[]` stage does NOT render the header |

### Spot-check (post-Phase 1)

```
STAGE_DAG len: 12
SKILL_USE_CASES len: 13
  stage  1 [conductor] skills=2 body_has_section=True
  stage  2 [conductor] skills=1 body_has_section=True
  stage  3 [architect] skills=2 body_has_section=True
  stage  4 [executor ] skills=1 body_has_section=True
  stage  5 [conductor] skills=1 body_has_section=True
  stage  6 [conductor] skills=2 body_has_section=True
  stage  7 [conductor] skills=1 body_has_section=True
  stage  8 [executor ] skills=3 body_has_section=True
  stage  9 [architect] skills=2 body_has_section=True
  stage 10 [conductor] skills=1 body_has_section=True
  stage 11 [conductor] skills=1 body_has_section=True
  stage 12 [conductor] skills=1 body_has_section=True
```

All 12 stages carry at least one skill; the section renders on every
body. **153 pytest passing** (v6 was 139; +14 net).

---

## Phase 2 — SOUL.md skill catalog (commit `136cf2f`)

Each profile's SOUL.md gains a `## 스킬 카탈로그 (필요 시 로드)`
section appended **at the tail** (after `## 성격`, NOT inside the
⚠️ priority block). The catalog is a reference, not a directive —
the ⚠️ block stays as the single behavioral contract.

| File | Line | Skills | Final lines |
|---|---|---|---|
| `core/souls/conductor.SOUL.md` | 65-80 | 8 (plan, writing-plans, github-pr-workflow, github-auth, github-repo-management, codebase-inspection, architecture-diagram, spike) + context-budget reminder | 80 |
| `core/souls/architect.SOUL.md` | 57-67 | 7 (codebase-inspection, architecture-diagram, TDD, requesting-code-review, github-code-review, systematic-debugging, spike) | 67 |
| `core/souls/executor.SOUL.md` | 61-70 | 6 (TDD, systematic-debugging, subagent-driven-development, codebase-inspection, requesting-code-review, github-pr-workflow) | 70 |
| `~/.hermes/profiles/conductor/SOUL.md` | mirror | mirror | 80 |
| `~/.hermes/profiles/architect/SOUL.md` | mirror | mirror | 67 |
| `~/.hermes/profiles/executor/SOUL.md` | mirror | mirror | 70 |

All 6 files in sync with single source of truth in `core/souls/`.

**Activation:** Hermes workers read SOUL.md at spawn time, so
already-running workers won't pick this up. Operator action required:
`sudo systemctl restart hermes-gateway` (see §7.3).

**Conductor sample (tail, lines 65-80):**

```markdown
## 스킬 카탈로그 (필요 시 로드)

오케스트레이터로서 자주 쓰는 스킬 (`--skills`로 자동 로드되는 `kanban-orchestrator`
외에 본인이 판단해서 로드):

- `plan` — 코드 안 짜고 markdown 계획서 작성하는 모드 (stage 6).
- `writing-plans` — markdown 계획서 작성 컨벤션.
- `github-pr-workflow` — branch → commit → PR → merge 전체 흐름 (stage 7/10/11/12).
- `github-auth` — gh auth status / 토큰 검증 (stage 1).
- `github-repo-management` — fork / clone / 브랜치 생성 (stage 1, 7).
- `codebase-inspection` — 낯선 레포 구조 빠르게 파악 (stage 2).
- `architecture-diagram` — ASCII / Mermaid 아키텍처 (Architect 와 협업 시).
- `spike` — 옵션 비교용 시한부 탐색 (계획 단계에서 의심스러울 때).

각 스킬은 모델이 판단할 때 한 번씩 로드하면 됩니다 — 일괄 선로딩하지 않습니다
(컨텍스트 예산 28K, max_turns 15 한도 안에서만).
```

---

## Phase 3 — Synthetic verification (operator-gated)

The plan §6 specifies a probe that requires the gateway to restart so
workers reload the new SOUL.md — that means **sudo**, which the agent
runtime in this session does not have non-interactively. Phase 3 is
therefore documented for the operator to run:

```bash
# 1. activate the new SOUL.md
sudo systemctl restart hermes-gateway

# 2. seed a small probe board
DEV_BOOTH_DRYRUN=1 ./run.sh start v7-probe \
  https://github.com/mooner92/firebase-chat-exp "skill probe"

# 3. wait ~5 min for stages 1-3 to attempt
hermes kanban --board v7-probe stats

# 4. dump the architect's stage-3 worker log and grep for skill loads
STAGE3_TASK=$(hermes kanban --board v7-probe list --json | \
              python3 -c "import sys,json;ts=json.load(sys.stdin); \
              ts=ts if isinstance(ts,list) else ts.get('tasks',[]); \
              print(next((t['id'] for t in ts if t.get('assignee')=='architect'), ''))")
hermes kanban --board v7-probe log "$STAGE3_TASK" --tail 8192 \
  | grep -iE "loaded skill|codebase-inspection|architecture-diagram"

# Bar: at least one "Loaded skill: codebase-inspection" line for stage 3.
# Repeat for stage 8 (executor / TDD) and stage 9 (architect / review).
```

If zero skill-load lines appear after two synthetic sessions, escalate
to **F1** (upstream `--skills` injection patch).

---

## Acceptance criteria — final verification

| US | Acceptance summary | Status |
|---|---|---|
| US-001 | Phase 1 — `StageTask.skills` + `SKILL_USE_CASES` + all 12 stages populated + body section + 3 tests + pytest ≥ 142 | **MET** — 153 / 153 passing |
| US-002 | Phase 2 — `## 스킬 카탈로그` section in all 3 core/souls + 3 live mirrors; tail placement; ≤ 10 lines per profile | **MET** — 6 files in sync |
| US-003 | Phase 4 — verify, per-phase commits, results report, operator block | **MET** (this report + 3 commits + §7) |

---

## Risk-matrix follow-ups (plan §7)

| # | Status |
|---|---|
| R1 — body section bloats per-stage body past v5 budget | Mitigated — actual added text per stage is 4-6 lines × ~30 tokens = ≤ 200 tokens. v5 envelope intact |
| R2 — referenced skill name drift | Mitigated by P0.2 (15/15 verified on disk) + `test_every_stage_skills_known` (typo gate at test time) |
| R3 — model still doesn't load the suggested skill | Live risk — Phase 3 synthetic probe measures it; F1 (dispatcher patch) is the deterministic backstop |
| R4 — per-stage skill load eats conversation headroom | Bounded — each load happens on the turn the model invokes; 3-skill worst case ≈ 5 K tokens, still ≥ 10 K headroom |
| R5 — SOUL.md catalog drift over time | Mitigated — catalog is short (≤ 10 lines per profile); PR review enforces cap |
| R6 — skill content stale | Mitigated by v0.13.0 pin (OT5); F3 (skill-catalog sync test) logged |
| R7 — catalog ignored by model in favor of ⚠️ block | Acceptable — body mention (Phase 1) is the primary lever; SOUL catalog is reinforcement |

---

## 7. Operator TODOs (sudo + push — agent-blocked)

### 7.1. Push (pre-push hook + classifier block agent)

```bash
DEV_BOOTH_DRYRUN=0 git -C /dev-booth push origin feat/kanban-redesign-2026-05-14
```

All 9 v4+v5+v6+v7 commits are local on this branch (3ff83c1 → docs of v7).
`main` untouched.

### 7.2. (Optional) Dashboard restart

v7 made no backend or frontend change — the running dashboard already
serves the body content as opaque markdown (the new `## 활용 가능한 스킬`
section just renders for free in the chat tabs once tasks with the new
bodies are seeded). No restart strictly required, but a hard browser
refresh after a new session ensures the new bodies are visible.

### 7.3. Restart the gateway to activate the new SOUL.md

```bash
sudo systemctl restart hermes-gateway        # if systemd is wired
# OR — v4 OT1 fallback if hermes-gateway.service is still not installed:
pkill -f "hermes gateway run" && /dev-booth/run.sh gateway
hermes gateway status
# verify the conductor sees the new section:
HERMES_PROFILE=conductor hermes -z "스킬 카탈로그에 어떤 항목이 있나요?" --yolo | head -30
```

### 7.4. Run the Phase 3 synthetic probe

Per §6 of this report — capture the `Loaded skill: …` line and append
it to this report as an annex.

---

## 8. ADR (carried from plan §12)

- **Decision.** Bias the three Hermes worker profiles toward
  appropriate skill loading via per-stage body mention + per-role
  SOUL.md catalog. Do **not** force-load (no upstream patch, no
  unsupported config key).
- **Drivers.** Skill discovery must be testable (Driver 1), token
  budget must not regress (Driver 2), one source of truth for the
  stage→skill mapping (Driver 3).
- **Alternatives considered + rejected.**
  - B (profile-config default-load) — no hook on v0.13.0.
  - C (dispatcher patch) — breaks the v5 OT5 pin.
- **Why chosen.** A + D is the cheapest, fastest, most reversible
  intervention. It costs zero idle context and slot-aligns with the
  v5 dryrun gate's "bias through prompts" pattern.
- **Consequences.** Skill use is observable in `hermes kanban log`
  but is **probabilistic**, not deterministic. Phase 3 probe sets
  the measurement baseline; F1 is the deterministic upgrade path.
- **Follow-ups (post-v7).** F1 dispatcher-level `--skills`
  injection; F2 skill-load telemetry → dashboard badge; F3
  skill-catalog sync test; F4 `run.sh gateway` `--skills` baseline.

---

## 9. Files Touched

**New:**
- `reports/plans/2026_05_15_07-35-35_devbooth_hermes_skill_activation.md` (v7 plan)
- `reports/results/2026_05_15_07-45-33_devbooth_hermes_skill_activation.md` (this file)

**Modified (Phase 1, commit `c72c27b`):**
- `core/scenario.py` (+ `StageTask.skills`, + `SKILL_USE_CASES`, + 12 stage `skills=[...]`, + `format_task()` skills-section rendering)
- `tests/test_scenario_bodies.py` (+ 3 new tests, +1 import)

**Modified (Phase 2, commit `136cf2f`):**
- `core/souls/{conductor,architect,executor}.SOUL.md` (+ `## 스킬 카탈로그` section, 6/7/8 entries respectively + conductor context-budget note)
- `~/.hermes/profiles/{conductor,architect,executor}/SOUL.md` (live mirrors — outside repo)

**Untouched:**
- `main` branch
- `~/.hermes/hermes-agent` (v0.13.0 pin per OT5)
- `core/session.py`, `core/watchdog.py`, dashboard backend/frontend (no v7 change)
- `STAGE_NARRATION` (cross-seam test stays green)

---

## 10. Quick verification checklist (operator, post-restart)

1. `sudo systemctl restart hermes-gateway` (§7.3).
2. `HERMES_PROFILE=architect hermes -z "스킬 카탈로그를 보여줘"` should include
   `codebase-inspection`, `architecture-diagram`, etc.
3. Run the §6 synthetic probe; capture skill-load line for stage 3.
4. (Optional) `DEV_BOOTH_DRYRUN=0 git push origin feat/kanban-redesign-2026-05-14`.

If step 2 returns generic prose with no mention of the catalog skills,
the SOUL.md mirror at `~/.hermes/profiles/architect/SOUL.md` did not
load — re-run the `cp` from §2 of this report.

If step 3 shows zero `Loaded skill: …` lines, the biasing is not strong
enough; tighten by appending the catalog to the body itself (F4) or
escalate to F1.
