# Dev-Booth Hermes Skill Activation Plan (v7)

> **Status:** `pending approval` — produced by `/ralplan` (consensus planning).
> Execution paths after approval: `team` (parallel) or `ralph` (sequential).
> Do **not** start code changes until the operator authorizes execution.

**Date:** 2026-05-15
**Author:** /ralplan (Planner → Architect → Critic synthesis)
**Builds on:** v6 dashboard UX (commits `8d02d61` → `f916630`, all local).
**Base branch:** `feat/kanban-redesign-2026-05-14` (`main` untouched).
**Scope label:** capability enablement — teaches the three Hermes worker
profiles to discover and use the **82 builtin Hermes skills** during a
Dev-Booth session, without breaking v5's tight context budget.

---

## 0. Background — How Hermes Skills Actually Activate

This is the critical evidence Phase 0 captured **before** drafting the
plan; everything in the plan flows from these mechanics.

### Skill layout (verified on the host)

```
~/.hermes/skills/<category>/<skill-name>/SKILL.md
```

82 builtin skills enabled (`hermes skills list`); the four the user
flagged plus the rest of the relevant set:

| Skill (path) | Frontmatter `description` (the activation hook) |
|---|---|
| `devops/kanban-worker` | "Pitfalls, examples, and edge cases for Hermes Kanban workers. The lifecycle itself is auto-injected into every worker's system prompt as KANBAN_GUIDANCE…" |
| `devops/kanban-orchestrator` | "Decomposition playbook + anti-temptation rules for an orchestrator profile routing work through Kanban…" |
| `software-development/plan` | "Plan mode: write markdown plan to .hermes/plans/, no exec." |
| `software-development/test-driven-development` | "TDD: enforce RED-GREEN-REFACTOR, tests before code." |
| `github/github-pr-workflow` | "GitHub PR lifecycle: branch, commit, open, CI, merge." |
| `software-development/systematic-debugging` | (test-failure RCA) |
| `software-development/subagent-driven-development` | (delegating impl to a sub-agent) |
| `github/codebase-inspection` | (mapping unknown repos) |
| `github/github-code-review` | (reviewing PRs) |
| `software-development/requesting-code-review` | (publishing your code for review) |
| `software-development/writing-plans` | (markdown plan authoring) |
| `software-development/spike` | (time-boxed exploration) |

### Activation mechanics — three paths Hermes actually uses

1. **`hermes -z --skills <comma,list>`** — explicit per-session load
   when the agent is spawned. Used today by the dispatcher to inject
   `--skills kanban-worker` for every spawned Kanban worker
   (kanban-worker's own frontmatter confirms this: *"You're seeing
   this skill because the Hermes Kanban dispatcher spawned you as a
   worker with `--skills kanban-worker` — it's loaded automatically
   for every dispatched worker."*).
2. **Model-driven on-demand load** — the model sees a digest of every
   installed skill's frontmatter `description` field, and decides
   per-turn whether to invoke a skill via tool call. This is how
   `plan` / `TDD` / `github-pr-workflow` would activate today if the
   model judged them relevant.
3. **`KANBAN_GUIDANCE` system-prompt block** — a small lifecycle
   reminder injected into every Kanban worker before the user prompt
   (not a "skill", but the same activation pattern at the prompt-engine
   layer).

### What is **not** available (verified)

- Per-task `--skills` injection through Kanban metadata — `hermes
  kanban create` has no `--skills` flag. To add more forced loads,
  the dispatcher (`agent/prompt_builder.py`) would need an upstream
  patch — out of scope per v5 OT5 (Hermes v0.13.0 is pinned).
- A profile-level `default_skills:` config key — there is a top-level
  `skills:` block in `~/.hermes/profiles/<p>/config.yaml`, but its
  fields are infrastructure config (`external_dirs`, `template_vars`,
  `inline_shell`, …), not a default-load list. Confirmed by reading
  `~/.hermes/profiles/conductor/config.yaml` lines 340-360.

### What this means for the plan

The only two levers Dev-Booth controls are:
- **(A) Body-mention** in `core/scenario.py` — every stage body lists
  the 1-4 skills relevant to that stage, by name, with a one-line
  use-case. The model sees this as part of its task prompt and
  decides to load (path #2 above).
- **(D) SOUL.md catalog** — each profile's `core/souls/<p>.SOUL.md`
  carries a compact "스킬 카탈로그" section mapping role → most-useful
  skills. Persistent guidance across all sessions.

Both levers are **model-decision-driven, zero forced cost**. They are
the right fit for the v5 tight-budget envelope (28 K context, 15-turn
max). The third lever — forced load via `--skills` injection — would
need an upstream patch and is logged as a follow-up (F1).

---

## 1. RALPLAN-DR Summary

### Principles (decision frame)

1. **Skill discovery is a model decision.** We bias it via body
   hints and SOUL.md catalogs; we do not pre-bind skills the agent
   may not need (each pre-binding costs token budget).
2. **One skill, one stage, one use case.** Bodies map each stage to
   ≤ 4 skills, named with a single-line `why` so the model can decide
   in one read.
3. **Stay within v5's envelope.** No change to `max_turns:15`, no
   change to `context_length:28000`. Per-stage skill cost is bounded
   because skills load only on the turn the model invokes them.
4. **Verifiable via runtime logs.** `hermes kanban log <task_id>`
   already shows skill-load events; the acceptance bar uses log lines
   like *"Loaded skill: …"* not subjective "the agent seems better."
5. **Backward compatible.** v6 dashboard, v5 stabilization, v4 docs
   all stand. No DAG / no profile-config / no scenario.py narration
   change. Only body templates + SOUL.md.

### Decision drivers (top 3)

1. **The agent must actually load the right skill at the right stage**
   — proven by `hermes kanban log` evidence on a synthetic test,
   not by vibes.
2. **Token budget stays within v5's envelope** — no skill is
   force-loaded ahead of need; the worst-case turn loads one skill
   (~1-2 K tokens) on demand, leaving ≥ 10 K of conversation headroom.
3. **Single source of truth.** Per-stage skill set lives in
   `core/scenario.py:STAGE_DAG` — both the body template renderer
   (Phase 1) and the dashboard (Phase 4, optional) read from the
   same list.

### Viable options

| Option | Mechanism | Pros | Cons | Verdict |
|---|---|---|---|---|
| **A. Body-mention only** | Each `StageTask.skills: list[str]` rendered as a "## 활용 가능한 스킬" section in the body | Zero idle cost; per-stage targeting; SQL of truth in scenario.py | Model can still skip the load (Risk R3) | **Adopt as primary** |
| **B. Profile-config default-load** | Add a `default_skills:` key to each profile's config.yaml | Forced load; deterministic | The config schema does NOT support this on v0.13.0 (probe §0) — would require an upstream patch | **Reject** (no clean hook) |
| **C. Dispatcher injection** | Patch the dispatcher to read a task-metadata `skills` field and inject `--skills <list>` | Most precise per-task | Upstream Hermes patch breaks v5 OT5 pin | **Reject** (out of scope, logged F1) |
| **D. SOUL.md catalog** | Each profile's SOUL.md carries a one-section "스킬 카탈로그" mapping role → top-N skills | Persistent guidance; cheap to author; zero per-stage cost | Same model-decision unreliability as A | **Adopt as complement** |

Strategy: **A + D**. Together they bias the model toward the right
skill at the right time without paying any forced-load tax.

### Invalidations

- **B and C** are rejected because **the v0.13.0 surface does not
  expose the right hook** (B) or because **patching the dispatcher
  breaks the pinned version** (C). Both are logged in §8 follow-ups
  for the next Hermes-version bump.
- "Just describe the skills in run.sh / docs" — too disconnected
  from the per-stage body the model actually reads. The agent never
  sees run.sh.

---

## 2. Per-Stage Skill Map

This is the contract. Each entry has been chosen so the model has
exactly one obvious skill to load *if* it judges the task harder
than the body alone — no decision-paralysis from offering 6 skills
at once.

| Stage | Title | Assignee | Skills (rank-ordered) | Why |
|---|---|---|---|---|
| 1 | fork & clone | conductor | `github-auth`, `github-repo-management` | gh fork + clone needs auth; repo-mgmt for the create step |
| 2 | initial scan | conductor | `codebase-inspection` | quick mapping of an unknown repo |
| 3 | code structure analysis | architect | `codebase-inspection`, `architecture-diagram` | tree + module map → architecture render |
| 4 | dependency analysis | executor | `codebase-inspection` | manifest-aware repo scan |
| 5 | analysis summary | conductor | `writing-plans` | markdown plan authoring |
| 6 | improvements plan | conductor | `plan`, `writing-plans` | plan mode (no exec) + plan-authoring discipline |
| 7 | create feature branch | conductor | `github-pr-workflow` | branching is part of the PR lifecycle |
| 8 | implement TASK-{n} | executor | `test-driven-development`, `systematic-debugging`, `subagent-driven-development` | TDD red→green→refactor; debug when red lingers; decompose when scope creeps |
| 9 | code review | architect | `requesting-code-review`, `github-code-review` | both sides of the review fence |
| 10 | commit | conductor | `github-pr-workflow` | conventional-commit + branch hygiene |
| 11 | draft PR | conductor | `github-pr-workflow` | PR body authoring |
| 12 | submit PR | conductor | `github-pr-workflow` | gh pr create + CI handoff |

**`kanban-worker` / `kanban-orchestrator`** are NOT in this table —
they are auto-injected by the dispatcher and would be redundant in
the body. They are referenced once in SOUL.md so the operator knows
why they are there.

---

## 3. Phase 0 — Probes (record `/tmp/v7-phase0.md`)

Phase 0 was partially completed during planning; the remaining
probes confirm the plan's assumptions before the first code change.

| ID | Probe | What it gates |
|---|---|---|
| P0.1 | `hermes -z --help \| grep -i skill` | Confirm `--skills SKILLS` flag exists on v0.13.0 (DONE — confirmed) |
| P0.2 | `ls ~/.hermes/skills/<category>/<skill>/SKILL.md` for every skill in §2 | Every referenced skill exists on disk; if any name has drifted, fix in Phase 1 before render |
| P0.3 | `head -10 ~/.hermes/skills/<name>/SKILL.md` for each — read frontmatter | Confirms each skill's `description` is meaningful (the model uses this for discovery) |
| P0.4 | Synthetic probe: seed a one-line Kanban task with body `"활용 가능한 스킬: test-driven-development"` and watch `hermes kanban log <task_id>` for `Loaded skill: test-driven-development` | **Confirms model-driven activation works in practice** — if not, fall back to F1 (upstream patch) |
| P0.5 | `pytest tests/ dashboard/backend/tests/ -q` baseline (≥ 139 v6 bar) | Locks regression bar |
| P0.6 | Check there is no `default_skills:` or similar in `~/.hermes/profiles/<p>/config.yaml` | Confirms B option dead-end (DONE — verified) |

**Phase 0 exit:** all 6 recorded; any miss (esp. P0.2 name drift or
P0.4 negative) triggers a plan amendment before Phase 1.

---

## 4. Phase 1 — `core/scenario.py` + body templates

### 4.1 Add `skills` field to `StageTask`

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

`skills` is intentionally a plain `list[str]` of skill names (no
category, no description) — body rendering and tests both treat them
as opaque strings; the per-name use-case lookup lives in §4.3.

### 4.2 Populate `skills` per stage (per §2 table)

```python
StageTask(stage=1, ..., skills=["github-auth", "github-repo-management"], ...)
StageTask(stage=2, ..., skills=["codebase-inspection"], ...)
# ... etc per §2 table
```

### 4.3 Render "## 활용 가능한 스킬" section in every body

Add a shared registry at the top of `scenario.py`:

```python
SKILL_USE_CASES: dict[str, str] = {
    "github-auth":              "GitHub 인증 (gh auth status, token 환경변수 검증)",
    "github-repo-management":   "레포 fork / clone / 브랜치 생성",
    "github-pr-workflow":       "branch → commit → PR 작성/제출 / CI 대기 전체 lifecycle",
    "github-code-review":       "PR 리뷰 (코드 진단 + 코멘트 작성)",
    "requesting-code-review":   "내 코드를 리뷰받을 수 있게 정리하는 절차",
    "codebase-inspection":      "낯선 레포의 구조 / 핵심 파일 / 의존성 파악",
    "architecture-diagram":     "ASCII / Mermaid 로 아키텍처 그리기",
    "writing-plans":            "markdown 계획서 작성 컨벤션 (이 프로젝트는 reports/plans/)",
    "plan":                     "plan 모드 — 코드 안 짜고 markdown 계획만 작성",
    "test-driven-development":  "RED → GREEN → REFACTOR; 테스트가 코드보다 먼저",
    "systematic-debugging":     "실패 테스트 / 버그의 근본 원인 분리 절차",
    "subagent-driven-development": "범위 큰 구현을 자식 에이전트에게 위임",
    "spike":                    "옵션 비교용 시한부 탐색 (결과는 폐기되거나 흡수)",
}
```

`format_task()` renders a new section between `## 환경 정보` and
`## 단계` (or appended at the end of `## 환경 정보` for tightness):

```markdown
## 활용 가능한 스킬 (필요 시 로드)
- `test-driven-development` — RED → GREEN → REFACTOR; 테스트가 코드보다 먼저
- `systematic-debugging` — 실패 테스트 / 버그의 근본 원인 분리 절차
- `subagent-driven-development` — 범위 큰 구현을 자식 에이전트에게 위임
```

If `stage.skills` is empty, omit the section entirely (no blank
heading).

### 4.4 Tests

- `tests/test_scenario_bodies.py` gains:
  - `test_every_stage_skills_known` — every `stage.skills` name has
    an entry in `SKILL_USE_CASES` (catches typos at import-time-ish).
  - `test_body_has_skills_section_when_assigned` — for every stage
    whose `skills` is non-empty, the rendered body contains the
    `## 활용 가능한 스킬` header + each named skill.
  - `test_body_omits_skills_section_when_empty` — a hypothetical
    empty-skills stage (use a synthetic StageTask in the test) does
    NOT have the header (no blank heading).
- Existing `test_format_task_renders_without_keyerror` stays green
  (no new ctx key).
- Existing `test_body_renders_without_keyerror` stays green (no new
  `{placeholder}`).
- Existing `test_stage_narration_crossseam` stays green (STAGE_NARRATION
  unchanged).

### 4.5 Verify

```bash
cd /dev-booth && env/bin/python3.11 -m pytest tests/ dashboard/backend/tests/ -q
# Bar: ≥ 139 v6 baseline + 3 new from §4.4 = 142+ passing
```

### 4.6 No dashboard backend change

The dashboard backend already projects bodies as opaque markdown —
the new section renders for free in `ChatStream` (timeline + log
tabs). No `routers/kanban.py` change.

---

## 5. Phase 2 — SOUL.md skill catalog

For each of `core/souls/{conductor,architect,executor}.SOUL.md` (and
its `~/.hermes/profiles/<p>/SOUL.md` mirror), append **at the end**
(after the existing role prose) a compact catalog section. Placement
at the end so the model has the lifecycle rules first; the catalog
is a reference, not a header instruction.

### conductor SOUL.md tail

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

### architect SOUL.md tail

```markdown
## 스킬 카탈로그 (필요 시 로드)

분석/리뷰 담당으로서 자주 쓰는 스킬 (`kanban-worker` 외):

- `codebase-inspection` — 낯선 레포 구조 빠르게 파악 (stage 3).
- `architecture-diagram` — ASCII / Mermaid 아키텍처 (stage 3).
- `test-driven-development` — Executor 의 구현 리뷰 시 테스트 커버리지 점검 기준 (stage 9).
- `requesting-code-review` — 내 분석을 다음 단계가 읽을 수 있게 정리 (stage 3, 5).
- `github-code-review` — 코드 리뷰 절차 (stage 9).
- `systematic-debugging` — 리뷰 중 발견한 버그의 근본 원인 분리.
- `spike` — 설계 옵션 비교.
```

### executor SOUL.md tail

```markdown
## 스킬 카탈로그 (필요 시 로드)

구현 담당으로서 자주 쓰는 스킬 (`kanban-worker` 외):

- `test-driven-development` — RED → GREEN → REFACTOR; 테스트가 코드보다 먼저 (stage 8).
- `systematic-debugging` — 실패 테스트의 근본 원인 분리 (stage 8).
- `subagent-driven-development` — 범위 큰 구현을 자식 에이전트에게 위임 (stage 8).
- `codebase-inspection` — 의존성 분석 시 (stage 4).
- `requesting-code-review` — 내 구현이 Architect 가 읽기 좋게 정리 (stage 8 완료 직전).
- `github-pr-workflow` — 로컬 커밋 후 push 흐름 이해 (stage 10).
```

### Acceptance

- `head -50 ~/.hermes/profiles/<each>/SOUL.md | tail -25` shows the
  new section.
- The section sits **after** the role prose, **not** in the
  ⚠️ priority block (that block is the contract; the catalog is a
  reference).

---

## 6. Phase 3 — Verification (synthetic probe)

After Phases 1 + 2 are deployed, the operator restarts the gateway
so workers reload SOUL.md, then seeds one tiny board to confirm:

```bash
# operator action (sudo gated)
sudo systemctl restart hermes-gateway

# probe (no sudo)
DEV_BOOTH_DRYRUN=1 ./run.sh start v7-probe https://github.com/mooner92/firebase-chat-exp "skill probe"
sleep 60
hermes kanban --board v7-probe runs <stage-3-task-id>
hermes kanban --board v7-probe log <stage-3-task-id> --tail 4096 | grep -iE "loaded skill|codebase-inspection|architecture-diagram"
# Expect: at least one "loaded skill: codebase-inspection" (or similar) line
```

**Bar:** at least one of the §2 mapped skills appears in the log for
each of stages 3, 4, 8 (the highest-value mappings). If zero hits
after two synthetic sessions, escalate to F1 (upstream `--skills`
injection patch).

---

## 7. Risk Matrix

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Body's new "## 활용 가능한 스킬" section bloats per-stage body past the v5 budget envelope | Low | Low | Section is 4-8 lines × ~30 tokens = ~250 tokens max per stage; well within budget |
| R2 | A skill name in §2 has drifted in v0.13.0 (typo, renamed, removed) | Low | Med | P0.2 verifies every name exists on disk before Phase 1 lands |
| R3 | Model doesn't load the suggested skill even when prompted | Med | Med | Body mention + SOUL catalog are *biases*, not guarantees. F1 (upstream patch) is the deterministic backstop. Phase-3 synthetic probe surfaces non-loads early |
| R4 | Per-stage skill load eats ~1-2 K tokens × N turns, blows the 12 K conversation headroom | Low | Med | A skill loads on the turn the model invokes it; subsequent turns retain it. Worst case: 3 skills loaded = ~5 K. Still within budget |
| R5 | SOUL.md catalog drift — section grows over time, eats system-prompt budget | Med | Low | The catalog is compact (≤ 10 lines per profile, ≤ 30 tokens each). PR review enforces the cap |
| R6 | Skills the model loads have stale instructions (e.g., refer to deprecated `hermes kanban daemon`) | Low | Low | Skills are pinned to v0.13.0 via OT5; F1 includes a re-pin check |
| R7 | The "skill catalog" placement at end of SOUL.md gets ignored by the model in favor of the earlier ⚠️ block | Med | Low | The ⚠️ block is the contract; the catalog is a *reference* — model SHOULD treat them differently. If it doesn't, fall back to inline body mentions (Phase 1) which the model reads with the task itself |

---

## 8. Follow-ups (post-v7, out of scope)

- **F1: dispatcher-level `--skills` per-task injection.** Patch
  `agent/prompt_builder.py` (or wrap the dispatcher) to read a Kanban
  task metadata field `skills: [...]` and inject `--skills` on
  worker spawn. **Deterministic** vs. v7's model-driven biasing.
  Cost: breaks v0.13.0 pin (OT5); needs a separate Hermes-version
  bump checklist.
- **F2: skill-load telemetry.** Pull skill-load lines out of
  `hermes kanban log` into the dashboard as a per-task badge
  ("loaded: TDD, systematic-debugging"). Makes Phase-3 verification
  zero-touch.
- **F3: skill-catalog sync.** When the operator runs
  `hermes skills update`, the SOUL.md catalogs can go stale. Add a
  pre-commit hook or unit test that re-validates §4.3 `SKILL_USE_CASES`
  keys against the installed-skills list (`hermes skills list`).
- **F4: opt-in `--skills` baseline via run.sh.** `run.sh gateway`
  could carry an env-var hook `DEV_BOOTH_DEFAULT_SKILLS` that the
  gateway forwards. Lower-risk than dispatcher patching but only
  works at gateway-level (all profiles get the same baseline).

---

## 9. Test Plan (per phase)

### Phase 0

- [ ] `/tmp/v7-phase0.md` exists with 6 entries.
- [ ] Every §2 skill name verified to have a `SKILL.md` on disk (P0.2).
- [ ] Synthetic probe (P0.4) on a one-line task showing
  `Loaded skill: …` for the body-mentioned skill.

### Phase 1 (scenario.py)

- [ ] `StageTask.skills: list[str]` added; all 12 stages populated per §2.
- [ ] `SKILL_USE_CASES` populated with every name used in any stage.
- [ ] `format_task()` renders "## 활용 가능한 스킬" only when
  `stage.skills` is non-empty.
- [ ] 3 new tests in `tests/test_scenario_bodies.py` (§4.4).
- [ ] All existing scenario / cross-seam tests stay green.
- [ ] `pytest tests/ dashboard/backend/tests/ -q` → **≥ 142 passing**
  (v6 139 + 3 new).

### Phase 2 (SOUL.md)

- [ ] `core/souls/<each>.SOUL.md` carries a `## 스킬 카탈로그` section
  appended **after** the role prose.
- [ ] `~/.hermes/profiles/<each>/SOUL.md` mirrors the change
  (single source of truth maintained).
- [ ] Catalog ≤ 10 lines per profile; references at least 4 of §2's
  skills.

### Phase 3 (synthetic verification)

- [ ] Operator restarts gateway (TODO §10).
- [ ] One synthetic Kanban board run completes stages 1-3 with at
  least one skill-load line in the worker log for stage 3 (architect's
  `codebase-inspection`).

### Phase 4 (close-out)

- [ ] Per-phase commits per plan §11 commit policy.
- [ ] Results report at
  `reports/results/YYYY_MM_DD_HH-MM-SS_devbooth_hermes_skill_activation.md`.
- [ ] `main` untouched.

---

## 10. Operator TODOs (sudo + push — agent-blocked)

| # | Action | Why |
|---|---|---|
| 10.1 | `sudo systemctl restart hermes-gateway` | Workers re-spawn with the new SOUL.md (the catalog) — running workers won't pick up §5 |
| 10.2 | `sudo systemctl restart dev-booth-dashboard` | Optional — the dashboard already renders body markdown; only needed if backend changes ship in a later v7.1 |
| 10.3 | `DEV_BOOTH_DRYRUN=0 git -C /dev-booth push origin feat/kanban-redesign-2026-05-14` | Hook + classifier still block agent push |
| 10.4 | Run the Phase-3 synthetic probe (§6) and capture the `Loaded skill: …` line in the results report | Bar for "skills are actually firing" |

---

## 11. Files Touched (planning estimate)

| File | Change | Risk |
|---|---|---|
| `core/scenario.py` | + `StageTask.skills`, + `SKILL_USE_CASES`, + `## 활용 가능한 스킬` rendering in 12 bodies | Med (touches the hottest file in the repo per [Hot Paths]) |
| `tests/test_scenario_bodies.py` | + 3 tests (§4.4) | Low |
| `core/souls/conductor.SOUL.md` | + `## 스킬 카탈로그` section at tail | Low |
| `core/souls/architect.SOUL.md` | + `## 스킬 카탈로그` section at tail | Low |
| `core/souls/executor.SOUL.md` | + `## 스킬 카탈로그` section at tail | Low |
| `~/.hermes/profiles/{conductor,architect,executor}/SOUL.md` | mirror | Low (lives outside repo) |
| `reports/plans/2026_05_15_07-35-35_devbooth_hermes_skill_activation.md` | this file | n/a |
| `reports/results/<date>_devbooth_hermes_skill_activation.md` | end-of-exec | n/a |

**Commit policy** (feature-unit, mirrors v5 / v6):

| Phase | Commit |
|---|---|
| Phase 0 probes | (fold into Phase 1 — `/tmp` notes only) |
| Phase 1 scenario.py | `phase1(skills): per-stage skill map + use-case registry + body section` |
| Phase 2 SOUL.md | `phase2(skills): skill catalog appended to each role's SOUL.md` |
| Phase 3 probe | (no code — just a /tmp probe + report) |
| Phase 4 docs | `docs(skills): hermes skill activation v7 plan + results` |

---

## 12. ADR — Architecture Decision Record

- **Decision.** Bias the three Hermes worker profiles toward
  appropriate skill loading by surfacing a per-stage map in
  `core/scenario.py` body templates and a per-role catalog in
  SOUL.md. Do **not** force-load skills (no upstream patch, no
  unsupported config key).
- **Drivers.** Skill discovery must be testable (Driver 1), token
  budget must not regress (Driver 2), one source of truth for the
  stage→skill mapping (Driver 3).
- **Alternatives considered.**
  - B (profile-config default-load) — rejected: no clean hook on
    v0.13.0.
  - C (dispatcher patch) — rejected: breaks the v5 OT5 pin.
- **Why chosen.** A + D is the cheapest, fastest, and most reversible
  intervention. It costs zero idle context and slot-aligns with how
  the v5 dryrun gate already biases worker behavior (body templates
  + SOUL.md).
- **Consequences.**
  - The agent's skill use is observable in `hermes kanban log` but
    is *probabilistic*, not deterministic. The Phase-3 probe sets the
    measurement baseline; F1 is the deterministic upgrade path.
  - SOUL.md grows from ~30 lines (post-v6) to ~45 lines (post-v7) —
    still small.
  - Scenario bodies grow ~5-8 lines per stage with a skill section
    — within budget per R1.
- **Follow-ups (post-v7).** F1-F4 in §8.

---

## 13. Open Questions for the Operator

| OQ | Question | Default |
|---|---|---|
| OQ-1 | Should v7 also add `kanban-orchestrator` to the conductor's auto-injected skills (via a `run.sh gateway` wrapper that adds `--skills kanban-orchestrator`)? F4 has the mechanism. | Defer — F4 is the path; v7 stays prompt-only |
| OQ-2 | What's an acceptable Phase-3 bar — "at least 1 of 3 mapped skills loaded" or "all 3"? | At least 1 per stage on the first probe; tighten in v7.1 |
| OQ-3 | Should the SOUL.md catalog be at the top or the tail of the file? | **Tail** — the contract (⚠️ block) goes first; the reference goes last |
| OQ-4 | Should the SKILL_USE_CASES dict live in scenario.py or in a new module? | scenario.py — keeps the file as the single hot path the team already knows |

---

## 14. How to Execute This Plan After Approval

This plan is `pending approval`. Recommended path:

- **`Skill("oh-my-claudecode:team")`** — Phase 1 (scenario.py) and
  Phase 2 (SOUL.md) have **zero file overlap** — two parallel
  sub-agents.
- **`Skill("oh-my-claudecode:ralph")`** — sequential alternative.

After execution, the operator runs §10 (gateway restart + probe +
push). The Phase-3 synthetic probe result lands in the results report
as the empirical bar for "agents actually use the skills."

---

*End of v7 Hermes skill activation plan.*
