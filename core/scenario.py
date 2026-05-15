"""Dev-Booth 12-stage scenario — the domain layer, surgically extracted from the
v1 stateless orchestrator (archive/v1-stateless-orchestrator/orchestrator.py).

This module is pure data + formatting. It does NOT run agents. ``core/session.py``
seeds this DAG onto a Hermes Kanban board; the gateway dispatcher then spawns the
assigned profiles as workers.

Kept from v1 (P3 — reuse the tested domain layer):
  * STAGE_NARRATION — the canonical narration corpus (carries stage_mapper
    keywords so the dashboard derives a monotonic 12->~8 stage progression).
  * the assignee mapping (conductor / architect / executor).
  * the dryrun policy (DEV_BOOTH_DRYRUN, default on).

Retired from v1: the hermes -z per-turn execution loop, the MessageQueue
mediation, strand recovery, reply draining — Hermes Kanban does all of that.

DD5/§7 of plan v4: STAGE_NARRATION bodies must each carry their stage's
stage_mapper keyword and must NOT trip a *higher* stage's keyword than the next
DAG stage — verified monotonic non-decreasing by the cross-seam test
(dashboard/backend/tests/test_stage_narration_crossseam.py).

v5 (stabilization): every body_template follows a fixed skeleton so the worker
always knows (a) the absolute paths it should read/write, (b) the parent task
to query for runtime-resolved paths, and (c) the EXACT kanban_complete call
required to close the task. The closing block is repeated in SOUL.md as a
defense-in-depth measure against the protocol_violation failure mode.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# --------------------------------------------------------------------------
# Canonical narration corpus — one line per scenario stage. Each line contains
# the dashboard stage_mapper keyword(s) for the stage it represents; the
# sequence of detect_stage() results across 1..12 is monotonic non-decreasing.
# --------------------------------------------------------------------------
STAGE_NARRATION: dict[int, str] = {
    1:  "git clone: 레포지토리 포킹 및 클론 시작",
    2:  "initial scan: 프로젝트 초기 분석 시작",
    3:  "initial scan: 코드 구조 분석 중 (Architect)",
    4:  "initial scan: 의존성 분석 중 (Executor)",
    5:  "initial scan: 분석 취합 및 요약 작성",
    6:  "drafting the implementation plan: 개선방안 계획 수립",
    7:  "plan approved: 개발 계획 승인, feature 브랜치 생성",
    8:  "implementing: 개발 루프 시작",
    9:  "running tests: 자동 테스트 실행",
    10: "tests passed: 테스트 통과, 커밋 준비",
    11: "pr drafted: PR 초안 작성",
    12: "pr merged: PR 제출 완료",
}

# The three Hermes profiles the dispatcher can spawn. A task assigned to any
# other name sits in `ready` forever (the dispatcher silently does not spawn
# unknown assignees) — core/session.py validates against this set.
ALLOWED_ASSIGNEES: frozenset[str] = frozenset({"conductor", "architect", "executor"})


@dataclass
class StageTask:
    """One node of the static 12-stage DAG."""

    stage: int
    title: str
    assignee: str          # conductor / architect / executor
    workspace: str         # worktree / dir:<path> / scratch
    tag: str               # orchestration / analysis / implementation / review / pr
    body_template: str
    parent_stages: list[int] = field(default_factory=list)
    is_review_gate: bool = False  # True -> `blocked` is an expected terminal state


# --------------------------------------------------------------------------
# The static 12-stage DAG. Stages 6 & 8 are *statically pre-decomposed* here —
# autonomous kanban_create fan-out is integration-test-only and off the e2e
# critical path (plan v4 ADR-001 / scope honesty).
#
# v5 body skeleton (every body below follows this):
#   ## 작업                    one-line directive
#   ## 환경 정보                absolute paths + parent-task lookup hints
#   ## 단계                    numbered steps, each shell-runnable or tool-callable
#   ## 완료 직전 체크리스트      2-3 self-asserted booleans
#   ## ⚠️ 완료 시 반드시 호출   kanban_complete(...) example with non-empty metadata
#   ## 막힐 때 (when relevant)  kanban_block(...) example
# --------------------------------------------------------------------------
STAGE_DAG: list[StageTask] = [
    StageTask(
        stage=1, title="[{repo}] fork & clone",
        assignee="conductor", workspace="worktree", tag="orchestration",
        body_template="""## 작업
레포지토리를 fork하고 clone하세요. 목표: {goal}

## 환경 정보
- 작업 디렉터리 (워커가 자동 진입): $HERMES_KANBAN_WORKSPACE
- 세션 디렉터리:                    {session_path}
- 원본 레포:                        {repo_url}
- Bot 계정:                         CrownClownCrowd (GITHUB_TOKEN 환경변수에서)
- 원본 소유자:                      mooner92

## 단계
1. `gh repo fork {repo_url} --org CrownClownCrowd --clone=false`
2. `gh repo clone CrownClownCrowd/{repo} {session_path}/project`
3. `cd {session_path}/project && git checkout -b develop`
4. `bash /dev-booth/core/dryrun/install_hooks.sh {session_path}/project`
   ← dryrun Layer-1 (pre-push 훅) 설치. DEV_BOOTH_DRYRUN=1 이면 push 차단.

## 완료 직전 체크리스트
□ `{session_path}/project/.git/hooks/pre-push` 가 존재하는가? (Layer-1 설치 확인)
□ `git branch --show-current` 가 `develop` 인가?
□ 아래 kanban_complete 호출을 곧바로 실행하는가? (다른 텍스트 없이)

## ⚠️ 완료 시 반드시 호출
kanban_complete(
    summary="fork & clone 완료: {session_path}/project (branch=develop)",
    metadata={{
        "repo_name":  "{repo}",
        "repo_url":   "{repo_url}",
        "clone_path": "{session_path}/project",
        "branch":     "develop"
    }}
)
"""),

    StageTask(
        stage=2, title="[{repo}] initial project scan",
        assignee="conductor", workspace="worktree", tag="orchestration",
        parent_stages=[1],
        body_template="""## 작업
클론된 레포를 초기 스캔하고 핵심 발견사항을 정리하세요.

## 환경 정보
- 작업 디렉터리:    $HERMES_KANBAN_WORKSPACE
- 세션 디렉터리:    {session_path}
- 부모 태스크 조회: `kanban_show()` 의 metadata.clone_path 가 레포 경로
- 레포 경로 (예상): {session_path}/project

## 단계
1. `kanban_show()` 로 부모(stage 1)의 metadata 에서 `clone_path` 확인
2. `cd <clone_path>` 후 `ls -la`, `find . -maxdepth 2 -type f | head -30`, `cat README*`
3. 핵심 디렉터리/파일/언어를 1~3줄로 정리 (kanban_complete summary 에 들어갈 내용)

## 완료 직전 체크리스트
□ summary 가 *실제 발견사항* (언어/프레임워크/주요 파일)을 1~3줄로 담는가?
□ metadata.clone_path 가 stage 1 의 clone_path 와 동일한가?
□ 곧바로 kanban_complete 를 호출하는가?

## ⚠️ 완료 시 반드시 호출
kanban_complete(
    summary="초기 스캔 완료. <핵심 1~3줄>",
    metadata={{
        "clone_path": "<stage 1 에서 확인한 절대경로>",
        "tech_stack": "<예: React 17 + Firebase / Python FastAPI / ...>",
        "file_count": 0
    }}
)
"""),

    StageTask(
        stage=3, title="[{repo}] code structure analysis",
        assignee="architect", workspace="worktree", tag="analysis",
        parent_stages=[2],
        body_template="""## 작업
코드 구조와 아키텍처를 분석하고 결과 파일을 저장하세요.

## 환경 정보
- 작업 디렉터리:   $HERMES_KANBAN_WORKSPACE
- 레포 경로:       `kanban_show()` 로 부모/조부모 metadata 의 `clone_path` 확인 (예상: {session_path}/project)
- 분석 결과 저장:  {session_path}/analysis_architect.md

## 분석 항목
- 디렉터리 구조 및 모듈 경계
- 핵심 클래스/함수
- 코드 품질 이슈 (중복, 복잡도, 미사용 코드)
- 개선 가능한 아키텍처 포인트

## 단계
1. `kanban_show()` → 부모 stage 2 metadata.clone_path 확인
2. 레포 탐색 (`tree -L 3 -I 'node_modules|dist|.git'`, `wc -l <핵심 파일>`)
3. 분석 결과 markdown 작성 → `{session_path}/analysis_architect.md` 에 저장 (`mkdir -p` 후 `write`)
4. `issues_found` 카운트 집계

## 완료 직전 체크리스트
□ analysis_architect.md 파일이 디스크에 실제로 쓰였는가? (`ls -la`)
□ 파일 크기가 500바이트 이상이고 *실제 분석 내용* 인가? (템플릿 복붙 금지)
□ kanban_complete 를 곧바로 호출하는가?

## ⚠️ 완료 시 반드시 호출
kanban_complete(
    summary="코드 구조 분석 완료: <한 줄 요약>",
    metadata={{
        "file":         "{session_path}/analysis_architect.md",
        "issues_found": 0
    }}
)

## 막힐 때
kanban_block(reason="review-required: <구체적 이유>")
"""),

    StageTask(
        stage=4, title="[{repo}] dependency & tech stack analysis",
        assignee="executor", workspace="worktree", tag="analysis",
        parent_stages=[2],
        body_template="""## 작업
의존성과 기술 스택을 분석하고 결과 파일을 저장하세요.

## 환경 정보
- 작업 디렉터리:   $HERMES_KANBAN_WORKSPACE
- 레포 경로:       `kanban_show()` 로 부모/조부모 metadata 의 `clone_path` 확인 (예상: {session_path}/project)
- 분석 결과 저장:  {session_path}/analysis_executor.md

## 분석 항목
- `package.json` / `requirements.txt` / `go.mod` / `pyproject.toml` 등 의존성 매니페스트
- 오래된/취약 패키지 (npm audit / pip-audit 가능 시)
- 테스트 커버리지 현황 (테스트 파일 개수, 프레임워크)
- CI/CD 설정 (`.github/workflows/`, `.gitlab-ci.yml`)

## 단계
1. `kanban_show()` → 부모 stage 2 metadata.clone_path 확인
2. 매니페스트 파일 찾기 + `cat` 또는 `head`
3. `vulnerabilities` 카운트 (best-effort)
4. 분석 결과 markdown → `{session_path}/analysis_executor.md`

## 완료 직전 체크리스트
□ analysis_executor.md 가 실제로 쓰였는가?
□ 파일이 *실제 의존성 목록* 을 포함하는가? (요약만으로는 부족)
□ kanban_complete 를 곧바로 호출하는가?

## ⚠️ 완료 시 반드시 호출
kanban_complete(
    summary="의존성/기술스택 분석 완료: <한 줄 요약>",
    metadata={{
        "file":            "{session_path}/analysis_executor.md",
        "vulnerabilities": 0,
        "test_files":      0
    }}
)

## 막힐 때
kanban_block(reason="review-required: <구체적 이유>")
"""),

    StageTask(
        stage=5, title="[{repo}] analysis summary",
        assignee="conductor", workspace="worktree", tag="orchestration",
        parent_stages=[3, 4],
        body_template="""## 작업
Architect 분석과 Executor 분석을 *읽고* 종합 요약본을 작성하세요.

## 환경 정보
- 작업 디렉터리:    $HERMES_KANBAN_WORKSPACE
- Architect 산출물: {session_path}/analysis_architect.md
- Executor 산출물:  {session_path}/analysis_executor.md
- 요약 저장:        {session_path}/summary_v1.0.0.md

## 단계
1. 두 분석 파일을 `read` 로 끝까지 읽는다 (요약만 가져오지 말 것)
2. 핵심 발견사항을 종합 (중복 제거, 우선순위 매기기)
3. `{session_path}/summary_v1.0.0.md` 작성:
   - `# Summary v1.0.0`
   - `## Architecture findings` (analysis_architect 기반)
   - `## Dependency findings` (analysis_executor 기반)
   - `## Top issues (우선순위순)`
4. 파일 크기가 1KB 이상인지 확인

## 완료 직전 체크리스트
□ summary_v1.0.0.md 가 디스크에 쓰였고 1KB 이상인가?
□ 두 부모 산출물의 *핵심 사항* 이 모두 반영됐는가?
□ kanban_complete 를 곧바로 호출하는가?

## ⚠️ 완료 시 반드시 호출
kanban_complete(
    summary="분석 종합 요약 완료",
    metadata={{
        "file":            "{session_path}/summary_v1.0.0.md",
        "sources":         ["{session_path}/analysis_architect.md", "{session_path}/analysis_executor.md"],
        "top_issue_count": 0
    }}
)
"""),

    StageTask(
        stage=6, title="[{repo}] improvements plan",
        assignee="conductor", workspace="worktree", tag="orchestration",
        parent_stages=[5],
        body_template="""## 작업
요약본을 *읽고* 구체적인 개선 TASK 목록을 작성하세요.
**금지:** 이 태스크 본문을 그대로 파일로 저장하는 행위. 새 문서를 작성합니다.

## 환경 정보
- 작업 디렉터리:  $HERMES_KANBAN_WORKSPACE
- 입력 요약본:    {session_path}/summary_v1.0.0.md
- 출력 저장 경로: {session_path}/improvements_v0.0.1.md

## improvements_v0.0.1.md 형식
```
# Dev-Booth Improvements (v0.0.1)

## TASK-1: <제목>
- 담당:  executor
- 파일:  <수정 대상 파일 목록>
- 설명:  <구체적 구현 내용 / 변경 사유>
- 수용 기준: <검증 가능한 1~2개 조건>

## TASK-2: <제목>
...
```
(최소 3개, 최대 5개 TASK)

## 단계
1. `read {session_path}/summary_v1.0.0.md` (끝까지)
2. Top issues 를 실행 가능한 TASK 로 변환
3. `{session_path}/improvements_v0.0.1.md` 작성
4. (선택) Architect / Executor 와 `kanban_comment()` 로 사전 합의

## 완료 직전 체크리스트
□ improvements_v0.0.1.md 가 200바이트 이상이고 *summary 와 다른 내용* 인가?
□ TASK 가 3~5개이고 각각에 담당/파일/설명/수용 기준이 있는가?
□ 이 태스크 body 의 마크다운을 그대로 복붙하지 *않았는가*?
□ kanban_complete 를 곧바로 호출하는가?

## ⚠️ 완료 시 반드시 호출
kanban_complete(
    summary="개선방안 작성 완료 (TASK N개)",
    metadata={{
        "file":          "{session_path}/improvements_v0.0.1.md",
        "task_count":    0,
        "primary_owner": "executor"
    }}
)
"""),

    StageTask(
        stage=7, title="[{repo}] create feature branch",
        assignee="conductor", workspace="worktree", tag="orchestration",
        parent_stages=[6],
        body_template="""## 작업
feature 브랜치를 생성하세요.

## 환경 정보
- 작업 디렉터리: $HERMES_KANBAN_WORKSPACE
- 레포 경로:     {session_path}/project
- 브랜치명:      feature/devbooth-{session}-improvements
- DEV_BOOTH_DRYRUN=1 ⇒ git push 는 --dry-run

## 단계
1. `cd {session_path}/project`
2. `git fetch origin && git checkout develop && git pull --ff-only`
3. `git checkout -b feature/devbooth-{session}-improvements`
4. (dryrun) `git push --dry-run -u origin feature/devbooth-{session}-improvements`
   (live)   `git push -u origin feature/devbooth-{session}-improvements`

## 완료 직전 체크리스트
□ `git branch --show-current` 가 feature/devbooth-{session}-improvements 인가?
□ push 가 dryrun 이면 --dry-run 출력만 봤는가?
□ kanban_complete 를 곧바로 호출하는가?

## ⚠️ 완료 시 반드시 호출
kanban_complete(
    summary="feature 브랜치 생성 완료",
    metadata={{
        "branch":      "feature/devbooth-{session}-improvements",
        "from":        "develop",
        "clone_path":  "{session_path}/project"
    }}
)
"""),

    StageTask(
        stage=8, title="[{repo}] implement TASK-{n}",
        assignee="executor", workspace="worktree", tag="implementation",
        parent_stages=[7],
        body_template="""## 작업
improvements_v0.0.1.md 의 TASK-{n} 을 구현하고 테스트를 통과시키세요.

## 환경 정보
- 작업 디렉터리:    $HERMES_KANBAN_WORKSPACE
- 개선안 파일:      {session_path}/improvements_v0.0.1.md
- 레포 경로:        {session_path}/project
- 브랜치 (예상):    feature/devbooth-{session}-improvements

## 단계
1. `read {session_path}/improvements_v0.0.1.md` → TASK-{n} 섹션 파악
2. `cd {session_path}/project && git status` (clean 확인)
3. 코드 구현 (`edit` / `write` 툴)
4. 테스트 실행 (`npm test` / `pytest -q` / 프로젝트별 명령)
5. 통과하면 다음 단계, 실패하면 수정 후 재시도 (최대 3회)

## 완료 직전 체크리스트
□ 모든 테스트가 통과했는가? (실패가 1건이라도 있으면 complete 금지)
□ `git status` 에 의도한 변경만 있고 노이즈가 없는가?
□ changed_files 리스트가 실제 수정 파일과 일치하는가?
□ 턴 예산이 얼마 남지 않았는데 작업이 미완이면 **block 으로 전환** (아래 "막힐 때")

## ⚠️ 완료 시 반드시 호출 (테스트 통과 후)
kanban_complete(
    summary="TASK-{n} 구현 완료 — <한 줄 요약>",
    metadata={{
        "task_id_local": "TASK-{n}",
        "changed_files": ["<파일1>", "<파일2>"],
        "test_command":  "<예: npm test / pytest -q>",
        "test_result":   "passed"
    }}
)

## 막힐 때 (테스트 실패 또는 턴 부족)
kanban_block(reason="review-required: <구체적 에러 / 'needs-continuation: 어디까지 했고 다음에 무엇'>")
"""),

    StageTask(
        stage=9, title="[{repo}] code review TASK-{n}",
        assignee="architect", workspace="worktree", tag="review",
        parent_stages=[8], is_review_gate=True,
        body_template="""## 작업
Executor 의 TASK-{n} 구현을 리뷰하고 통과/미통과 판단을 내리세요.

## 환경 정보
- 작업 디렉터리: $HERMES_KANBAN_WORKSPACE
- 레포 경로:     {session_path}/project
- 부모 metadata 에서 `changed_files`, `test_command` 확인
- 개선안 출처:   {session_path}/improvements_v0.0.1.md (TASK-{n})

## 리뷰 기준
- 기존 코드 스타일/네이밍 준수
- TASK-{n} 의 수용 기준 충족
- 테스트 커버리지 (변경 코드에 대응하는 테스트 존재)
- 성능/보안 회귀 없음

## 단계
1. `kanban_show()` → 부모 stage 8 metadata 의 changed_files 확인
2. `git -C {session_path}/project diff develop...feature/devbooth-{session}-improvements -- <files>`
3. 각 파일 검토 + 테스트 실행 (parent metadata.test_command)
4. 통과/미통과 판단

## 완료 직전 체크리스트
□ 변경 파일을 *실제로* 봤는가? (요약만으로 LGTM 금지)
□ 테스트를 한 번 더 돌렸는가?
□ 통과면 kanban_complete, 미통과면 kanban_block — 둘 중 하나만.

## ⚠️ 완료 시 — 통과
kanban_complete(
    summary="LGTM: <구체적 통과 사유>",
    metadata={{
        "approved":     true,
        "review_notes": "<선택적 코멘트>"
    }}
)

## 막힐 때 — 미통과
kanban_block(reason="review-required: <구체적 피드백 (어떤 파일/어떤 줄/왜)>")
"""),

    StageTask(
        stage=10, title="[{repo}] commit approved changes",
        assignee="conductor", workspace="worktree", tag="orchestration",
        parent_stages=[9],
        body_template="""## 작업
리뷰 통과한 변경사항을 로컬 커밋하세요.

## 환경 정보
- 작업 디렉터리:  $HERMES_KANBAN_WORKSPACE
- 레포 경로:      {session_path}/project
- 브랜치:         feature/devbooth-{session}-improvements
- 부모 stage 8 metadata 에서 changed_files 확인
- DEV_BOOTH_DRYRUN=1 ⇒ git push 는 --dry-run (커밋 자체는 항상 로컬)

## 단계
1. `cd {session_path}/project && git status`
2. `git add <changed_files>` (stage 8 metadata 의 목록)
3. `git commit -m "feat: {task_description} [devbooth/{session}]"`
4. (dryrun) `git push --dry-run origin feature/devbooth-{session}-improvements`
   (live)   `git push origin feature/devbooth-{session}-improvements`

## 완료 직전 체크리스트
□ `git log -1 --oneline` 가 방금 만든 커밋을 보이는가?
□ 커밋 메시지가 컨벤션을 따르는가? (`feat:` / `fix:` / ...)
□ kanban_complete 를 곧바로 호출하는가?

## ⚠️ 완료 시 반드시 호출
kanban_complete(
    summary="커밋 완료: <첫 줄 요약>",
    metadata={{
        "commit_sha": "<git log -1 --format=%H>",
        "branch":     "feature/devbooth-{session}-improvements",
        "files":      ["<파일1>", "<파일2>"]
    }}
)
"""),

    StageTask(
        stage=11, title="[{repo}] draft PR",
        assignee="conductor", workspace="worktree", tag="pr",
        parent_stages=[10],
        body_template="""## 작업
PR 초안을 작성하세요.

## 환경 정보
- 작업 디렉터리:    $HERMES_KANBAN_WORKSPACE
- 세션 디렉터리:    {session_path}
- 초안 저장 경로:   {session_path}/pr_draft.json
- 입력 자료:        {session_path}/summary_v1.0.0.md, {session_path}/improvements_v0.0.1.md,
                    부모 stage 10 metadata 의 commit_sha
- 목표:             {goal}

## pr_draft.json 형식
```json
{{
  "title": "[Dev-Booth] {goal}",
  "body":  "## 변경사항\\n...\\n## 테스트\\n...\\n## 주요 파일\\n...",
  "head":  "CrownClownCrowd:feature/devbooth-{session}-improvements",
  "base":  "main",
  "url":   "DRYRUN://no-pr"
}}
```

## 단계
1. summary + improvements + commit_sha 를 종합하여 body 작성 (한국어 OK)
2. `{session_path}/pr_draft.json` 에 저장 (`write`)
3. DEV_BOOTH_DRYRUN=1 이면 url 은 "DRYRUN://no-pr" 그대로

## 완료 직전 체크리스트
□ pr_draft.json 이 유효한 JSON 이고 4개 키(title/body/head/base)가 모두 있는가?
□ body 가 *실제 변경사항* 을 담는가? (템플릿 placeholder 그대로 금지)
□ kanban_complete 를 곧바로 호출하는가?

## ⚠️ 완료 시 반드시 호출
kanban_complete(
    summary="PR 초안 작성 완료",
    metadata={{
        "draft_file": "{session_path}/pr_draft.json",
        "title":      "[Dev-Booth] {goal}"
    }}
)
"""),

    StageTask(
        stage=12, title="[{repo}] submit PR",
        assignee="conductor", workspace="worktree", tag="pr",
        parent_stages=[11],
        body_template="""## 작업
PR 을 제출하세요 (dryrun 모드면 시뮬레이션만).

## 환경 정보
- 작업 디렉터리: $HERMES_KANBAN_WORKSPACE
- 초안 파일:     {session_path}/pr_draft.json (부모 stage 11 metadata.draft_file)
- 최종 산출물:   {session_path}/pr_final.json
- DEV_BOOTH_DRYRUN=1 ⇒ gh 호출 금지; pr_final.json 의 url = "DRYRUN://no-pr"

## 단계 (dryrun)
1. `cp {session_path}/pr_draft.json {session_path}/pr_final.json`
2. pr_final.json 의 url 을 "DRYRUN://no-pr" 로 보장 (이미 그렇다면 그대로)
3. kanban_complete

## 단계 (live, 운영자 승인 후)
1. `gh pr create --repo mooner92/{repo} --base main --head CrownClownCrowd:feature/devbooth-{session}-improvements -t "<title>" -b "<body>"`
2. 반환된 URL 을 pr_final.json 에 기록 (`write`)
3. kanban_complete

## 완료 직전 체크리스트
□ pr_final.json 이 디스크에 쓰였는가?
□ dryrun 이면 url == "DRYRUN://no-pr" 가 맞는가?
□ kanban_complete 를 곧바로 호출하는가?

## ⚠️ 완료 시 반드시 호출
kanban_complete(
    summary="PR 제출 처리 완료 (dryrun=<true/false>)",
    metadata={{
        "final_file": "{session_path}/pr_final.json",
        "pr_url":     "<DRYRUN://no-pr 또는 실제 URL>"
    }}
)
"""),
]


def get_stage(n: int) -> Optional[StageTask]:
    """Return the StageTask for stage number ``n`` (1-12), or None."""
    return next((s for s in STAGE_DAG if s.stage == n), None)


def format_task(stage: StageTask, **kwargs) -> dict:
    """Render a StageTask into ``hermes kanban create`` parameters."""
    return {
        "title": stage.title.format(**kwargs),
        "assignee": stage.assignee,
        "workspace": stage.workspace,
        "tag": stage.tag,
        "body": stage.body_template.format(**kwargs),
    }
